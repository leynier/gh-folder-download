import hashlib
import time
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest

from gh_folder_download import parallel_downloader as downloader_module
from gh_folder_download.integrity import IntegrityError
from gh_folder_download.parallel_downloader import (
    DownloadResult,
    DownloadTask,
    ParallelDownloader,
    run_parallel_downloads,
)


def _git_blob_sha(body: bytes) -> str:
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()


class FakeContent:
    def __init__(self, body: bytes, error: Exception | None = None):
        self.body = body
        self.error = error

    async def iter_chunked(self, chunk_size):
        yield self.body
        if self.error:
            raise self.error


class FakeResponse:
    def __init__(
        self,
        status: int,
        body: bytes = b"",
        error: Exception | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.status = status
        self.reason = "test response"
        self.headers = headers or {}
        self.content = FakeContent(body, error)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def get(self, url):
        self.calls += 1
        return next(self.responses)


def _task(tmp_path: Path, body: bytes, sha: str | None = None) -> DownloadTask:
    return DownloadTask(
        file_path="folder/file.txt",
        download_url="https://example.invalid/file.txt",
        local_path=tmp_path / "file.txt",
        expected_size=len(body),
        sha=sha or _git_blob_sha(body),
        repo_full_name="user/repo",
        ref="main",
    )


@pytest.mark.asyncio
async def test_transient_status_is_retried(monkeypatch, tmp_path):
    body = b"verified content"
    session = FakeSession([FakeResponse(503), FakeResponse(200, body)])
    downloader = ParallelDownloader(
        verify_integrity=True,
        use_cache=False,
        show_progress=False,
        quiet=True,
        max_retries=2,
        retry_delay=0.01,
    )

    async def no_wait(delay):
        pass

    monkeypatch.setattr("gh_folder_download.parallel_downloader.asyncio.sleep", no_wait)
    result = await downloader._download_with_retries(cast(Any, session), _task(tmp_path, body), time.time())

    assert result.success is True
    assert session.calls == 2
    assert (tmp_path / "file.txt").read_bytes() == body


@pytest.mark.asyncio
async def test_partial_file_is_removed_before_retry(monkeypatch, tmp_path):
    body = b"complete"
    session = FakeSession(
        [
            FakeResponse(200, b"partial", aiohttp.ClientConnectionError("disconnected")),
            FakeResponse(200, body),
        ]
    )
    downloader = ParallelDownloader(
        verify_integrity=True,
        use_cache=False,
        show_progress=False,
        quiet=True,
        max_retries=2,
        retry_delay=0.01,
    )

    async def no_wait(delay):
        pass

    monkeypatch.setattr("gh_folder_download.parallel_downloader.asyncio.sleep", no_wait)
    result = await downloader._download_with_retries(cast(Any, session), _task(tmp_path, body), time.time())

    assert result.success is True
    assert (tmp_path / "file.txt").read_bytes() == body
    assert not list(tmp_path.glob("*.part-*"))


@pytest.mark.asyncio
async def test_integrity_failure_is_not_reported_as_success(tmp_path):
    body = b"corrupt"
    session = FakeSession([FakeResponse(200, body)])
    downloader = ParallelDownloader(
        verify_integrity=True,
        use_cache=False,
        show_progress=False,
        quiet=True,
        max_retries=1,
    )
    result = await downloader._download_with_retries(
        cast(Any, session),
        _task(tmp_path, body, sha="0" * 40),
        time.time(),
    )

    assert result.success is False
    assert result.integrity_verified is False
    assert not (tmp_path / "file.txt").exists()
    assert not list(tmp_path.glob("*.part-*"))


def test_progress_tracker_selection(monkeypatch):
    rich_tracker = Mock()
    monkeypatch.setattr(downloader_module, "ProgressTracker", Mock(return_value=rich_tracker))
    downloader = ParallelDownloader(use_cache=False, show_progress=True, quiet=False)
    assert downloader.progress_tracker is rich_tracker


@pytest.mark.asyncio
async def test_download_files_empty():
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False)
    assert await downloader.download_files([]) == []


@pytest.mark.asyncio
async def test_download_files_processes_results_exceptions_and_cache(monkeypatch, tmp_path):
    tasks = [_task(tmp_path / "one", b"one"), _task(tmp_path / "two", b"two")]
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False, show_progress=False)
    downloader.cache = Mock()
    downloader.progress_tracker = Mock()

    async def download(_session, _semaphore, task):
        if task is tasks[1]:
            raise RuntimeError("worker failed")
        return DownloadResult(task, True, bytes_downloaded=3, from_cache=True)

    class ClientSession:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(downloader, "_download_single_file", download)
    monkeypatch.setattr(downloader_module.aiohttp, "ClientSession", ClientSession)

    results = await downloader.download_files(tasks)

    assert [result.success for result in results] == [True, False]
    assert results[1].error == "worker failed"
    downloader.cache.finalize.assert_called_once()
    downloader.progress_tracker.finish_session.assert_called_once()
    assert downloader.get_stats()["success_rate"] == 50


@pytest.mark.asyncio
async def test_download_single_file_cache_hit(tmp_path, monkeypatch):
    task = _task(tmp_path, b"cached")
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False, show_progress=False)
    downloader.cache = Mock()
    downloader.progress_tracker = Mock()
    monkeypatch.setattr(downloader, "_check_cache", lambda _task: True)

    result = await downloader._download_single_file(Mock(), __import__("asyncio").Semaphore(1), task)

    assert result.success is True
    assert result.from_cache is True
    assert result.integrity_verified is True
    downloader.progress_tracker.complete_file.assert_called_once_with(task.file_path, success=True, from_cache=True)


