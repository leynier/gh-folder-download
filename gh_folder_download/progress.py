"""
Advanced progress tracking for gh-folder-download using Rich Progress.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from .logger import get_logger


@dataclass
class DownloadStats:
    """Statistics for download tracking."""

    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    cached_files: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def completion_percentage(self) -> float:
        """Get completion percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.completed_files / self.total_files) * 100

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time

    @property
    def download_speed_bps(self) -> float:
        """Get download speed in bytes per second."""
        if self.elapsed_time == 0:
            return 0.0
        return self.downloaded_bytes / self.elapsed_time

    @property
    def download_speed_mbps(self) -> float:
        """Get download speed in MB/s."""
        return self.download_speed_bps / (1024 * 1024)

    @property
    def eta_seconds(self) -> float | None:
        """Estimate time to completion in seconds."""
        if self.download_speed_bps == 0 or self.total_bytes == 0:
            return None

        remaining_bytes = self.total_bytes - self.downloaded_bytes
        return remaining_bytes / self.download_speed_bps

    def format_bytes(self, bytes_value: int) -> str:
        """Format bytes in human-readable format."""
        bytes_float = float(bytes_value)
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_float < 1024.0:
                return f"{bytes_float:.1f} {unit}"
            bytes_float /= 1024.0
        return f"{bytes_float:.1f} TB"

    def format_speed(self) -> str:
        """Format download speed."""
        speed_bps = self.download_speed_bps
        for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
            if speed_bps < 1024.0:
                return f"{speed_bps:.1f} {unit}"
            speed_bps /= 1024.0
        return f"{speed_bps:.1f} TB/s"

    def format_eta(self) -> str:
        """Format estimated time to completion."""
        eta = self.eta_seconds
        if eta is None:
            return "calculating..."

        if eta < 60:
            return f"{eta:.0f}s"
        elif eta < 3600:
            return f"{eta // 60:.0f}m {eta % 60:.0f}s"
        else:
            hours = eta // 3600
            minutes = (eta % 3600) // 60
            return f"{hours:.0f}h {minutes:.0f}m"


