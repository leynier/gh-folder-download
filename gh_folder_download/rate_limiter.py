"""
Rate limiting system for GitHub API calls in gh-folder-download.
"""

import threading
import time
from dataclasses import dataclass
from typing import Any

from github import Github, GithubException

from .logger import get_logger


@dataclass
class RateLimitInfo:
    """Information about GitHub rate limits."""

    limit: int
    remaining: int
    reset_time: int
    used: int

    @property
    def reset_datetime(self) -> str:
        """Human readable reset time."""
        import datetime

        return datetime.datetime.fromtimestamp(self.reset_time).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    @property
    def seconds_until_reset(self) -> int:
        """Seconds until rate limit resets."""
        return max(0, self.reset_time - int(time.time()))

    @property
    def usage_percentage(self) -> float:
        """Percentage of rate limit used."""
        if self.limit == 0:
            return 0.0
        return (self.used / self.limit) * 100


class GitHubRateLimiter:
    """Intelligent rate limiter for GitHub API calls."""

    def __init__(self, github_client: Github, buffer_requests: int = 100):
        """
        Initialize rate limiter.

        Args:
            github_client: PyGithub client instance
            buffer_requests: Number of requests to keep as buffer
        """
        self.github = github_client
        self.buffer_requests = buffer_requests
        self.logger = get_logger()

        # Thread lock for rate limit info
        self._lock = threading.Lock()

        # Rate limit information
        self._core_rate_limit: RateLimitInfo | None = None
        self._search_rate_limit: RateLimitInfo | None = None
        self._last_update = 0

        # Adaptive delay settings
        self._base_delay = 0.1  # 100ms base delay
        self._adaptive_delay = 0.1
        self._last_request_time = 0

        # Initialize rate limit info
        self._update_rate_limit_info()

    def _update_rate_limit_info(self) -> None:
        """Update rate limit information from GitHub API."""
        try:
            with self._lock:
                rate_limit = self.github.get_rate_limit()

                # Core API rate limit
                core = rate_limit.core
                self._core_rate_limit = RateLimitInfo(
                    limit=core.limit,
                    remaining=core.remaining,
                    reset_time=int(core.reset.timestamp()),
                    used=core.limit - core.remaining,
                )

                # Search API rate limit
                search = rate_limit.search
                self._search_rate_limit = RateLimitInfo(
                    limit=search.limit,
                    remaining=search.remaining,
                    reset_time=int(search.reset.timestamp()),
                    used=search.limit - search.remaining,
                )

                self._last_update = time.time()

                self.logger.debug(
                    f"Rate limit updated - Core: {self._core_rate_limit.remaining}/{self._core_rate_limit.limit}, "
                    f"Search: {self._search_rate_limit.remaining}/{self._search_rate_limit.limit}"
                )

        except GithubException as e:
            self.logger.warning(f"Failed to update rate limit info: {e}")
        except Exception as e:
            self.logger.warning(f"Unexpected error updating rate limit: {e}")

    def _should_update_rate_limit(self) -> bool:
        """Check if rate limit info should be updated."""
        # Update every 30 seconds or if we don't have info
        # Protected access to _last_update to prevent race conditions
        with self._lock:
            return self._core_rate_limit is None or time.time() - self._last_update > 30

    def _calculate_adaptive_delay(self, rate_limit: RateLimitInfo) -> float:
        """Calculate adaptive delay based on current rate limit status."""
        if rate_limit.remaining <= 0:
            # No requests remaining, wait until reset
            return rate_limit.seconds_until_reset + 1

        # Calculate delay based on remaining requests and time
        remaining_time = rate_limit.seconds_until_reset
        if remaining_time <= 0:
            return self._base_delay

        # Calculate optimal delay to spread requests evenly
        available_requests = rate_limit.remaining - self.buffer_requests
        if available_requests <= 0:
            # We're in the buffer zone, slow down significantly
            return min(60, remaining_time / 10)  # Up to 1 minute delay

        # Calculate delay to spread requests over remaining time
        optimal_delay = remaining_time / available_requests

        # Apply adaptive scaling based on usage
        usage = rate_limit.usage_percentage
        if usage > 80:
            # High usage, be more conservative
            adaptive_factor = 2.0
        elif usage > 60:
            # Medium usage, be somewhat conservative
            adaptive_factor = 1.5
        else:
            # Low usage, use minimal delay
            adaptive_factor = 1.0

        delay = max(self._base_delay, optimal_delay * adaptive_factor)

        # Cap maximum delay at 30 seconds for normal operations
        return min(30, delay)

    def wait_if_needed(self, operation_type: str = "core") -> None:
        """
        Wait if necessary to respect rate limits.

        Args:
            operation_type: Type of operation ("core" or "search")
        """
        # Update rate limit info if needed
        if self._should_update_rate_limit():
            self._update_rate_limit_info()

        if operation_type == "search":
            rate_limit = self._search_rate_limit
        else:
            rate_limit = self._core_rate_limit

        if rate_limit is None:
            # Fallback to base delay if no rate limit info
            time.sleep(self._base_delay)
            return

        # Check if we're at or near the limit
        if rate_limit.remaining <= self.buffer_requests:
            if rate_limit.remaining <= 0:
                # Rate limit exceeded, wait for reset
                wait_time = rate_limit.seconds_until_reset + 1
                self.logger.warning(
                    f"Rate limit exceeded for {operation_type} API. "
                    f"Waiting {wait_time} seconds until reset at {rate_limit.reset_datetime}"
                )
                time.sleep(wait_time)
                self._update_rate_limit_info()
                return
            else:
                # In buffer zone, log warning
                self.logger.warning(
                    f"Approaching rate limit for {operation_type} API. "
                    f"Remaining: {rate_limit.remaining}/{rate_limit.limit}"
                )

        # Calculate and apply adaptive delay
        delay = self._calculate_adaptive_delay(rate_limit)

        # Ensure minimum time between requests
        time_since_last = time.time() - self._last_request_time
        if time_since_last < delay:
            actual_delay = delay - time_since_last
            if actual_delay > 0.01:  # Only log significant delays
                self.logger.debug(f"Rate limiting delay: {actual_delay:.2f}s")
            time.sleep(actual_delay)

        self._last_request_time = time.time()

    def get_rate_limit_status(self) -> dict[str, Any]:
        """Get current rate limit status for monitoring."""
        if self._should_update_rate_limit():
            self._update_rate_limit_info()

        status = {}

        if self._core_rate_limit:
            status["core"] = {
                "limit": self._core_rate_limit.limit,
                "remaining": self._core_rate_limit.remaining,
                "used": self._core_rate_limit.used,
                "reset_time": self._core_rate_limit.reset_datetime,
                "seconds_until_reset": self._core_rate_limit.seconds_until_reset,
                "usage_percentage": round(self._core_rate_limit.usage_percentage, 1),
            }

        if self._search_rate_limit:
            status["search"] = {
                "limit": self._search_rate_limit.limit,
                "remaining": self._search_rate_limit.remaining,
                "used": self._search_rate_limit.used,
                "reset_time": self._search_rate_limit.reset_datetime,
                "seconds_until_reset": self._search_rate_limit.seconds_until_reset,
                "usage_percentage": round(self._search_rate_limit.usage_percentage, 1),
            }

        return status

    def is_rate_limited(self, operation_type: str = "core") -> bool:
        """Check if we're currently rate limited."""
        if operation_type == "search":
            rate_limit = self._search_rate_limit
        else:
            rate_limit = self._core_rate_limit

        if rate_limit is None:
            return False

        return rate_limit.remaining <= 0

    def get_wait_time(self, operation_type: str = "core") -> int:
        """Get wait time in seconds if rate limited."""
        if not self.is_rate_limited(operation_type):
            return 0

        if operation_type == "search":
            rate_limit = self._search_rate_limit
        else:
            rate_limit = self._core_rate_limit

        if rate_limit is None:
            return 0

        return rate_limit.seconds_until_reset + 1

    def log_rate_limit_status(self) -> None:
        """Log current rate limit status for monitoring."""
        status = self.get_rate_limit_status()

        if "core" in status:
            core = status["core"]
            self.logger.info(
                f"Core API: {core['remaining']}/{core['limit']} remaining "
                f"({core['usage_percentage']}% used), resets in {core['seconds_until_reset']}s"
            )

        if "search" in status:
            search = status["search"]
            self.logger.info(
                f"Search API: {search['remaining']}/{search['limit']} remaining "
                f"({search['usage_percentage']}% used), resets in {search['seconds_until_reset']}s"
            )


