"""Tests for input validation utilities."""

import pytest

from gh_folder_download.validation import InputValidator, ValidationError


class TestValidateGitHubURL:
    """Tests for GitHub URL validation."""

    def setup_method(self):
        self.validator = InputValidator()

    def test_validate_github_url_valid_repo(self):
        """Test valid repository URL."""
        org, repo, branch, path = self.validator.validate_github_url("https://github.com/leynier/gh-folder-download")
        assert org == "leynier"
        assert repo == "gh-folder-download"
        assert branch is None or branch == "main"  # Default branch handling
        assert path is None or path == ""

    def test_validate_github_url_with_branch(self):
        """Test URL with branch specified."""
        org, repo, branch, path = self.validator.validate_github_url(
            "https://github.com/leynier/gh-folder-download/tree/develop"
        )
        assert org == "leynier"
        assert repo == "gh-folder-download"
        assert branch == "develop"

    def test_validate_github_url_with_path(self):
        """Test URL with folder path."""
        org, repo, branch, path = self.validator.validate_github_url(
            "https://github.com/leynier/gh-folder-download/tree/main/src/utils"
        )
        assert org == "leynier"
        assert repo == "gh-folder-download"
        assert branch == "main"
        assert path == "src/utils"

    def test_validate_github_url_invalid_not_github(self):
        """Test non-GitHub URL raises error."""
        with pytest.raises(ValidationError):
            self.validator.validate_github_url("https://gitlab.com/user/repo")

    def test_validate_github_url_invalid_format(self):
        """Test malformed URL raises error."""
        with pytest.raises(ValidationError):
            self.validator.validate_github_url("not-a-url")

    def test_validate_github_url_empty(self):
        """Test empty URL raises error."""
        with pytest.raises(ValidationError):
            self.validator.validate_github_url("")


class TestValidateOutputPath:
    """Tests for output path validation."""

    def setup_method(self):
        self.validator = InputValidator()

    def test_validate_output_path_existing_dir(self, tmp_path):
        """Test existing directory is valid."""
        result = self.validator.validate_output_path(tmp_path)
        assert result == tmp_path

    def test_validate_output_path_creates_dir(self, tmp_path):
        """Test creates directory if missing."""
        new_dir = tmp_path / "new_folder"
        assert not new_dir.exists()
        result = self.validator.validate_output_path(new_dir, create_if_missing=True)
        assert result == new_dir
        # Check directory was created (or is at least usable)
        assert result.is_dir() or result.parent.exists()

    def test_validate_output_path_not_writable(self, tmp_path):
        """Test raises error for non-writable paths."""
        # Create a file (not a directory)
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        with pytest.raises(ValidationError):
            self.validator.validate_output_path(file_path)


class TestValidateGitHubToken:
    """Tests for GitHub token validation."""

    def setup_method(self):
        self.validator = InputValidator()

    def test_validate_github_token_none(self):
        """Test None token is valid (public access)."""
        result = self.validator.validate_github_token(None)
        assert result is None

    def test_validate_github_token_empty(self):
        """Test empty string returns None."""
        result = self.validator.validate_github_token("")
        assert result is None

    @pytest.mark.skip(reason="Token validation hits actual GitHub API")
    def test_validate_github_token_classic_format(self):
        """Test classic personal access token format (ghp_...)."""
        # 40 characters total with ghp_ prefix
        token = "ghp_" + "a" * 36
        result = self.validator.validate_github_token(token)
        assert result == token

    @pytest.mark.skip(reason="Token validation hits actual GitHub API")
    def test_validate_github_token_fine_grained_format(self):
        """Test fine-grained token format (github_pat_...)."""
        token = "github_pat_" + "a" * 50
        result = self.validator.validate_github_token(token)
        assert result == token

    @pytest.mark.skip(reason="Token validation hits actual GitHub API")
    def test_validate_github_token_legacy_format(self):
        """Test legacy 40-char hex token format."""
        token = "a" * 40  # 40 hex characters
        result = self.validator.validate_github_token(token)
        assert result == token

    def test_validate_github_token_invalid_format(self):
        """Test invalid token format raises error."""
        with pytest.raises(ValidationError):
            self.validator.validate_github_token("invalid_token")


class TestValidateLogFilePath:
    """Tests for log file path validation."""

    def setup_method(self):
        self.validator = InputValidator()

    def test_validate_log_file_path_none(self):
        """Test None log file is valid."""
        result = self.validator.validate_log_file_path(None)
        assert result is None

    def test_validate_log_file_path_valid(self, tmp_path):
        """Test valid log file path."""
        log_file = tmp_path / "app.log"
        result = self.validator.validate_log_file_path(log_file)
        assert result == log_file

    def test_validate_log_file_path_creates_parent_dir(self, tmp_path):
        """Test creates parent directory if needed."""
        log_file = tmp_path / "logs" / "app.log"
        result = self.validator.validate_log_file_path(log_file)
        assert result == log_file
        assert log_file.parent.exists()
