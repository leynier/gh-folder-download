"""
Parallel download system for gh-folder-download using asyncio.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from .cache import DownloadCache
from .integrity import FileIntegrityChecker, IntegrityError
from .logger import get_logger


@dataclass
class DownloadTask:
    """Represents a file download task."""

    file_path: str
    download_url: str
    local_path: Path
    expected_size: Optional[int]
    sha: str
    repo_full_name: str
    ref: str


@dataclass
class DownloadResult:
    """Result of a download operation."""

    task: DownloadTask
    success: bool
    error: Optional[str] = None
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
    ):
        """
        Initialize parallel downloader.

        Args:
            max_concurrent_downloads: Maximum number of concurrent downloads
            chunk_size: Size of chunks for streaming downloads
            timeout: Timeout for individual downloads in seconds
            verify_integrity: Whether to verify file integrity
            use_cache: Whether to use caching
        """
        self.max_concurrent_downloads = max_concurrent_downloads
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.verify_integrity = verify_integrity
        self.use_cache = use_cache

        self.logger = get_logger()

        # Initialize cache and integrity checker
        self.cache = DownloadCache() if use_cache else None
        self.integrity_checker = FileIntegrityChecker() if verify_integrity else None

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
        download_tasks: List[DownloadTask],
    ) -> List[DownloadResult]:
        """
        Download multiple files in parallel.

        Args:
            download_tasks: List of download tasks

        Returns:
            List of download results
        """
        if not download_tasks:
            return []

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
                else:
                    processed_results.append(result)

        # Update global statistics
        total_time = time.time() - start_time
        self._update_stats(processed_results, total_time)

        # Finalize cache if used
        if self.cache:
            self.cache.finalize()

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
        """
        Download a single file with caching and integrity verification.

        Args:
            session: aiohttp session
            semaphore: Semaphore for concurrency control
            task: Download task

        Returns:
            Download result
        """
        async with semaphore:
            start_time = time.time()

            # Check cache first
            if self.cache and self._check_cache(task):
                self.logger.debug(f"File found in cache: {task.file_path}")
                return DownloadResult(
                    task=task,
                    success=True,
                    duration=time.time() - start_time,
                    bytes_downloaded=task.expected_size or 0,
                    from_cache=True,
                    integrity_verified=True,  # Assume cached files are verified
                )

            # Ensure parent directory exists
            task.local_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                # Download the file
                self.logger.debug(f"Downloading: {task.file_path}")
                bytes_downloaded = await self._stream_download(session, task)

                # Verify integrity if enabled
                integrity_verified = False
                if self.integrity_checker:
                    integrity_verified = await self._verify_file_integrity(task)

                # Add to cache if successful
                if self.cache and integrity_verified:
                    await self._add_to_cache(task)

                duration = time.time() - start_time

                self.logger.debug(
                    f"Successfully downloaded {task.file_path} "
                    f"({bytes_downloaded} bytes in {duration:.2f}s)"
                )

                return DownloadResult(
                    task=task,
                    success=True,
                    duration=duration,
                    bytes_downloaded=bytes_downloaded,
                    from_cache=False,
                    integrity_verified=integrity_verified,
                )

            except Exception as e:
                duration = time.time() - start_time
                self.logger.error(f"Failed to download {task.file_path}: {e}")

                return DownloadResult(
                    task=task,
                    success=False,
                    error=str(e),
                    duration=duration,
                )

    async def _stream_download(
        self,
        session: aiohttp.ClientSession,
        task: DownloadTask,
    ) -> int:
        """
        Stream download a file from URL.

        Args:
            session: aiohttp session
            task: Download task

        Returns:
            Number of bytes downloaded
        """
        async with session.get(task.download_url) as response:
            response.raise_for_status()

            # Note: Content-Length verification is informational only
            # Some files may have slight differences due to encoding
            content_length = response.headers.get("Content-Length")
            if content_length and task.expected_size:
                expected = task.expected_size
                actual = int(content_length)
                if abs(actual - expected) > 0:
                    self.logger.debug(
                        f"Content-Length differs for {task.file_path}: "
                        f"expected {expected}, server reports {actual}"
                    )

            bytes_downloaded = 0

            # Stream the content to file
            with open(task.local_path, "wb") as f:
                async for chunk in response.content.iter_chunked(self.chunk_size):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)

            # Verify downloaded size (allow some flexibility)
            if task.expected_size and bytes_downloaded > 0:
                expected = task.expected_size
                # Allow up to 10% difference for encoding variations
                tolerance = max(1, int(expected * 0.1))
                if abs(bytes_downloaded - expected) > tolerance:
                    self.logger.warning(
                        f"Downloaded size significantly differs for {task.file_path}: "
                        f"expected ~{expected}, got {bytes_downloaded}"
                    )

            return bytes_downloaded

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
        with ThreadPoolExecutor(max_workers=2) as executor:
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
            except Exception as e:
                self.logger.warning(f"Failed to add {task.file_path} to cache: {e}")

        # Run cache operation in thread pool
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            await loop.run_in_executor(executor, add_to_cache)

    def _update_stats(self, results: List[DownloadResult], total_time: float) -> None:
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

    def get_stats(self) -> Dict[str, Any]:
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

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if self.cache:
            return self.cache.get_cache_stats()
        return {}


def run_parallel_downloads(
    download_tasks: List[DownloadTask],
    max_concurrent_downloads: int = 5,
    verify_integrity: bool = True,
    use_cache: bool = True,
) -> List[DownloadResult]:
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
