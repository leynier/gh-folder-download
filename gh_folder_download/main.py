"""Typer command-line interface for gh-folder-download."""

from __future__ import annotations

import os
import re
from pathlib import Path
from time import time

import typer
from github import Auth, Github, GithubException
from pydantic import ValidationError as PydanticValidationError
from typer import Option, Typer

from .cache import DownloadCache
from .config import ConfigurationError, FilterConfig, create_sample_config, load_config
from .core import (
    DownloadOperationError,
    download_folder_parallel,
    get_sha_for_branch_or_tag,
    resolve_ref_and_path,
)
from .filters import create_file_filter, get_preset_filter
from .logger import setup_logger
from .rate_limiter import RateLimitedGitHubClient
from .retry import APIRetryHandler, RetryConfig, RetryError
from .validation import InputValidator, ValidationError

app = Typer(no_args_is_help=False)


@app.command()
def download_command(
    url: str | None = Option(None, help="Repository or folder URL"),
    output: Path | None = Option(None, help="Parent output directory", file_okay=False),
    token: str | None = Option(None, help="GitHub token"),
    ref: str | None = Option(None, help="Explicit branch, tag, or commit; supports slashes"),
    remote_path: str | None = Option(None, "--path", help="Explicit repository folder path"),
    force: bool = Option(False, help="Replace the calculated destination if it exists"),
    verbose: bool = Option(False, "--verbose", "-v", help="Enable verbose logging"),
    quiet: bool | None = Option(None, "--quiet/--no-quiet", "-q", help="Suppress output except errors"),
    log_file: Path | None = Option(None, help="Log to file"),
    verify_integrity: bool | None = Option(
        None, "--verify-integrity/--no-verify-integrity", help="Verify size and Git blob SHA"
    ),
    max_retries: int | None = Option(None, min=1, max=10, help="Maximum download/API attempts"),
    retry_delay: float | None = Option(None, min=0.1, max=30.0, help="Base retry delay in seconds"),
    parallel_downloads: bool | None = Option(
        None, "--parallel-downloads/--no-parallel-downloads", help="Enable concurrent downloads"
    ),
    max_concurrent: int | None = Option(None, min=1, max=20, help="Maximum concurrent downloads"),
    use_cache: bool | None = Option(None, "--use-cache/--no-use-cache", help="Use the content cache"),
    clear_cache: bool = Option(False, help="Clear the content cache"),
    cache_stats: bool = Option(False, help="Show content cache statistics"),
    rate_limit_buffer: int | None = Option(None, min=10, max=1000, help="Reserved GitHub API requests"),
    disable_rate_limiting: bool | None = Option(
        None, "--disable-rate-limiting/--enable-rate-limiting", help="Disable API throttling"
    ),
    show_progress: bool | None = Option(None, "--show-progress/--no-show-progress", help="Show progress bars"),
    config_file: Path | None = Option(None, exists=True, readable=True, help="Configuration file"),
    create_config: bool = Option(False, help="Create a sample configuration file and exit"),
    include_extensions: list[str] | None = Option(None, help="Include only these extensions"),
    exclude_extensions: list[str] | None = Option(None, help="Exclude these extensions"),
    include_patterns: list[str] | None = Option(None, help="Include matching repository-relative globs"),
    exclude_patterns: list[str] | None = Option(None, help="Exclude matching repository-relative globs"),
    min_size: str | None = Option(None, help="Minimum file size, for example 1KB"),
    max_size: str | None = Option(None, help="Maximum file size, for example 10MB"),
    exclude_binary: bool | None = Option(None, "--exclude-binary/--include-binary", help="Exclude binary files"),
    exclude_large_files: bool | None = Option(
        None, "--exclude-large-files/--include-large-files", help="Exclude files larger than 10MB"
    ),
    respect_gitignore: bool | None = Option(
        None, "--respect-gitignore/--ignore-gitignore", help="Respect repository .gitignore rules"
    ),
    filter_preset: str | None = Option(None, help="Filter preset"),
) -> None:
    if create_config:
        if create_sample_config():
            return
        raise typer.Exit(1)

    try:
        config = load_config(config_file)
    except ConfigurationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error

    validator = InputValidator()
    try:
        validated_log_file = validator.validate_log_file_path(log_file)
    except ValidationError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(2) from error

    effective_quiet = config.ui.quiet_mode if quiet is None else quiet
    log_level = "DEBUG" if verbose else ("ERROR" if effective_quiet else config.ui.verbosity)
    logger = setup_logger(
        level=log_level,
        log_file=validated_log_file,
        quiet=effective_quiet,
        use_colors=config.ui.use_colors,
    )

    effective_cache = config.cache.enabled if use_cache is None else use_cache
    if clear_cache or cache_stats:
        cache = DownloadCache(
            max_size_gb=config.cache.max_size_gb,
            max_age_days=config.cache.max_age_days,
            auto_cleanup=config.cache.auto_cleanup,
        )
        if clear_cache:
            cache.clear_cache()
        if cache_stats:
            stats = cache.get_cache_stats()
            logger.info(f"Cache: {stats['total_entries']} entries, {stats['total_size_mb']} MB")
    if not url and (clear_cache or cache_stats):
        return
    if not url:
        logger.error("Repository URL is required")
        raise typer.Exit(2)

    effective_output = output or Path(config.paths.default_output)
    effective_token = token if token is not None else config.github_token or os.getenv("GITHUB_TOKEN")
    effective_integrity = config.download.verify_integrity if verify_integrity is None else verify_integrity
    effective_retries = config.download.max_retries if max_retries is None else max_retries
    effective_retry_delay = config.download.retry_delay if retry_delay is None else retry_delay
    effective_parallel = config.download.parallel_downloads if parallel_downloads is None else parallel_downloads
    effective_concurrent = config.download.max_concurrent if max_concurrent is None else max_concurrent
    effective_progress = config.ui.show_progress if show_progress is None else show_progress
    effective_rate_buffer = config.rate_limit.buffer if rate_limit_buffer is None else rate_limit_buffer
    rate_limiting_disabled = not config.rate_limit.enabled if disable_rate_limiting is None else disable_rate_limiting

    try:
        parsed_url = validator.parse_github_url(url)
        effective_output = validator.validate_output_path(effective_output, create_if_missing=True)
        effective_token = validator.validate_github_token(effective_token)
        filter_config = _resolve_filter_config(
            config.filters,
            filter_preset=filter_preset,
            include_extensions=include_extensions,
            exclude_extensions=exclude_extensions,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            min_size=min_size,
            max_size=max_size,
            exclude_binary=exclude_binary,
            exclude_large_files=exclude_large_files,
            respect_gitignore=respect_gitignore,
        )
        file_filter = create_file_filter(filter_config)

        api_retry = APIRetryHandler(
            RetryConfig(
                max_attempts=effective_retries,
                base_delay=effective_retry_delay,
                max_delay=30.0,
                backoff_factor=2.0,
            )
        )

        if rate_limiting_disabled:
            github = Github(auth=Auth.Token(effective_token)) if effective_token else Github()
            github_client = None
            repository = api_retry.retry_api_call(
                lambda: github.get_repo(f"{parsed_url.owner}/{parsed_url.repository}"), "get repository"
            )
        else:
            github_client = RateLimitedGitHubClient(effective_token, effective_rate_buffer)
            repository = api_retry.retry_api_call(
                lambda: github_client.get_repo(f"{parsed_url.owner}/{parsed_url.repository}"), "get repository"
            )

        resolved_ref, sha, path = _resolve_ref_path(
            repository,
            parsed_url.tree_segments,
            explicit_ref=ref,
            explicit_path=remote_path,
            retry_handler=api_retry,
        )
        path = validator.validate_repository_path(path)
        logger.repository_info(parsed_url.owner, parsed_url.repository, resolved_ref, path)

        started = time()
        stats = download_folder_parallel(
            repository=repository,
            sha=sha,
            path=path,
            output=effective_output,
            force=force,
            max_concurrent=effective_concurrent if effective_parallel else 1,
            verify_integrity=effective_integrity,
            use_cache=effective_cache,
            github_client=github_client,
            api_retry_handler=api_retry,
            quiet=effective_quiet,
            show_progress=effective_progress,
            file_filter=file_filter,
            ref_name=resolved_ref,
            timeout=config.download.timeout,
            chunk_size=config.download.chunk_size,
            max_retries=effective_retries,
            retry_delay=effective_retry_delay,
            cache_max_size_gb=config.cache.max_size_gb,
            cache_max_age_days=config.cache.max_age_days,
            cache_auto_cleanup=config.cache.auto_cleanup,
        )
        logger.summary(stats["total_files"], stats["total_size"], time() - started)
        logger.success(f"Installed to {stats['destination']}")
        if stats["filtered_files"]:
            logger.info(f"Filtered out: {stats['filtered_files']} files")
        if stats["cached_files"]:
            logger.info(f"Cache hits: {stats['cached_files']} files")
    except (ValidationError, PydanticValidationError, ValueError) as error:
        logger.error(str(error))
        if verbose:
            logger.debug("Input/configuration failure", exc_info=True)
        raise typer.Exit(2) from error
    except (DownloadOperationError, RetryError, GithubException, OSError) as error:
        logger.error(str(error))
        if verbose:
            logger.debug("Operational failure", exc_info=True)
        raise typer.Exit(1) from error
    except Exception as error:
        logger.error(f"Unexpected error: {error}")
        if verbose:
            logger.debug("Unexpected failure", exc_info=True)
        raise typer.Exit(1) from error


