"""
Core functionality for gh-folder-download.
"""

import asyncio
import urllib.request
from os import makedirs
from os.path import exists, join
from pathlib import Path
from shutil import rmtree

from github import Github
from github.ContentFile import ContentFile
from github.Repository import Repository

from .integrity import FileIntegrityChecker, IntegrityError
from .logger import get_logger
from .parallel_downloader import DownloadTask, ParallelDownloader
from .rate_limiter import RateLimitedGitHubClient
from .retry import APIRetryHandler, DownloadRetryHandler, RetryError


def get_sha_for_branch_or_tag(repository: Repository, branch_or_tag: str) -> str:
    """
    Returns a commit PyGithub object for the specified repository and branch or tag.
    """
    logger = get_logger()

    # Try branches first
    logger.debug(f"Looking for branch: {branch_or_tag}")
    branches = repository.get_branches()
    matched_branches = [match for match in branches if match.name == branch_or_tag]
    if matched_branches:
        logger.debug(f"Found branch: {branch_or_tag}")
        return matched_branches[0].commit.sha

    # Try tags
    logger.debug(f"Branch not found, looking for tag: {branch_or_tag}")
    tags = repository.get_tags()
    matched_tags = [match for match in tags if match.name == branch_or_tag]
    if matched_tags:
        logger.debug(f"Found tag: {branch_or_tag}")
        return matched_tags[0].commit.sha

    raise ValueError(f"No branch or tag named '{branch_or_tag}' exists in the repository")


def download_folder_parallel(
    repository: Repository,
    sha: str,
    path: str,
    output: Path,
    force: bool,
    max_concurrent: int,
    verify_integrity: bool,
    use_cache: bool,
    github_client: RateLimitedGitHubClient,
    api_retry_handler: APIRetryHandler,
    quiet: bool,
    show_progress: bool,
) -> dict[str, int]:
    """
    Download all contents using parallel downloader.

    Returns download statistics.
    """
    logger = get_logger()

    fullpath = join(output, path)

    if exists(fullpath):
        if force:
            logger.warning(f"Removing existing folder: {fullpath}")
            rmtree(fullpath)
        else:
            logger.error(f"Output folder already exists: {fullpath}")
            logger.info("Use --force to overwrite existing folders")
            return {"total_files": 0, "total_size": 0}

    logger.progress_info(f"Creating directory: {fullpath}")
    makedirs(fullpath, exist_ok=True)

    # Collect all download tasks
    download_tasks = []
    repo_full_name = repository.full_name

    def collect_tasks(current_path: str, current_output: Path):
        """Recursively collect all download tasks."""

        # Get directory contents with rate limiting and retry
        def get_contents():
            github_client.rate_limiter.wait_if_needed()
            return repository.get_dir_contents(current_path, ref=sha)

        try:
            contents = api_retry_handler.retry_api_call(get_contents, f"get directory contents for {current_path}")
        except RetryError as e:
            logger.error(f"Failed to get directory contents for '{current_path}': {e}")
            return

        for content in contents:
            content_output_path = current_output / content.name

            if content.type == "dir":
                logger.debug(f"Found directory: {content.path}")
                content_output_path.mkdir(parents=True, exist_ok=True)
                # Recursively collect from subdirectory
                collect_tasks(content.path, content_output_path)
            else:
                # Get file content to get download URL
                try:

                    def get_file_content(c_path=content.path):
                        github_client.rate_limiter.wait_if_needed()
                        return repository.get_contents(c_path, ref=sha)

                    file_content = api_retry_handler.retry_api_call(
                        get_file_content, f"get file content for {content.path}"
                    )

                    if isinstance(file_content, ContentFile) and file_content.download_url:
                        task = DownloadTask(
                            file_path=content.path,
                            download_url=file_content.download_url,
                            local_path=content_output_path,
                            expected_size=content.size,
                            sha=file_content.sha,
                            repo_full_name=repo_full_name,
                            ref=sha,
                        )
                        download_tasks.append(task)
                    else:
                        logger.warning(f"No download URL for {content.path}")

                except Exception as e:
                    logger.error(f"Failed to get file content for {content.path}: {e}")

    # Collect all tasks
    collect_tasks(path, Path(fullpath))

    if not download_tasks:
        logger.warning("No files found to download")
        return {"total_files": 0, "total_size": 0}

    # Execute parallel downloads
    downloader = ParallelDownloader(
        max_concurrent_downloads=max_concurrent,
        verify_integrity=verify_integrity,
        use_cache=use_cache,
        show_progress=show_progress,
        quiet=quiet,
    )

    results = asyncio.run(downloader.download_files(download_tasks))

    # Process results and calculate stats
    stats = {
        "total_files": len([r for r in results if r.success]),
        "total_size": sum(r.bytes_downloaded for r in results if r.success),
        "integrity_failures": len([r for r in results if r.success and not r.integrity_verified]),
        "download_failures": len([r for r in results if not r.success]),
        "cached_files": len([r for r in results if r.from_cache]),
    }

    # Add performance stats
    downloader_stats = downloader.get_stats()
    stats.update(
        {
            "average_speed_mbps": downloader_stats.get("average_speed_mbps", 0),
            "success_rate": downloader_stats.get("success_rate", 0),
            "cache_hit_rate": downloader_stats.get("cache_hit_rate", 0),
        }
    )

    return stats


