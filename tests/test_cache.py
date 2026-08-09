"""Tests for caching system."""

import builtins
import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from gh_folder_download import cache as cache_module
from gh_folder_download.cache import CacheEntry, DownloadCache


@pytest.fixture
def cache_dir(tmp_path):
    """Temporary cache directory."""
    return tmp_path / ".gh-folder-download-cache"


@pytest.fixture
def download_cache(cache_dir):
    """DownloadCache instance with temp directory."""
    return DownloadCache(cache_dir=cache_dir)


@pytest.fixture
def sample_cache_entry():
    """Sample cache entry for testing."""
    return CacheEntry(
        file_path="src/main.py",
        sha="abc123def456",
        size=1024,
        last_modified="2024-01-01T00:00:00Z",
        download_time=time.time(),
        checksums={"sha256": "deadbeef" * 8},
    )


class TestCacheEntry:
    """Tests for CacheEntry class."""

    def test_to_dict(self, sample_cache_entry):
        """Test serialization to dictionary."""
        data = sample_cache_entry.to_dict()

        assert data["file_path"] == "src/main.py"
        assert data["sha"] == "abc123def456"
        assert data["size"] == 1024
        assert "checksums" in data

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "file_path": "src/main.py",
            "sha": "abc123def456",
            "size": 1024,
            "last_modified": "2024-01-01T00:00:00Z",
            "download_time": 1234567890.0,
            "checksums": {"sha256": "deadbeef" * 8},
        }

        entry = CacheEntry.from_dict(data)

        assert entry.file_path == "src/main.py"
        assert entry.sha == "abc123def456"
        assert entry.size == 1024

    def test_is_current_match(self, sample_cache_entry):
        """Test is_current returns True when SHA and size match."""
        result = sample_cache_entry.is_current(
            github_sha="abc123def456",
            github_size=1024,
        )

        assert result is True

    def test_is_current_sha_mismatch(self, sample_cache_entry):
        """Test is_current returns False when SHA differs."""
        result = sample_cache_entry.is_current(
            github_sha="different_sha",
            github_size=1024,
        )

        assert result is False

    def test_is_current_size_mismatch(self, sample_cache_entry):
        """Test is_current returns False when size differs."""
        result = sample_cache_entry.is_current(
            github_sha="abc123def456",
            github_size=2048,
        )

        assert result is False