def _resolve_ref_path(repository, tree_segments, *, explicit_ref, explicit_path, retry_handler):
    if explicit_ref:
        sha = retry_handler.retry_api_call(
            lambda: get_sha_for_branch_or_tag(repository, explicit_ref), f"resolve ref {explicit_ref}"
        )
        ref_segments = tuple(explicit_ref.split("/"))
        inferred_path = ""
        if tuple(tree_segments[: len(ref_segments)]) == ref_segments:
            inferred_path = "/".join(tree_segments[len(ref_segments) :])
        return explicit_ref, sha, explicit_path if explicit_path is not None else inferred_path

    resolved_ref, sha, inferred_path = resolve_ref_and_path(repository, tuple(tree_segments))
    return resolved_ref, sha, explicit_path if explicit_path is not None else inferred_path


def _resolve_filter_config(
    configured: FilterConfig,
    *,
    filter_preset: str | None,
    include_extensions: list[str] | None,
    exclude_extensions: list[str] | None,
    include_patterns: list[str] | None,
    exclude_patterns: list[str] | None,
    min_size: str | None,
    max_size: str | None,
    exclude_binary: bool | None,
    exclude_large_files: bool | None,
    respect_gitignore: bool | None,
) -> FilterConfig:
    values = configured.model_dump()
    if filter_preset:
        values.update(get_preset_filter(filter_preset).model_dump())
    overrides = {
        "include_extensions": include_extensions,
        "exclude_extensions": exclude_extensions,
        "include_patterns": include_patterns,
        "exclude_patterns": exclude_patterns,
        "exclude_binary": exclude_binary,
        "exclude_large_files": exclude_large_files,
        "respect_gitignore": respect_gitignore,
    }
    values.update({key: value for key, value in overrides.items() if value is not None})
    if min_size is not None:
        parsed = _parse_size_string(min_size)
        if parsed is None:
            raise ValidationError(f"Invalid min-size format: {min_size}")
        values["min_size_bytes"] = parsed
    if max_size is not None:
        parsed = _parse_size_string(max_size)
        if parsed is None:
            raise ValidationError(f"Invalid max-size format: {max_size}")
        values["max_size_bytes"] = parsed
    return FilterConfig(**values)


def _parse_size_string(size_str: str) -> int | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMGT]?B)?", size_str.strip().upper())
    if not match:
        return None
    number, unit = match.groups()
    multipliers = {
        None: 1,
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }
    return int(float(number) * multipliers[unit])
