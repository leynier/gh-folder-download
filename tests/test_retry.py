"""Tests for retry mechanism with exponential backoff."""

from unittest.mock import Mock

import pytest

from gh_folder_download.retry import (
    APIRetryHandler,
    DownloadRetryHandler,
    RetryConfig,
    RetryError,
    RetryHandler,
    with_retry,
)


@pytest.fixture
def default_config():
    """Default retry configuration."""
    return RetryConfig()


@pytest.fixture
def fast_config():
    """Fast retry configuration for tests."""
    return RetryConfig(
        max_attempts=3,
        base_delay=0.01,
        max_delay=0.1,
        backoff_factor=2.0,
        jitter=False,
    )


@pytest.fixture
def handler(fast_config):
    """RetryHandler with fast config."""
    return RetryHandler(fast_config)


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_default_values(self, default_config):
        """Test default configuration values."""
        assert default_config.max_attempts == 3
        assert default_config.base_delay == 1.0
        assert default_config.max_delay == 60.0
        assert default_config.backoff_factor == 2.0
        assert default_config.jitter is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=0.5,
            max_delay=30.0,
            backoff_factor=3.0,
            jitter=False,
        )
        assert config.max_attempts == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 30.0
        assert config.backoff_factor == 3.0
        assert config.jitter is False


class TestRetryHandler:
    """Tests for RetryHandler."""

    def test_retry_success_first_attempt(self, handler):
        """Test function succeeds on first try."""
        mock_func = Mock(return_value="success")

        result = handler.retry(mock_func)

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_success_after_failures(self, handler):
        """Test function succeeds after retries."""
        call_count = 0

        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"

        result = handler.retry(failing_then_success)

        assert result == "success"
        assert call_count == 3

    def test_retry_exhausted_raises_error(self, handler):
        """Test raises RetryError after max attempts."""
        mock_func = Mock(side_effect=ConnectionError("Network error"))

        with pytest.raises(RetryError) as exc_info:
            handler.retry(mock_func)

        assert "Failed after" in str(exc_info.value)
        assert mock_func.call_count == 3

    def test_non_retryable_exception_raises_immediately(self, handler):
        """Test non-retryable exception raises immediately."""
        mock_func = Mock(side_effect=ValueError("Invalid input"))

        with pytest.raises(ValueError):
            handler.retry(mock_func)

        assert mock_func.call_count == 1


class TestIsRetryable:
    """Tests for _is_retryable method."""

    def setup_method(self):
        self.handler = RetryHandler()

    def test_connection_error_is_retryable(self):
        """Test ConnectionError is retryable."""
        assert self.handler._is_retryable(ConnectionError("test")) is True

    def test_timeout_error_is_retryable(self):
        """Test TimeoutError is retryable."""
        assert self.handler._is_retryable(TimeoutError("test")) is True

    def test_os_error_is_retryable(self):
        """Test OSError is retryable."""
        assert self.handler._is_retryable(OSError("Network unreachable")) is True

    def test_value_error_not_retryable(self):
        """Test ValueError is not retryable."""
        assert self.handler._is_retryable(ValueError("test")) is False

    def test_key_error_not_retryable(self):
        """Test KeyError is not retryable."""
        assert self.handler._is_retryable(KeyError("test")) is False


class TestCalculateDelay:
    """Tests for _calculate_delay method."""

    def test_exponential_backoff(self):
        """Test delay increases exponentially."""
        config = RetryConfig(base_delay=1.0, backoff_factor=2.0, jitter=False)
        handler = RetryHandler(config)

        delay0 = handler._calculate_delay(0, config)
        delay1 = handler._calculate_delay(1, config)
        delay2 = handler._calculate_delay(2, config)

        assert delay0 == 1.0
        assert delay1 == 2.0
        assert delay2 == 4.0

    def test_max_delay_cap(self):
        """Test delay is capped at max_delay."""
        config = RetryConfig(base_delay=10.0, max_delay=20.0, backoff_factor=3.0, jitter=False)
        handler = RetryHandler(config)

        delay = handler._calculate_delay(5, config)

        assert delay <= config.max_delay


class TestDownloadRetryHandler:
    """Tests for DownloadRetryHandler."""

    def test_default_config(self):
        """Test default configuration for download handler."""
        handler = DownloadRetryHandler()

        # Should have more aggressive retry settings
        assert handler.config.max_attempts == 5
        assert handler.config.base_delay == 2.0

    def test_retry_download_success(self):
        """Test retry_download with successful function."""
        handler = DownloadRetryHandler(RetryConfig(max_attempts=3, base_delay=0.01, jitter=False))
        mock_func = Mock(return_value=b"file content")

        result = handler.retry_download(mock_func, "/path/to/file")

        assert result == b"file content"

    def test_retry_download_failure(self):
        """Test retry_download raises after max attempts."""
        handler = DownloadRetryHandler(RetryConfig(max_attempts=2, base_delay=0.01, jitter=False))
        mock_func = Mock(side_effect=ConnectionError("Network error"))

        with pytest.raises(RetryError):
            handler.retry_download(mock_func, "/path/to/file")


class TestAPIRetryHandler:
    """Tests for APIRetryHandler."""

    def test_default_config(self):
        """Test default configuration for API handler."""
        handler = APIRetryHandler()

        # Should have conservative retry settings
        assert handler.config.max_attempts == 3
        assert handler.config.base_delay == 1.0

    def test_retry_api_call_success(self):
        """Test retry_api_call with successful function."""
        handler = APIRetryHandler(RetryConfig(max_attempts=3, base_delay=0.01, jitter=False))
        mock_func = Mock(return_value={"data": "test"})

        result = handler.retry_api_call(mock_func, "test_operation")

        assert result == {"data": "test"}


class TestWithRetryDecorator:
    """Tests for with_retry decorator."""

    def test_decorator_success(self):
        """Test decorator with successful function."""

        @with_retry(max_attempts=3, base_delay=0.01)
        def success_func():
            return "success"

        result = success_func()

        assert result == "success"

    def test_decorator_retry_then_success(self):
        """Test decorator retries and succeeds."""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("test")
            return "success"

        result = failing_then_success()

        assert result == "success"
        assert call_count == 2
