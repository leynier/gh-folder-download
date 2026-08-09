"""Tests for the Rich-backed application logger."""

import logging
from pathlib import Path

import pytest

from gh_folder_download import logger as logger_module
from gh_folder_download.logger import GHFolderLogger, get_logger, setup_logger


@pytest.fixture(autouse=True)
def reset_global_logger():
    """Keep the module-level logger isolated between tests."""
    logger_module._logger = None
    yield
    logger_module._logger = None


def test_logger_writes_all_message_types_to_file(tmp_path: Path):
    log_file = tmp_path / "nested" / "download.log"
    logger = GHFolderLogger(level="debug", log_file=log_file, use_colors=False)

    logger.info("information")
    logger.success("finished")
    logger.warning("warning")
    logger.error("error")
    logger.debug("debug")
    logger.progress_info("working")
    logger.download_start("src/file.txt", 2048)
    logger.download_start("src/unknown.txt")
    logger.download_complete("src/file.txt")
    logger.download_error("src/broken.txt", "network")
    logger.repository_info("owner", "repo", "main", "src")
    logger.repository_info("owner", "repo", "main", "")
    logger.summary(2, 2048, 2)
    logger.summary(0, 0, 0)

    for handler in logger.logger.handlers:
        handler.flush()

    contents = log_file.read_text()
    for expected in (
        "information",
        "SUCCESS: finished",
        "warning",
        "error",
        "debug",
        "PROGRESS: working",
        "DOWNLOAD_START: src/file.txt (2.0 KB)",
        "DOWNLOAD_START: src/unknown.txt",
        "DOWNLOAD_COMPLETE: src/file.txt",
        "Failed to download src/broken.txt: network",
        "REPOSITORY_INFO: owner/repo, branch: main, path: src",
        "REPOSITORY_INFO: owner/repo, branch: main, path: (root)",
        "SUMMARY: 2 files, 2.0 KB, 2.00s, 1.0 KB/s",
        "SUMMARY: 0 files, 0.0 B, 0.00s, N/A",
    ):
        assert expected in contents


def test_quiet_logger_only_emits_errors_to_console(capsys: pytest.CaptureFixture[str]):
    logger = GHFolderLogger(quiet=True, use_colors=False)

    logger.success("hidden")
    logger.progress_info("hidden")
    logger.download_start("hidden")
    logger.download_complete("hidden")
    logger.repository_info("owner", "repo", "main", "")
    logger.summary(1, 1, 1)
    logger.error("visible")

    captured = capsys.readouterr()
    assert "visible" in captured.out
    assert "✅" not in captured.out


@pytest.mark.parametrize(
    ("size", "formatted"),
    [
        (None, "Unknown"),
        (1, "1.0 B"),
        (1024, "1.0 KB"),
        (1024**2, "1.0 MB"),
        (1024**3, "1.0 GB"),
        (1024**4, "1.0 TB"),
    ],
)
def test_format_size(size: int | None, formatted: str):
    assert GHFolderLogger._format_size(size) == formatted


def test_setup_and_get_global_logger(tmp_path: Path):
    implicit = get_logger()
    assert isinstance(implicit, GHFolderLogger)

    configured = setup_logger(
        level="WARNING",
        log_file=tmp_path / "configured.log",
        quiet=True,
        use_colors=False,
    )

    assert get_logger() is configured
    assert configured.quiet is True
    assert configured.logger.handlers[0].level == logging.ERROR
