"""Tests for rate limiting system."""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from github import GithubException

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

    @pytest.mark.parametrize(
        "error",
        [GithubException(500, "server"), RuntimeError("unexpected")],
    )
    def test_update_rate_limit_errors_are_tolerated(self, error):
        client = Mock()
        client.get_rate_limit.side_effect = error

        limiter = GitHubRateLimiter(client)

        assert limiter._core_rate_limit is None

    def test_should_update_for_missing_stale_and_fresh_data(self, mock_github_client, monkeypatch):
        limiter = GitHubRateLimiter(mock_github_client)
        monkeypatch.setattr("gh_folder_download.rate_limiter.time.time", lambda: 100)
        limiter._core_rate_limit = None
        assert limiter._should_update_rate_limit() is True
        limiter._core_rate_limit = RateLimitInfo(1, 1, 200, 0)
        limiter._last_update = 0
        assert limiter._should_update_rate_limit() is True
        limiter._last_update = 90
        assert limiter._should_update_rate_limit() is False

    def test_wait_refreshes_stale_data(self, mock_github_client, monkeypatch):
        limiter = GitHubRateLimiter(mock_github_client)
        update = Mock()
        monkeypatch.setattr(limiter, "_should_update_rate_limit", lambda: True)
        monkeypatch.setattr(limiter, "_update_rate_limit_info", update)

        limiter.wait_if_needed()

        update.assert_called_once()

    def test_status_refreshes_stale_data(self, mock_github_client, monkeypatch):
        limiter = GitHubRateLimiter(mock_github_client)
        update = Mock()
        monkeypatch.setattr(limiter, "_should_update_rate_limit", lambda: True)
        monkeypatch.setattr(limiter, "_update_rate_limit_info", update)

        limiter.get_rate_limit_status()

        update.assert_called_once()

    def test_missing_rate_data_uses_fallback_delay(self, mock_github_client, monkeypatch):
        limiter = GitHubRateLimiter(mock_github_client)
        limiter._core_rate_limit = None
        monkeypatch.setattr(limiter, "_should_update_rate_limit", lambda: False)
        sleep = Mock()
        monkeypatch.setattr("gh_folder_download.rate_limiter.time.sleep", sleep)

        limiter.wait_if_needed()

        sleep.assert_called_once_with(limiter._base_delay)

    def test_waits_until_reset_when_exhausted(self, mock_github_client, monkeypatch):
        limiter = GitHubRateLimiter(mock_github_client)
        limiter._core_rate_limit = RateLimitInfo(100, 0, int(time.time()) + 5, 100)
        monkeypatch.setattr(limiter, "_should_update_rate_limit", lambda: False)
        update = Mock()
        monkeypatch.setattr(limiter, "_update_rate_limit_info", update)
        sleep = Mock()
        monkeypatch.setattr("gh_folder_download.rate_limiter.time.sleep", sleep)

        limiter.wait_if_needed()

        assert sleep.call_args.args[0] > 0
        update.assert_called_once()

    def test_buffer_warning_delay_and_local_accounting(self, mock_github_client, monkeypatch):
        limiter = GitHubRateLimiter(mock_github_client, buffer_requests=100)
        limiter._core_rate_limit = RateLimitInfo(100, 5, int(time.time()) + 100, 95)
        limiter._last_request_time = time.time()
        monkeypatch.setattr(limiter, "_should_update_rate_limit", lambda: False)
        sleep = Mock()
        monkeypatch.setattr("gh_folder_download.rate_limiter.time.sleep", sleep)

        limiter.wait_if_needed()

        assert limiter._core_rate_limit.remaining == 4
        assert limiter._core_rate_limit.used == 96
        sleep.assert_called_once()

    def test_empty_status_and_none_rate_limit_checks(self, mock_github_client, monkeypatch):
        limiter = GitHubRateLimiter(mock_github_client)
        limiter._core_rate_limit = None
        limiter._search_rate_limit = None
        monkeypatch.setattr(limiter, "_should_update_rate_limit", lambda: False)

        assert limiter.get_rate_limit_status() == {}
        assert limiter.is_rate_limited() is False
        monkeypatch.setattr(limiter, "is_rate_limited", lambda _operation: True)
        assert limiter.get_wait_time() == 0

    def test_log_rate_limit_status(self, mock_github_client):
        limiter = GitHubRateLimiter(mock_github_client)
        limiter.logger = Mock()

        limiter.log_rate_limit_status()

        assert limiter.logger.info.call_count == 2


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

    def test_default_buffer_does_not_throttle_every_anonymous_request(self, mock_github_client):
        limiter = GitHubRateLimiter(mock_github_client, buffer_requests=100)
        anonymous_limit = RateLimitInfo(
            limit=60,
            remaining=50,
            reset_time=int(time.time()) + 3600,
            used=10,
        )

        assert limiter._effective_buffer(anonymous_limit) == 3
        assert limiter._calculate_adaptive_delay(anonymous_limit) == 0

    def test_expired_reset_uses_base_delay(self, mock_github_client):
        limiter = GitHubRateLimiter(mock_github_client)
        info = RateLimitInfo(100, 50, int(time.time()) - 1, 50)
        assert limiter._calculate_adaptive_delay(info) == limiter._base_delay

    def test_buffer_zone_caps_delay(self, mock_github_client):
        limiter = GitHubRateLimiter(mock_github_client, buffer_requests=100)
        info = RateLimitInfo(100, 1, int(time.time()) + 1000, 99)
        assert limiter._calculate_adaptive_delay(info) == 60

    def test_medium_usage_applies_factor(self, mock_github_client):
        limiter = GitHubRateLimiter(mock_github_client)
        info = RateLimitInfo(100, 30, int(time.time()) + 100, 70)
        assert limiter._calculate_adaptive_delay(info) > 0


