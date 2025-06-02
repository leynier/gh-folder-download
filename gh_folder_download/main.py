import asyncio
import os
import urllib.request
from os import makedirs
from os.path import exists, join
from pathlib import Path
from shutil import rmtree
from time import time

import typer
from github import Github, GithubException
from github.ContentFile import ContentFile
from github.Repository import Repository
from typer import Option, Typer

from .cache import DownloadCache
from .config import create_sample_config, load_config
from .filters import create_file_filter, get_preset_filter
from .integrity import FileIntegrityChecker, IntegrityError
from .logger import get_logger, setup_logger
from .parallel_downloader import DownloadTask, ParallelDownloader
from .rate_limiter import RateLimitedGitHubClient
from .retry import APIRetryHandler, DownloadRetryHandler, RetryConfig, RetryError
from .validation import InputValidator, ValidationError

app = Typer()


@app.command()
def download_command(
    url: str | None = Option(None, help="Repository URL"),
    output: Path = Option(
        ".",
        help="Output folder",
        file_okay=False,
        writable=True,
    ),
    token: str | None = Option(None, help="GitHub token"),
    force: bool = Option(False, help="Remove existing output folder if it exists"),
    verbose: bool = Option(False, "--verbose", "-v", help="Enable verbose logging"),
    quiet: bool = Option(False, "--quiet", "-q", help="Suppress output except errors"),
    log_file: Path | None = Option(None, help="Log to file"),
    verify_integrity: bool = Option(True, help="Verify file integrity after download"),
    max_retries: int = Option(
        3,
        help="Maximum number of retry attempts for failed operations",
        min=1,
        max=10,
    ),
    retry_delay: float = Option(
        1.0,
        help="Base delay between retries in seconds",
        min=0.1,
        max=30.0,
    ),
    # New performance options
    parallel_downloads: bool = Option(
        True,
        help="Enable parallel downloads for better performance",
    ),
    max_concurrent: int = Option(
        5,
        help="Maximum number of concurrent downloads",
        min=1,
        max=20,
    ),
    use_cache: bool = Option(
        True,
        help="Enable intelligent caching to avoid re-downloading unchanged files",
    ),
    clear_cache: bool = Option(
        False,
        help="Clear download cache before starting",
    ),
    cache_stats: bool = Option(
        False,
        help="Show cache statistics",
    ),
    rate_limit_buffer: int = Option(
        100,
        help="Number of GitHub API requests to keep as buffer",
        min=10,
        max=1000,
    ),
    disable_rate_limiting: bool = Option(
        False,
        help="Disable rate limiting completely for maximum speed (may exhaust API limits)",
    ),
    show_progress: bool = Option(
        True,
        help="Show advanced progress bars and real-time statistics",
    ),
    # Configuration options
    config_file: Path | None = Option(
        None,
        help="Path to configuration file",
        exists=True,
        readable=True,
    ),
    create_config: bool = Option(
        False,
        help="Create a sample configuration file and exit",
    ),
    # Filter options
    include_extensions: list[str] | None = Option(
        None,
        help="Include only files with these extensions (e.g., --include-extensions .py .js)",
    ),
    exclude_extensions: list[str] | None = Option(
        None,
        help="Exclude files with these extensions (e.g., --exclude-extensions .log .tmp)",
    ),
    include_patterns: list[str] | None = Option(
        None,
        help="Include files matching these glob patterns (e.g., --include-patterns 'src/**' 'docs/**')",
    ),
    exclude_patterns: list[str] | None = Option(
        None,
        help="Exclude files matching these glob patterns (e.g., --exclude-patterns '**/test/**' '**/*.pyc')",
    ),
    min_size: str | None = Option(
        None,
        help="Minimum file size (e.g., --min-size 1KB, 1MB)",
    ),
    max_size: str | None = Option(
        None,
        help="Maximum file size (e.g., --max-size 10MB, 100KB)",
    ),
    exclude_binary: bool = Option(
        False,
        help="Exclude binary files",
    ),
    exclude_large_files: bool = Option(
        False,
        help="Exclude files larger than 10MB",
    ),
    respect_gitignore: bool = Option(
        False,
        help="Respect common .gitignore patterns",
    ),
    filter_preset: str | None = Option(
        None,
        help="Use a predefined filter preset (code-only, docs-only, config-only, no-tests, small-files, minimal)",
    ),
) -> None:
    # Handle config creation request
    if create_config:
        if create_sample_config():
            logger = setup_logger()
            logger.info("Sample configuration file created successfully")
            return
        else:
            logger = setup_logger()
            logger.error("Failed to create sample configuration file")
            raise typer.Exit(1)

    # Load configuration
    config = load_config(config_file)

    # Setup logging with config defaults
    if quiet:
        log_level = "ERROR"
    elif verbose:
        log_level = "DEBUG"
    else:
        log_level = config.ui.verbosity

    logger = setup_logger(
        level=log_level, log_file=log_file, quiet=quiet or config.ui.quiet_mode
    )

    # Parse size filters
    min_size_bytes = None
    max_size_bytes = None

    if min_size:
        min_size_bytes = _parse_size_string(min_size)
        if min_size_bytes is None:
            logger.error(f"Invalid min-size format: {min_size}")
            raise typer.Exit(1)

    if max_size:
        max_size_bytes = _parse_size_string(max_size)
        if max_size_bytes is None:
            logger.error(f"Invalid max-size format: {max_size}")
            raise typer.Exit(1)

    # Setup file filters
    filter_config = config.filters.copy()

    # Override config with CLI options if provided
    if include_extensions:
        filter_config.include_extensions = include_extensions
    if exclude_extensions:
        filter_config.exclude_extensions = exclude_extensions
    if include_patterns:
        filter_config.include_patterns = include_patterns
    if exclude_patterns:
        filter_config.exclude_patterns = exclude_patterns
    if min_size_bytes is not None:
        filter_config.min_size_bytes = min_size_bytes
    if max_size_bytes is not None:
        filter_config.max_size_bytes = max_size_bytes
    if exclude_binary:
        filter_config.exclude_binary = True
    if exclude_large_files:
        filter_config.exclude_large_files = True
    if respect_gitignore:
        filter_config.respect_gitignore = True

    # Apply filter preset if specified
    if filter_preset:
        try:
            preset_config = get_preset_filter(filter_preset)
            # Merge preset with CLI overrides
            if not include_extensions:
                filter_config.include_extensions = preset_config.include_extensions
            if not exclude_extensions:
                filter_config.exclude_extensions = preset_config.exclude_extensions
            if not include_patterns:
                filter_config.include_patterns = preset_config.include_patterns
            if not exclude_patterns:
                filter_config.exclude_patterns = preset_config.exclude_patterns
            if min_size_bytes is None and preset_config.min_size_bytes:
                filter_config.min_size_bytes = preset_config.min_size_bytes
            if max_size_bytes is None and preset_config.max_size_bytes:
                filter_config.max_size_bytes = preset_config.max_size_bytes
            if not exclude_binary:
                filter_config.exclude_binary = preset_config.exclude_binary
            if not exclude_large_files:
                filter_config.exclude_large_files = preset_config.exclude_large_files
            if not respect_gitignore:
                filter_config.respect_gitignore = preset_config.respect_gitignore
        except ValueError as e:
            logger.error(str(e))
            raise typer.Exit(1)

    # Create file filter
    file_filter = create_file_filter(filter_config)

    # Log filter summary if verbose
    if verbose:
        filter_summary = file_filter.get_filter_summary()
        logger.info("Active file filters:")
        for key, value in filter_summary.items():
            if value:
                logger.info(f"  {key}: {value}")

    # Validate URL is provided when not creating config
    if not url:
        logger.error("Repository URL is required")
        raise typer.Exit(1)

    # Initialize components with custom retry configuration
    validator = InputValidator()

    # Create custom retry configs based on CLI parameters
    api_retry_config = RetryConfig(
        max_attempts=max_retries,
        base_delay=retry_delay,
        max_delay=30.0,
        backoff_factor=2.0,
    )

    download_retry_config = RetryConfig(
        max_attempts=max_retries + 2,  # More attempts for downloads
        base_delay=retry_delay,
        max_delay=120.0,
        backoff_factor=2.0,
    )

    api_retry_handler = APIRetryHandler(api_retry_config)
    download_retry_handler = DownloadRetryHandler(download_retry_config)
    integrity_checker = FileIntegrityChecker()

    # Initialize cache
    cache = DownloadCache() if use_cache else None
    if clear_cache and cache:
        cache.clear_cache()
        logger.info("Cache cleared")

    # Show cache stats if requested
    if cache_stats and cache:
        stats = cache.get_cache_stats()
        if stats["total_entries"] > 0:
            logger.info(
                f"Cache stats: {stats['total_entries']} entries, "
                f"{stats['total_size_mb']} MB, "
                f"oldest: {stats['oldest_entry']}, "
                f"newest: {stats['newest_entry']}"
            )
        else:
            logger.info("Cache is empty")

    try:
        # Enhanced input validation
        logger.progress_info("Validating inputs...")

        # Validate GitHub URL
        org, repo, branch, path = validator.validate_github_url(url)

        # Validate output path
        output = validator.validate_output_path(output, create_if_missing=True)

        # Validate GitHub token
        token = validator.validate_github_token(token)

        # Validate log file path
        if log_file:
            log_file = validator.validate_log_file_path(log_file)

        # Get GitHub token from environment if not provided
        if not token:
            token = os.getenv("GITHUB_TOKEN")
            if token:
                logger.debug(
                    "Using GitHub token from GITHUB_TOKEN environment variable"
                )
                token = validator.validate_github_token(token)

        logger.debug("✅ All inputs validated successfully")

        # Setup GitHub client with or without rate limiting
        logger.progress_info("Connecting to GitHub API...")

        if disable_rate_limiting:
            logger.warning("Rate limiting disabled - API limits may be exhausted")
            github = Github(token)
            github_client = None  # Signal that we're using direct client

            # Get repository directly
            repository = github.get_repo(f"{org}/{repo}")

        else:
            github_client = RateLimitedGitHubClient(token, rate_limit_buffer)

            # Log rate limit status
            if verbose:
                github_client.log_rate_limit_status()

            # Get repository with rate limiting
            repository = github_client.get_repo(f"{org}/{repo}")
            github = github_client.github  # For compatibility

        if not branch:
            branch = repository.default_branch

        # Display repository information
        logger.repository_info(org, repo, branch, path)

        # Get SHA for branch/tag with retry
        logger.progress_info(f"Getting commit SHA for branch '{branch}'")

        def get_branch_sha():
            return get_sha_for_branch_or_tag(repository, branch)

        sha = api_retry_handler.retry_api_call(
            get_branch_sha, f"get SHA for branch {branch}"
        )
        logger.debug(f"Found SHA: {sha}")

        # Start download
        start_time = time()

        if parallel_downloads:
            # Use parallel downloader
            if disable_rate_limiting:
                # Use direct GitHub client without rate limiting
                stats = download_folder_parallel_no_rate_limit(
                    repository=repository,
                    sha=sha,
                    path=path,
                    output=output,
                    force=force,
                    max_concurrent=max_concurrent,
                    verify_integrity=verify_integrity,
                    use_cache=use_cache,
                    github=github,
                    api_retry_handler=api_retry_handler,
                    quiet=quiet,
                    show_progress=show_progress,
                )
            else:
                # Use rate-limited client
                if github_client is None:
                    logger.error("Rate-limited client not properly initialized")
                    raise typer.Exit(1)
                stats = download_folder_parallel(
                    repository=repository,
                    sha=sha,
                    path=path,
                    output=output,
                    force=force,
                    max_concurrent=max_concurrent,
                    verify_integrity=verify_integrity,
                    use_cache=use_cache,
                    github_client=github_client,
                    api_retry_handler=api_retry_handler,
                    quiet=quiet,
                    show_progress=show_progress,
                )
        else:
            # Use sequential downloader (legacy)
            stats = download_folder(
                repository=repository,
                sha=sha,
                path=path,
                output=output,
                force=force,
                verify_integrity=verify_integrity,
                api_retry_handler=api_retry_handler,
                download_retry_handler=download_retry_handler,
                integrity_checker=integrity_checker,
            )

        end_time = time()

        # Show summary
        if stats["total_files"] > 0:
            logger.summary(
                total_files=stats["total_files"],
                total_size=stats["total_size"],
                duration=end_time - start_time,
            )

            # Show integrity results if verification was enabled
            if verify_integrity and stats.get("integrity_failures", 0) > 0:
                logger.warning(
                    f"{stats['integrity_failures']} files failed integrity verification"
                )
            elif verify_integrity:
                logger.success("All files passed integrity verification")

            # Show cache stats for parallel downloads
            if parallel_downloads and stats.get("cached_files", 0) > 0:
                logger.info(f"Cache hits: {stats['cached_files']} files")

            # Show performance stats
            if parallel_downloads and "average_speed_mbps" in stats:
                logger.info(f"Average speed: {stats['average_speed_mbps']:.2f} MB/s")

        else:
            logger.warning("No files were downloaded")

        # Final rate limit status
        if verbose:
            logger.progress_info("Final rate limit status:")
            if github_client:
                github_client.log_rate_limit_status()
            else:
                logger.info("Rate limiting was disabled for this session")

    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise
    except RetryError as e:
        logger.error(f"Operation failed after retries: {e}")
        raise
    except GithubException as e:
        logger.error(f"GitHub API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


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

    raise ValueError(
        f"No branch or tag named '{branch_or_tag}' exists in the repository"
    )


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
            contents = api_retry_handler.retry_api_call(
                get_contents, f"get directory contents for {current_path}"
            )
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

                    def get_file_content():
                        github_client.rate_limiter.wait_if_needed()
                        return repository.get_contents(content.path, ref=sha)

                    file_content = api_retry_handler.retry_api_call(
                        get_file_content, f"get file content for {content.path}"
                    )

                    if (
                        isinstance(file_content, ContentFile)
                        and file_content.download_url
                    ):
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
        "integrity_failures": len(
            [r for r in results if r.success and not r.integrity_verified]
        ),
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
            contents = api_retry_handler.retry_api_call(
                get_contents, f"get directory contents for {current_path}"
            )
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

                    def get_file_content():
                        return repository.get_contents(content.path, ref=sha)

                    file_content = api_retry_handler.retry_api_call(
                        get_file_content, f"get file content for {content.path}"
                    )

                    if (
                        isinstance(file_content, ContentFile)
                        and file_content.download_url
                    ):
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
        "integrity_failures": len(
            [r for r in results if r.success and not r.integrity_verified]
        ),
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
        contents = api_retry_handler.retry_api_call(
            get_contents, f"get directory contents for {path}"
        )
    except RetryError as e:
        logger.error(
            f"Failed to get directory contents for '{path}' after retries: {e}"
        )
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


def _parse_size_string(size_str: str) -> int | None:
    """
    Parse a human-readable size string into bytes.

    Args:
        size_str: Size string like "10MB", "1KB", "500B"

    Returns:
        Size in bytes, or None if parsing failed
    """
    size_str = size_str.strip().upper()

    # Define size multipliers
    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "TB": 1024 * 1024 * 1024 * 1024,
    }

    # Try to extract number and unit
    import re

    # Fixed regex: requires at least one digit, properly handles decimal numbers
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGT]?B?)$", size_str)
    if not match:
        return None

    number_str, unit = match.groups()

    try:
        number = float(number_str)
        # Ensure positive number
        if number < 0:
            return None
    except ValueError:
        return None

    # Default to bytes if no unit specified
    if not unit or unit == "":
        unit = "B"

    # Handle common abbreviations
    if unit in multipliers:
        return int(number * multipliers[unit])

    return None