@pytest.mark.asyncio
async def test_download_single_file_network_path(tmp_path, monkeypatch):
    task = _task(tmp_path, b"body")
    expected = DownloadResult(task, True)
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False, show_progress=False)
    downloader.progress_tracker = Mock()
    monkeypatch.setattr(downloader, "_download_with_retries", AsyncMock(return_value=expected))

    result = await downloader._download_single_file(Mock(), __import__("asyncio").Semaphore(1), task)

    assert result is expected
    downloader.progress_tracker.complete_file.assert_called_once_with(task.file_path, success=True)


@pytest.mark.asyncio
async def test_non_retryable_http_status_stops_immediately(tmp_path):
    session = FakeSession([FakeResponse(404)])
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False, max_retries=3)

    result = await downloader._download_with_retries(cast(Any, session), _task(tmp_path, b"body"), time.time())

    assert result.success is False
    assert "HTTP 404" in (result.error or "")
    assert session.calls == 1


@pytest.mark.asyncio
async def test_retry_after_header_is_honored(monkeypatch, tmp_path):
    session = FakeSession([FakeResponse(429, headers={"Retry-After": "2"}), FakeResponse(200, b"body")])
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False, max_retries=2)
    sleep = AsyncMock()
    monkeypatch.setattr(downloader_module.asyncio, "sleep", sleep)

    result = await downloader._download_with_retries(cast(Any, session), _task(tmp_path, b"body"), time.time())

    assert result.success is True
    sleep.assert_awaited_once_with(2.0)


@pytest.mark.asyncio
async def test_integrity_failure_retries(monkeypatch, tmp_path):
    body = b"body"
    session = FakeSession([FakeResponse(200, body), FakeResponse(200, body)])
    downloader = ParallelDownloader(use_cache=False, verify_integrity=True, max_retries=2)
    monkeypatch.setattr(downloader, "_verify_file_integrity", AsyncMock(return_value=False))
    sleep = AsyncMock()
    monkeypatch.setattr(downloader_module.asyncio, "sleep", sleep)

    result = await downloader._download_with_retries(cast(Any, session), _task(tmp_path, body), time.time())

    assert result.success is False
    assert sleep.await_count == 1


@pytest.mark.asyncio
async def test_successful_download_adds_to_cache(monkeypatch, tmp_path):
    body = b"body"
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False)
    downloader.cache = Mock()
    add = AsyncMock()
    monkeypatch.setattr(downloader, "_add_to_cache", add)

    result = await downloader._download_with_retries(
        cast(Any, FakeSession([FakeResponse(200, body)])),
        _task(tmp_path, body),
        time.time(),
    )

    assert result.success is True
    add.assert_awaited_once()


def test_retry_delay_is_capped_and_jittered(monkeypatch):
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False, retry_delay=100)
    monkeypatch.setattr(downloader_module.random, "uniform", lambda _low, _high: 1.0)
    assert downloader._retry_delay(3) == 120


def test_check_cache_with_and_without_cache(tmp_path):
    task = _task(tmp_path, b"body")
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False)
    assert downloader._check_cache(task) is False
    downloader.cache = Mock()
    downloader.cache.is_file_cached.return_value = True
    assert downloader._check_cache(task) is True


@pytest.mark.asyncio
async def test_verify_file_integrity_paths(tmp_path):
    task = _task(tmp_path, b"body")
    task.local_path.write_bytes(b"body")
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False)
    assert await downloader._verify_file_integrity(task) is True

    downloader.integrity_checker = Mock()
    assert await downloader._verify_file_integrity(task) is True
    downloader.integrity_checker.verify_file_size.side_effect = IntegrityError("bad size")
    assert await downloader._verify_file_integrity(task) is False


@pytest.mark.asyncio
async def test_add_to_cache_paths(tmp_path):
    task = _task(tmp_path, b"body")
    task.local_path.write_bytes(b"body")
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False)
    await downloader._add_to_cache(task)

    downloader.cache = Mock()
    downloader.integrity_checker = Mock()
    downloader.integrity_checker.calculate_checksums.return_value = {"sha256": "hash"}
    await downloader._add_to_cache(task)
    downloader.cache.add_file_to_cache.assert_called_once()

    downloader.integrity_checker.calculate_checksums.side_effect = ValueError("bad")
    await downloader._add_to_cache(task)


def test_stats_cache_helpers_and_run_wrapper(monkeypatch, tmp_path):
    task = _task(tmp_path, b"body")
    downloader = ParallelDownloader(use_cache=False, verify_integrity=False)
    assert downloader.get_stats()["success_rate"] == 0
    assert downloader.get_cache_stats() == {}
    downloader.clear_cache()

    downloader.cache = Mock()
    downloader.cache.get_cache_stats.return_value = {"total_entries": 1}
    downloader.clear_cache()
    assert downloader.get_cache_stats() == {"total_entries": 1}
    downloader.cache.clear_cache.assert_called_once()

    expected = [DownloadResult(task, True)]

    class FakeDownloader:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def download_files(self, tasks):
            assert tasks == [task]
            return expected

    monkeypatch.setattr(downloader_module, "ParallelDownloader", FakeDownloader)
    assert run_parallel_downloads([task], 2, False, False) is expected