class RateLimitedGitHubClient:
    """GitHub client wrapper with automatic rate limiting."""

    def __init__(self, token: str | None = None, buffer_requests: int = 100):
        """
        Initialize rate-limited GitHub client.

        Args:
            token: GitHub access token
            buffer_requests: Number of requests to keep as buffer
        """
        self.github = Github(token)
        self.rate_limiter = GitHubRateLimiter(self.github, buffer_requests)
        self.logger = get_logger()

    def make_api_call(self, func, *args, operation_type: str = "core", **kwargs):
        """
        Make an API call with automatic rate limiting.

        Args:
            func: Function to call
            *args: Arguments for the function
            operation_type: Type of operation for rate limiting
            **kwargs: Keyword arguments for the function
        """
        self.rate_limiter.wait_if_needed(operation_type)
        try:
            result = func(*args, **kwargs)
            return result
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                self.logger.warning("Rate limit hit during API call, updating limits")
                self.rate_limiter._update_rate_limit_info()
                # Wait and retry once
                wait_time = self.rate_limiter.get_wait_time(operation_type)
                if wait_time > 0:
                    self.logger.info(
                        f"Waiting {wait_time} seconds for rate limit reset"
                    )
                    time.sleep(wait_time)
                    return func(*args, **kwargs)
            raise

    def get_repo(self, full_name: str):
        """Get repository with rate limiting."""
        return self.make_api_call(self.github.get_repo, full_name)

    def get_rate_limit_status(self) -> dict[str, Any]:
        """Get rate limit status."""
        return self.rate_limiter.get_rate_limit_status()

    def log_rate_limit_status(self) -> None:
        """Log rate limit status."""
        self.rate_limiter.log_rate_limit_status()
