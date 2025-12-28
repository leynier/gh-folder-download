import pytest


@pytest.fixture
def mock_config_data():
    return {
        "github_token": "test_token",
        "download": {
            "max_concurrent": 3,
            "timeout": 10,
        },
        "ui": {
            "show_progress": False,
        },
    }
