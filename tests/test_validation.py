"""Tests for input validation utilities."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from gh_folder_download import validation as validation_module
from gh_folder_download.validation import InputValidator, ParsedGitHubURL, ValidationError


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

    @pytest.mark.parametrize("repository", ["widget", "digit", "git"])
    def test_repository_suffix_is_not_mutilated(self, repository):
        parsed = self.validator.parse_github_url(f"https://github.com/user/{repository}")
        assert parsed.repository == repository

    def test_tree_segments_preserve_ref_slashes(self):
        parsed = self.validator.parse_github_url("https://github.com/user/repo/tree/feature/foo/src")
        assert parsed.tree_segments == ("feature", "foo", "src")

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

    def test_validate_github_url_non_string(self):
        with pytest.raises(ValidationError, match="must be a string"):
            self.validator.parse_github_url(123)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/user",
            "https://github.com/-bad/repo",
            "https://github.com/user/-bad",
            "https://github.com/user/repo/issues",
            "https://github.com/user/repo/tree",
            "https://github.com/user/repo/tree/main/..",
            "https://github.com/user/repo?tab=readme",
            "https://github.com/user/repo#readme",
        ],
    )
    def test_rejects_invalid_github_url_variants(self, url):
        with pytest.raises(ValidationError):
            self.validator.parse_github_url(url)

    def test_strips_exact_git_suffix(self):
        parsed = self.validator.parse_github_url("https://github.com/user/repo.git")
        assert parsed == ParsedGitHubURL("user", "repo")

    def test_url_parser_failures_are_wrapped(self, monkeypatch):
        monkeypatch.setattr(validation_module, "urlparse", Mock(side_effect=ValueError("bad parse")))
        with pytest.raises(ValidationError, match="Malformed URL"):
            self.validator.parse_github_url("https://github.com/user/repo")

    def test_parsed_domain_must_be_github(self, monkeypatch):
        parsed = Mock(netloc="example.com", query="", fragment="")
        monkeypatch.setattr(validation_module, "urlparse", Mock(return_value=parsed))
        with pytest.raises(ValidationError, match="Invalid GitHub domain"):
            self.validator.parse_github_url("https://github.com/user/repo")


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
        new_dir = tmp_path / "parent" / "new_folder"
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

    def test_missing_parent_is_rejected_when_creation_disabled(self, tmp_path):
        with pytest.raises(ValidationError, match="Parent directory does not exist"):
            self.validator.validate_output_path(tmp_path / "missing" / "output", create_if_missing=False)

    def test_parent_must_be_directory(self, tmp_path):
        parent = tmp_path / "file"
        parent.write_text("content")
        with pytest.raises(ValidationError, match="Parent path is not a directory"):
            self.validator.validate_output_path(parent / "output")

    def test_parent_must_be_writable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(self.validator, "_is_writable", lambda _path: False)
        with pytest.raises(ValidationError, match="No write permission"):
            self.validator.validate_output_path(tmp_path / "output")

    def test_output_os_error_is_wrapped(self):
        path = Mock(spec=Path)
        path.resolve.side_effect = OSError("broken")
        with pytest.raises(ValidationError, match="Invalid output path"):
            self.validator.validate_output_path(path)


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

    def test_validate_github_token_classic_format(self):
        """Test classic personal access token format (ghp_...)."""
        # 40 characters total with ghp_ prefix
        token = "ghp_" + "a" * 36
        result = self.validator.validate_github_token(token)
        assert result == token

    def test_validate_github_token_fine_grained_format(self):
        """Test fine-grained token format (github_pat_...)."""
        token = "github_pat_" + "a" * 50
        result = self.validator.validate_github_token(token)
        assert result == token

    def test_validate_github_token_legacy_format(self):
        """Test legacy 40-char hex token format."""
        token = "a" * 40  # 40 hex characters
        result = self.validator.validate_github_token(token)
        assert result == token

    def test_validate_github_token_invalid_format(self):
        """Test invalid token format raises error."""
        with pytest.raises(ValidationError):
            self.validator.validate_github_token("invalid_token")

    def test_token_type_and_whitespace_are_rejected(self):
        with pytest.raises(ValidationError, match="must be a string"):
            self.validator.validate_github_token(123)  # type: ignore[arg-type]
        with pytest.raises(ValidationError, match="cannot be empty"):
            self.validator.validate_github_token("   ")

    @pytest.mark.parametrize("prefix", ["gho_", "ghu_", "ghs_", "ghr_"])
    def test_other_classic_token_prefixes(self, prefix):
        token = prefix + "a" * 20
        assert self.validator.validate_github_token(token) == token

    def test_non_hex_legacy_token_is_rejected(self):
        with pytest.raises(ValidationError, match="Invalid GitHub token format"):
            self.validator.validate_github_token("z" * 40)


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

    def test_log_parent_must_be_directory(self, tmp_path):
        parent = tmp_path / "file"
        parent.write_text("content")
        with pytest.raises(ValidationError, match="parent is not a directory"):
            self.validator.validate_log_file_path(parent / "app.log")

    def test_log_parent_must_be_writable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(self.validator, "_is_writable", lambda _path: False)
        with pytest.raises(ValidationError, match="No write permission"):
            self.validator.validate_log_file_path(tmp_path / "app.log")

    def test_log_path_cannot_be_directory(self, tmp_path):
        with pytest.raises(ValidationError, match="path is a directory"):
            self.validator.validate_log_file_path(tmp_path)

    def test_existing_log_file_must_be_writable(self, tmp_path, monkeypatch):
        log_file = tmp_path / "app.log"
        log_file.touch()
        monkeypatch.setattr(self.validator, "_is_writable", lambda path: path != log_file)
        with pytest.raises(ValidationError, match="not writable"):
            self.validator.validate_log_file_path(log_file)

    def test_non_regular_log_path_is_rejected(self, tmp_path, monkeypatch):
        log_file = tmp_path / "app.log"
        log_file.touch()
        original_is_file = Path.is_file
        monkeypatch.setattr(Path, "is_file", lambda path: False if path == log_file else original_is_file(path))
        with pytest.raises(ValidationError, match="not a regular file"):
            self.validator.validate_log_file_path(log_file)

    def test_log_path_os_error_is_wrapped(self):
        path = Mock(spec=Path)
        path.resolve.side_effect = OSError("broken")
        with pytest.raises(ValidationError, match="Invalid log file path"):
            self.validator.validate_log_file_path(path)


class TestValidationHelpers:
    def setup_method(self):
        self.validator = InputValidator()

    @pytest.mark.parametrize("ref", ["", ".main", "main.", "bad ref", "bad..ref", "bad\x7fref"])
    def test_invalid_git_refs(self, ref):
        assert self.validator._is_valid_git_ref(ref) is False

    def test_valid_git_ref(self):
        assert self.validator._is_valid_git_ref("feature/topic") is True

    @pytest.mark.parametrize("path", ["bad\x00path", "bad\\path", "/absolute", "a//b", "a/./b", "a/../b"])
    def test_invalid_repository_paths(self, path):
        assert self.validator._is_valid_path(path) is False
        with pytest.raises(ValidationError):
            self.validator.validate_repository_path(path)

    def test_empty_repository_path(self):
        assert self.validator._is_valid_path("") is True
        assert self.validator.validate_repository_path("") == ""

    def test_is_writable_file_directory_and_other(self, tmp_path):
        file = tmp_path / "file"
        file.write_text("content")
        assert self.validator._is_writable(file) is True
        assert self.validator._is_writable(tmp_path) is True

        missing = tmp_path / "missing"
        assert self.validator._is_writable(missing) is False

    def test_is_writable_handles_touch_and_path_errors(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "touch", Mock(side_effect=OSError("denied")))
        assert self.validator._is_writable(tmp_path) is False

        path = Mock(spec=Path)
        path.is_file.side_effect = OSError("broken")
        assert self.validator._is_writable(path) is False