class TestDownloadCache:
    """Tests for DownloadCache class."""

    def test_cache_dir_created(self, cache_dir):
        """Test cache directory is created."""
        DownloadCache(cache_dir=cache_dir)

        assert cache_dir.exists()

    def test_default_cache_directory_uses_xdg_cache_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        cache = DownloadCache(auto_cleanup=False)
        assert cache.cache_dir == tmp_path / "gh-folder-download"

    def test_existing_cache_metadata_is_loaded(self, cache_dir):
        cache_dir.mkdir()
        entry = CacheEntry("file.txt", "abc123", 1, "now", 1).to_dict()
        (cache_dir / "cache_metadata.json").write_text(json.dumps({"key": entry}))

        cache = DownloadCache(cache_dir=cache_dir, auto_cleanup=False)

        assert cache.cache_data["key"].file_path == "file.txt"

    @pytest.mark.parametrize("contents", ["not json", '{"key": {}}'])
    def test_invalid_cache_metadata_starts_fresh(self, cache_dir, contents):
        cache_dir.mkdir()
        (cache_dir / "cache_metadata.json").write_text(contents)
        assert DownloadCache(cache_dir=cache_dir, auto_cleanup=False).cache_data == {}

    def test_save_cache_error_is_tolerated(self, download_cache, monkeypatch):
        monkeypatch.setattr(builtins, "open", Mock(side_effect=OSError("denied")))
        download_cache._save_cache()
        assert download_cache.cache_data == {}

    def test_is_file_cached_new_file(self, download_cache, tmp_path):
        """Test is_file_cached returns False for new file."""
        local_file = tmp_path / "test.txt"
        local_file.write_text("content")

        result = download_cache.is_file_cached(
            repo_full_name="user/repo",
            file_path="src/main.py",
            ref="main",
            github_sha="abc123",
            github_size=1024,
            local_file_path=local_file,
        )

        assert result is False

    def test_add_and_retrieve_cached_file(self, download_cache, tmp_path):
        """Test adding and retrieving a cached file."""
        local_file = tmp_path / "test.txt"
        local_file.write_text("content")

        # Add to cache
        download_cache.add_file_to_cache(
            repo_full_name="user/repo",
            file_path="src/main.py",
            ref="main",
            github_sha="abc123",
            github_size=len("content"),
            local_file_path=local_file,
        )

        # Check if cached
        result = download_cache.is_file_cached(
            repo_full_name="user/repo",
            file_path="src/main.py",
            ref="main",
            github_sha="abc123",
            github_size=len("content"),
            local_file_path=local_file,
        )

        assert result is True

    def test_cached_file_stale_after_sha_change(self, download_cache, tmp_path):
        """Test cached file becomes stale when SHA changes."""
        local_file = tmp_path / "test.txt"
        local_file.write_text("content")

        # Add to cache
        download_cache.add_file_to_cache(
            repo_full_name="user/repo",
            file_path="src/main.py",
            ref="main",
            github_sha="abc123",
            github_size=len("content"),
            local_file_path=local_file,
        )

        # Check with different SHA
        result = download_cache.is_file_cached(
            repo_full_name="user/repo",
            file_path="src/main.py",
            ref="main",
            github_sha="different_sha",
            github_size=len("content"),
            local_file_path=local_file,
        )

        assert result is False

    def test_missing_cached_blob_invalidates_all_matching_entries(self, download_cache, tmp_path):
        local = tmp_path / "file.txt"
        local.write_text("content")
        download_cache.add_file_to_cache("user/repo", "one.txt", "main", "abc123", 7, local)
        key = download_cache._get_cache_key("other/repo", "two.txt", "main")
        download_cache.cache_data[key] = CacheEntry("two.txt", "abc123", 7, "now", time.time())
        download_cache._get_blob_path("abc123").unlink()

        assert download_cache.is_file_cached("user/repo", "one.txt", "main", "abc123", 7, local) is False
        assert download_cache.cache_data == {}

    def test_cached_blob_size_mismatch_is_removed(self, download_cache, tmp_path):
        local = tmp_path / "file.txt"
        local.write_text("content")
        download_cache.add_file_to_cache("user/repo", "file.txt", "main", "abc123", 7, local)
        download_cache._get_blob_path("abc123").write_text("wrong size")

        assert download_cache.is_file_cached("user/repo", "file.txt", "main", "abc123", 7, local) is False
        assert not download_cache._get_blob_path("abc123").exists()

    def test_cached_blob_checksum_mismatch_is_removed(self, download_cache, tmp_path):
        local = tmp_path / "file.txt"
        local.write_text("content")
        download_cache.add_file_to_cache(
            "user/repo",
            "file.txt",
            "main",
            "abc123",
            7,
            local,
            checksums={"sha256": "0" * 64},
        )

        assert download_cache.is_file_cached("user/repo", "file.txt", "main", "abc123", 7, local) is False

    def test_restore_error_removes_requested_entry(self, download_cache, tmp_path, monkeypatch):
        local = tmp_path / "file.txt"
        local.write_text("content")
        download_cache.add_file_to_cache("user/repo", "file.txt", "main", "abc123", 7, local)
        monkeypatch.setattr(cache_module.shutil, "copy2", Mock(side_effect=OSError("denied")))

        assert download_cache.is_file_cached("user/repo", "file.txt", "main", "abc123", 7, local) is False

    def test_store_error_does_not_create_entry(self, download_cache, tmp_path, monkeypatch):
        local = tmp_path / "file.txt"
        local.write_text("content")
        monkeypatch.setattr(cache_module.shutil, "copy2", Mock(side_effect=OSError("denied")))

        download_cache.add_file_to_cache("user/repo", "file.txt", "main", "abc123", 7, local)

        assert download_cache.cache_data == {}

    def test_stat_error_uses_current_time_for_metadata(self, download_cache, tmp_path, monkeypatch):
        local = tmp_path / "file.txt"
        local.write_text("content")
        original_stat = Path.stat

        def conditional_stat(path, *args, **kwargs):
            if path == local:
                raise OSError("denied")
            return original_stat(path, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", conditional_stat)
        download_cache.add_file_to_cache("user/repo", "file.txt", "main", "abc123", 7, local)

        key = download_cache._get_cache_key("user/repo", "file.txt", "main")
        assert download_cache.cache_data[key].last_modified

    def test_cache_restores_same_size_tampering(self, download_cache, tmp_path):
        local_file = tmp_path / "test.txt"
        local_file.write_text("original")
        download_cache.add_file_to_cache(
            repo_full_name="user/repo",
            file_path="test.txt",
            ref="main",
            github_sha="abc123",
            github_size=8,
            local_file_path=local_file,
            checksums={"sha256": "0682c5f2076f099c34cfdd15a9e063849ed437a49677e6fcc5b4198c76575be5"},
        )
        local_file.write_text("tampered")

        assert download_cache.is_file_cached("user/repo", "test.txt", "main", "abc123", 8, local_file)
        assert local_file.read_text() == "original"

    def test_blob_can_be_reused_for_a_new_destination(self, download_cache, tmp_path):
        original = tmp_path / "first" / "test.txt"
        original.parent.mkdir()
        original.write_text("content")
        download_cache.add_file_to_cache("user/repo", "test.txt", "main", "abc123", 7, original)
        restored = tmp_path / "second" / "test.txt"

        assert download_cache.is_file_cached("user/repo", "other.txt", "other-ref", "abc123", 7, restored)
        assert restored.read_text() == "content"

    def test_get_cached_checksums(self, download_cache, tmp_path):
        """Test retrieving cached checksums."""
        local_file = tmp_path / "test.txt"
        local_file.write_text("content")

        checksums = {"sha256": "abc123"}

        download_cache.add_file_to_cache(
            repo_full_name="user/repo",
            file_path="src/main.py",
            ref="main",
            github_sha="abc123",
            github_size=len("content"),
            local_file_path=local_file,
            checksums=checksums,
        )

        result = download_cache.get_cached_checksums(
            repo_full_name="user/repo",
            file_path="src/main.py",
            ref="main",
        )

        assert result == checksums

    def test_get_cached_checksums_not_found(self, download_cache):
        """Test get_cached_checksums returns None for missing entry."""
        result = download_cache.get_cached_checksums(
            repo_full_name="user/repo",
            file_path="nonexistent.py",
            ref="main",
        )

        assert result is None


class TestCacheCleanup:
    """Tests for cache cleanup functionality."""

    def test_clean_cache_removes_old_entries(self, download_cache, tmp_path):
        """Test clean_cache removes old entries."""
        local_file = tmp_path / "test.txt"
        local_file.write_text("content")

        # Add to cache with old download time
        download_cache.add_file_to_cache(
            repo_full_name="user/repo",
            file_path="old_file.py",
            ref="main",
            github_sha="abc123",
            github_size=len("content"),
            local_file_path=local_file,
        )

        # Manually set old download time
        cache_key = download_cache._get_cache_key("user/repo", "old_file.py", "main")
        if cache_key in download_cache.cache_data:
            download_cache.cache_data[cache_key].download_time = time.time() - (40 * 24 * 3600)

        # Clean with 30 day max age
        removed = download_cache.clean_cache(max_age_days=30)

        assert removed >= 1

    def test_clear_cache(self, download_cache, tmp_path):
        """Test clear_cache removes all entries."""
        local_file = tmp_path / "test.txt"
        local_file.write_text("content")

        # Add some entries
        for i in range(3):
            download_cache.add_file_to_cache(
                repo_full_name="user/repo",
                file_path=f"file{i}.py",
                ref="main",
                github_sha=f"sha{i}",
                github_size=len("content"),
                local_file_path=local_file,
            )

        download_cache.clear_cache()

        stats = download_cache.get_cache_stats()
        assert stats["total_entries"] == 0

    def test_clean_cache_keeps_recent_entries(self, download_cache, tmp_path):
        local = tmp_path / "file.txt"
        local.write_text("content")
        download_cache.add_file_to_cache("user/repo", "file.txt", "main", "abc123", 7, local)
        assert download_cache.clean_cache(max_age_days=30) == 0

    def test_enforce_size_limit_evicts_oldest_and_saves(self, download_cache, tmp_path, monkeypatch):
        local = tmp_path / "file.txt"
        local.write_text("content")
        download_cache.add_file_to_cache("user/repo", "one.txt", "main", "abc123", 7, local)
        download_cache.add_file_to_cache("user/repo", "two.txt", "main", "def456", 7, local)
        save = Mock()
        monkeypatch.setattr(download_cache, "_save_cache", save)

        removed = download_cache.enforce_size_limit(0)

        assert removed == 2
        assert download_cache.cache_data == {}
        save.assert_called_once()

    def test_finalize_saves_cache(self, download_cache, monkeypatch):
        save = Mock()
        monkeypatch.setattr(download_cache, "_save_cache", save)
        download_cache.finalize()
        save.assert_called_once()


class TestCacheStats:
    """Tests for cache statistics."""

    def test_get_cache_stats_empty(self, download_cache):
        """Test stats for empty cache."""
        stats = download_cache.get_cache_stats()

        assert stats["total_entries"] == 0
        assert stats["total_size_mb"] == 0

    def test_get_cache_stats_with_entries(self, download_cache, tmp_path):
        """Test stats with cached entries."""
        local_file = tmp_path / "test.txt"
        local_file.write_text("content")

        download_cache.add_file_to_cache(
            repo_full_name="user/repo",
            file_path="file.py",
            ref="main",
            github_sha="abc123",
            github_size=100,
            local_file_path=local_file,
        )

        stats = download_cache.get_cache_stats()

        assert stats["total_entries"] == 1
        assert stats["total_size_mb"] >= 0  # Size in MB