class ProgressTracker:
    """Advanced progress tracking with Rich Progress bars."""

    def __init__(self, console: Console | None = None, quiet: bool = False):
        """
        Initialize progress tracker.

        Args:
            console: Rich console instance
            quiet: If True, disable progress display
        """
        self.console = console or Console()
        self.quiet = quiet
        self.logger = get_logger()

        # Progress tracking
        self.stats = DownloadStats()
        self.file_tasks: dict[str, TaskID] = {}
        self.individual_progress = {}

        # Single integrated progress display
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.fields[filename]}", justify="left"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            console=self.console if not quiet else None,
            disable=quiet,
        )

        self.overall_task: TaskID | None = None
        self.live: Live | None = None

    def start_session(self, total_files: int, total_bytes: int):
        """Start a download session."""
        self.stats.total_files = total_files
        self.stats.total_bytes = total_bytes
        self.stats.start_time = time.time()

        if not self.quiet:
            # Create summary table
            summary_table = Table(
                title="Download Session", show_header=True, header_style="bold cyan"
            )
            summary_table.add_column("Metric", style="bold")
            summary_table.add_column("Value", justify="right")

            summary_table.add_row("Total Files", str(total_files))
            summary_table.add_row("Total Size", self.stats.format_bytes(total_bytes))
            summary_table.add_row("Started", time.strftime("%H:%M:%S"))

            self.console.print(
                Panel(
                    summary_table, title="📊 Download Information", border_style="cyan"
                )
            )

            # Start progress display
            self.progress.start()

            # Create overall task
            self.overall_task = self.progress.add_task(
                "OVERALL",
                total=total_bytes,
                filename=f"[bold green]Overall Progress ({total_files} files)",
            )

    def add_file_task(self, file_path: str, size: int) -> TaskID:
        """Add a file download task."""
        if self.quiet:
            return TaskID(0)  # Dummy task ID

        # Truncate filename if too long
        filename = Path(file_path).name
        if len(filename) > 50:
            filename = filename[:47] + "..."

        task_id = self.progress.add_task(
            file_path,
            total=size,
            filename=filename,
        )
        self.file_tasks[file_path] = task_id
        return task_id

    def update_file_progress(self, file_path: str, downloaded: int):
        """Update progress for a specific file."""
        if self.quiet or file_path not in self.file_tasks:
            return

        task_id = self.file_tasks[file_path]
        self.progress.update(task_id, completed=downloaded)

        # Update overall progress
        self._update_overall_progress()

    def complete_file(self, file_path: str, success: bool, from_cache: bool = False):
        """Mark a file as completed."""
        self.stats.completed_files += 1

        if success:
            if from_cache:
                self.stats.cached_files += 1

            # Get file size from task if available
            if not self.quiet and file_path in self.file_tasks:
                task_id = self.file_tasks[file_path]
                try:
                    task = self.progress.tasks[task_id]
                    if task.total:
                        self.stats.downloaded_bytes += int(task.total)
                        self.progress.update(task_id, completed=task.total)
                except (IndexError, KeyError):
                    # Handle case where task was already removed or doesn't exist
                    pass
        else:
            self.stats.failed_files += 1

        # Remove completed task
        if not self.quiet and file_path in self.file_tasks:
            task_id = self.file_tasks[file_path]
            try:
                self.progress.remove_task(task_id)
            except (IndexError, KeyError):
                # Handle case where task was already removed
                pass
            del self.file_tasks[file_path]

        self._update_overall_progress()

    def _update_overall_progress(self):
        """Update the overall progress display."""
        if self.quiet or self.overall_task is None:
            return

        # Update overall task
        self.progress.update(
            self.overall_task,
            completed=self.stats.downloaded_bytes,
        )

    def finish_session(self):
        """Finish the download session and show summary."""
        if not self.quiet:
            self.progress.stop()

            # Show final summary
            summary = self._create_final_summary()
            self.console.print(
                Panel(summary, title="✅ Download Complete", border_style="green")
            )

    def _create_final_summary(self) -> Table:
        """Create final download summary."""
        summary_table = Table(show_header=True, header_style="bold green")
        summary_table.add_column("Metric", style="bold")
        summary_table.add_column("Value", justify="right")

        # File statistics
        summary_table.add_row("Total Files", str(self.stats.total_files))
        summary_table.add_row(
            "Successfully Downloaded",
            str(self.stats.completed_files - self.stats.failed_files),
        )
        summary_table.add_row("From Cache", str(self.stats.cached_files))
        summary_table.add_row("Failed", str(self.stats.failed_files))
        summary_table.add_row("", "")  # Separator

        # Size and performance
        summary_table.add_row(
            "Total Downloaded", self.stats.format_bytes(self.stats.downloaded_bytes)
        )
        summary_table.add_row("Total Time", f"{self.stats.elapsed_time:.1f}s")
        summary_table.add_row("Average Speed", self.stats.format_speed())

        # Success rate
        if self.stats.total_files > 0:
            success_rate = (
                (self.stats.completed_files - self.stats.failed_files)
                / self.stats.total_files
            ) * 100
            summary_table.add_row("Success Rate", f"{success_rate:.1f}%")

        # Cache hit rate
        if self.stats.completed_files > 0:
            cache_rate = (self.stats.cached_files / self.stats.completed_files) * 100
            summary_table.add_row("Cache Hit Rate", f"{cache_rate:.1f}%")

        return summary_table

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics as dictionary."""
        return {
            "total_files": self.stats.total_files,
            "completed_files": self.stats.completed_files,
            "failed_files": self.stats.failed_files,
            "cached_files": self.stats.cached_files,
            "total_bytes": self.stats.total_bytes,
            "downloaded_bytes": self.stats.downloaded_bytes,
            "elapsed_time": self.stats.elapsed_time,
            "download_speed_bps": self.stats.download_speed_bps,
            "download_speed_mbps": self.stats.download_speed_mbps,
            "eta_seconds": self.stats.eta_seconds,
            "completion_percentage": self.stats.completion_percentage,
        }


class SimpleProgressTracker:
    """Simple progress tracker for quiet mode or fallback."""

    def __init__(self):
        self.logger = get_logger()
        self.stats = DownloadStats()

    def start_session(self, total_files: int, total_bytes: int):
        """Start a download session."""
        self.stats.total_files = total_files
        self.stats.total_bytes = total_bytes
        self.stats.start_time = time.time()

        self.logger.info(
            f"Starting download of {total_files} files ({self.stats.format_bytes(total_bytes)})"
        )

    def add_file_task(self, file_path: str, size: int):
        """Add a file download task (no-op for simple tracker)."""
        return TaskID(0)

    def update_file_progress(self, file_path: str, downloaded: int):
        """Update file progress (no-op for simple tracker)."""
        pass

    def complete_file(self, file_path: str, success: bool, from_cache: bool = False):
        """Mark a file as completed."""
        self.stats.completed_files += 1

        if success:
            if from_cache:
                self.stats.cached_files += 1
            # Approximate downloaded bytes
            avg_size = self.stats.total_bytes // max(1, self.stats.total_files)
            self.stats.downloaded_bytes += avg_size
        else:
            self.stats.failed_files += 1

        # Log progress every 10 files or at milestones
        if self.stats.completed_files % 10 == 0 or self.stats.completed_files in [
            1,
            5,
            self.stats.total_files,
        ]:
            progress_pct = (self.stats.completed_files / self.stats.total_files) * 100
            self.logger.info(
                f"Progress: {self.stats.completed_files}/{self.stats.total_files} "
                f"({progress_pct:.1f}%) - Speed: {self.stats.format_speed()}"
            )

    def finish_session(self):
        """Finish the download session."""
        self.logger.info(
            f"Download completed: {self.stats.completed_files} files, "
            f"{self.stats.format_bytes(self.stats.downloaded_bytes)}, "
            f"{self.stats.elapsed_time:.1f}s, {self.stats.format_speed()}"
        )

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics."""
        return {
            "total_files": self.stats.total_files,
            "completed_files": self.stats.completed_files,
            "failed_files": self.stats.failed_files,
            "cached_files": self.stats.cached_files,
            "total_bytes": self.stats.total_bytes,
            "downloaded_bytes": self.stats.downloaded_bytes,
            "elapsed_time": self.stats.elapsed_time,
            "download_speed_bps": self.stats.download_speed_bps,
            "download_speed_mbps": self.stats.download_speed_mbps,
            "eta_seconds": self.stats.eta_seconds,
            "completion_percentage": self.stats.completion_percentage,
        }
