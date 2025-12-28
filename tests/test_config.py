from gh_folder_download.config import ConfigManager


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
