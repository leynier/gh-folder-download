from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from github import GithubException
from github.ContentFile import ContentFile

from gh_folder_download import core
from gh_folder_download.config import FilterConfig
from gh_folder_download.filters import FileFilter
from gh_folder_download.parallel_downloader import DownloadResult
from gh_folder_download.retry import APIRetryHandler, DownloadRetryHandler, RetryConfig


def _repository(name="repo"):
    repository = MagicMock()
    repository.name = name
    repository.full_name = f"user/{name}"
    repository.default_branch = "main"
    return repository


def _content(path: str, body: bytes) -> MagicMock:
    content = MagicMock(spec=ContentFile)
    content.type = "file"
    content.name = Path(path).name
    content.path = path
    content.size = len(body)
    content.sha = "a" * 40
    content.download_url = f"https://example.invalid/{path}"
    return content


def _one_attempt_retry():
    return APIRetryHandler(RetryConfig(max_attempts=1, jitter=False))


def test_root_destination_is_repository_subdirectory(tmp_path):
    repository = _repository("widget")
    assert core.resolve_destination(repository, "", tmp_path) == tmp_path / "widget"


def test_force_preserves_existing_destination_when_collection_fails(tmp_path):
    repository = _repository()
    repository.get_contents.side_effect = GithubException(500, {"message": "server error"})
    destination = tmp_path / "repo"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("important")

    with pytest.raises(core.DownloadOperationError):
        core.download_folder_parallel(
            repository,
            "sha",
            "",
            tmp_path,
            True,
            2,
            True,
            False,
            None,
            _one_attempt_retry(),
            True,
            False,
        )

    assert marker.read_text() == "important"


def test_filters_are_applied_before_download(monkeypatch, tmp_path):
    repository = _repository()
    repository.get_contents.return_value = [_content("main.py", b"python"), _content("notes.txt", b"text")]
    captured_tasks = []

    class FakeDownloader:
        def __init__(self, **kwargs):
            pass

        async def download_files(self, tasks):
            captured_tasks.extend(tasks)
            results = []
            for task in tasks:
                task.local_path.parent.mkdir(parents=True, exist_ok=True)
                task.local_path.write_bytes(b"python")
                results.append(
                    DownloadResult(
                        task=task,
                        success=True,
                        bytes_downloaded=6,
                        integrity_verified=True,
                    )
                )
            return results

        def get_stats(self):
            return {}

    monkeypatch.setattr(core, "ParallelDownloader", FakeDownloader)
    stats = core.download_folder_parallel(
        repository,
        "sha",
        "",
        tmp_path,
        False,
        2,
        True,
        False,
        None,
        _one_attempt_retry(),
        True,
        False,
        file_filter=FileFilter(FilterConfig(include_extensions=[".py"])),
    )

    assert [task.file_path for task in captured_tasks] == ["main.py"]
    assert (tmp_path / "repo" / "main.py").exists()
    assert not (tmp_path / "repo" / "notes.txt").exists()
    assert stats["filtered_files"] == 1


def test_force_replaces_only_repository_destination(monkeypatch, tmp_path):
    repository = _repository()
    repository.get_contents.return_value = [_content("main.py", b"new")]
    sentinel = tmp_path / "outside.txt"
    sentinel.write_text("keep")
    destination = tmp_path / "repo"
    destination.mkdir()
    (destination / "old.txt").write_text("old")

    class FakeDownloader:
        def __init__(self, **kwargs):
            pass

        async def download_files(self, tasks):
            task = tasks[0]
            task.local_path.write_bytes(b"new")
            return [DownloadResult(task=task, success=True, bytes_downloaded=3, integrity_verified=True)]

        def get_stats(self):
            return {}

    monkeypatch.setattr(core, "ParallelDownloader", FakeDownloader)
    core.download_folder_parallel(
        repository,
        "sha",
        "",
        tmp_path,
        True,
        2,
        True,
        False,
        None,
        _one_attempt_retry(),
        True,
        False,
    )

    assert sentinel.read_text() == "keep"
    assert not (destination / "old.txt").exists()
    assert (destination / "main.py").read_bytes() == b"new"


def test_resolve_ref_uses_longest_valid_prefix():
    repository = _repository()

    def get_commit(ref):
        if ref == "feature/foo":
            return MagicMock(sha="resolved-sha")
        raise GithubException(404, {"message": "not found"})

    repository.get_commit.side_effect = get_commit
    assert core.resolve_ref_and_path(repository, ("feature", "foo", "src")) == (
        "feature/foo",
        "resolved-sha",
        "src",
    )


