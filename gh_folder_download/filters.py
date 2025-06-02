"""
File filtering system for gh-folder-download.
"""

import fnmatch
import re
from pathlib import Path

from github.ContentFile import ContentFile

from .config import FilterConfig
from .logger import get_logger


class FileFilter:
    """Advanced file filtering system."""

    def __init__(self, config: FilterConfig):
        """
        Initialize file filter with configuration.

        Args:
            config: Filter configuration
        """
        self.config = config
        self.logger = get_logger()

        # Compile patterns for better performance
        self.include_patterns = [
            self._compile_pattern(p) for p in config.include_patterns
        ]
        self.exclude_patterns = [
            self._compile_pattern(p) for p in config.exclude_patterns
        ]

        # Load gitignore rules if requested
        self.gitignore_rules: list[str] = []
        if config.respect_gitignore:
            self.gitignore_rules = self._load_gitignore_patterns()

        # Binary file extensions (common binary file types)
        self.binary_extensions = {
            # Images
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".tiff",
            ".svg",
            ".ico",
            ".webp",
            # Videos
            ".mp4",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".mkv",
            ".m4v",
            # Audio
            ".mp3",
            ".wav",
            ".flac",
            ".aac",
            ".ogg",
            ".wma",
            ".m4a",
            # Archives
            ".zip",
            ".rar",
            ".7z",
            ".tar",
            ".gz",
            ".bz2",
            ".xz",
            ".lzma",
            # Documents
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".odt",
            ".ods",
            ".odp",
            # Executables
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".bin",
            ".app",
            ".deb",
            ".rpm",
            ".msi",
            # Fonts
            ".ttf",
            ".otf",
            ".woff",
            ".woff2",
            ".eot",
            # Others
            ".db",
            ".sqlite",
            ".dat",
            ".cache",
            ".tmp",
            ".log",
            ".pid",
            ".lock",
            ".pyc",
            ".pyo",
            ".class",
            ".o",
            ".obj",
            ".lib",
            ".a",
        }

        self.logger.debug(
            f"File filter initialized with {len(self.include_patterns)} include patterns, "
            f"{len(self.exclude_patterns)} exclude patterns"
        )

    def should_include_file(
        self,
        file_path: str,
        file_size: int | None = None,
        content_file: ContentFile | None = None,
    ) -> bool:
        """
        Determine if a file should be included based on all filters.

        Args:
            file_path: Path of the file relative to repository root
            file_size: Size of the file in bytes (optional)
            content_file: GitHub ContentFile object (optional)

        Returns:
            True if file should be included, False otherwise
        """
        # Apply filters in order of computational cost (cheap to expensive)

        # 1. Extension filters (cheapest)
        if not self._check_extension_filters(file_path):
            self.logger.debug(f"File excluded by extension filter: {file_path}")
            return False

        # 2. Pattern filters
        if not self._check_pattern_filters(file_path):
            self.logger.debug(f"File excluded by pattern filter: {file_path}")
            return False

        # 3. Size filters
        if not self._check_size_filters(file_size):
            self.logger.debug(
                f"File excluded by size filter: {file_path} ({file_size} bytes)"
            )
            return False

        # 4. Binary file filter
        if not self._check_binary_filter(file_path, content_file):
            self.logger.debug(f"File excluded by binary filter: {file_path}")
            return False

        # 5. Large file filter
        if not self._check_large_file_filter(file_size):
            self.logger.debug(
                f"File excluded by large file filter: {file_path} ({file_size} bytes)"
            )
            return False

        # 6. Gitignore filters (most expensive)
        if not self._check_gitignore_filters(file_path):
            self.logger.debug(f"File excluded by gitignore filter: {file_path}")
            return False

        return True

    def _check_extension_filters(self, file_path: str) -> bool:
        """Check extension include/exclude filters."""
        file_ext = Path(file_path).suffix.lower()

        # If include extensions are specified, file must match one of them
        if self.config.include_extensions:
            include_match = any(
                file_ext == ext.lower() for ext in self.config.include_extensions
            )
            if not include_match:
                return False

        # If exclude extensions are specified, file must not match any of them
        if self.config.exclude_extensions:
            exclude_match = any(
                file_ext == ext.lower() for ext in self.config.exclude_extensions
            )
            if exclude_match:
                return False

        return True

    def _check_pattern_filters(self, file_path: str) -> bool:
        """Check pattern include/exclude filters."""
        # If include patterns are specified, file must match at least one
        if self.include_patterns:
            include_match = any(
                pattern.match(file_path) for pattern in self.include_patterns
            )
            if not include_match:
                return False

        # If exclude patterns are specified, file must not match any
        if self.exclude_patterns:
            exclude_match = any(
                pattern.match(file_path) for pattern in self.exclude_patterns
            )
            if exclude_match:
                return False

        return True

    def _check_size_filters(self, file_size: int | None) -> bool:
        """Check file size filters."""
        if file_size is None:
            return True  # Can't filter if size is unknown

        # Check minimum size
        if self.config.min_size_bytes is not None:
            if file_size < self.config.min_size_bytes:
                return False

        # Check maximum size
        if self.config.max_size_bytes is not None:
            if file_size > self.config.max_size_bytes:
                return False

        return True

    def _check_binary_filter(
        self, file_path: str, content_file: ContentFile | None = None
    ) -> bool:
        """Check if file should be excluded as binary."""
        if not self.config.exclude_binary:
            return True

        # Check by extension first (fast)
        file_ext = Path(file_path).suffix.lower()
        if file_ext in self.binary_extensions:
            return False

        # Check GitHub's file type detection if available
        if content_file and hasattr(content_file, "type"):
            if content_file.type == "file" and self._is_likely_binary_name(file_path):
                return False

        return True

    def _check_large_file_filter(self, file_size: int | None) -> bool:
        """Check large file filter (10MB default)."""
        if not self.config.exclude_large_files:
            return True

        if file_size is None:
            return True  # Can't filter if size is unknown

        # 10MB threshold
        large_file_threshold = 10 * 1024 * 1024
        return file_size <= large_file_threshold

    def _check_gitignore_filters(self, file_path: str) -> bool:
        """Check gitignore patterns."""
        if not self.config.respect_gitignore or not self.gitignore_rules:
            return True

        # Check each gitignore pattern
        for pattern in self.gitignore_rules:
            if self._matches_gitignore_pattern(file_path, pattern):
                return False

        return True

    def _compile_pattern(self, pattern: str) -> re.Pattern:
        """Convert glob pattern to regex for efficient matching."""
        # Convert glob patterns to regex
        regex_pattern = fnmatch.translate(pattern)
        return re.compile(regex_pattern)

    def _load_gitignore_patterns(self) -> list[str]:
        """Load gitignore patterns from common gitignore rules."""
        # Since we're downloading from GitHub, we can't access the actual .gitignore file
        # So we use common gitignore patterns
        common_patterns = [
            # Python
            "__pycache__/**",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".Python",
            "build/**",
            "develop-eggs/**",
            "dist/**",
            "downloads/**",
            "eggs/**",
            ".eggs/**",
            "lib/**",
            "lib64/**",
            "parts/**",
            "sdist/**",
            "var/**",
            "wheels/**",
            "*.egg-info/**",
            ".installed.cfg",
            "*.egg",
            # Node.js
            "node_modules/**",
            "npm-debug.log*",
            "yarn-debug.log*",
            "yarn-error.log*",
            ".npm",
            ".eslintcache",
            # IDEs
            ".vscode/**",
            ".idea/**",
            "*.swp",
            "*.swo",
            "*~",
            # OS
            ".DS_Store",
            "Thumbs.db",
            "ehthumbs.db",
            "Desktop.ini",
            # Git
            ".git/**",
            ".gitignore",
            # Logs
            "*.log",
            "logs/**",
            # Temporary files
            "*.tmp",
            "*.temp",
            ".cache/**",
            ".pytest_cache/**",
        ]

        self.logger.debug(f"Loaded {len(common_patterns)} common gitignore patterns")
        return common_patterns

    def _matches_gitignore_pattern(self, file_path: str, pattern: str) -> bool:
        """Check if file path matches a gitignore pattern."""
        # Remove leading/trailing whitespace and comments
        pattern = pattern.strip()
        if not pattern or pattern.startswith("#"):
            return False

        # Handle negation patterns (starting with !)
        if pattern.startswith("!"):
            return False  # We don't support negation for simplicity

        # Use fnmatch for glob-style matching
        return fnmatch.fnmatch(file_path, pattern)

    def _is_likely_binary_name(self, file_path: str) -> bool:
        """Check if filename suggests it's a binary file."""
        filename = Path(file_path).name.lower()

        # Files without extensions in certain directories might be binaries
        if "." not in filename:
            path_parts = Path(file_path).parts
            if any(part in ["bin", "sbin", "libexec"] for part in path_parts):
                return True

        return False

    def get_filter_summary(self) -> dict:
        """Get a summary of active filters."""
        return {
            "include_extensions": self.config.include_extensions,
            "exclude_extensions": self.config.exclude_extensions,
            "include_patterns": self.config.include_patterns,
            "exclude_patterns": self.config.exclude_patterns,
            "min_size_bytes": self.config.min_size_bytes,
            "max_size_bytes": self.config.max_size_bytes,
            "exclude_binary": self.config.exclude_binary,
            "exclude_large_files": self.config.exclude_large_files,
            "respect_gitignore": self.config.respect_gitignore,
            "gitignore_rules_count": len(self.gitignore_rules)
            if self.config.respect_gitignore
            else 0,
        }


