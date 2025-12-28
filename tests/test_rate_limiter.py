"""Tests for rate limiting system."""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from gh_folder_download.rate_limiter import (
    GitHubRateLimiter,
    RateLimitedGitHubClient,
    RateLimitInfo,
)


@pytest.fixture
def rate_limit_info():
    """Sample RateLimitInfo for testing."""
    return RateLimitInfo(
        limit=5000,
        remaining=4500,
        reset_time=int(time.time()) + 3600,
        used=500,
    )


@pytest.fixture
def mock_github_client():
    """Mock GitHub client with rate limit info."""
    client = MagicMock()

    # Create mock rate limit response
    rate_limit = MagicMock()

    # Core rate limit
    rate_limit.core.limit = 5000
    rate_limit.core.remaining = 4500
    rate_limit.core.reset.timestamp.return_value = time.time() + 3600

    # Search rate limit
    rate_limit.search.limit = 30
    rate_limit.search.remaining = 25
    rate_limit.search.reset.timestamp.return_value = time.time() + 60

    client.get_rate_limit.return_value = rate_limit

    return client


class TestRateLimitInfo:
    """Tests for RateLimitInfo dataclass."""

    def test_reset_datetime_format(self, rate_limit_info):
        """Test reset_datetime returns formatted string."""
        result = rate_limit_info.reset_datetime

        assert isinstance(result, str)
        # Should contain date-like format
        assert "-" in result and ":" in result

    def test_seconds_until_reset_positive(self, rate_limit_info):
        """Test seconds_until_reset returns positive value."""
        result = rate_limit_info.seconds_until_reset

        assert result > 0
        assert result <= 3600

    def test_seconds_until_reset_expired(self):
        """Test seconds_until_reset returns 0 for past reset time."""
        info = RateLimitInfo(
            limit=5000,
            remaining=0,
            reset_time=int(time.time()) - 100,  # Past time
            used=5000,
        )

        result = info.seconds_until_reset

        assert result == 0

    def test_usage_percentage_calculation(self, rate_limit_info):
        """Test usage_percentage is calculated correctly."""
        result = rate_limit_info.usage_percentage

        # 500 used / 5000 limit = 10%
        assert result == 10.0

    def test_usage_percentage_zero_limit(self):
        """Test usage_percentage handles zero limit."""
        info = RateLimitInfo(limit=0, remaining=0, reset_time=0, used=0)

        result = info.usage_percentage

        assert result == 0.0


class TestGitHubRateLimiter:
    """Tests for GitHubRateLimiter class."""

    def test_initialization(self, mock_github_client):
        """Test rate limiter initializes correctly."""
        limiter = GitHubRateLimiter(mock_github_client)

        assert limiter.github == mock_github_client
        assert limiter.buffer_requests == 100

    def test_custom_buffer_requests(self, mock_github_client):
        """Test custom buffer requests value."""
        limiter = GitHubRateLimiter(mock_github_client, buffer_requests=200)

        assert limiter.buffer_requests == 200

    def test_get_rate_limit_status(self, mock_github_client):
        """Test get_rate_limit_status returns status dict."""
        limiter = GitHubRateLimiter(mock_github_client)

        status = limiter.get_rate_limit_status()

        assert "core" in status
        assert "search" in status
        assert status["core"]["limit"] == 5000
        assert status["core"]["remaining"] == 4500

    def test_is_rate_limited_false(self, mock_github_client):
        """Test is_rate_limited returns False when requests remaining."""
        limiter = GitHubRateLimiter(mock_github_client)

        result = limiter.is_rate_limited("core")

        assert result is False

    def test_is_rate_limited_true(self, mock_github_client):
        """Test is_rate_limited returns True when no requests remaining."""
        # Modify mock to show no remaining requests
        mock_github_client.get_rate_limit.return_value.core.remaining = 0

        limiter = GitHubRateLimiter(mock_github_client)
        # Force update
        limiter._update_rate_limit_info()

        result = limiter.is_rate_limited("core")

        assert result is True

    def test_get_wait_time_not_limited(self, mock_github_client):
        """Test get_wait_time returns 0 when not rate limited."""
        limiter = GitHubRateLimiter(mock_github_client)

        result = limiter.get_wait_time("core")

        assert result == 0

    def test_get_wait_time_limited(self, mock_github_client):
        """Test get_wait_time returns positive value when rate limited."""
        # Modify mock to show no remaining requests
        mock_github_client.get_rate_limit.return_value.core.remaining = 0

        limiter = GitHubRateLimiter(mock_github_client)
        limiter._update_rate_limit_info()

        result = limiter.get_wait_time("core")

        assert result > 0


