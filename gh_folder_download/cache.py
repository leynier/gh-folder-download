"""
Intelligent caching system for gh-folder-download.
"""

import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .logger import get_logger


class CacheEntry:
    """Represents a cached file entry with metadata."""

    def __init__(
        self,
        file_path: str,
        sha: str,
        size: int,
        last_modified: str,
        download_time: float,
        checksums: dict[str, str] | None = None,
    ):
        self.file_path = file_path
        self.sha = sha
        self.size = size
        self.last_modified = last_modified
        self.download_time = download_time
        self.checksums = checksums or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert cache entry to dictionary for serialization."""
        return {
            "file_path": self.file_path,
            "sha": self.sha,
            "size": self.size,
            "last_modified": self.last_modified,
            "download_time": self.download_time,
            "checksums": self.checksums,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheEntry":
        """Create cache entry from dictionary."""
        return cls(
            file_path=data["file_path"],
            sha=data["sha"],
            size=data["size"],
            last_modified=data["last_modified"],
            download_time=data["download_time"],
            checksums=data.get("checksums", {}),
        )

    def is_current(self, github_sha: str, github_size: int) -> bool:
        """Check if cached file is still current based on GitHub metadata."""
        return self.sha == github_sha and self.size == github_size


class DownloadCache:
    """Intelligent cache for downloaded files."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_size_gb: float = 5.0,
        max_age_days: int = 30,
        auto_cleanup: bool = True,
    ):
        self.logger = get_logger()
        self._lock = threading.RLock()

        # Default cache directory
        if cache_dir is None:
            cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
            cache_dir = cache_root / "gh-folder-download"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.blob_dir = self.cache_dir / "blobs"
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024)
        self.max_age_days = max_age_days
        self.auto_cleanup = auto_cleanup

        self.cache_file = self.cache_dir / "cache_metadata.json"
        self.cache_data: dict[str, CacheEntry] = {}

        self._load_cache()
        if self.auto_cleanup:
            self.clean_cache(self.max_age_days)
            self.enforce_size_limit(self.max_size_bytes)

    def _load_cache(self) -> None:
        """Load cache data from disk."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file) as f:
                    data = json.load(f)
                    self.cache_data = {key: CacheEntry.from_dict(value) for key, value in data.items()}
                self.logger.debug(f"Loaded cache with {len(self.cache_data)} entries")
            else:
                self.logger.debug("No existing cache found, starting fresh")
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
            self.logger.warning(f"Failed to load cache, starting fresh: {e}")
            self.cache_data = {}

    def _save_cache(self) -> None:
        """Save cache data to disk."""
        try:
            with self._lock:
                data = {key: entry.to_dict() for key, entry in self.cache_data.items()}
            temporary = self.cache_file.with_name(f".{self.cache_file.name}.tmp-{os.getpid()}-{threading.get_ident()}")
            with open(temporary, "w") as f:
                json.dump(data, f, indent=2)
            temporary.replace(self.cache_file)
            self.logger.debug(f"Saved cache with {len(self.cache_data)} entries")
        except OSError as e:
            self.logger.warning(f"Failed to save cache: {e}")

    def _get_cache_key(self, repo_full_name: str, file_path: str, ref: str) -> str:
        """Generate a unique cache key for a file."""
        return f"{repo_full_name}:{ref}:{file_path}"

    def _get_blob_path(self, sha: str) -> Path:
        """Return the content-addressed path for a Git object id."""
        safe_sha = "".join(char for char in sha.lower() if char in "0123456789abcdef")
        if not safe_sha or safe_sha != sha.lower():
            # Tests and older metadata may contain non-Git identifiers. Hashing the
            # identifier keeps the cache path safe while preserving compatibility.
            import hashlib

            safe_sha = hashlib.sha256(sha.encode()).hexdigest()
        return self.blob_dir / safe_sha[:2] / safe_sha[2:]

    def is_file_cached(
        self,
        repo_full_name: str,
        file_path: str,
        ref: str,
        github_sha: str,
        github_size: int,
        local_file_path: Path,
    ) -> bool:
        """
        Check if a file is cached and current.

        Args:
            repo_full_name: Full repository name (org/repo)
            file_path: Path of file in repository
            ref: Git reference (branch/tag/commit)
            github_sha: Current SHA from GitHub
            github_size: Current size from GitHub
            local_file_path: Local path where file should be

        Returns:
            True if file is cached and current
        """
        cache_key = self._get_cache_key(repo_full_name, file_path, ref)

        cache_entry = self.cache_data.get(cache_key)
        if cache_entry is None:
            cache_entry = next(
                (entry for entry in self.cache_data.values() if entry.sha == github_sha and entry.size == github_size),
                None,
            )
        if cache_entry is None:
            self.logger.debug(f"No cache entry for {file_path}")
            return False

        # Check if file is still current
        if not cache_entry.is_current(github_sha, github_size):
            self.logger.debug(f"Cache entry outdated for {file_path}")
            return False

        blob_path = self._get_blob_path(cache_entry.sha)
        if not blob_path.is_file():
            self.logger.debug(f"Cached blob no longer exists: {blob_path}")
            self._invalidate_sha(cache_entry.sha)
            return False

        # Verify the cached blob, then materialize it into the requested staging path.
        try:
            if blob_path.stat().st_size != cache_entry.size:
                self.logger.warning(f"Cached blob size mismatch for {file_path}")
                self._invalidate_sha(cache_entry.sha)
                blob_path.unlink(missing_ok=True)
                return False

            if cache_entry.checksums.get("sha256"):
                import hashlib

                hasher = hashlib.sha256()
                with open(blob_path, "rb") as file:
                    while chunk := file.read(8192):
                        hasher.update(chunk)
                digest = hasher.hexdigest()
                if digest != cache_entry.checksums["sha256"]:
                    self.logger.warning(f"Cached blob checksum mismatch for {file_path}")
                    self._invalidate_sha(cache_entry.sha)
                    blob_path.unlink(missing_ok=True)
                    return False

            local_file_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(blob_path, local_file_path)
            cache_entry.download_time = time.time()
            self.cache_data[cache_key] = CacheEntry(
                file_path=file_path,
                sha=github_sha,
                size=github_size,
                last_modified=cache_entry.last_modified,
                download_time=cache_entry.download_time,
                checksums=cache_entry.checksums,
            )
        except OSError as e:
            self.logger.warning(f"Failed to restore cached file: {e}")
            self.cache_data.pop(cache_key, None)
            return False

        self.logger.debug(f"File is cached and current: {file_path}")
        return True

    def _invalidate_sha(self, sha: str) -> None:
        for key in [key for key, entry in self.cache_data.items() if entry.sha == sha]:
            del self.cache_data[key]

    def add_file_to_cache(
        self,
        repo_full_name: str,
        file_path: str,
        ref: str,
        github_sha: str,
        github_size: int,
        local_file_path: Path,
        checksums: dict[str, str] | None = None,
    ) -> None:
        """
        Add a file to the cache.

        Args:
            repo_full_name: Full repository name (org/repo)
            file_path: Path of file in repository
            ref: Git reference (branch/tag/commit)
            github_sha: SHA from GitHub
            github_size: Size from GitHub
            local_file_path: Local path where file is stored
            checksums: Optional checksums dictionary
        """
        cache_key = self._get_cache_key(repo_full_name, file_path, ref)

        blob_path = self._get_blob_path(github_sha)
        try:
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_blob = blob_path.with_suffix(f".tmp-{time.time_ns()}")
            shutil.copy2(local_file_path, temporary_blob)
            temporary_blob.replace(blob_path)
        except OSError as e:
            self.logger.warning(f"Failed to store cached blob for {file_path}: {e}")
            return

        # Get file modification time
        try:
            mtime = local_file_path.stat().st_mtime
            last_modified = datetime.fromtimestamp(mtime).isoformat()
        except OSError:
            last_modified = datetime.now().isoformat()

        cache_entry = CacheEntry(
            file_path=file_path,
            sha=github_sha,
            size=github_size,
            last_modified=last_modified,
            download_time=time.time(),
            checksums=checksums,
        )

        self.cache_data[cache_key] = cache_entry
        self.logger.debug(f"Added file to cache: {file_path}")

        # Save cache more frequently to prevent data loss
        # (every 5 new entries) or when cache is small
        if len(self.cache_data) % 5 == 0 or len(self.cache_data) <= 3:
            self._save_cache()

        if self.auto_cleanup:
            self.enforce_size_limit(self.max_size_bytes)

    def get_cached_checksums(
        self,
        repo_full_name: str,
        file_path: str,
        ref: str,
    ) -> dict[str, str] | None:
        """Get cached checksums for a file if available."""
        cache_key = self._get_cache_key(repo_full_name, file_path, ref)

        if cache_key in self.cache_data:
            return self.cache_data[cache_key].checksums

        return None

    def clean_cache(self, max_age_days: int = 30) -> int:
        """
        Clean old entries from cache.

        Args:
            max_age_days: Maximum age in days for cache entries

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60

        keys_to_remove = []
        for key, entry in self.cache_data.items():
            age = current_time - entry.download_time
            if age > max_age_seconds:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.cache_data[key]

        if keys_to_remove:
            self._remove_orphaned_blobs()
            self._save_cache()
            self.logger.info(f"Cleaned {len(keys_to_remove)} old cache entries")

        return len(keys_to_remove)

    def enforce_size_limit(self, max_size_bytes: int | None = None) -> int:
        """Evict least-recently-used entries until cached blobs fit the limit."""
        limit = self.max_size_bytes if max_size_bytes is None else max_size_bytes
        removed = 0
        while self._blob_size() > limit and self.cache_data:
            oldest_key = min(self.cache_data, key=lambda key: self.cache_data[key].download_time)
            del self.cache_data[oldest_key]
            removed += 1
            self._remove_orphaned_blobs()
        if removed:
            self._save_cache()
        return removed

    def _blob_size(self) -> int:
        return sum(path.stat().st_size for path in self.blob_dir.rglob("*") if path.is_file())

    def _remove_orphaned_blobs(self) -> None:
        referenced = {self._get_blob_path(entry.sha) for entry in self.cache_data.values()}
        for blob in self.blob_dir.rglob("*"):
            if blob.is_file() and blob not in referenced:
                blob.unlink(missing_ok=True)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        if not self.cache_data:
            return {
                "total_entries": 0,
                "total_size_mb": 0,
                "oldest_entry": None,
                "newest_entry": None,
            }

        total_size = self._blob_size()
        download_times = [entry.download_time for entry in self.cache_data.values()]

        return {
            "total_entries": len(self.cache_data),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_entry": datetime.fromtimestamp(min(download_times)).isoformat(),
            "newest_entry": datetime.fromtimestamp(max(download_times)).isoformat(),
        }

    def clear_cache(self) -> None:
        """Clear all cache data."""
        self.cache_data.clear()
        if self.cache_file.exists():
            self.cache_file.unlink()
        if self.blob_dir.exists():
            shutil.rmtree(self.blob_dir)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info("Cache cleared")

    def finalize(self) -> None:
        """Finalize cache operations (save to disk)."""
        self._save_cache()
        self.logger.debug("Cache finalized and saved")
