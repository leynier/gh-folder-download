"""
Configuration management for gh-folder-download.
"""

import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, validator

from .logger import get_logger


class DownloadConfig(BaseModel):
    """Download-related configuration."""

    max_concurrent: int = Field(
        default=5, ge=1, le=20, description="Maximum concurrent downloads"
    )
    timeout: int = Field(
        default=30, ge=5, le=300, description="Download timeout in seconds"
    )
    chunk_size: int = Field(
        default=8192, ge=1024, le=65536, description="Download chunk size"
    )
    max_retries: int = Field(
        default=3, ge=1, le=10, description="Maximum retry attempts"
    )
    retry_delay: float = Field(
        default=1.0, ge=0.1, le=30.0, description="Base retry delay"
    )
    verify_integrity: bool = Field(default=True, description="Verify file integrity")
    parallel_downloads: bool = Field(
        default=True, description="Enable parallel downloads"
    )


class CacheConfig(BaseModel):
    """Cache-related configuration."""

    enabled: bool = Field(default=True, description="Enable caching")
    max_size_gb: float = Field(
        default=5.0, ge=0.1, le=100.0, description="Maximum cache size in GB"
    )
    max_age_days: int = Field(
        default=30, ge=1, le=365, description="Maximum cache age in days"
    )
    auto_cleanup: bool = Field(
        default=True, description="Enable automatic cache cleanup"
    )


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    enabled: bool = Field(default=True, description="Enable rate limiting")
    buffer: int = Field(default=100, ge=10, le=1000, description="Rate limit buffer")
    aggressive_mode: bool = Field(
        default=False, description="Use aggressive rate limiting"
    )


class FilterConfig(BaseModel):
    """File filtering configuration."""

    # Extension filters
    include_extensions: list[str] = Field(
        default_factory=list, description="Include only these extensions"
    )
    exclude_extensions: list[str] = Field(
        default_factory=list, description="Exclude these extensions"
    )

    # Size filters
    min_size_bytes: int | None = Field(
        default=None, ge=0, description="Minimum file size in bytes"
    )
    max_size_bytes: int | None = Field(
        default=None, ge=0, description="Maximum file size in bytes"
    )

    # Pattern filters
    include_patterns: list[str] = Field(
        default_factory=list, description="Include files matching these patterns"
    )
    exclude_patterns: list[str] = Field(
        default_factory=list, description="Exclude files matching these patterns"
    )

    # Special filters
    exclude_binary: bool = Field(default=False, description="Exclude binary files")
    exclude_large_files: bool = Field(
        default=False, description="Exclude files larger than 10MB"
    )
    respect_gitignore: bool = Field(
        default=False, description="Respect .gitignore rules"
    )

    @validator("include_extensions", "exclude_extensions", pre=True)
    def normalize_extensions(cls, v):
        """Normalize extensions to start with a dot."""
        if isinstance(v, str):
            v = [v]
        return [ext if ext.startswith(".") else f".{ext}" for ext in v]


class PathConfig(BaseModel):
    """Path-related configuration."""

    default_output: str = Field(default=".", description="Default output directory")
    create_subdirs: bool = Field(
        default=True, description="Create subdirectories for organization"
    )
    preserve_structure: bool = Field(
        default=True, description="Preserve repository structure"
    )


class UIConfig(BaseModel):
    """User interface configuration."""

    show_progress: bool = Field(default=True, description="Show progress bars")
    verbosity: str = Field(default="INFO", description="Log level")
    use_colors: bool = Field(default=True, description="Use colored output")
    quiet_mode: bool = Field(default=False, description="Quiet mode")


class GHFolderDownloadConfig(BaseModel):
    """Main configuration model."""

    # Authentication
    github_token: str | None = Field(
        default=None, description="GitHub personal access token"
    )

    # Main sections
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    @validator("github_token", pre=True)
    def validate_github_token(cls, v):
        """Validate GitHub token format."""
        if not v:
            return v

        if not isinstance(v, str):
            raise ValueError("GitHub token must be a string")

        v = v.strip()
        if not v:
            return None

        # Check for valid GitHub token formats

        is_valid_format = False

        if v.startswith("ghp_") and len(v) == 40:
            # Classic personal access token
            is_valid_format = True
        elif v.startswith("github_pat_") and len(v) >= 50:
            # Fine-grained personal access token
            is_valid_format = True
        elif len(v) == 40:
            # Legacy format - must be hexadecimal
            is_valid_format = bool(re.match(r"^[a-fA-F0-9]{40}$", v))

        if not is_valid_format:
            raise ValueError(
                "Invalid GitHub token format. Expected: classic (ghp_...), "
                "fine-grained (github_pat_...), or legacy (40-char hex) token."
            )

        return v


