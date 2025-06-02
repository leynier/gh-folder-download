"""
Retry mechanism with exponential backoff for gh-folder-download.
"""

import re
import time
from functools import wraps
from typing import Any, Callable, cast

from github import GithubException

from .logger import get_logger


class RetryError(Exception):
    """Exception raised when all retry attempts are exhausted."""

    pass


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter


class RetryHandler:
    """Handles retry logic with exponential backoff."""

    # Exceptions that should trigger retries
    RETRYABLE_EXCEPTIONS = (
        ConnectionError,
        TimeoutError,
        OSError,  # Network-related OS errors
    )

    # GitHub API specific retryable status codes
    RETRYABLE_GITHUB_STATUS = (
        403,  # Rate limit exceeded
        500,  # Internal server error
        502,  # Bad gateway
        503,  # Service unavailable
        504,  # Gateway timeout
    )

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
        self.logger = get_logger()

    def retry(
        self,
        func: Callable,
        *args,
        config: RetryConfig | None = None,
        **kwargs,
    ) -> Any:
        """
        Execute a function with retry logic.

        Args:
            func: Function to execute
            *args: Arguments to pass to the function
            config: Optional retry configuration override
            **kwargs: Keyword arguments to pass to the function

        Returns:
            Result of the function call

        Raises:
            RetryError: If all retry attempts are exhausted
        """
        retry_config = config or self.config
        last_exception = None

        for attempt in range(retry_config.max_attempts):
            try:
                self.logger.debug(
                    f"Attempt {attempt + 1}/{retry_config.max_attempts} for {func.__name__}"
                )
                return func(*args, **kwargs)

            except Exception as e:
                last_exception = e

                if not self._is_retryable(e):
                    self.logger.debug(f"Exception {type(e).__name__} is not retryable")
                    raise e

                if attempt + 1 >= retry_config.max_attempts:
                    self.logger.error(
                        f"All {retry_config.max_attempts} attempts failed for {func.__name__}"
                    )
                    break

                delay = self._calculate_delay(attempt, retry_config)

                # Special handling for GitHub rate limiting
                if (
                    isinstance(e, GithubException)
                    and cast(GithubException, e).status == 403
                ):
                    # Check if it's rate limiting
                    if "rate limit" in str(e).lower():
                        # Use longer delay for rate limiting
                        delay = max(delay, 60)  # At least 1 minute
                        self.logger.warning(
                            f"Rate limit exceeded, waiting {delay:.1f} seconds"
                        )
                    else:
                        self.logger.warning(f"GitHub permission error: {e}")
                else:
                    self.logger.warning(f"Attempt {attempt + 1} failed: {e}")

                self.logger.info(f"Retrying in {delay:.1f} seconds...")
                time.sleep(delay)

        # All attempts failed
        raise RetryError(
            f"Failed after {retry_config.max_attempts} attempts: {last_exception}"
        )

    def _is_retryable(self, exception: Exception) -> bool:
        """Check if an exception should trigger a retry."""

        # Check for network-related exceptions
        if isinstance(exception, self.RETRYABLE_EXCEPTIONS):
            return True

        # Check for GitHub API exceptions
        if isinstance(exception, GithubException):
            return (
                cast(GithubException, exception).status in self.RETRYABLE_GITHUB_STATUS
            )

        # Check for specific error messages that indicate temporary issues
        error_msg = str(exception).lower()
        temporary_indicators = [
            "timeout",
            "connection",
            "network",
            "temporary",
            "unavailable",
            "rate limit",
        ]

        # Use word boundaries for more accurate matching

        return any(
            re.search(rf"\b{re.escape(indicator)}\b", error_msg)
            for indicator in temporary_indicators
        )

    def _calculate_delay(self, attempt: int, config: RetryConfig) -> float:
        """Calculate delay for the next retry attempt."""
        delay = config.base_delay * (config.backoff_factor**attempt)
        delay = min(delay, config.max_delay)

        # Add jitter to avoid thundering herd problem
        if config.jitter:
            import random

            jitter_factor = random.uniform(0.5, 1.5)
            delay *= jitter_factor

        return delay


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
) -> Callable:
    """
    Decorator to add retry functionality to a function.

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Multiplier for exponential backoff

    Returns:
        Decorated function with retry capability
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            config = RetryConfig(
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                backoff_factor=backoff_factor,
            )
            handler = RetryHandler(config)
            return handler.retry(func, *args, **kwargs)

        return wrapper

    return decorator


class DownloadRetryHandler(RetryHandler):
    """Specialized retry handler for download operations."""

    def __init__(self, config: RetryConfig | None = None):
        # More aggressive retry for downloads
        default_config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            backoff_factor=2.0,
        )
        super().__init__(config or default_config)

    def retry_download(
        self,
        download_func: Callable,
        file_path: str,
        *args,
        **kwargs,
    ) -> Any:
        """
        Retry download with specific logging for file downloads.

        Args:
            download_func: Function that performs the download
            file_path: Path of the file being downloaded (for logging)
            *args: Arguments to pass to download function
            **kwargs: Keyword arguments to pass to download function

        Returns:
            Result of the download function
        """

        def wrapper():
            return download_func(*args, **kwargs)

        try:
            return self.retry(wrapper)
        except RetryError as e:
            self.logger.error(
                f"Failed to download {file_path} after all retry attempts: {e}"
            )
            raise


class APIRetryHandler(RetryHandler):
    """Specialized retry handler for GitHub API operations."""

    def __init__(self, config: RetryConfig | None = None):
        # Conservative retry for API calls
        default_config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0,
        )
        super().__init__(config or default_config)

    def retry_api_call(
        self,
        api_func: Callable,
        operation_name: str,
        *args,
        **kwargs,
    ) -> Any:
        """
        Retry API call with specific logging for GitHub API operations.

        Args:
            api_func: Function that makes the API call
            operation_name: Name of the operation (for logging)
            *args: Arguments to pass to API function
            **kwargs: Keyword arguments to pass to API function

        Returns:
            Result of the API function
        """

        def wrapper():
            return api_func(*args, **kwargs)

        try:
            return self.retry(wrapper)
        except RetryError as e:
            self.logger.error(
                f"API operation '{operation_name}' failed after all retry attempts: {e}"
            )
            raise
