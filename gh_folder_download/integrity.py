"""
File integrity verification for gh-folder-download.
"""

import hashlib
from pathlib import Path
from typing import Any

from .logger import get_logger


class IntegrityError(Exception):
    """Exception raised when file integrity check fails."""

    pass


class FileIntegrityChecker:
    """Handles file integrity verification using checksums and size validation."""

    def __init__(self):
        self.logger = get_logger()

    def calculate_checksums(self, file_path: Path) -> dict[str, str]:
        """
        Calculate multiple checksums for a file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with checksum algorithm names as keys and hashes as values

        Raises:
            IntegrityError: If file cannot be read or checksums cannot be calculated
        """
        self.logger.debug(f"Calculating checksums for: {file_path}")

        if not file_path.exists():
            raise IntegrityError(f"File does not exist: {file_path}")

        if not file_path.is_file():
            raise IntegrityError(f"Path is not a file: {file_path}")

        checksums = {}
        hash_algorithms = {
            "md5": hashlib.md5(),
            "sha1": hashlib.sha1(),
            "sha256": hashlib.sha256(),
        }

        try:
            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files efficiently
                chunk_size = 8192
                while chunk := f.read(chunk_size):
                    for hasher in hash_algorithms.values():
                        hasher.update(chunk)

            # Get hex digests
            for name, hasher in hash_algorithms.items():
                checksums[name] = hasher.hexdigest()

            self.logger.debug(f"Checksums calculated: {checksums}")
            return checksums

        except (OSError, IOError) as e:
            raise IntegrityError(f"Failed to calculate checksums for {file_path}: {e}")

    def verify_file_size(self, file_path: Path, expected_size: int | None) -> bool:
        """
        Verify that file size matches expected size.

        Args:
            file_path: Path to the file
            expected_size: Expected file size in bytes, or None to skip check

        Returns:
            True if size matches or expected_size is None

        Raises:
            IntegrityError: If file size doesn't match
        """
        if expected_size is None:
            self.logger.debug(
                f"Skipping size verification for {file_path} (no expected size)"
            )
            return True

        if not file_path.exists():
            raise IntegrityError(f"File does not exist: {file_path}")

        try:
            actual_size = file_path.stat().st_size
            self.logger.debug(
                f"File size check: {actual_size} bytes (expected: {expected_size})"
            )

            if actual_size != expected_size:
                raise IntegrityError(
                    f"File size mismatch for {file_path}: "
                    f"expected {expected_size} bytes, got {actual_size} bytes"
                )

            return True

        except (OSError, IOError) as e:
            raise IntegrityError(f"Failed to get file size for {file_path}: {e}")

    def verify_checksum(
        self,
        file_path: Path,
        expected_checksum: str,
        algorithm: str = "sha256",
    ) -> bool:
        """
        Verify file checksum against expected value.

        Args:
            file_path: Path to the file
            expected_checksum: Expected checksum hex string
            algorithm: Hash algorithm to use ('md5', 'sha1', 'sha256')

        Returns:
            True if checksum matches

        Raises:
            IntegrityError: If checksum doesn't match or algorithm is unsupported
        """
        supported_algorithms = ["md5", "sha1", "sha256"]
        if algorithm not in supported_algorithms:
            raise IntegrityError(f"Unsupported hash algorithm: {algorithm}")

        self.logger.debug(f"Verifying {algorithm} checksum for: {file_path}")

        checksums = self.calculate_checksums(file_path)
        actual_checksum = checksums[algorithm]

        if actual_checksum.lower() != expected_checksum.lower():
            raise IntegrityError(
                f"{algorithm.upper()} checksum mismatch for {file_path}: "
                f"expected {expected_checksum}, got {actual_checksum}"
            )

        self.logger.debug(f"{algorithm.upper()} checksum verified successfully")
        return True

    def verify_file_content(self, file_path: Path) -> dict[str, Any]:
        """
        Perform basic content verification checks.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with verification results

        Raises:
            IntegrityError: If file cannot be analyzed
        """
        self.logger.debug(f"Performing content verification for: {file_path}")

        if not file_path.exists():
            raise IntegrityError(f"File does not exist: {file_path}")

        results = {
            "file_path": str(file_path),
            "exists": True,
            "is_file": file_path.is_file(),
            "is_readable": False,
            "is_empty": False,
            "size_bytes": 0,
            "appears_binary": False,
            "has_null_bytes": False,
        }

        try:
            # Basic file checks
            stat = file_path.stat()
            results["size_bytes"] = stat.st_size
            results["is_empty"] = stat.st_size == 0

            # Check if file is readable
            try:
                with open(file_path, "rb") as f:
                    # Read first few bytes to check content
                    first_bytes = f.read(8192)
                    results["is_readable"] = True

                    # Check for null bytes (indicating binary file)
                    results["has_null_bytes"] = b"\x00" in first_bytes

                    # Simple binary detection
                    if first_bytes:
                        # Count non-printable characters
                        non_printable = sum(
                            1 for b in first_bytes if b < 32 and b not in [9, 10, 13]
                        )
                        results["appears_binary"] = (
                            non_printable > len(first_bytes) * 0.1
                        )

            except (OSError, IOError):
                results["is_readable"] = False

            # Log results
            if results["is_empty"]:
                self.logger.warning(f"File is empty: {file_path}")
            elif not results["is_readable"]:
                self.logger.warning(f"File is not readable: {file_path}")
            elif results["appears_binary"]:
                self.logger.debug(f"File appears to be binary: {file_path}")
            else:
                self.logger.debug(f"File appears to be text: {file_path}")

            return results

        except (OSError, IOError) as e:
            raise IntegrityError(f"Failed to verify content for {file_path}: {e}")

    def comprehensive_verify(
        self,
        file_path: Path,
        expected_size: int | None = None,
        expected_checksum: str | None = None,
        checksum_algorithm: str = "sha256",
    ) -> dict[str, Any]:
        """
        Perform comprehensive file verification.

        Args:
            file_path: Path to the file
            expected_size: Expected file size in bytes
            expected_checksum: Expected checksum hex string
            checksum_algorithm: Hash algorithm for checksum verification

        Returns:
            Dictionary with all verification results

        Raises:
            IntegrityError: If any verification fails
        """
        self.logger.debug(f"Starting comprehensive verification for: {file_path}")

        verification_results = {
            "file_path": str(file_path),
            "size_verified": False,
            "checksum_verified": False,
            "content_verified": False,
            "checksums": {},
            "content_info": {},
            "verification_passed": False,
        }

        try:
            # 1. Verify file size
            if expected_size is not None:
                self.verify_file_size(file_path, expected_size)
                verification_results["size_verified"] = True
                self.logger.debug("✅ Size verification passed")
            else:
                verification_results["size_verified"] = (
                    True  # No expected size to check
                )

            # 2. Calculate all checksums
            verification_results["checksums"] = self.calculate_checksums(file_path)

            # 3. Verify specific checksum if provided
            if expected_checksum is not None:
                self.verify_checksum(file_path, expected_checksum, checksum_algorithm)
                verification_results["checksum_verified"] = True
                self.logger.debug("✅ Checksum verification passed")
            else:
                verification_results["checksum_verified"] = (
                    True  # No expected checksum to check
                )

            # 4. Verify file content
            verification_results["content_info"] = self.verify_file_content(file_path)
            verification_results["content_verified"] = True
            self.logger.debug("✅ Content verification passed")

            # All verifications passed
            verification_results["verification_passed"] = True
            self.logger.success(f"File integrity verified: {file_path}")

            return verification_results

        except IntegrityError as e:
            verification_results["verification_passed"] = False
            verification_results["error"] = str(e)
            self.logger.error(f"File integrity verification failed: {e}")
            raise

    def create_integrity_report(self, file_path: Path) -> dict[str, Any]:
        """
        Create a comprehensive integrity report for a file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with complete file integrity information
        """
        self.logger.debug(f"Creating integrity report for: {file_path}")

        report = {
            "file_path": str(file_path),
            "timestamp": None,
            "file_exists": False,
            "file_size": 0,
            "checksums": {},
            "content_info": {},
            "errors": [],
        }

        try:
            import datetime

            report["timestamp"] = datetime.datetime.now().isoformat()

            if file_path.exists():
                report["file_exists"] = True
                report["file_size"] = file_path.stat().st_size

                try:
                    report["checksums"] = self.calculate_checksums(file_path)
                except IntegrityError as e:
                    report["errors"].append(f"Checksum calculation failed: {e}")

                try:
                    report["content_info"] = self.verify_file_content(file_path)
                except IntegrityError as e:
                    report["errors"].append(f"Content verification failed: {e}")
            else:
                report["errors"].append("File does not exist")

            return report

        except Exception as e:
            report["errors"].append(f"Report generation failed: {e}")
            return report


# Convenience function for quick integrity check
def quick_integrity_check(
    file_path: Path,
    expected_size: int | None = None,
    expected_checksum: str | None = None,
) -> bool:
    """
    Quick integrity check for a file.

    Args:
        file_path: Path to the file
        expected_size: Expected file size in bytes
        expected_checksum: Expected SHA256 checksum

    Returns:
        True if all checks pass

    Raises:
        IntegrityError: If any check fails
    """
    checker = FileIntegrityChecker()
    result = checker.comprehensive_verify(
        file_path=file_path,
        expected_size=expected_size,
        expected_checksum=expected_checksum,
        checksum_algorithm="sha256",
    )
    return result["verification_passed"]
