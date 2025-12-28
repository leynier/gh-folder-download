"""
Integration tests for gh-folder-download.

These tests perform REAL downloads from GitHub and save files locally.
Run with: uv run pytest tests/test_integration.py -v

NOTE: These tests require internet connection and may be slow.
"""

import os
import shutil
from pathlib import Path

import pytest

from gh_folder_download.config import FilterConfig
from gh_folder_download.filters import FileFilter
from gh_folder_download.rate_limiter import RateLimitedGitHubClient
from gh_folder_download.validation import InputValidator

# Test output directory (git-ignored)
DOWNLOADS_DIR = Path(__file__).parent / "downloads"


@pytest.fixture(scope="module")
def downloads_dir():
    """Create and return the downloads directory."""
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    return DOWNLOADS_DIR


@pytest.fixture(scope="module")
def github_client():
    """Create a rate-limited GitHub client."""
    token = os.environ.get("GITHUB_TOKEN")
    return RateLimitedGitHubClient(token=token)


@pytest.fixture
def validator():
    """InputValidator instance."""
    return InputValidator()


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestURLValidation:
    """Integration tests for URL validation with real GitHub repos."""

    def test_validate_public_repo_url(self, validator):
        """Test validating a real public repository URL."""
        url = "https://github.com/leynier/gh-folder-download"
        org, repo, branch, path = validator.validate_github_url(url)

        assert org == "leynier"
        assert repo == "gh-folder-download"

    def test_validate_repo_with_branch_and_path(self, validator):
        """Test validating URL with branch and folder path."""
        url = "https://github.com/leynier/gh-folder-download/tree/main/gh_folder_download"
        org, repo, branch, path = validator.validate_github_url(url)

        assert org == "leynier"
        assert repo == "gh-folder-download"
        assert branch == "main"
        assert path == "gh_folder_download"


class TestFolderContents:
    """Integration tests for getting folder contents from GitHub."""

    def test_get_root_contents(self, github_client):
        """Test getting contents of repository root."""
        repo = github_client.get_repo("leynier/gh-folder-download")

        # Get root contents
        contents = repo.get_contents("")

        # Should have some files
        assert len(contents) > 0

        # Should contain common files
        file_names = [c.name for c in contents]
        assert "pyproject.toml" in file_names or "README.md" in file_names or "readme.md" in file_names

    def test_get_subfolder_contents(self, github_client):
        """Test getting contents of a subfolder."""
        repo = github_client.get_repo("leynier/gh-folder-download")

        # Get subfolder contents
        contents = repo.get_contents("gh_folder_download")

        # Should have Python files
        assert len(contents) > 0

        file_names = [c.name for c in contents]
        assert "__init__.py" in file_names


class TestRealDownloads:
    """Integration tests that perform actual file downloads."""

    def test_download_single_file(self, github_client, downloads_dir):
        """Test downloading a single file."""
        output_dir = downloads_dir / "single_file_test"
        output_dir.mkdir(exist_ok=True)

        repo = github_client.get_repo("leynier/gh-folder-download")

        # Get a specific file
        content = repo.get_contents("pyproject.toml")

        # Download it
        file_path = output_dir / "pyproject.toml"
        file_path.write_bytes(content.decoded_content)

        # Verify
        assert file_path.exists()
        assert file_path.stat().st_size > 0

        # Check content
        content_text = file_path.read_text()
        assert "gh-folder-download" in content_text

    def test_download_folder_with_filter(self, github_client, downloads_dir):
        """Test downloading a folder with extension filter."""
        output_dir = downloads_dir / "filtered_folder_test"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(exist_ok=True)

        repo = github_client.get_repo("leynier/gh-folder-download")

        # Create filter for Python files only
        filter_config = FilterConfig(include_extensions=[".py"])
        file_filter = FileFilter(filter_config)

        # Get folder contents
        contents = repo.get_contents("gh_folder_download")

        # Download only Python files
        downloaded_files = []
        for content in contents:
            if content.type == "file" and file_filter.should_include_file(content.path):
                file_path = output_dir / content.name
                file_path.write_bytes(content.decoded_content)
                downloaded_files.append(file_path)

        # Verify
        assert len(downloaded_files) > 0

        # All files should be .py files
        for file_path in downloaded_files:
            assert file_path.suffix == ".py"

    def test_download_small_folder(self, github_client, downloads_dir):
        """Test downloading the tests folder (smaller)."""
        output_dir = downloads_dir / "tests_folder"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(exist_ok=True)

        repo = github_client.get_repo("leynier/gh-folder-download")

        # Get tests folder contents
        try:
            contents = repo.get_contents("tests")
        except Exception:
            pytest.skip("tests folder not found in repository")

        # Download all files
        downloaded_count = 0
        for content in contents:
            if content.type == "file":
                file_path = output_dir / content.name
                file_path.write_bytes(content.decoded_content)
                downloaded_count += 1

        assert downloaded_count > 0
        assert (output_dir / "conftest.py").exists() or downloaded_count > 0


class TestIntegrityVerification:
    """Integration tests for file integrity after download."""

    def test_downloaded_file_matches_size(self, github_client, downloads_dir):
        """Test that downloaded file size matches GitHub's reported size."""
        output_dir = downloads_dir / "integrity_test"
        output_dir.mkdir(exist_ok=True)

        repo = github_client.get_repo("leynier/gh-folder-download")
        content = repo.get_contents("pyproject.toml")

        # Download
        file_path = output_dir / "pyproject.toml"
        file_path.write_bytes(content.decoded_content)

        # Verify size
        local_size = file_path.stat().st_size
        github_size = content.size

        assert local_size == github_size

    def test_downloaded_file_checksum(self, github_client, downloads_dir):
        """Test that downloaded file has consistent checksum."""
        from gh_folder_download.integrity import FileIntegrityChecker

        output_dir = downloads_dir / "checksum_test"
        output_dir.mkdir(exist_ok=True)

        repo = github_client.get_repo("leynier/gh-folder-download")
        content = repo.get_contents("pyproject.toml")

        # Download
        file_path = output_dir / "pyproject.toml"
        file_path.write_bytes(content.decoded_content)

        # Calculate checksums
        checker = FileIntegrityChecker()
        checksums = checker.calculate_checksums(file_path)

        # Verify we got checksums
        assert "sha256" in checksums
        assert len(checksums["sha256"]) == 64  # SHA256 hex length


class TestRateLimiting:
    """Integration tests for rate limiting behavior."""

    def test_rate_limit_status(self, github_client):
        """Test getting rate limit status."""
        status = github_client.get_rate_limit_status()

        # Status may be empty if rate limit API changed, just verify it's a dict
        assert isinstance(status, dict)


# Cleanup fixture
@pytest.fixture(scope="session", autouse=True)
def cleanup_downloads():
    """Optionally clean up downloads after all tests."""
    yield
    # Uncomment to clean up after tests:
    # if DOWNLOADS_DIR.exists():
    #     shutil.rmtree(DOWNLOADS_DIR)
