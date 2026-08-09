"""
Input validation utilities for gh-folder-download.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from .logger import get_logger


class ValidationError(Exception):
    """Custom exception for validation errors."""

    pass


@dataclass(frozen=True)
class ParsedGitHubURL:
    owner: str
    repository: str
    tree_segments: tuple[str, ...] = ()


class InputValidator:
    """Comprehensive input validation for gh-folder-download."""

    # GitHub URL patterns
    GITHUB_URL_PATTERN = re.compile(
        r"^https://github\.com/([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)(?:/tree/([a-zA-Z0-9._/-]+))?(?:/(.+))?$"
    )

    # Valid GitHub username/org pattern - must start and end with alphanumeric
    GITHUB_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$")

    def __init__(self):
        self.logger = get_logger()

    def validate_github_url(self, url: str) -> tuple[str, str, str | None, str]:
        """
        Validate and parse GitHub URL with enhanced validation.

        Returns:
            Tuple of (org, repo, branch, path)

        Raises:
            ValidationError: If URL is invalid
        """
        parsed_url = self.parse_github_url(url)
        branch = parsed_url.tree_segments[0] if parsed_url.tree_segments else None
        folder_path = "/".join(parsed_url.tree_segments[1:])
        return parsed_url.owner, parsed_url.repository, branch, folder_path

    def parse_github_url(self, url: str) -> ParsedGitHubURL:
        """Validate a URL while preserving all segments needed to resolve refs containing slashes."""
        self.logger.debug(f"Validating GitHub URL: {url}")

        if not isinstance(url, str):
            raise ValidationError("URL must be a string")

        if not url:
            raise ValidationError("URL cannot be empty")

        # Basic URL structure validation
        if not url.startswith("https://github.com/"):
            raise ValidationError("Invalid GitHub URL - must start with 'https://github.com/'")

        # Parse URL components
        try:
            parsed = urlparse(url)
            if parsed.netloc != "github.com":
                raise ValidationError("Invalid GitHub domain")
            if parsed.query or parsed.fragment:
                raise ValidationError("GitHub URL must not contain a query string or fragment")
        except Exception as e:
            raise ValidationError(f"Malformed URL: {e}") from e

        # Extract path components
        path_parts = [unquote(part) for part in parsed.path.strip("/").split("/")]

        if len(path_parts) < 2:
            raise ValidationError("Invalid GitHub URL - must include owner and repository")

        org = path_parts[0]
        repo = path_parts[1]
        if repo.endswith(".git"):
            repo = repo[:-4]

        # Validate org and repo names
        if not self.GITHUB_NAME_PATTERN.match(org):
            raise ValidationError(f"Invalid organization/user name: {org}")

        if not self.GITHUB_NAME_PATTERN.match(repo):
            raise ValidationError(f"Invalid repository name: {repo}")

        tree_segments: tuple[str, ...] = ()
        if len(path_parts) >= 3:
            if path_parts[2] != "tree" or len(path_parts) < 4:
                raise ValidationError("Invalid GitHub URL format - use /tree/ref/path for specific folders")
            tree_segments = tuple(path_parts[3:])
            if not all(self._is_valid_path(segment) for segment in tree_segments):
                raise ValidationError("Invalid branch, tag, or folder path")

        self.logger.debug(f"Validated URL - Org: {org}, Repo: {repo}, Tree: {tree_segments}")
        return ParsedGitHubURL(org, repo, tree_segments)

    def validate_output_path(
        self,
        output_path: Path,
        create_if_missing: bool = True,
    ) -> Path:
        """
        Validate output directory path.

        Args:
            output_path: Path to validate
            create_if_missing: Whether to create the directory if it doesn't exist

        Returns:
            Validated Path object

        Raises:
            ValidationError: If path is invalid or inaccessible
        """
        self.logger.debug(f"Validating output path: {output_path}")

        try:
            # Resolve to absolute path
            abs_path = output_path.resolve()

            # Check if parent directory exists and is writable
            parent = abs_path.parent
            if not parent.exists():
                if create_if_missing:
                    parent.mkdir(parents=True, exist_ok=True)
                    self.logger.debug(f"Created parent directory: {parent}")
                else:
                    raise ValidationError(f"Parent directory does not exist: {parent}")

            if not parent.is_dir():
                raise ValidationError(f"Parent path is not a directory: {parent}")

            # Check write permissions
            if not self._is_writable(parent):
                raise ValidationError(f"No write permission for directory: {parent}")

            # If output path exists, check if it's a directory
            if abs_path.exists() and not abs_path.is_dir():
                raise ValidationError(f"Output path exists but is not a directory: {abs_path}")

            self.logger.debug(f"Output path validated: {abs_path}")
            return abs_path

        except (OSError, PermissionError) as e:
            raise ValidationError(f"Invalid output path: {e}") from e

    def validate_github_token(self, token: str | None) -> str | None:
        """
        Validate GitHub token format and basic connectivity.

        Args:
            token: GitHub personal access token or None

        Returns:
            Validated token or None

        Raises:
            ValidationError: If token is invalid
        """
        if not token:
            self.logger.debug("No GitHub token provided")
            return None

        self.logger.debug("Validating GitHub token")

        # Basic format validation
        if not isinstance(token, str):
            raise ValidationError("GitHub token must be a string")

        token = token.strip()
        if not token:
            raise ValidationError("GitHub token cannot be empty")

        # GitHub token patterns
        # Classic personal access tokens: ghp_xxxx (40 chars total)
        # Fine-grained personal access tokens: github_pat_xxxx
        # Legacy tokens: 40-char hex strings
        is_valid_format = False

        if token.startswith(("ghp_", "gho_", "ghu_", "ghs_", "ghr_")) and len(token) >= 20:
            is_valid_format = True
        elif token.startswith("github_pat_") and len(token) >= 50:
            # Fine-grained personal access token
            is_valid_format = True
        elif len(token) == 40:
            # Legacy format - must be hexadecimal
            is_valid_format = bool(re.match(r"^[a-fA-F0-9]{40}$", token))

        if not is_valid_format:
            raise ValidationError(
                "Invalid GitHub token format. Expected: classic (ghp_...), "
                "fine-grained (github_pat_...), or legacy (40-char hex) token."
            )

        return token

    def validate_log_file_path(self, log_file: Path | None) -> Path | None:
        """
        Validate log file path.

        Args:
            log_file: Path for log file or None

        Returns:
            Validated Path object or None

        Raises:
            ValidationError: If path is invalid
        """
        if not log_file:
            return None

        self.logger.debug(f"Validating log file path: {log_file}")

        try:
            abs_path = log_file.resolve()

            # Check parent directory
            parent = abs_path.parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Created log directory: {parent}")

            if not parent.is_dir():
                raise ValidationError(f"Log file parent is not a directory: {parent}")

            if not self._is_writable(parent):
                raise ValidationError(f"No write permission for log directory: {parent}")

            # If log file exists, check if it's writable
            if abs_path.exists():
                if abs_path.is_dir():
                    raise ValidationError(f"Log file path is a directory: {abs_path}")
                if not abs_path.is_file():
                    raise ValidationError(f"Log file path is not a regular file: {abs_path}")
                if not self._is_writable(abs_path):
                    raise ValidationError(f"Log file is not writable: {abs_path}")

            self.logger.debug(f"Log file path validated: {abs_path}")
            return abs_path

        except (OSError, PermissionError) as e:
            raise ValidationError(f"Invalid log file path: {e}") from e

    def _is_valid_git_ref(self, ref: str) -> bool:
        """Check if a string is a valid Git reference name."""
        if not ref or ref.startswith(".") or ref.endswith("."):
            return False

        # Check for invalid characters
        invalid_chars = [" ", "~", "^", ":", "?", "*", "[", "\\", ".."]
        for char in invalid_chars:
            if char in ref:
                return False

        # Check for control characters
        return not any(ord(c) < 32 or ord(c) == 127 for c in ref)

    def _is_valid_path(self, path: str) -> bool:
        """Check if a string is a valid file path."""
        if not path:
            return True  # Empty path is valid (root)

        # Check for null bytes
        if "\x00" in path:
            return False

        if "\\" in path or path.startswith("/"):
            return False
        return all(part not in ("", ".", "..") for part in path.split("/"))

    def validate_repository_path(self, path: str) -> str:
        """Validate a repository-relative path supplied outside a GitHub URL."""
        if path and not self._is_valid_path(path):
            raise ValidationError(f"Invalid repository path: {path}")
        return path

    def _is_writable(self, path: Path) -> bool:
        """Check if a path is writable."""
        try:
            if path.is_file():
                return path.stat().st_mode & 0o200 != 0
            elif path.is_dir():
                # Try creating a temporary file
                test_file = path / ".write_test"
                try:
                    test_file.touch()
                    test_file.unlink()
                    return True
                except (OSError, PermissionError):
                    return False
            return False
        except (OSError, PermissionError):
            return False
