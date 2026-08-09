import builtins
from unittest.mock import Mock

import pytest
from pydantic import ValidationError as PydanticValidationError

from gh_folder_download import config as config_module
from gh_folder_download.config import (
    ConfigManager,
    ConfigurationError,
    FilterConfig,
    GHFolderDownloadConfig,
)


def test_config_manager_defaults():
    manager = ConfigManager()
    config = manager.config

    # Test defaults
    assert config.download.max_concurrent == 5
    assert config.download.timeout == 30
    assert config.cache.enabled is True
    assert config.paths.default_output == "."


def test_config_load_from_env(monkeypatch):
    monkeypatch.setenv("GH_FOLDER_DOWNLOAD_MAX_CONCURRENT", "10")
    monkeypatch.setenv("GH_FOLDER_DOWNLOAD_CACHE_ENABLED", "false")

    manager = ConfigManager()
    config = manager.load_config()

    assert config.download.max_concurrent == 10
    assert config.cache.enabled is False


def test_environment_override_preserves_file_siblings(monkeypatch, tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("download:\n  timeout: 90\n  max_concurrent: 3\n")
    monkeypatch.setenv("GH_FOLDER_DOWNLOAD_MAX_CONCURRENT", "10")

    config = ConfigManager().load_config(config_file)

    assert config.download.max_concurrent == 10
    assert config.download.timeout == 90


def test_invalid_configuration_fails_instead_of_resetting(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("download:\n  timeout: not-a-number\n")

    with pytest.raises(ConfigurationError):
        ConfigManager().load_config(config_file)


def test_unknown_configuration_key_fails(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("download:\n  timout: 30\n")

    with pytest.raises(ConfigurationError):
        ConfigManager().load_config(config_file)


def test_configuration_root_must_be_mapping(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("- download\n- cache\n")

    with pytest.raises(ConfigurationError):
        ConfigManager().load_config(config_file)


def test_filter_extensions_accept_single_string_and_normalize_lists():
    assert FilterConfig(include_extensions="py").include_extensions == [".py"]  # type: ignore[arg-type]
    assert FilterConfig(exclude_extensions=[".log", "tmp"]).exclude_extensions == [".log", ".tmp"]


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "   ",
        "ghp_" + "a" * 20,
        "gho_" + "a" * 20,
        "github_pat_" + "a" * 50,
        "a" * 40,
    ],
)
def test_config_token_formats(token):
    expected = None if token == "   " else token
    assert GHFolderDownloadConfig(github_token=token).github_token == expected


@pytest.mark.parametrize("token", [123, "short", "z" * 40])
def test_config_rejects_invalid_token(token):
    with pytest.raises(PydanticValidationError):
        GHFolderDownloadConfig(github_token=token)


def test_get_config_paths_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    paths = ConfigManager().get_config_paths()
    assert paths[1] == tmp_path / "gh-folder-download" / "gh-folder-download.yaml"


def test_loads_first_existing_default_config(monkeypatch, tmp_path):
    missing = tmp_path / "missing.yaml"
    existing = tmp_path / "config.yaml"
    existing.write_text("download:\n  timeout: 45\n")
    manager = ConfigManager()
    monkeypatch.setattr(manager, "get_config_paths", lambda: [missing, existing])

    config = manager.load_config()

    assert config.download.timeout == 45
    assert manager.config_file_path == existing


def test_load_resets_previous_config_path(tmp_path, monkeypatch):
    file = tmp_path / "config.yaml"
    file.write_text("{}")
    manager = ConfigManager()
    manager.load_config(file)
    monkeypatch.setattr(manager, "get_config_paths", lambda: [])
    manager.load_config()
    assert manager.config_file_path is None


def test_deprecated_config_options_warn(tmp_path):
    file = tmp_path / "config.yaml"
    file.write_text(
        "rate_limit:\n  aggressive_mode: true\npaths:\n  create_subdirs: false\n  preserve_structure: false\n"
    )
    manager = ConfigManager()
    manager.logger = Mock()

    manager.load_config(file)

    assert manager.logger.warning.call_count == 2


def test_empty_yaml_loads_defaults(tmp_path):
    file = tmp_path / "empty.yaml"
    file.write_text("")
    assert ConfigManager().load_config(file) == GHFolderDownloadConfig()


def test_invalid_yaml_and_read_error_are_wrapped(tmp_path, monkeypatch):
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("download: [")
    with pytest.raises(ConfigurationError, match="Failed to load"):
        ConfigManager().load_config(invalid)

    monkeypatch.setattr(builtins, "open", Mock(side_effect=OSError("denied")))
    with pytest.raises(ConfigurationError, match="Failed to load"):
        ConfigManager().load_config(tmp_path / "config.yaml")


def test_all_environment_mappings(monkeypatch):
    values = {
        "GITHUB_TOKEN": "ghp_" + "a" * 20,
        "MAX_CONCURRENT": "4",
        "TIMEOUT": "60",
        "CHUNK_SIZE": "4096",
        "MAX_RETRIES": "2",
        "RETRY_DELAY": "1.5",
        "VERIFY_INTEGRITY": "false",
        "PARALLEL_DOWNLOADS": "no",
        "CACHE_ENABLED": "0",
        "CACHE_SIZE_GB": "2.5",
        "CACHE_MAX_AGE_DAYS": "10",
        "CACHE_AUTO_CLEANUP": "off",
        "RATE_LIMIT_ENABLED": "false",
        "RATE_LIMIT_BUFFER": "50",
        "DEFAULT_OUTPUT": "downloads",
        "SHOW_PROGRESS": "false",
        "VERBOSITY": "WARNING",
        "USE_COLORS": "false",
        "QUIET": "true",
    }
    for key, value in values.items():
        monkeypatch.setenv(f"GH_FOLDER_DOWNLOAD_{key}", value)

    config = ConfigManager().load_config()

    assert config.download.chunk_size == 4096
    assert config.download.retry_delay == 1.5
    assert config.cache.auto_cleanup is False
    assert config.rate_limit.buffer == 50
    assert config.paths.default_output == "downloads"
    assert config.ui.verbosity == "WARNING"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", ""),
        ("YES", True),
        ("ON", True),
        ("NO", False),
        ("OFF", False),
        ("12", 12),
        ("1.25", 1.25),
        ("nan", "nan"),
        ("inf", "inf"),
        ("text", "text"),
    ],
)
def test_convert_environment_values(value, expected):
    assert ConfigManager()._convert_env_value(value) == expected