class TestCalculateAdaptiveDelay:
    """Tests for adaptive delay calculation."""

    def test_low_usage_minimal_delay(self, mock_github_client):
        """Test minimal delay when usage is low."""
        limiter = GitHubRateLimiter(mock_github_client)

        # Create low usage rate limit info
        rate_limit = RateLimitInfo(
            limit=5000,
            remaining=4000,
            reset_time=int(time.time()) + 3600,
            used=1000,
        )

        delay = limiter._calculate_adaptive_delay(rate_limit)

        # Should be relatively small
        assert delay <= 5.0

    def test_high_usage_longer_delay(self, mock_github_client):
        """Test longer delay when usage is high."""
        limiter = GitHubRateLimiter(mock_github_client)

        # Create high usage rate limit info
        rate_limit = RateLimitInfo(
            limit=5000,
            remaining=500,
            reset_time=int(time.time()) + 3600,
            used=4500,
        )

        delay = limiter._calculate_adaptive_delay(rate_limit)

        # Should be longer than base delay
        assert delay > limiter._base_delay

    def test_no_remaining_requests_waits_for_reset(self, mock_github_client):
        """Test delay equals reset time when no requests remaining."""
        limiter = GitHubRateLimiter(mock_github_client)

        rate_limit = RateLimitInfo(
            limit=5000,
            remaining=0,
            reset_time=int(time.time()) + 60,
            used=5000,
        )

        delay = limiter._calculate_adaptive_delay(rate_limit)

        # Should wait until reset plus buffer
        assert delay >= 60


class TestRateLimitedGitHubClient:
    """Tests for RateLimitedGitHubClient wrapper."""

    @patch("gh_folder_download.rate_limiter.Github")
    def test_initialization(self, mock_github_class):
        """Test client initializes correctly."""
        client = RateLimitedGitHubClient(token="test_token")

        mock_github_class.assert_called_once_with("test_token")
        assert client.rate_limiter is not None

    @patch("gh_folder_download.rate_limiter.Github")
    def test_make_api_call_success(self, mock_github_class):
        """Test make_api_call executes function."""
        # Setup mock
        mock_github_instance = MagicMock()
        mock_rate_limit = MagicMock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4500
        mock_rate_limit.core.reset.timestamp.return_value = time.time() + 3600
        mock_rate_limit.search.limit = 30
        mock_rate_limit.search.remaining = 25
        mock_rate_limit.search.reset.timestamp.return_value = time.time() + 60
        mock_github_instance.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github_instance

        client = RateLimitedGitHubClient(token="test_token")
        mock_func = Mock(return_value="result")

        result = client.make_api_call(mock_func, "arg1", kwarg1="value1")

        assert result == "result"
        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    @patch("gh_folder_download.rate_limiter.Github")
    def test_get_rate_limit_status(self, mock_github_class):
        """Test get_rate_limit_status delegates to rate_limiter."""
        mock_github_instance = MagicMock()
        mock_rate_limit = MagicMock()
        mock_rate_limit.core.limit = 5000
        mock_rate_limit.core.remaining = 4500
        mock_rate_limit.core.reset.timestamp.return_value = time.time() + 3600
        mock_rate_limit.search.limit = 30
        mock_rate_limit.search.remaining = 25
        mock_rate_limit.search.reset.timestamp.return_value = time.time() + 60
        mock_github_instance.get_rate_limit.return_value = mock_rate_limit
        mock_github_class.return_value = mock_github_instance

        client = RateLimitedGitHubClient(token="test_token")

        status = client.get_rate_limit_status()

        assert "core" in status
