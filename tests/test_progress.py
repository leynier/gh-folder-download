"""Tests for rich and simple download progress tracking."""

from io import StringIO
from unittest.mock import Mock

import pytest
from rich.console import Console

from gh_folder_download import progress as progress_module
from gh_folder_download.progress import DownloadStats, ProgressTracker, SimpleProgressTracker


@pytest.mark.parametrize(
    ("size", "formatted"),
    [
        (1, "1.0 B"),
        (1024, "1.0 KB"),
        (1024**2, "1.0 MB"),
        (1024**3, "1.0 GB"),
        (1024**4, "1.0 TB"),
    ],
)
def test_download_stats_format_bytes(size: int, formatted: str):
    assert DownloadStats().format_bytes(size) == formatted


@pytest.mark.parametrize(
    ("bytes_per_second", "formatted"),
    [
        (1, "1.0 B/s"),
        (1024, "1.0 KB/s"),
        (1024**2, "1.0 MB/s"),
        (1024**3, "1.0 GB/s"),
        (1024**4, "1.0 TB/s"),
    ],
)
def test_download_stats_format_speed(
    monkeypatch: pytest.MonkeyPatch,
    bytes_per_second: int,
    formatted: str,
):
    monkeypatch.setattr(progress_module.time, "time", lambda: 1.0)
    stats = DownloadStats(downloaded_bytes=bytes_per_second, start_time=0.0)
    assert stats.format_speed() == formatted


@pytest.mark.parametrize(
    ("eta", "formatted"),
    [(30, "30s"), (90, "1m 30s"), (3660, "1h 1m")],
)
def test_download_stats_format_eta(monkeypatch: pytest.MonkeyPatch, eta: int, formatted: str):
    monkeypatch.setattr(progress_module.time, "time", lambda: 1.0)
    stats = DownloadStats(total_bytes=eta + 1, downloaded_bytes=1, start_time=0.0)
    assert stats.format_eta() == formatted


def test_download_stats_empty_and_zero_elapsed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(progress_module.time, "time", lambda: 5.0)
    empty = DownloadStats(start_time=5.0)

    assert empty.completion_percentage == 0
    assert empty.download_speed_bps == 0
    assert empty.download_speed_mbps == 0
    assert empty.eta_seconds is None
    assert empty.format_eta() == "calculating..."


def test_download_stats_computed_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(progress_module.time, "time", lambda: 12.0)
    stats = DownloadStats(
        total_files=4,
        completed_files=2,
        total_bytes=400,
        downloaded_bytes=200,
        start_time=2.0,
    )

    assert stats.completion_percentage == 50
    assert stats.elapsed_time == 10
    assert stats.download_speed_bps == 20
    assert stats.download_speed_mbps == 20 / (1024 * 1024)
    assert stats.eta_seconds == 10


def test_progress_tracker_full_session(monkeypatch: pytest.MonkeyPatch):
    now = 100.0
    monkeypatch.setattr(progress_module.time, "time", lambda: now)
    output = StringIO()
    tracker = ProgressTracker(Console(file=output, force_terminal=False, width=120))

    tracker.start_session(total_files=3, total_bytes=300)
    long_path = "folder/" + "a" * 60 + ".txt"
    tracker.add_file_task(long_path, 100)
    tracker.update_file_progress(long_path, 40)
    tracker.update_file_progress(long_path, 30)
    tracker.complete_file(long_path, success=True)

    cached = "folder/cached.txt"
    tracker.add_file_task(cached, 100)
    tracker.complete_file(cached, success=True, from_cache=True)

    failed = "folder/failed.txt"
    tracker.add_file_task(failed, 100)
    tracker.update_file_progress(failed, 25)
    tracker.complete_file(failed, success=False)

    tracker.update_file_progress("missing", 10)
    tracker.finish_session()
    stats = tracker.get_stats()

    assert stats["completed_files"] == 3
    assert stats["failed_files"] == 1
    assert stats["cached_files"] == 1
    assert stats["downloaded_bytes"] == 200
    assert stats["completion_percentage"] == 100
    rendered = output.getvalue()
    assert "Download Information" in rendered
    assert "Download Complete" in rendered


def test_progress_tracker_handles_missing_rich_task(monkeypatch: pytest.MonkeyPatch):
    tracker = ProgressTracker(Console(file=StringIO(), force_terminal=False))
    tracker.start_session(1, 10)
    task_id = tracker.add_file_task("gone.txt", 10)
    tracker.progress.remove_task(task_id)

    tracker.complete_file("gone.txt", success=True)

    assert tracker.stats.completed_files == 1
    tracker.finish_session()


def test_progress_tracker_quiet_paths():
    tracker = ProgressTracker(quiet=True)

    tracker.start_session(0, 0)
    assert int(tracker.add_file_task("quiet.txt", 10)) == 0
    tracker.update_file_progress("quiet.txt", 5)
    tracker.complete_file("quiet.txt", success=True)
    tracker.finish_session()
    summary = tracker._create_final_summary()

    assert tracker.overall_task is None
    assert tracker.stats.completed_files == 1
    assert summary.row_count >= 7


def test_progress_tracker_overall_update_without_task():
    tracker = ProgressTracker(quiet=False)
    tracker._update_overall_progress()
    assert tracker.overall_task is None


def test_simple_progress_tracker(monkeypatch: pytest.MonkeyPatch):
    logger = Mock()
    monkeypatch.setattr(progress_module, "get_logger", lambda: logger)
    monkeypatch.setattr(progress_module.time, "time", lambda: 10.0)
    tracker = SimpleProgressTracker()

    tracker.start_session(10, 1000)
    assert int(tracker.add_file_task("one", 100)) == 0
    tracker.update_file_progress("one", 80)
    tracker.complete_file("one", success=True)

    for index in range(2, 5):
        name = str(index)
        tracker.add_file_task(name, 100)
        tracker.update_file_progress(name, 100)
        tracker.complete_file(name, success=index != 4)

    tracker.add_file_task("five", 100)
    tracker.complete_file("five", success=True, from_cache=True)

    for index in range(6, 11):
        tracker.complete_file(str(index), success=True)

    tracker.finish_session()
    stats = tracker.get_stats()

    assert stats["completed_files"] == 10
    assert stats["failed_files"] == 1
    assert stats["cached_files"] == 1
    assert stats["downloaded_bytes"] == 380
    assert logger.info.call_count >= 4
