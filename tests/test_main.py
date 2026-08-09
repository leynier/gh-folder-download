import runpy
from unittest.mock import MagicMock, Mock

import pytest
from typer.testing import CliRunner

from gh_folder_download import main
from gh_folder_download.config import ConfigurationError, FilterConfig
from gh_folder_download.core import DownloadOperationError
from gh_folder_download.validation import ValidationError

runner = CliRunner()


class FakeCache:
    def __init__(self, **kwargs):
        pass

    def clear_cache(self):
        pass

    def get_cache_stats(self):
        return {"total_entries": 0, "total_size_mb": 0}


class FakeGitHubClient:
    def __init__(self, token, buffer):
        self.repository = MagicMock(name="repository")
        self.repository.name = "repo"
        self.repository.full_name = "user/repo"

    def get_repo(self, full_name):
        return self.repository


def _patch_remote(monkeypatch, download_impl):
    monkeypatch.setattr(main, "DownloadCache", FakeCache)
    monkeypatch.setattr(main, "RateLimitedGitHubClient", FakeGitHubClient)
    monkeypatch.setattr(main, "_resolve_ref_path", lambda *args, **kwargs: ("main", "sha", ""))
    monkeypatch.setattr(main, "download_folder_parallel", download_impl)


def test_cli_uses_config_and_cli_precedence(monkeypatch, tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("download:\n  max_concurrent: 7\nui:\n  show_progress: false\n")
    captured = {}

    def download(**kwargs):
        captured.update(kwargs)
        return {
            "total_files": 1,
            "total_size": 4,
            "filtered_files": 0,
            "cached_files": 0,
            "destination": str(tmp_path / "repo"),
        }

    _patch_remote(monkeypatch, download)
    result = runner.invoke(
        main.app,
        [
            "--url",
            "https://github.com/user/repo",
            "--output",
            str(tmp_path / "output"),
            "--config-file",
            str(config_file),
            "--max-concurrent",
            "9",
            "--quiet",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["max_concurrent"] == 9
    assert captured["show_progress"] is False


def test_cli_returns_one_for_operational_failure(monkeypatch, tmp_path):
    def download(**kwargs):
        raise DownloadOperationError("destination exists")

    _patch_remote(monkeypatch, download)
    result = runner.invoke(
        main.app,
        ["--url", "https://github.com/user/repo", "--output", str(tmp_path), "--quiet"],
    )

    assert result.exit_code == 1
    assert "destination exists" in result.output


def test_cli_returns_two_for_invalid_url(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DownloadCache", FakeCache)
    result = runner.invoke(main.app, ["--url", "https://example.com/user/repo", "--output", str(tmp_path)])

    assert result.exit_code == 2
    assert "must start with" in result.output


def test_create_config_success_and_failure(monkeypatch):
    monkeypatch.setattr(main, "create_sample_config", Mock(return_value=True))
    assert runner.invoke(main.app, ["--create-config"]).exit_code == 0

    monkeypatch.setattr(main, "create_sample_config", Mock(return_value=False))
    assert runner.invoke(main.app, ["--create-config"]).exit_code == 1


def test_configuration_error_has_usage_exit_code(monkeypatch):
    monkeypatch.setattr(main, "load_config", Mock(side_effect=ConfigurationError("bad config")))
    result = runner.invoke(main.app, ["--url", "https://github.com/user/repo"])
    assert result.exit_code == 2
    assert "bad config" in result.output


def test_invalid_log_path_has_usage_exit_code(monkeypatch):
    validator = Mock()
    validator.validate_log_file_path.side_effect = ValidationError("bad log")
    monkeypatch.setattr(main, "InputValidator", Mock(return_value=validator))
    result = runner.invoke(main.app, ["--url", "https://github.com/user/repo"])
    assert result.exit_code == 2
    assert "bad log" in result.output


def test_cache_actions_can_run_without_url(monkeypatch):
    cache = Mock()
    cache.get_cache_stats.return_value = {"total_entries": 2, "total_size_mb": 3.5}
    logger = Mock()
    monkeypatch.setattr(main, "DownloadCache", Mock(return_value=cache))
    monkeypatch.setattr(main, "setup_logger", Mock(return_value=logger))

    result = runner.invoke(main.app, ["--clear-cache", "--cache-stats"])

    assert result.exit_code == 0
    cache.clear_cache.assert_called_once()
    logger.info.assert_called_once_with("Cache: 2 entries, 3.5 MB")


def test_missing_url_is_usage_error(monkeypatch):
    logger = Mock()
    monkeypatch.setattr(main, "setup_logger", Mock(return_value=logger))
    result = runner.invoke(main.app, [])
    assert result.exit_code == 2
    logger.error.assert_called_once_with("Repository URL is required")


def test_success_logs_filter_and_cache_counts(monkeypatch, tmp_path):
    logger = Mock()
    monkeypatch.setattr(main, "setup_logger", Mock(return_value=logger))

    def download(**_kwargs):
        return {
            "total_files": 3,
            "total_size": 10,
            "filtered_files": 2,
            "cached_files": 1,
            "destination": str(tmp_path / "repo"),
        }

    _patch_remote(monkeypatch, download)
    result = runner.invoke(
        main.app,
        [
            "--url",
            "https://github.com/user/repo",
            "--output",
            str(tmp_path),
            "--no-parallel-downloads",
            "--no-use-cache",
            "--no-verify-integrity",
            "--no-show-progress",
            "--rate-limit-buffer",
            "50",
            "--include-extensions",
            "py",
            "--exclude-extensions",
            "log",
            "--include-patterns",
            "src/**",
            "--exclude-patterns",
            "tests/**",
            "--min-size",
            "1KB",
            "--max-size",
            "1MB",
            "--exclude-binary",
            "--exclude-large-files",
            "--respect-gitignore",
            "--verbose",
        ],
    )

    assert result.exit_code == 0, result.output
    assert logger.info.call_count == 2
    logger.success.assert_called_once()


def test_disabled_rate_limiting_uses_plain_github(monkeypatch, tmp_path):
    repository = MagicMock(name="repository")
    repository.name = "repo"
    repository.full_name = "user/repo"
    github = Mock()
    github.get_repo.return_value = repository
    github_class = Mock(return_value=github)
    captured = {}

    def download(**kwargs):
        captured.update(kwargs)
        return {
            "total_files": 0,
            "total_size": 0,
            "filtered_files": 0,
            "cached_files": 0,
            "destination": str(tmp_path / "repo"),
        }

    monkeypatch.setattr(main, "Github", github_class)
    monkeypatch.setattr(main, "_resolve_ref_path", lambda *args, **kwargs: ("main", "sha", ""))
    monkeypatch.setattr(main, "download_folder_parallel", download)
    result = runner.invoke(
        main.app,
        ["--url", "https://github.com/user/repo", "--output", str(tmp_path), "--disable-rate-limiting"],
    )

    assert result.exit_code == 0, result.output
    github_class.assert_called_once_with()
    assert captured["github_client"] is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValidationError("bad input"), "Input/configuration failure"),
        (DownloadOperationError("offline"), "Operational failure"),
        (RuntimeError("boom"), "Unexpected failure"),
    ],
)
def test_verbose_error_paths_log_traceback(monkeypatch, tmp_path, error, expected):
    logger = Mock()
    monkeypatch.setattr(main, "setup_logger", Mock(return_value=logger))
    monkeypatch.setattr(main, "create_file_filter", Mock(side_effect=error))
    result = runner.invoke(
        main.app,
        ["--url", "https://github.com/user/repo", "--output", str(tmp_path), "--verbose"],
    )

    assert result.exit_code in (1, 2)
    assert any(call.args[0] == expected for call in logger.debug.call_args_list)


def test_resolve_ref_path_explicit_ref_and_path():
    repository = Mock()
    retry = Mock()
    retry.retry_api_call.return_value = "sha"

    assert main._resolve_ref_path(
        repository,
        ("feature", "topic", "src"),
        explicit_ref="feature/topic",
        explicit_path=None,
        retry_handler=retry,
    ) == ("feature/topic", "sha", "src")
    assert main._resolve_ref_path(
        repository,
        ("main", "src"),
        explicit_ref="release",
        explicit_path="docs",
        retry_handler=retry,
    ) == ("release", "sha", "docs")


def test_resolve_ref_path_inferred_ref(monkeypatch):
    monkeypatch.setattr(main, "resolve_ref_and_path", lambda _repo, _segments: ("main", "sha", "src"))
    assert main._resolve_ref_path(
        Mock(), ("main", "src"), explicit_ref=None, explicit_path="docs", retry_handler=Mock()
    ) == ("main", "sha", "docs")


def test_resolve_filter_config_preset_and_overrides(monkeypatch):
    preset = FilterConfig(include_extensions=[".md"], exclude_binary=True)
    monkeypatch.setattr(main, "get_preset_filter", Mock(return_value=preset))
    result = main._resolve_filter_config(
        FilterConfig(),
        filter_preset="docs",
        include_extensions=["py"],
        exclude_extensions=None,
        include_patterns=None,
        exclude_patterns=None,
        min_size="1KB",
        max_size="2MB",
        exclude_binary=None,
        exclude_large_files=True,
        respect_gitignore=None,
    )
    assert result.include_extensions == [".py"]
    assert result.min_size_bytes == 1024
    assert result.max_size_bytes == 2 * 1024**2
    assert result.exclude_binary is True


@pytest.mark.parametrize(
    ("field", "message"),
    [("min_size", "Invalid min-size"), ("max_size", "Invalid max-size")],
)
def test_resolve_filter_config_rejects_invalid_sizes(field, message):
    kwargs = {"min_size": None, "max_size": None}
    kwargs[field] = "invalid"
    with pytest.raises(ValidationError, match=message):
        main._resolve_filter_config(
            FilterConfig(),
            filter_preset=None,
            include_extensions=None,
            exclude_extensions=None,
            include_patterns=None,
            exclude_patterns=None,
            exclude_binary=None,
            exclude_large_files=None,
            respect_gitignore=None,
            **kwargs,
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12", 12),
        ("1 B", 1),
        ("1.5kb", 1536),
        ("2MB", 2 * 1024**2),
        ("1GB", 1024**3),
        ("1TB", 1024**4),
        ("invalid", None),
    ],
)
def test_parse_size_string(value, expected):
    assert main._parse_size_string(value) == expected


def test_module_entrypoint_invokes_app(monkeypatch):
    app = Mock()
    monkeypatch.setattr(main, "app", app)
    runpy.run_module("gh_folder_download.__main__", run_name="__main__")
    app.assert_called_once_with(prog_name="gh-folder-download")