class FilterPresets:
    """Predefined filter presets for common use cases."""

    @staticmethod
    def code_only() -> FilterConfig:
        """Filter to include only source code files."""
        return FilterConfig(
            include_extensions=[
                ".py",
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".java",
                ".c",
                ".cpp",
                ".h",
                ".hpp",
                ".cs",
                ".php",
                ".rb",
                ".go",
                ".rs",
                ".swift",
                ".kt",
                ".scala",
                ".clj",
                ".sh",
                ".bash",
                ".zsh",
                ".fish",
                ".ps1",
                ".bat",
                ".cmd",
                ".html",
                ".css",
                ".scss",
                ".sass",
                ".less",
                ".vue",
                ".svelte",
                ".sql",
                ".r",
                ".m",
                ".mm",
                ".perl",
                ".pl",
                ".lua",
                ".dart",
                ".yaml",
                ".yml",
                ".json",
                ".xml",
                ".toml",
                ".ini",
                ".cfg",
                ".conf",
                ".md",
                ".rst",
                ".txt",
                ".cmake",
                ".makefile",
                ".dockerfile",
            ],
            exclude_binary=True,
            exclude_large_files=True,
            respect_gitignore=True,
        )

    @staticmethod
    def documentation_only() -> FilterConfig:
        """Filter to include only documentation files."""
        return FilterConfig(
            include_extensions=[
                ".md",
                ".rst",
                ".txt",
                ".pdf",
                ".html",
                ".tex",
                ".adoc",
                ".org",
            ],
            include_patterns=[
                "docs/**",
                "documentation/**",
                "README*",
                "CHANGELOG*",
                "LICENSE*",
                "CONTRIBUTING*",
                "AUTHORS*",
                "CREDITS*",
            ],
            max_size_bytes=10 * 1024 * 1024,  # 10MB max for docs
        )

    @staticmethod
    def config_only() -> FilterConfig:
        """Filter to include only configuration files."""
        return FilterConfig(
            include_extensions=[
                ".yaml",
                ".yml",
                ".json",
                ".xml",
                ".toml",
                ".ini",
                ".cfg",
                ".conf",
                ".env",
                ".properties",
                ".settings",
                ".config",
            ],
            include_patterns=[
                "*.config.*",
                "config/**",
                "configs/**",
                "settings/**",
                ".github/**",
                ".vscode/**",
                ".idea/**",
                "docker-compose.*",
                "Dockerfile*",
                "Makefile*",
                "CMakeLists.txt",
            ],
            max_size_bytes=1024 * 1024,  # 1MB max for config files
        )

    @staticmethod
    def no_tests() -> FilterConfig:
        """Filter to exclude test files."""
        return FilterConfig(
            exclude_patterns=[
                "**/test/**",
                "**/tests/**",
                "**/*_test.*",
                "**/*test*",
                "**/spec/**",
                "**/*_spec.*",
                "**/*spec*",
                "**/__tests__/**",
                "**/test_*.py",
                "**/*Test.java",
                "**/testing/**",
                "**/testdata/**",
            ],
        )

    @staticmethod
    def small_files_only() -> FilterConfig:
        """Filter to include only small files (under 1MB)."""
        return FilterConfig(
            max_size_bytes=1024 * 1024,  # 1MB
            exclude_binary=True,
        )

    @staticmethod
    def minimal() -> FilterConfig:
        """Minimal filter for fastest downloads."""
        return FilterConfig(
            include_extensions=[".md", ".txt", ".py", ".js", ".html", ".css"],
            max_size_bytes=512 * 1024,  # 512KB
            exclude_binary=True,
            exclude_large_files=True,
            respect_gitignore=True,
        )


def create_file_filter(config: FilterConfig) -> FileFilter:
    """Create a file filter with the given configuration."""
    return FileFilter(config)


def get_preset_filter(preset_name: str) -> FilterConfig:
    """
    Get a predefined filter preset.

    Args:
        preset_name: Name of the preset

    Returns:
        FilterConfig for the preset

    Raises:
        ValueError: If preset name is not recognized
    """
    presets = {
        "code-only": FilterPresets.code_only,
        "docs-only": FilterPresets.documentation_only,
        "config-only": FilterPresets.config_only,
        "no-tests": FilterPresets.no_tests,
        "small-files": FilterPresets.small_files_only,
        "minimal": FilterPresets.minimal,
    }

    if preset_name not in presets:
        available = ", ".join(presets.keys())
        raise ValueError(
            f"Unknown preset '{preset_name}'. Available presets: {available}"
        )

    return presets[preset_name]()