class TestRateLimitedGitHubClient:
    """Tests for RateLimitedGitHubClient wrapper."""

    @patch("gh_folder_download.rate_limiter.Github")
    def test_initialization(self, mock_github_class):
        """Test client initializes correctly."""
        client = RateLimitedGitHubClient(token="test_token")

        mock_github_class.assert_called_once()
        assert mock_github_class.call_args.kwargs["auth"]._token == "test_token"
        assert client.rate_limiter is not None

    @patch("gh_folder_download.rate_limiter.Github")
    def test_anonymous_initialization(self, mock_github_class):
        RateLimitedGitHubClient()
        mock_github_class.assert_called_once_with()

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

    @patch("gh_folder_download.rate_limiter.Github")
    def test_rate_limit_exception_waits_and_retries(self, mock_github_class, monkeypatch):
        mock_github_class.return_value.get_rate_limit.return_value = mock_github_client = MagicMock()
        mock_github_client.core.limit = 1
        mock_github_client.core.remaining = 1
        mock_github_client.core.reset.timestamp.return_value = time.time() + 1
        mock_github_client.search.limit = 1
        mock_github_client.search.remaining = 1
        mock_github_client.search.reset.timestamp.return_value = time.time() + 1
        client = RateLimitedGitHubClient()
        monkeypatch.setattr(client.rate_limiter, "wait_if_needed", Mock())
        monkeypatch.setattr(client.rate_limiter, "_update_rate_limit_info", Mock())
        monkeypatch.setattr(client.rate_limiter, "get_wait_time", Mock(return_value=2))
        monkeypatch.setattr("gh_folder_download.rate_limiter.time.sleep", Mock())
        func = Mock(side_effect=[GithubException(403, "rate limit exceeded"), "ok"])

        assert client.make_api_call(func) == "ok"
        assert func.call_count == 2

    @patch("gh_folder_download.rate_limiter.Github")
    @pytest.mark.parametrize(
        "error",
        [GithubException(403, "rate limit exceeded"), GithubException(404, "missing")],
    )
    def test_api_errors_without_wait_are_raised(self, mock_github_class, error, monkeypatch):
        mock_github_class.return_value.get_rate_limit.side_effect = RuntimeError("no status")
        client = RateLimitedGitHubClient()
        monkeypatch.setattr(client.rate_limiter, "wait_if_needed", Mock())
        monkeypatch.setattr(client.rate_limiter, "get_wait_time", Mock(return_value=0))

        with pytest.raises(GithubException):
            client.make_api_call(Mock(side_effect=error))

    @patch("gh_folder_download.rate_limiter.Github")
    def test_get_repo_and_log_delegate(self, mock_github_class, monkeypatch):
        mock_github_class.return_value.get_rate_limit.side_effect = RuntimeError("no status")
        client = RateLimitedGitHubClient()
        make_api_call = Mock(return_value="repo")
        log_status = Mock()
        monkeypatch.setattr(client, "make_api_call", make_api_call)
        monkeypatch.setattr(client.rate_limiter, "log_rate_limit_status", log_status)

        assert client.get_repo("owner/repo") == "repo"
        log_status.assert_not_called()
        client.log_rate_limit_status()
        log_status.assert_called_once()