def test_get_sha_success_and_non_not_found_error():
    repository = _repository()
    repository.get_commit.return_value.sha = "resolved"
    assert core.get_sha_for_branch_or_tag(repository, "main") == "resolved"

    repository.get_commit.side_effect = GithubException(500, "server")
    with pytest.raises(GithubException):
        core.get_sha_for_branch_or_tag(repository, "main")


def test_resolve_default_ref_and_unresolvable_ref():
    repository = _repository()
    repository.get_commit.return_value.sha = "default-sha"
    assert core.resolve_ref_and_path(repository, ()) == ("main", "default-sha", "")

    repository.get_commit.side_effect = GithubException(404, "missing")
    with pytest.raises(ValueError, match="Could not resolve"):
        core.resolve_ref_and_path(repository, ("missing", "path"))


def test_resolve_destination_rejects_parent_traversal(tmp_path):
    with pytest.raises(core.DownloadOperationError, match="Unsafe output"):
        core.resolve_destination(_repository(), "../outside", tmp_path)


def test_existing_destination_requires_force(tmp_path):
    destination = tmp_path / "repo"
    destination.mkdir()
    with pytest.raises(core.DownloadOperationError, match="Use --force"):
        core.download_folder_parallel(
            _repository(),
            "sha",
            "",
            tmp_path,
            False,
            1,
            False,
            False,
            None,
            _one_attempt_retry(),
            True,
            False,
        )


class _SuccessfulDownloader:
    captured_tasks = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def download_files(self, tasks):
        type(self).captured_tasks = list(tasks)
        results = []
        for task in tasks:
            task.local_path.parent.mkdir(parents=True, exist_ok=True)
            task.local_path.write_bytes(b"data")
            results.append(
                DownloadResult(
                    task,
                    True,
                    bytes_downloaded=4,
                    from_cache=task.file_path.endswith("cached.txt"),
                    integrity_verified=True,
                )
            )
        return results

    def get_stats(self):
        return {"average_speed_mbps": 1.0, "success_rate": 100.0, "cache_hit_rate": 50.0}


def _download_with_repository(monkeypatch, tmp_path, repository, **kwargs):
    _SuccessfulDownloader.captured_tasks = []
    monkeypatch.setattr(core, "ParallelDownloader", _SuccessfulDownloader)
    return core.download_folder_parallel(
        repository,
        "sha",
        "",
        tmp_path,
        False,
        2,
        True,
        False,
        kwargs.pop("github_client", None),
        kwargs.pop("api_retry_handler", _one_attempt_retry()),
        True,
        False,
        **kwargs,
    )


def test_rate_limiter_is_used_for_repository_calls(monkeypatch, tmp_path):
    repository = _repository()
    repository.get_contents.return_value = []
    github_client = Mock()

    stats = _download_with_repository(monkeypatch, tmp_path, repository, github_client=github_client)

    github_client.rate_limiter.wait_if_needed.assert_called_once()
    assert stats["total_files"] == 0
    assert (tmp_path / "repo").is_dir()


def test_remote_path_must_be_directory(tmp_path):
    repository = _repository()
    repository.get_contents.return_value = _content("file.txt", b"data")
    with pytest.raises(core.DownloadOperationError, match="not a directory"):
        core.download_folder_parallel(
            repository,
            "sha",
            "",
            tmp_path,
            False,
            1,
            False,
            False,
            None,
            _one_attempt_retry(),
            True,
            False,
        )


def test_gitignore_rules_and_recursive_directories(monkeypatch, tmp_path):
    repository = _repository()
    directory = MagicMock(type="dir", path="nested")
    directory.name = "nested"
    gitignore = _content("nested/.gitignore", b"ignored.txt\n")
    gitignore.name = ".gitignore"
    decoded = _content("nested/.gitignore", b"ignored.txt\n")
    decoded.decoded_content = b"ignored.txt\n"
    file = _content("nested/cached.txt", b"data")
    repository.get_contents.side_effect = [[directory], [gitignore, file], decoded]
    file_filter = Mock()
    file_filter.config.respect_gitignore = True
    file_filter.should_include_file.return_value = True

    stats = _download_with_repository(monkeypatch, tmp_path, repository, file_filter=file_filter)

    file_filter.add_gitignore_rules.assert_called_once_with("nested", ["ignored.txt"])
    assert stats["cached_files"] == 1
    assert stats["average_speed_mbps"] == 1.0
    assert (tmp_path / "repo" / "nested" / "cached.txt").exists()