def test_set_nested_value_reuses_existing_section():
    data = {"download": {"timeout": 30}}
    ConfigManager()._set_nested_value(data, "download.max_concurrent", 2)
    assert data == {"download": {"timeout": 30, "max_concurrent": 2}}


def test_save_config_explicit_and_default_paths(tmp_path, monkeypatch):
    manager = ConfigManager()
    explicit = tmp_path / "nested" / "config.yaml"
    assert manager.save_config(explicit) is True
    assert explicit.exists()

    monkeypatch.chdir(tmp_path)
    assert manager.save_config() is True
    assert (tmp_path / manager.CONFIG_FILENAME).exists()


def test_save_config_failure(tmp_path, monkeypatch):
    manager = ConfigManager()
    monkeypatch.setattr(builtins, "open", Mock(side_effect=OSError("denied")))
    assert manager.save_config(tmp_path / "config.yaml") is False


def test_create_sample_config_explicit_and_default(tmp_path, monkeypatch):
    manager = ConfigManager()
    explicit = tmp_path / "sample.yaml"
    assert manager.create_sample_config(explicit) is True
    assert "Download settings" in explicit.read_text()

    monkeypatch.chdir(tmp_path)
    assert manager.create_sample_config() is True
    assert (tmp_path / "gh-folder-download.sample.yaml").exists()


def test_create_sample_config_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(builtins, "open", Mock(side_effect=OSError("denied")))
    assert ConfigManager().create_sample_config(tmp_path / "sample.yaml") is False


def test_effective_config_and_custom_validation_warnings():
    manager = ConfigManager()
    assert manager.get_effective_config()["download"]["max_concurrent"] == 5

    object.__setattr__(manager.config.download, "max_concurrent", 21)
    object.__setattr__(manager.config.cache, "max_size_gb", 51)
    issues = manager.validate_config()

    assert len(issues) == 3
    assert any("validation failed" in issue for issue in issues)
    assert any("max_concurrent" in issue for issue in issues)
    assert any("50GB" in issue for issue in issues)


def test_module_level_config_helpers(monkeypatch, tmp_path):
    manager = Mock()
    manager.config = GHFolderDownloadConfig()
    manager.load_config.return_value = manager.config
    manager.save_config.return_value = True
    manager.create_sample_config.return_value = True
    monkeypatch.setattr(config_module, "config_manager", manager)
    path = tmp_path / "config.yaml"

    assert config_module.get_config() is manager.config
    assert config_module.load_config(path) is manager.config
    assert config_module.save_config(path) is True
    assert config_module.create_sample_config(path) is True
