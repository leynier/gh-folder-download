"""Tests for file filtering system."""

import pytest

from gh_folder_download.config import FilterConfig
from gh_folder_download.filters import FileFilter, FilterPresets, get_preset_filter


@pytest.fixture
def default_filter():
    """FileFilter with default configuration."""
    return FileFilter(FilterConfig())


@pytest.fixture
def extension_include_filter():
    """FileFilter with extension include filter."""
    config = FilterConfig(include_extensions=[".py", ".md"])
    return FileFilter(config)


@pytest.fixture
def extension_exclude_filter():
    """FileFilter with extension exclude filter."""
    config = FilterConfig(exclude_extensions=[".log", ".tmp"])
    return FileFilter(config)


class TestExtensionFilters:
    """Tests for extension-based filtering."""

    def test_include_extensions_match(self, extension_include_filter):
        """Test files with included extensions are included."""
        assert extension_include_filter.should_include_file("src/main.py") is True
        assert extension_include_filter.should_include_file("docs/readme.md") is True

    def test_include_extensions_no_match(self, extension_include_filter):
        """Test files without included extensions are excluded."""
        assert extension_include_filter.should_include_file("config.json") is False
        assert extension_include_filter.should_include_file("script.sh") is False

    def test_exclude_extensions_match(self, extension_exclude_filter):
        """Test files with excluded extensions are excluded."""
        assert extension_exclude_filter.should_include_file("debug.log") is False
        assert extension_exclude_filter.should_include_file("temp.tmp") is False

    def test_exclude_extensions_no_match(self, extension_exclude_filter):
        """Test files without excluded extensions are included."""
        assert extension_exclude_filter.should_include_file("main.py") is True
        assert extension_exclude_filter.should_include_file("readme.md") is True


class TestPatternFilters:
    """Tests for pattern-based filtering."""

    def test_include_patterns(self):
        """Test include patterns filter correctly."""
        config = FilterConfig(include_patterns=["src/**", "docs/**"])
        file_filter = FileFilter(config)

        assert file_filter.should_include_file("src/main.py") is True
        assert file_filter.should_include_file("docs/readme.md") is True
        assert file_filter.should_include_file("tests/test_main.py") is False

    def test_exclude_patterns(self):
        """Test exclude patterns filter correctly."""
        config = FilterConfig(exclude_patterns=["**/test/**", "**/*.pyc"])
        file_filter = FileFilter(config)

        assert file_filter.should_include_file("src/test/test_main.py") is False
        assert file_filter.should_include_file("src/main.pyc") is False
        assert file_filter.should_include_file("src/main.py") is True


class TestSizeFilters:
    """Tests for size-based filtering."""

    def test_min_size_filter(self):
        """Test minimum size filter."""
        config = FilterConfig(min_size_bytes=100)
        file_filter = FileFilter(config)

        assert file_filter.should_include_file("small.txt", file_size=50) is False
        assert file_filter.should_include_file("large.txt", file_size=200) is True

    def test_max_size_filter(self):
        """Test maximum size filter."""
        config = FilterConfig(max_size_bytes=1000)
        file_filter = FileFilter(config)

        assert file_filter.should_include_file("small.txt", file_size=500) is True
        assert file_filter.should_include_file("large.txt", file_size=2000) is False

    def test_size_filter_none_size_included(self):
        """Test files with unknown size are included."""
        config = FilterConfig(min_size_bytes=100)
        file_filter = FileFilter(config)

        # When size is None, file should be included (can't filter)
        assert file_filter.should_include_file("unknown.txt", file_size=None) is True