def download_folder_parallel_no_rate_limit(
    repository: Repository,
    sha: str,
    path: str,
    output: Path,
    force: bool,
    max_concurrent: int,
    verify_integrity: bool,
    use_cache: bool,
    github: Github,
    api_retry_handler: APIRetryHandler,
    quiet: bool,
    show_progress: bool,
) -> dict[str, int]:
    """
    Download all contents using parallel downloader without rate limiting.

    Returns download statistics.
    """
    logger = get_logger()

    fullpath = join(output, path)

    if exists(fullpath):
        if force:
            logger.warning(f"Removing existing folder: {fullpath}")
            rmtree(fullpath)
        else:
            logger.error(f"Output folder already exists: {fullpath}")
            logger.info("Use --force to overwrite existing folders")
            return {"total_files": 0, "total_size": 0}

    logger.progress_info(f"Creating directory: {fullpath}")
    makedirs(fullpath, exist_ok=True)

    # Collect all download tasks
    download_tasks = []
    repo_full_name = repository.full_name

    def collect_tasks(current_path: str, current_output: Path):
        """Recursively collect all download tasks."""

        # Get directory contents without rate limiting
        def get_contents():
            return repository.get_dir_contents(current_path, ref=sha)

        try:
            contents = api_retry_handler.retry_api_call(get_contents, f"get directory contents for {current_path}")
        except RetryError as e:
            logger.error(f"Failed to get directory contents for '{current_path}': {e}")
            return

        for content in contents:
            content_output_path = current_output / content.name

            if content.type == "dir":
                logger.debug(f"Found directory: {content.path}")
                content_output_path.mkdir(parents=True, exist_ok=True)
                # Recursively collect from subdirectory
                collect_tasks(content.path, content_output_path)
            else:
                # Get file content to get download URL
                try:

                    def get_file_content(c_path=content.path):
                        return repository.get_contents(c_path, ref=sha)

                    file_content = api_retry_handler.retry_api_call(
                        get_file_content, f"get file content for {content.path}"
                    )

                    if isinstance(file_content, ContentFile) and file_content.download_url:
                        task = DownloadTask(
                            file_path=content.path,
                            download_url=file_content.download_url,
                            local_path=content_output_path,
                            expected_size=content.size,
                            sha=file_content.sha,
                            repo_full_name=repo_full_name,
                            ref=sha,
                        )
                        download_tasks.append(task)
                    else:
                        logger.warning(f"No download URL for {content.path}")

                except Exception as e:
                    logger.error(f"Failed to get file content for {content.path}: {e}")

    # Collect all tasks
    collect_tasks(path, Path(fullpath))

    if not download_tasks:
        logger.warning("No files found to download")
        return {"total_files": 0, "total_size": 0}

    # Execute parallel downloads
    downloader = ParallelDownloader(
        max_concurrent_downloads=max_concurrent,
        verify_integrity=verify_integrity,
        use_cache=use_cache,
        show_progress=show_progress,
        quiet=quiet,
    )

    results = asyncio.run(downloader.download_files(download_tasks))

    # Process results and calculate stats
    stats = {
        "total_files": len([r for r in results if r.success]),
        "total_size": sum(r.bytes_downloaded for r in results if r.success),
        "integrity_failures": len([r for r in results if r.success and not r.integrity_verified]),
        "download_failures": len([r for r in results if not r.success]),
        "cached_files": len([r for r in results if r.from_cache]),
    }

    # Add performance stats
    downloader_stats = downloader.get_stats()
    stats.update(
        {
            "average_speed_mbps": downloader_stats.get("average_speed_mbps", 0),
            "success_rate": downloader_stats.get("success_rate", 0),
            "cache_hit_rate": downloader_stats.get("cache_hit_rate", 0),
        }
    )

    return stats