@pytest.mark.parametrize("error", [OSError("decode"), UnicodeError("unicode")])
def test_gitignore_loading_failure_is_operational(monkeypatch, tmp_path, error):
    repository = _repository()
    gitignore = _content(".gitignore", b"")
    gitignore.name = ".gitignore"
    repository.get_contents.side_effect = [[gitignore], error]
    file_filter = Mock()
    file_filter.config.respect_gitignore = True

    with pytest.raises(core.DownloadOperationError, match="Could not load"):
        _download_with_repository(monkeypatch, tmp_path, repository, file_filter=file_filter)


def test_missing_download_url_is_refetched(monkeypatch, tmp_path):
    repository = _repository()
    initial = _content("file.txt", b"data")
    initial.download_url = None
    fetched = _content("file.txt", b"data")
    repository.get_contents.side_effect = [[initial], fetched]

    _download_with_repository(monkeypatch, tmp_path, repository)

    assert _SuccessfulDownloader.captured_tasks[0].download_url == fetched.download_url


def test_refetched_entry_must_be_file(monkeypatch, tmp_path):
    repository = _repository()
    initial = _content("file.txt", b"data")
    initial.download_url = None
    repository.get_contents.side_effect = [[initial], []]

    with pytest.raises(core.DownloadOperationError, match="Unsupported repository entry"):
        _download_with_repository(monkeypatch, tmp_path, repository)


def test_refetch_retry_failure_is_operational(monkeypatch, tmp_path):
    repository = _repository()
    initial = _content("file.txt", b"data")
    initial.download_url = None
    repository.get_contents.side_effect = [[initial], ConnectionError("offline")]

    with pytest.raises(core.DownloadOperationError, match="Failed after"):
        _download_with_repository(monkeypatch, tmp_path, repository)


def test_refetched_entry_must_have_download_url(monkeypatch, tmp_path):
    repository = _repository()
    initial = _content("file.txt", b"data")
    initial.download_url = None
    fetched = _content("file.txt", b"data")
    fetched.download_url = None
    repository.get_contents.side_effect = [[initial], fetched]

    with pytest.raises(core.DownloadOperationError, match="No download URL"):
        _download_with_repository(monkeypatch, tmp_path, repository)


def test_failed_downloads_abort_install(monkeypatch, tmp_path):
    repository = _repository()
    repository.get_contents.return_value = [_content("file.txt", b"data")]

    class FailedDownloader(_SuccessfulDownloader):
        async def download_files(self, tasks):
            return [DownloadResult(tasks[0], False, error="offline")]

    monkeypatch.setattr(core, "ParallelDownloader", FailedDownloader)
    with pytest.raises(core.DownloadOperationError, match=r"1 file\(s\) failed"):
        core.download_folder_parallel(
            repository,
            "sha",
            "",
            tmp_path,
            False,
            1,
            False,
            False,
            None,
            _one_attempt_retry(),
            True,
            False,
        )
    assert not (tmp_path / "repo").exists()


def test_install_staging_rolls_back_failed_rename(monkeypatch, tmp_path):
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "old").write_text("old")
    staging = tmp_path / "staging"
    staging.mkdir()
    original_rename = Path.rename

    def failing_rename(path, target):
        if path == staging:
            raise OSError("rename failed")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", failing_rename)
    with pytest.raises(OSError, match="rename failed"):
        core._install_staging(staging, destination)
    assert (destination / "old").read_text() == "old"


def test_install_staging_removes_file_backup(tmp_path):
    destination = tmp_path / "destination"
    destination.write_text("old")
    staging = tmp_path / "staging"
    staging.mkdir()
    core._install_staging(staging, destination)
    assert destination.is_dir()


def test_install_staging_warns_when_backup_cleanup_fails(monkeypatch, tmp_path):
    destination = tmp_path / "destination"
    destination.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    logger = Mock()
    monkeypatch.setattr(core, "get_logger", lambda: logger)
    monkeypatch.setattr(core.shutil, "rmtree", Mock(side_effect=OSError("busy")))

    core._install_staging(staging, destination)

    logger.warning.assert_called_once()


def test_compatibility_wrappers_delegate(monkeypatch, tmp_path):
    repository = _repository()
    expected = {"destination": "target"}
    download = Mock(return_value=expected)
    monkeypatch.setattr(core, "download_folder_parallel", download)
    retry = _one_attempt_retry()

    assert (
        core.download_folder_parallel_no_rate_limit(
            repository, "sha", "", tmp_path, False, 2, True, True, Mock(), retry, True, False
        )
        is expected
    )
    download_retry = DownloadRetryHandler(RetryConfig(max_attempts=4, base_delay=0.5))
    assert core.download_folder(repository, "sha", "", tmp_path, False, True, retry, download_retry, Mock()) is expected
    assert download.call_count == 2
