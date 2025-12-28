"""Tests for file integrity verification."""

import pytest

from gh_folder_download.integrity import FileIntegrityChecker, IntegrityError


@pytest.fixture
def temp_text_file(tmp_path):
    """Create a temporary text file for testing."""
    file = tmp_path / "test.txt"
    file.write_text("Hello, World!")
    return file


@pytest.fixture
def temp_binary_file(tmp_path):
    """Create a temporary binary file for testing."""
    file = tmp_path / "test.bin"
    file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
    return file


@pytest.fixture
def checker():
    """FileIntegrityChecker instance."""
    return FileIntegrityChecker()


class TestCalculateChecksums:
    """Tests for checksum calculation."""

    def test_calculate_checksums_returns_all_algorithms(self, checker, temp_text_file):
        """Test that checksums are returned for all algorithms."""
        checksums = checker.calculate_checksums(temp_text_file)

        assert "md5" in checksums
        assert "sha1" in checksums
        assert "sha256" in checksums

    def test_calculate_checksums_consistent(self, checker, temp_text_file):
        """Test that checksums are consistent across calls."""
        checksums1 = checker.calculate_checksums(temp_text_file)
        checksums2 = checker.calculate_checksums(temp_text_file)

        assert checksums1 == checksums2

    def test_calculate_checksums_file_not_found(self, checker, tmp_path):
        """Test that missing file raises IntegrityError."""
        missing_file = tmp_path / "missing.txt"

        with pytest.raises(IntegrityError) as exc_info:
            checker.calculate_checksums(missing_file)

        assert "does not exist" in str(exc_info.value)

    def test_calculate_checksums_directory_raises_error(self, checker, tmp_path):
        """Test that directory raises IntegrityError."""
        with pytest.raises(IntegrityError) as exc_info:
            checker.calculate_checksums(tmp_path)

        assert "not a file" in str(exc_info.value)


class TestVerifyFileSize:
    """Tests for file size verification."""

    def test_verify_file_size_match(self, checker, temp_text_file):
        """Test size verification passes when size matches."""
        expected_size = temp_text_file.stat().st_size
        result = checker.verify_file_size(temp_text_file, expected_size)

        assert result is True

    def test_verify_file_size_mismatch(self, checker, temp_text_file):
        """Test size verification raises error on mismatch."""
        wrong_size = temp_text_file.stat().st_size + 100

        with pytest.raises(IntegrityError) as exc_info:
            checker.verify_file_size(temp_text_file, wrong_size)

        assert "mismatch" in str(exc_info.value).lower()

    def test_verify_file_size_none_skips_check(self, checker, temp_text_file):
        """Test None expected size skips verification."""
        result = checker.verify_file_size(temp_text_file, None)

        assert result is True


class TestVerifyChecksum:
    """Tests for checksum verification."""

    def test_verify_checksum_match(self, checker, temp_text_file):
        """Test checksum verification passes when matching."""
        checksums = checker.calculate_checksums(temp_text_file)
        expected_sha256 = checksums["sha256"]

        result = checker.verify_checksum(temp_text_file, expected_sha256, "sha256")

        assert result is True

    def test_verify_checksum_mismatch(self, checker, temp_text_file):
        """Test checksum verification raises error on mismatch."""
        wrong_checksum = "a" * 64

        with pytest.raises(IntegrityError) as exc_info:
            checker.verify_checksum(temp_text_file, wrong_checksum, "sha256")

        assert "mismatch" in str(exc_info.value).lower()

    def test_verify_checksum_unsupported_algorithm(self, checker, temp_text_file):
        """Test unsupported algorithm raises error."""
        with pytest.raises(IntegrityError) as exc_info:
            checker.verify_checksum(temp_text_file, "dummy", "sha512")

        assert "unsupported" in str(exc_info.value).lower()


class TestVerifyFileContent:
    """Tests for content verification."""

    def test_verify_file_content_text_file(self, checker, temp_text_file):
        """Test content verification for text file."""
        result = checker.verify_file_content(temp_text_file)

        assert result["exists"] is True
        assert result["is_file"] is True
        assert result["is_readable"] is True
        assert result["appears_binary"] is False

    def test_verify_file_content_binary_file(self, checker, temp_binary_file):
        """Test content verification for binary file."""
        result = checker.verify_file_content(temp_binary_file)

        assert result["exists"] is True
        assert result["is_file"] is True
        assert result["has_null_bytes"] is True

    def test_verify_file_content_empty_file(self, checker, tmp_path):
        """Test content verification for empty file."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        result = checker.verify_file_content(empty_file)

        assert result["is_empty"] is True
        assert result["size_bytes"] == 0


class TestComprehensiveVerify:
    """Tests for comprehensive verification."""

    def test_comprehensive_verify_all_pass(self, checker, temp_text_file):
        """Test comprehensive verification when all checks pass."""
        checksums = checker.calculate_checksums(temp_text_file)
        size = temp_text_file.stat().st_size

        result = checker.comprehensive_verify(
            temp_text_file,
            expected_size=size,
            expected_checksum=checksums["sha256"],
        )

        assert result["verification_passed"] is True
        assert result["size_verified"] is True
        assert result["checksum_verified"] is True
        assert result["content_verified"] is True

    def test_comprehensive_verify_no_expectations(self, checker, temp_text_file):
        """Test comprehensive verification with no expectations."""
        result = checker.comprehensive_verify(temp_text_file)

        assert result["verification_passed"] is True
        assert "checksums" in result

    def test_comprehensive_verify_size_mismatch_raises(self, checker, temp_text_file):
        """Test comprehensive verification raises on size mismatch."""
        with pytest.raises(IntegrityError):
            checker.comprehensive_verify(temp_text_file, expected_size=9999)


class TestCreateIntegrityReport:
    """Tests for integrity report generation."""

    def test_create_integrity_report_existing_file(self, checker, temp_text_file):
        """Test report generation for existing file."""
        report = checker.create_integrity_report(temp_text_file)

        assert report["file_exists"] is True
        assert report["file_size"] > 0
        assert "checksums" in report
        assert "content_info" in report
        assert report["errors"] == []

    def test_create_integrity_report_missing_file(self, checker, tmp_path):
        """Test report generation for missing file."""
        missing_file = tmp_path / "missing.txt"

        report = checker.create_integrity_report(missing_file)

        assert report["file_exists"] is False
        assert "File does not exist" in report["errors"]