class TestBinaryFilter:
    """Tests for binary file filtering."""

    def test_exclude_binary_by_extension(self):
        """Test binary files are excluded by extension."""
        config = FilterConfig(exclude_binary=True)
        file_filter = FileFilter(config)

        assert file_filter.should_include_file("image.png") is False
        assert file_filter.should_include_file("app.exe") is False
        assert file_filter.should_include_file("archive.zip") is False

    def test_include_text_files(self):
        """Test text files are included when binary filter is on."""
        config = FilterConfig(exclude_binary=True)
        file_filter = FileFilter(config)

        assert file_filter.should_include_file("readme.md") is True
        assert file_filter.should_include_file("main.py") is True
        assert file_filter.should_include_file("config.json") is True


class TestLargeFileFilter:
    """Tests for large file filtering."""

    def test_exclude_large_files(self):
        """Test files over 10MB are excluded."""
        config = FilterConfig(exclude_large_files=True)
        file_filter = FileFilter(config)

        # 10MB = 10 * 1024 * 1024 = 10485760 bytes
        assert file_filter.should_include_file("small.txt", file_size=1000) is True
        assert file_filter.should_include_file("large.bin", file_size=20_000_000) is False

    def test_large_file_threshold(self):
        """Test exact threshold for large files."""
        config = FilterConfig(exclude_large_files=True)
        file_filter = FileFilter(config)

        # Just under 10MB
        assert file_filter.should_include_file("file.txt", file_size=10_485_759) is True
        # Just over 10MB
        assert file_filter.should_include_file("file.txt", file_size=10_485_761) is False


class TestCombinedFilters:
    """Tests for multiple filters applied together."""

    def test_combined_extension_and_size(self):
        """Test extension and size filters together."""
        config = FilterConfig(
            include_extensions=[".py"],
            max_size_bytes=1000,
        )
        file_filter = FileFilter(config)

        # Matches extension, under size limit
        assert file_filter.should_include_file("main.py", file_size=500) is True
        # Matches extension, over size limit
        assert file_filter.should_include_file("main.py", file_size=2000) is False
        # Wrong extension
        assert file_filter.should_include_file("readme.md", file_size=500) is False

    def test_combined_include_exclude_patterns(self):
        """Test include and exclude patterns together."""
        config = FilterConfig(
            include_patterns=["src/**"],
            exclude_patterns=["**/*_test.py"],
        )
        file_filter = FileFilter(config)

        assert file_filter.should_include_file("src/main.py") is True
        assert file_filter.should_include_file("src/main_test.py") is False


class TestFilterPresets:
    """Tests for filter presets."""

    def test_code_only_preset(self):
        """Test code_only preset includes code files."""
        config = FilterPresets.code_only()
        file_filter = FileFilter(config)

        assert file_filter.should_include_file("main.py") is True
        assert file_filter.should_include_file("app.js") is True
        assert file_filter.should_include_file("image.png") is False

    def test_documentation_only_preset(self):
        """Test documentation_only preset."""
        config = FilterPresets.documentation_only()
        file_filter = FileFilter(config)

        # Files matching include patterns
        assert file_filter.should_include_file("docs/guide.md") is True
        assert file_filter.should_include_file("README.md") is True
        # File not matching patterns
        assert file_filter.should_include_file("main.py") is False

    def test_get_preset_filter_valid(self):
        """Test get_preset_filter with valid preset name."""
        config = get_preset_filter("code-only")
        assert config is not None
        assert len(config.include_extensions) > 0

    def test_get_preset_filter_invalid(self):
        """Test get_preset_filter with invalid preset name."""
        with pytest.raises(ValueError):
            get_preset_filter("nonexistent_preset")


class TestGetFilterSummary:
    """Tests for filter summary generation."""

    def test_summary_with_filters(self):
        """Test summary includes active filters."""
        config = FilterConfig(
            include_extensions=[".py"],
            exclude_patterns=["**/test/**"],
        )
        file_filter = FileFilter(config)

        summary = file_filter.get_filter_summary()

        assert "include_extensions" in summary or ".py" in str(summary)

    def test_summary_empty_config(self, default_filter):
        """Test summary with no filters."""
        summary = default_filter.get_filter_summary()

        assert summary is not None