class ConfigManager:
    """Configuration manager for gh-folder-download."""

    CONFIG_FILENAME = "gh-folder-download.yaml"
    ENV_PREFIX = "GH_FOLDER_DOWNLOAD_"

    def __init__(self):
        """Initialize configuration manager."""
        self.logger = get_logger()
        self.config: GHFolderDownloadConfig = GHFolderDownloadConfig()
        self.config_file_path: Path | None = None

    def get_config_paths(self) -> list[Path]:
        """Get possible configuration file paths in order of priority."""
        paths = []

        # 1. Current directory
        paths.append(Path.cwd() / self.CONFIG_FILENAME)

        # 2. User config directory
        if sys.platform == "win32":
            config_dir = Path(os.environ.get("APPDATA", "")) / "gh-folder-download"
        else:
            config_dir = Path.home() / ".config" / "gh-folder-download"
        paths.append(config_dir / self.CONFIG_FILENAME)

        # 3. User home directory
        paths.append(Path.home() / f".{self.CONFIG_FILENAME}")

        return paths

    def load_config(self, config_file: Path | None = None) -> GHFolderDownloadConfig:
        """
        Load configuration from file, environment variables, and defaults.

        Args:
            config_file: Specific config file path (optional)

        Returns:
            Loaded configuration
        """
        # Start with defaults
        config_data = {}

        # Load from file
        if config_file:
            config_data.update(self._load_from_file(config_file))
            self.config_file_path = config_file
        else:
            # Try default locations
            for path in self.get_config_paths():
                if path.exists():
                    config_data.update(self._load_from_file(path))
                    self.config_file_path = path
                    break

        # Override with environment variables
        config_data.update(self._load_from_env())

        # Create and validate configuration
        try:
            self.config = GHFolderDownloadConfig(**config_data)
            self.logger.debug("Configuration loaded successfully")
            if self.config_file_path:
                self.logger.debug(f"Config file: {self.config_file_path}")
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"Invalid configuration: {e}")
            self.config = GHFolderDownloadConfig()

        return self.config

    def _load_from_file(self, file_path: Path) -> dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            self.logger.debug(f"Loading config from: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.logger.debug(f"Loaded {len(data)} configuration sections")
            return data
        except (OSError, IOError, yaml.YAMLError) as e:
            self.logger.warning(f"Failed to load config from {file_path}: {e}")
            return {}

    def _load_from_env(self) -> dict[str, Any]:
        """Load configuration from environment variables."""
        config_data = {}
        env_mappings = {
            f"{self.ENV_PREFIX}GITHUB_TOKEN": "github_token",
            f"{self.ENV_PREFIX}MAX_CONCURRENT": "download.max_concurrent",
            f"{self.ENV_PREFIX}TIMEOUT": "download.timeout",
            f"{self.ENV_PREFIX}MAX_RETRIES": "download.max_retries",
            f"{self.ENV_PREFIX}CACHE_ENABLED": "cache.enabled",
            f"{self.ENV_PREFIX}CACHE_SIZE_GB": "cache.max_size_gb",
            f"{self.ENV_PREFIX}RATE_LIMIT_ENABLED": "rate_limit.enabled",
            f"{self.ENV_PREFIX}RATE_LIMIT_BUFFER": "rate_limit.buffer",
            f"{self.ENV_PREFIX}DEFAULT_OUTPUT": "paths.default_output",
            f"{self.ENV_PREFIX}SHOW_PROGRESS": "ui.show_progress",
            f"{self.ENV_PREFIX}VERBOSITY": "ui.verbosity",
            f"{self.ENV_PREFIX}QUIET": "ui.quiet_mode",
        }

        for env_var, config_path in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                self._set_nested_value(
                    config_data, config_path, self._convert_env_value(value)
                )

        return config_data

    def _set_nested_value(self, data: dict[str, Any], path: str, value: Any) -> None:
        """Set a nested value in a dictionary using dot notation."""
        keys = path.split(".")
        current = data

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def _convert_env_value(self, value: str) -> Any:
        """Convert environment variable string to appropriate type."""
        if not value:
            return value

        # Boolean values
        if value.lower() in ("true", "1", "yes", "on"):
            return True
        elif value.lower() in ("false", "0", "no", "off"):
            return False

        # Numeric values
        try:
            # Check for float first (contains decimal point)
            if "." in value:
                parsed_float = float(value)
                # Ensure it's a valid number (not NaN or infinity)
                if not (
                    parsed_float != parsed_float or abs(parsed_float) == float("inf")
                ):
                    return parsed_float
            else:
                parsed_int = int(value)
                return parsed_int
        except (ValueError, OverflowError):
            # If numeric parsing fails, continue to return as string
            pass

        # String value (default)
        return value

    def save_config(self, file_path: Path | None = None) -> bool:
        """
        Save current configuration to file.

        Args:
            file_path: Optional specific path to save to

        Returns:
            True if saved successfully
        """
        if file_path is None:
            file_path = self.config_file_path or (Path.cwd() / self.CONFIG_FILENAME)

        try:
            # Create directory if it doesn't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Convert config to dict, excluding defaults for cleaner file
            config_dict = self.config.model_dump(exclude_defaults=True)

            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    config_dict, f, default_flow_style=False, sort_keys=True, indent=2
                )

            self.logger.info(f"Configuration saved to: {file_path}")
            return True

        except (OSError, IOError, yaml.YAMLError) as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False

    def create_sample_config(self, file_path: Path | None = None) -> bool:
        """
        Create a sample configuration file with comments.

        Args:
            file_path: Path to create sample config

        Returns:
            True if created successfully
        """
        if file_path is None:
            file_path = Path.cwd() / "gh-folder-download.sample.yaml"

        sample_config = """# gh-folder-download Configuration File
# This file contains all available configuration options with their default values.
# Remove the comments (#) and modify values as needed.

# GitHub authentication
# github_token: "your_github_token_here"

# Download settings
download:
  max_concurrent: 5          # Maximum parallel downloads (1-20)
  timeout: 30               # Download timeout in seconds (5-300)
  chunk_size: 8192          # Download chunk size in bytes (1024-65536)
  max_retries: 3            # Maximum retry attempts (1-10)
  retry_delay: 1.0          # Base retry delay in seconds (0.1-30.0)
  verify_integrity: true    # Verify file integrity after download
  parallel_downloads: true  # Enable parallel downloads

# Cache settings
cache:
  enabled: true             # Enable file caching
  max_size_gb: 5.0         # Maximum cache size in GB (0.1-100.0)
  max_age_days: 30         # Maximum cache age in days (1-365)
  auto_cleanup: true       # Enable automatic cache cleanup

# Rate limiting settings
rate_limit:
  enabled: true            # Enable GitHub API rate limiting
  buffer: 100              # Rate limit buffer (10-1000)
  aggressive_mode: false   # Use aggressive rate limiting

# File filtering settings
filters:
  # Extension filters (include/exclude specific file types)
  # include_extensions: [".py", ".js", ".md"]
  # exclude_extensions: [".log", ".tmp"]

  # Size filters
  # min_size_bytes: 1024      # Minimum file size in bytes
  # max_size_bytes: 10485760  # Maximum file size in bytes (10MB)

  # Pattern filters (glob patterns)
  # include_patterns: ["src/**", "docs/**"]
  # exclude_patterns: ["**/test/**", "**/*.pyc"]

  # Special filters
  exclude_binary: false        # Exclude binary files
  exclude_large_files: false   # Exclude files larger than 10MB
  respect_gitignore: false     # Respect .gitignore rules

# Path settings
paths:
  default_output: "."          # Default output directory
  create_subdirs: true         # Create subdirectories for organization
  preserve_structure: true     # Preserve repository directory structure

# User interface settings
ui:
  show_progress: true          # Show progress bars
  verbosity: "INFO"           # Log level (DEBUG, INFO, WARNING, ERROR)
  use_colors: true            # Use colored output
  quiet_mode: false           # Enable quiet mode
"""

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(sample_config)
            self.logger.info(f"Sample configuration created: {file_path}")
            return True
        except (OSError, IOError) as e:
            self.logger.error(f"Failed to create sample configuration: {e}")
            return False

    def get_effective_config(self) -> dict[str, Any]:
        """Get the effective configuration as a dictionary."""
        return self.config.model_dump()

    def validate_config(self) -> list[str]:
        """
        Validate current configuration and return list of issues.

        Returns:
            List of validation error messages
        """
        issues = []

        try:
            # This will raise ValidationError if invalid
            GHFolderDownloadConfig(**self.config.model_dump())
        except (ValueError, TypeError) as e:
            issues.append(f"Configuration validation failed: {e}")

        # Additional custom validations
        if self.config.download.max_concurrent > 20:
            issues.append("max_concurrent should not exceed 20 for optimal performance")

        if self.config.cache.max_size_gb > 50:
            issues.append(
                "cache size larger than 50GB may consume significant disk space"
            )

        return issues


# Global configuration instance
config_manager = ConfigManager()


def get_config() -> GHFolderDownloadConfig:
    """Get the current configuration."""
    return config_manager.config


def load_config(config_file: Path | None = None) -> GHFolderDownloadConfig:
    """Load configuration from file and environment."""
    return config_manager.load_config(config_file)


def save_config(file_path: Path | None = None) -> bool:
    """Save current configuration to file."""
    return config_manager.save_config(file_path)


def create_sample_config(file_path: Path | None = None) -> bool:
    """Create a sample configuration file."""
    return config_manager.create_sample_config(file_path)
