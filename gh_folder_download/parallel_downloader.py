"""
Parallel download system for gh-folder-download using asyncio.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

from .cache import DownloadCache
from .integrity import FileIntegrityChecker, IntegrityError
from .logger import get_logger
from .progress import ProgressTracker, SimpleProgressTracker


@dataclass
class DownloadTask:
    """Represents a file download task."""

    file_path: str
    download_url: str
    local_path: Path
    expected_size: int | None
    sha: str
    repo_full_name: str
    ref: str


@dataclass
class DownloadResult:
    """Result of a download operation."""

    task: DownloadTask
    success: bool
    error: str | None = None
    duration: float = 0.0
    bytes_downloaded: int = 0
    from_cache: bool = False
    integrity_verified: bool = False


class ParallelDownloader:
    """Manages parallel downloads with concurrency control."""

    def __init__(
        self,
        max_concurrent_downloads: int = 5,
        chunk_size: int = 8192,
        timeout: int = 30,
        verify_integrity: bool = True,
        use_cache: bool = True,
        show_progress: bool = True,
        quiet: bool = False,
    ):
        """
        Initialize parallel downloader.

        Args:
            max_concurrent_downloads: Maximum number of concurrent downloads
            chunk_size: Size of chunks for streaming downloads
            timeout: Timeout for individual downloads in seconds
            verify_integrity: Whether to verify file integrity
            use_cache: Whether to use caching
            show_progress: Whether to show progress bars
            quiet: Whether to suppress progress display
        """
        self.max_concurrent_downloads = max_concurrent_downloads
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.verify_integrity = verify_integrity
        self.use_cache = use_cache
        self.show_progress = show_progress
        self.quiet = quiet

        self.logger = get_logger()

        # Initialize cache and integrity checker
        self.cache = DownloadCache() if use_cache else None
        self.integrity_checker = FileIntegrityChecker() if verify_integrity else None

        # Initialize progress tracker
        if show_progress and not quiet:
            self.progress_tracker = ProgressTracker(quiet=quiet)
        else:
            self.progress_tracker = SimpleProgressTracker()

        # Statistics
        self.stats = {
            "total_downloads": 0,
            "successful_downloads": 0,
            "failed_downloads": 0,
            "cached_files": 0,
            "total_bytes": 0,
            "total_time": 0.0,
        }

    async def download_files(
        self,
        download_tasks: list[DownloadTask],
    ) -> list[DownloadResult]:
        """
        Download multiple files in parallel.

        Args:
            download_tasks: List of download tasks

        Returns:
            List of download results
        """
        if not download_tasks:
            return []

        # Calculate total size
        total_bytes = sum(task.expected_size or 0 for task in download_tasks)

        # Start progress tracking
        self.progress_tracker.start_session(len(download_tasks), total_bytes)

        self.logger.info(f"Starting parallel download of {len(download_tasks)} files")
        self.logger.info(f"Max concurrent downloads: {self.max_concurrent_downloads}")

        start_time = time.time()

        # Create semaphore to limit concurrent downloads
        semaphore = asyncio.Semaphore(self.max_concurrent_downloads)

        # Create aiohttp session with timeout
        timeout_config = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            # Create download coroutines
            download_coroutines = [
                self._download_single_file(session, semaphore, task)
                for task in download_tasks
            ]

            # Execute downloads concurrently
            results = await asyncio.gather(*download_coroutines, return_exceptions=True)

            # Process results and handle exceptions
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Handle exceptions from asyncio.gather
                    error_result = DownloadResult(
                        task=download_tasks[i],
                        success=False,
                        error=str(result),
                    )
                    processed_results.append(error_result)
                    # Update progress for failed download
                    self.progress_tracker.complete_file(
                        download_tasks[i].file_path, success=False
                    )
                else:
                    processed_results.append(result)

        # Update global statistics
        total_time = time.time() - start_time
        self._update_stats(processed_results, total_time)

        # Finalize cache and progress
        if self.cache:
            self.cache.finalize()

        self.progress_tracker.finish_session()

        self.logger.info(
            f"Parallel download completed in {total_time:.2f}s. "
            f"Success: {self.stats['successful_downloads']}, "
            f"Failed: {self.stats['failed_downloads']}, "
            f"Cached: {self.stats['cached_files']}"
        )

        return processed_results

    async def _download_single_file(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        task: DownloadTask,
    ) -> DownloadResult:
        """Download a single file with progress tracking."""
        start_time = time.time()

        # Add progress task for this file
        self.progress_tracker.add_file_task(task.file_path, task.expected_size or 0)

        async with semaphore:
            # Check cache first
            if self.cache and self._check_cache(task):
                self.logger.debug(f"📁 Cache hit: {task.file_path}")

                # Update progress for cached file
                self.progress_tracker.complete_file(
                    task.file_path, success=True, from_cache=True
                )

                return DownloadResult(
                    task=task,
                    success=True,
                    bytes_downloaded=task.expected_size or 0,
                    duration=time.time() - start_time,
                    from_cache=True,
                    integrity_verified=True,  # Assume cached files are verified
                )

            try:
                # Ensure parent directory exists
                task.local_path.parent.mkdir(parents=True, exist_ok=True)

                # Download the file with progress tracking
                async with session.get(task.download_url) as response:
                    if response.status != 200:
                        error_msg = f"HTTP {response.status}: {response.reason}"
                        self.logger.error(
                            f"❌ Download failed for {task.file_path}: {error_msg}"
                        )

                        # Update progress for failed file
                        self.progress_tracker.complete_file(
                            task.file_path, success=False
                        )

                        return DownloadResult(
                            task=task,
                            success=False,
                            error=error_msg,
                            duration=time.time() - start_time,
                        )

                    # Stream download with progress updates
                    total_downloaded = 0
                    with open(task.local_path, "wb") as file:
                        async for chunk in response.content.iter_chunked(
                            self.chunk_size
                        ):
                            file.write(chunk)
                            total_downloaded += len(chunk)

                            # Update progress
                            self.progress_tracker.update_file_progress(
                                task.file_path, total_downloaded
                            )

                # Verify integrity if enabled
                integrity_verified = True
                if self.verify_integrity and self.integrity_checker:
                    integrity_verified = await self._verify_file_integrity(task)

                # Update cache if enabled
                if self.cache and integrity_verified:
                    await self._add_to_cache(task)

                self.logger.debug(
                    f"✅ Downloaded: {task.file_path} ({total_downloaded} bytes)"
                )

                # Update progress for completed file
                self.progress_tracker.complete_file(task.file_path, success=True)

                return DownloadResult(
                    task=task,
                    success=True,
                    bytes_downloaded=total_downloaded,
                    duration=time.time() - start_time,
                    integrity_verified=integrity_verified,
                )

            except asyncio.TimeoutError:
                error_msg = f"Download timeout after {self.timeout}s"
                self.logger.error(f"⏰ {error_msg}: {task.file_path}")

                # Update progress for failed file
                self.progress_tracker.complete_file(task.file_path, success=False)

                return DownloadResult(
                    task=task,
                    success=False,
                    error=error_msg,
                    duration=time.time() - start_time,
                )

            except (aiohttp.ClientError, OSError, IOError) as e:
                error_msg = f"Unexpected error: {str(e)}"
                self.logger.error(f"💥 {error_msg}: {task.file_path}")

                # Update progress for failed file
                self.progress_tracker.complete_file(task.file_path, success=False)

                return DownloadResult(
                    task=task,
                    success=False,
                    error=error_msg,
                    duration=time.time() - start_time,
                )

    def _check_cache(self, task: DownloadTask) -> bool:
        """Check if file is available in cache."""
        if not self.cache:
            return False

        return self.cache.is_file_cached(
            repo_full_name=task.repo_full_name,
            file_path=task.file_path,
            ref=task.ref,
            github_sha=task.sha,
            github_size=task.expected_size or 0,
            local_file_path=task.local_path,
        )

    async def _verify_file_integrity(self, task: DownloadTask) -> bool:
        """Verify file integrity in a thread pool."""
        if not self.integrity_checker:
            return True

        def verify():
            try:
                # Type guard to ensure integrity_checker is not None
                assert self.integrity_checker is not None
                self.integrity_checker.verify_file_size(
                    task.local_path, task.expected_size
                )
                self.integrity_checker.verify_file_content(task.local_path)
                return True
            except IntegrityError as e:
                self.logger.error(
                    f"Integrity verification failed for {task.file_path}: {e}"
                )
                return False

        # Run integrity check in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        max_workers = min(2, max(1, self.max_concurrent_downloads // 2))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return await loop.run_in_executor(executor, verify)

    async def _add_to_cache(self, task: DownloadTask) -> None:
        """Add file to cache in a thread pool."""
        if not self.cache:
            return

        def add_to_cache():
            try:
                # Calculate checksums if integrity checker is available
                checksums = None
                if self.integrity_checker:
                    checksums = self.integrity_checker.calculate_checksums(
                        task.local_path
                    )

                # Type guard to ensure cache is not None
                assert self.cache is not None
                self.cache.add_file_to_cache(
                    repo_full_name=task.repo_full_name,
                    file_path=task.file_path,
                    ref=task.ref,
                    github_sha=task.sha,
                    github_size=task.expected_size or 0,
                    local_file_path=task.local_path,
                    checksums=checksums,
                )
            except (OSError, IOError, ValueError) as e:
                self.logger.warning(f"Failed to add {task.file_path} to cache: {e}")

        # Run cache operation in thread pool
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            await loop.run_in_executor(executor, add_to_cache)

    def _update_stats(self, results: list[DownloadResult], total_time: float) -> None:
        """Update download statistics."""
        self.stats["total_downloads"] = len(results)
        self.stats["total_time"] = total_time

        for result in results:
            if result.success:
                self.stats["successful_downloads"] += 1
                self.stats["total_bytes"] += result.bytes_downloaded
                if result.from_cache:
                    self.stats["cached_files"] += 1
            else:
                self.stats["failed_downloads"] += 1

    def get_stats(self) -> dict[str, Any]:
        """Get download statistics."""
        stats = self.stats.copy()

        # Calculate additional metrics
        if stats["total_time"] > 0:
            stats["average_speed_mbps"] = (
                stats["total_bytes"] / (1024 * 1024)
            ) / stats["total_time"]
        else:
            stats["average_speed_mbps"] = 0

        if stats["total_downloads"] > 0:
            stats["success_rate"] = (
                stats["successful_downloads"] / stats["total_downloads"]
            ) * 100
            stats["cache_hit_rate"] = (
                stats["cached_files"] / stats["total_downloads"]
            ) * 100
        else:
            stats["success_rate"] = 0
            stats["cache_hit_rate"] = 0

        return stats

    def clear_cache(self) -> None:
        """Clear download cache."""
        if self.cache:
            self.cache.clear_cache()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if self.cache:
            return self.cache.get_cache_stats()
        return {}


def run_parallel_downloads(
    download_tasks: list[DownloadTask],
    max_concurrent_downloads: int = 5,
    verify_integrity: bool = True,
    use_cache: bool = True,
) -> list[DownloadResult]:
    """
    Convenience function to run parallel downloads.

    Args:
        download_tasks: List of download tasks
        max_concurrent_downloads: Maximum concurrent downloads
        verify_integrity: Whether to verify file integrity
        use_cache: Whether to use caching

    Returns:
        List of download results
    """
    downloader = ParallelDownloader(
        max_concurrent_downloads=max_concurrent_downloads,
        verify_integrity=verify_integrity,
        use_cache=use_cache,
    )

    # Run the async download function
    return asyncio.run(downloader.download_files(download_tasks))
