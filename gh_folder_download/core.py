"""Core repository traversal and transactional download orchestration."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import TypedDict

from github import GithubException
from github.ContentFile import ContentFile
from github.Repository import Repository

from .filters import FileFilter
from .logger import get_logger
from .parallel_downloader import DownloadTask, ParallelDownloader
from .rate_limiter import RateLimitedGitHubClient
from .retry import APIRetryHandler, DownloadRetryHandler, RetryError


class DownloadOperationError(Exception):
    """Raised when a download cannot be completed without changing the target."""


class DownloadStats(TypedDict):
    total_files: int
    matched_files: int
    filtered_files: int
    total_size: int
    integrity_failures: int
    download_failures: int
    cached_files: int
    average_speed_mbps: float
    success_rate: float
    cache_hit_rate: float
    destination: str


def get_sha_for_branch_or_tag(repository: Repository, branch_or_tag: str) -> str:
    """Resolve a branch, tag, or commit-ish without listing every ref."""
    try:
        return repository.get_commit(branch_or_tag).sha
    except GithubException as error:
        if error.status == 404:
            raise ValueError(f"No branch, tag, or commit named '{branch_or_tag}' exists in the repository") from error
        raise


def resolve_ref_and_path(repository: Repository, tree_segments: tuple[str, ...]) -> tuple[str, str, str]:
    """Resolve the longest valid ref prefix from a GitHub ``/tree/...`` URL."""
    if not tree_segments:
        ref = repository.default_branch
        return ref, get_sha_for_branch_or_tag(repository, ref), ""

    for split_at in range(len(tree_segments), 0, -1):
        ref = "/".join(tree_segments[:split_at])
        try:
            sha = get_sha_for_branch_or_tag(repository, ref)
        except ValueError:
            continue
        return ref, sha, "/".join(tree_segments[split_at:])
    raise ValueError(f"Could not resolve a branch or tag from {'/'.join(tree_segments)!r}")


def resolve_destination(repository: Repository, path: str, output: Path) -> Path:
    """Calculate a target that is always a child of the user-selected output."""
    output = output.resolve()
    relative_target = Path(path) if path else Path(repository.name)
    destination = (output / relative_target).resolve()
    if destination == output or not destination.is_relative_to(output):
        raise DownloadOperationError(f"Unsafe output destination: {destination}")
    return destination


def download_folder_parallel(
    repository: Repository,
    sha: str,
    path: str,
    output: Path,
    force: bool,
    max_concurrent: int,
    verify_integrity: bool,
    use_cache: bool,
    github_client: RateLimitedGitHubClient | None,
    api_retry_handler: APIRetryHandler,
    quiet: bool,
    show_progress: bool,
    *,
    file_filter: FileFilter | None = None,
    ref_name: str | None = None,
    timeout: int = 30,
    chunk_size: int = 8192,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    cache_max_size_gb: float = 5.0,
    cache_max_age_days: int = 30,
    cache_auto_cleanup: bool = True,
) -> DownloadStats:
    """Download a repository folder into staging and install it transactionally."""
    logger = get_logger()
    destination = resolve_destination(repository, path, output)
    if destination.exists() and not force:
        raise DownloadOperationError(f"Destination already exists: {destination}. Use --force to replace it.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(tempfile.mkdtemp(prefix=f".{destination.name}.ghfd-", dir=destination.parent))
    tasks: list[DownloadTask] = []
    filtered_files = 0

    def api_call(operation, description: str):
        def wrapped():
            if github_client is not None:
                github_client.rate_limiter.wait_if_needed()
            return operation()

        return api_retry_handler.retry_api_call(wrapped, description)

    def collect_tasks(remote_path: str, local_root: Path) -> None:
        nonlocal filtered_files
        try:
            contents = api_call(
                lambda: repository.get_contents(remote_path, ref=sha),
                f"get directory contents for {remote_path or '/'}",
            )
        except RetryError as error:
            raise DownloadOperationError(str(error)) from error

        if isinstance(contents, ContentFile):
            raise DownloadOperationError(f"GitHub path is not a directory: {remote_path}")

        if file_filter and file_filter.config.respect_gitignore:
            gitignore = next(
                (entry for entry in contents if entry.type == "file" and entry.name == ".gitignore"),
                None,
            )
            if gitignore is not None:
                try:
                    gitignore_content = api_call(
                        lambda: repository.get_contents(gitignore.path, ref=sha),
                        f"get gitignore rules for {remote_path or '/'}",
                    )
                    if isinstance(gitignore_content, ContentFile):
                        lines = gitignore_content.decoded_content.decode("utf-8", errors="replace").splitlines()
                        file_filter.add_gitignore_rules(remote_path, lines)
                except (RetryError, OSError, UnicodeError) as error:
                    raise DownloadOperationError(f"Could not load {gitignore.path}: {error}") from error

        for content in contents:
            local_path = local_root / content.name
            if content.type == "dir":
                local_path.mkdir(parents=True, exist_ok=True)
                collect_tasks(content.path, local_path)
                continue

            if file_filter and not file_filter.should_include_file(content.path, content.size, content):
                filtered_files += 1
                continue

            file_content = content
            if not file_content.download_url:
                try:
                    candidate = api_call(
                        lambda content_path=content.path: repository.get_contents(content_path, ref=sha),
                        f"get file metadata for {content.path}",
                    )
                except RetryError as error:
                    raise DownloadOperationError(str(error)) from error
                if not isinstance(candidate, ContentFile):
                    raise DownloadOperationError(f"Unsupported repository entry: {content.path}")
                file_content = candidate

            if not file_content.download_url:
                raise DownloadOperationError(f"No download URL available for {content.path}")

            tasks.append(
                DownloadTask(
                    file_path=content.path,
                    download_url=file_content.download_url,
                    local_path=local_path,
                    expected_size=content.size,
                    sha=file_content.sha,
                    repo_full_name=repository.full_name,
                    ref=ref_name or sha,
                )
            )

    try:
        logger.progress_info(f"Preparing download in: {destination}")
        collect_tasks(path, staging)
        downloader = ParallelDownloader(
            max_concurrent_downloads=max_concurrent,
            chunk_size=chunk_size,
            timeout=timeout,
            verify_integrity=verify_integrity,
            use_cache=use_cache,
            show_progress=show_progress,
            quiet=quiet,
            max_retries=max_retries,
            retry_delay=retry_delay,
            cache_max_size_gb=cache_max_size_gb,
            cache_max_age_days=cache_max_age_days,
            cache_auto_cleanup=cache_auto_cleanup,
        )
        results = asyncio.run(downloader.download_files(tasks)) if tasks else []
        failures = [result for result in results if not result.success]
        if failures:
            details = "; ".join(f"{result.task.file_path}: {result.error}" for result in failures[:3])
            raise DownloadOperationError(f"{len(failures)} file(s) failed: {details}")

        _install_staging(staging, destination)
        staging = None
        downloader_stats = downloader.get_stats()
        return {
            "total_files": len(results),
            "matched_files": len(tasks),
            "filtered_files": filtered_files,
            "total_size": sum(result.bytes_downloaded for result in results),
            "integrity_failures": 0,
            "download_failures": 0,
            "cached_files": sum(1 for result in results if result.from_cache),
            "average_speed_mbps": downloader_stats.get("average_speed_mbps", 0.0),
            "success_rate": downloader_stats.get("success_rate", 100.0),
            "cache_hit_rate": downloader_stats.get("cache_hit_rate", 0.0),
            "destination": str(destination),
        }
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _install_staging(staging: Path, destination: Path) -> None:
    """Replace a destination with rollback if the final rename fails."""
    backup: Path | None = None
    if destination.exists():
        backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.backup-", dir=destination.parent))
        backup.rmdir()
        destination.rename(backup)
    try:
        staging.rename(destination)
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            backup.rename(destination)
        raise
    if backup is not None and backup.exists():
        try:
            if backup.is_dir():
                shutil.rmtree(backup)
            else:
                backup.unlink()
        except OSError as error:
            get_logger().warning(f"Installed destination but could not remove backup {backup}: {error}")


def download_folder_parallel_no_rate_limit(
    repository: Repository,
    sha: str,
    path: str,
    output: Path,
    force: bool,
    max_concurrent: int,
    verify_integrity: bool,
    use_cache: bool,
    github,
    api_retry_handler: APIRetryHandler,
    quiet: bool,
    show_progress: bool,
    **kwargs,
) -> DownloadStats:
    """Compatibility wrapper for callers that disable API throttling."""
    return download_folder_parallel(
        repository,
        sha,
        path,
        output,
        force,
        max_concurrent,
        verify_integrity,
        use_cache,
        None,
        api_retry_handler,
        quiet,
        show_progress,
        **kwargs,
    )


def download_folder(
    repository: Repository,
    sha: str,
    path: str,
    output: Path,
    force: bool,
    verify_integrity: bool,
    api_retry_handler: APIRetryHandler,
    download_retry_handler: DownloadRetryHandler,
    integrity_checker,
    **kwargs,
) -> DownloadStats:
    """Compatibility wrapper using the unified downloader with concurrency one."""
    return download_folder_parallel(
        repository,
        sha,
        path,
        output,
        force,
        1,
        verify_integrity,
        False,
        None,
        api_retry_handler,
        False,
        False,
        max_retries=download_retry_handler.config.max_attempts,
        retry_delay=download_retry_handler.config.base_delay,
        **kwargs,
    )
