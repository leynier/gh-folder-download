"""
Logging configuration for gh-folder-download.
"""

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table


class GHFolderLogger:
    """Logger with rich formatting and progress tracking."""

    def __init__(
        self,
        level: str = "INFO",
        log_file: Path | None = None,
        quiet: bool = False,
    ):
        self.console = Console()
        self.logger = logging.getLogger("gh-folder-download")
        self.logger.setLevel(logging.DEBUG)  # Always capture all logs
        self.quiet = quiet

        # Clear existing handlers
        self.logger.handlers.clear()

        # Rich console handler - only for non-quiet mode or errors
        console_level = logging.ERROR if quiet else getattr(logging, level.upper())
        rich_handler = RichHandler(
            console=self.console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
        )
        rich_handler.setLevel(console_level)
        rich_handler.setFormatter(
            logging.Formatter(
                fmt="%(message)s",
                datefmt="[%X]",
            )
        )
        self.logger.addHandler(rich_handler)

        # File handler if specified - always logs everything
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            self.logger.addHandler(file_handler)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(message, **kwargs)

    def success(self, message: str, **kwargs) -> None:
        """Log success message in green."""
        if not self.quiet:
            self.console.print(f"✅ {message}", style="green", **kwargs)
        # Also log to file handlers
        self.logger.info(f"SUCCESS: {message}")

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(message, **kwargs)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(message, **kwargs)

    def progress_info(self, message: str) -> None:
        """Log progress information with spinner."""
        if not self.quiet:
            self.console.print(f"🔄 {message}", style="blue")
        # Also log to file handlers
        self.logger.info(f"PROGRESS: {message}")

    def download_start(self, file_path: str, file_size: int | None = None) -> None:
        """Log download start."""
        size_info = f" ({self._format_size(file_size)})" if file_size else ""
        if not self.quiet:
            self.console.print(f"⬇️  Downloading: [bold]{file_path}[/bold]{size_info}")
        # Also log to file handlers
        self.logger.info(f"DOWNLOAD_START: {file_path}{size_info}")

    def download_complete(self, file_path: str) -> None:
        """Log download completion."""
        if not self.quiet:
            self.console.print(f"✅ Downloaded: {file_path}", style="green")
        # Also log to file handlers
        self.logger.info(f"DOWNLOAD_COMPLETE: {file_path}")

    def download_error(self, file_path: str, error: str) -> None:
        """Log download error."""
        self.logger.error(f"Failed to download {file_path}: {error}")

    def repository_info(self, org: str, repo: str, branch: str, path: str) -> None:
        """Display repository information in a nice table."""
        if not self.quiet:
            table = Table(title="Repository Information")
            table.add_column("Field", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")

            table.add_row("Organization/User", org)
            table.add_row("Repository", repo)
            table.add_row("Branch", branch)
            table.add_row("Path", path or "(root)")

            self.console.print(table)

        # Also log to file handlers
        self.logger.info(
            f"REPOSITORY_INFO: {org}/{repo}, branch: {branch}, path: {path or '(root)'}"
        )

    def summary(self, total_files: int, total_size: int, duration: float) -> None:
        """Display download summary."""
        if not self.quiet:
            table = Table(title="Download Summary")
            table.add_column("Metric", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")

            table.add_row("Total Files", str(total_files))
            table.add_row("Total Size", self._format_size(total_size))
            table.add_row("Duration", f"{duration:.2f} seconds")
            if duration > 0:
                avg_speed = self._format_size(int(total_size / duration)) + "/s"
            else:
                avg_speed = "N/A"
            table.add_row("Average Speed", avg_speed)

            self.console.print(table)

        # Also log to file handlers
        speed = (
            f"{self._format_size(int(total_size / duration))}/s"
            if duration > 0
            else "N/A"
        )
        self.logger.info(
            f"SUMMARY: {total_files} files, {self._format_size(total_size)}, {duration:.2f}s, {speed}"
        )

    @staticmethod
    def _format_size(size_bytes: int | None) -> str:
        """Format file size in human readable format."""
        if size_bytes is None:
            return "Unknown"

        size = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


# Global logger instance
_logger: GHFolderLogger | None = None


def setup_logger(
    level: str = "INFO",
    log_file: Path | None = None,
    quiet: bool = False,
) -> GHFolderLogger:
    """Setup and return the global logger instance."""
    global _logger
    _logger = GHFolderLogger(level=level, log_file=log_file, quiet=quiet)
    return _logger


def get_logger() -> GHFolderLogger:
    """Get the global logger instance."""
    if _logger is None:
        return setup_logger()
    return _logger