def download_folder(
    repository: Repository,
    sha: str,
    path: str,
    output: Path,
    force: bool,
    verify_integrity: bool,
    api_retry_handler: APIRetryHandler,
    download_retry_handler: DownloadRetryHandler,
    integrity_checker: FileIntegrityChecker,
) -> dict[str, int]:
    """
    Download all contents at server_path with commit tag sha in
    the repository. (Legacy sequential version)

    Returns download statistics.
    """
    logger = get_logger()
    stats = {
        "total_files": 0,
        "total_size": 0,
        "integrity_failures": 0,
        "download_failures": 0,
    }

    fullpath = join(output, path)

    if exists(fullpath):
        if force:
            logger.warning(f"Removing existing folder: {fullpath}")
            rmtree(fullpath)
        else:
            logger.error(f"Output folder already exists: {fullpath}")
            logger.info("Use --force to overwrite existing folders")
            return stats

    logger.progress_info(f"Creating directory: {fullpath}")
    makedirs(fullpath, exist_ok=True)

    # Get directory contents with retry
    def get_contents():
        return repository.get_dir_contents(path, ref=sha)

    try:
        logger.debug(f"Getting contents for path: {path}")
        contents = api_retry_handler.retry_api_call(get_contents, f"get directory contents for {path}")
    except RetryError as e:
        logger.error(f"Failed to get directory contents for '{path}' after retries: {e}")
        return stats

    for content in contents:
        fullpath = join(output, content.path)

        if content.type == "dir":
            logger.debug(f"Found directory: {content.path}")
            makedirs(fullpath, exist_ok=True)
            # Recursively download subdirectory
            sub_stats = download_folder(
                repository=repository,
                sha=sha,
                path=content.path,
                output=output,
                force=force,
                verify_integrity=verify_integrity,
                api_retry_handler=api_retry_handler,
                download_retry_handler=download_retry_handler,
                integrity_checker=integrity_checker,
            )
            stats["total_files"] += sub_stats["total_files"]
            stats["total_size"] += sub_stats["total_size"]
            stats["integrity_failures"] += sub_stats["integrity_failures"]
            stats["download_failures"] += sub_stats["download_failures"]
        else:
            # Download file with retry and integrity verification
            success = download_file_with_verification(
                repository=repository,
                content=content,
                fullpath=fullpath,
                sha=sha,
                verify_integrity=verify_integrity,
                download_retry_handler=download_retry_handler,
                integrity_checker=integrity_checker,
            )

            if success:
                stats["total_files"] += 1
                stats["total_size"] += content.size or 0
            else:
                stats["download_failures"] += 1

    return stats


def download_file_with_verification(
    repository: Repository,
    content,
    fullpath: str,
    sha: str,
    verify_integrity: bool,
    download_retry_handler: DownloadRetryHandler,
    integrity_checker: FileIntegrityChecker,
) -> bool:
    """
    Download a single file with retry and integrity verification.
    (Legacy sequential version)

    Returns True if download and verification succeeded, False otherwise.
    """
    logger = get_logger()

    try:
        logger.download_start(content.path, content.size)

        # Get file content with API retry
        def get_file_content():
            return repository.get_contents(content.path, ref=sha)

        file_content = get_file_content()

        if not isinstance(file_content, ContentFile):
            logger.error(f"Expected ContentFile for {content.path}")
            return False

        if file_content.download_url is None:
            logger.warning(f"No download URL available for {content.path}")
            return False

        # Download the file with retry
        def download_file():
            urllib.request.urlretrieve(file_content.download_url, fullpath)

        download_retry_handler.retry_download(download_file, content.path)

        # Verify integrity if enabled
        if verify_integrity:
            try:
                file_path = Path(fullpath)

                # Verify file size matches expected size
                if content.size is not None:
                    integrity_checker.verify_file_size(file_path, content.size)

                # Perform basic content verification
                content_info = integrity_checker.verify_file_content(file_path)

                # Log any warnings about file content
                if content_info.get("is_empty"):
                    logger.warning(f"Downloaded file is empty: {content.path}")
                elif not content_info.get("is_readable"):
                    logger.warning(f"Downloaded file is not readable: {content.path}")

                logger.debug(f"✅ Integrity verification passed for {content.path}")

            except IntegrityError as e:
                logger.error(f"Integrity verification failed for {content.path}: {e}")
                # Don't count as download failure, but note the integrity issue
                # The file was downloaded, just failed verification

        logger.download_complete(content.path)
        return True

    except RetryError as e:
        logger.download_error(content.path, f"Download failed after retries: {e}")
        return False
    except Exception as e:
        logger.download_error(content.path, str(e))
        return False
