"""
Parallel download system for gh-folder-download using asyncio.
"""

import asyncio
import contextlib
import os
import random
import time
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
        max_retries: int = 3,
        retry_delay: float = 1.0,
        cache_max_size_gb: float = 5.0,
        cache_max_age_days: int = 30,
        cache_auto_cleanup: bool = True,
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
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.logger = get_logger()

        # Initialize cache and integrity checker
        self.cache = (
            DownloadCache(
                max_size_gb=cache_max_size_gb,
                max_age_days=cache_max_age_days,
                auto_cleanup=cache_auto_cleanup,
            )
            if use_cache
            else None
        )
        self.integrity_checker = FileIntegrityChecker() if verify_integrity or use_cache else None

        # Initialize progress tracker
        if show_progress and not quiet:
            self.progress_tracker = ProgressTracker(console=self.logger.console, quiet=quiet)
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
            download_coroutines = [self._download_single_file(session, semaphore, task) for task in download_tasks]

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
                    self.progress_tracker.complete_file(download_tasks[i].file_path, success=False)
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
            if self.cache and await asyncio.to_thread(self._check_cache, task):
                self.logger.debug(f"📁 Cache hit: {task.file_path}")

                # Update progress for cached file
                self.progress_tracker.update_file_progress(task.file_path, task.expected_size or 0)
                self.progress_tracker.complete_file(task.file_path, success=True, from_cache=True)

                return DownloadResult(
                    task=task,
                    success=True,
                    bytes_downloaded=task.expected_size or 0,
                    duration=time.time() - start_time,
                    from_cache=True,
                    integrity_verified=True,  # Assume cached files are verified
                )

            result = await self._download_with_retries(session, task, start_time)
            self.progress_tracker.complete_file(task.file_path, success=result.success)
            return result

    async def _download_with_retries(
        self,
        session: aiohttp.ClientSession,
        task: DownloadTask,
        start_time: float,
    ) -> DownloadResult:
        """Download one file to a temporary path and retry transient failures."""
        task.local_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = task.local_path.with_name(f".{task.local_path.name}.part-{os.getpid()}-{id(task)}")
        retryable_statuses = {408, 429, 500, 502, 503, 504}
        last_error = "unknown download error"

        for attempt in range(1, self.max_retries + 1):
            with contextlib.suppress(OSError):
                part_path.unlink()
            self.progress_tracker.update_file_progress(task.file_path, 0)
            try:
                async with session.get(task.download_url) as response:
                    if response.status != 200:
                        last_error = f"HTTP {response.status}: {response.reason}"
                        if response.status not in retryable_statuses:
                            break
                        retry_after = response.headers.get("Retry-After")
                        delay = (
                            float(retry_after) if retry_after and retry_after.isdigit() else self._retry_delay(attempt)
                        )
                        if attempt < self.max_retries:
                            await asyncio.sleep(delay)
                        continue

                    total_downloaded = 0
                    with open(part_path, "wb") as file:
                        async for chunk in response.content.iter_chunked(self.chunk_size):
                            file.write(chunk)
                            total_downloaded += len(chunk)
                            self.progress_tracker.update_file_progress(task.file_path, total_downloaded)

                integrity_verified = True
                if self.verify_integrity and self.integrity_checker:
                    integrity_verified = await self._verify_file_integrity(task, part_path)
                    if not integrity_verified:
                        last_error = "integrity verification failed"
                        if attempt < self.max_retries:
                            await asyncio.sleep(self._retry_delay(attempt))
                            continue
                        break

                part_path.replace(task.local_path)
                if self.cache:
                    await self._add_to_cache(task)

                self.logger.debug(f"✅ Downloaded: {task.file_path} ({total_downloaded} bytes)")
                return DownloadResult(
                    task=task,
                    success=True,
                    bytes_downloaded=total_downloaded,
                    duration=time.time() - start_time,
                    integrity_verified=integrity_verified,
                )
            except (TimeoutError, aiohttp.ClientError, OSError) as e:
                last_error = str(e) or type(e).__name__
                if attempt < self.max_retries:
                    await asyncio.sleep(self._retry_delay(attempt))

        with contextlib.suppress(OSError):
            part_path.unlink()
        self.logger.error(f"Download failed for {task.file_path}: {last_error}")
        return DownloadResult(
            task=task,
            success=False,
            error=last_error,
            duration=time.time() - start_time,
            integrity_verified=False,
        )

    def _retry_delay(self, attempt: int) -> float:
        return min(120.0, self.retry_delay * (2 ** (attempt - 1))) * random.uniform(0.5, 1.5)

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

    async def _verify_file_integrity(self, task: DownloadTask, file_path: Path | None = None) -> bool:
        """Verify file integrity in a thread pool."""
        if not self.integrity_checker:
            return True

        def verify():
            try:
                # Type guard to ensure integrity_checker is not None
                assert self.integrity_checker is not None
                checked_path = file_path or task.local_path
                self.integrity_checker.verify_file_size(checked_path, task.expected_size)
                self.integrity_checker.verify_git_blob_sha(checked_path, task.sha)
                self.integrity_checker.verify_file_content(checked_path)
                return True
            except IntegrityError as e:
                self.logger.error(f"Integrity verification failed for {task.file_path}: {e}")
                return False

        # Run integrity check in thread pool to avoid blocking
        return await asyncio.to_thread(verify)

    async def _add_to_cache(self, task: DownloadTask) -> None:
        """Add file to cache in a thread pool."""
        if not self.cache:
            return

        def add_to_cache():
            try:
                # Calculate checksums if integrity checker is available
                checksums = None
                if self.integrity_checker:
                    checksums = self.integrity_checker.calculate_checksums(task.local_path)

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
            except (OSError, ValueError) as e:
                self.logger.warning(f"Failed to add {task.file_path} to cache: {e}")

        # Run cache operation in thread pool
        await asyncio.to_thread(add_to_cache)

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
            stats["average_speed_mbps"] = (stats["total_bytes"] / (1024 * 1024)) / stats["total_time"]
        else:
            stats["average_speed_mbps"] = 0

        if stats["total_downloads"] > 0:
            stats["success_rate"] = (stats["successful_downloads"] / stats["total_downloads"]) * 100
            stats["cache_hit_rate"] = (stats["cached_files"] / stats["total_downloads"]) * 100
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
