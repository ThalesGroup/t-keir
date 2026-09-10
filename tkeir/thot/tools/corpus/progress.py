"""Title: Corpus progress (elapsed, remaining, summary)

Log conversion / compile progress with elapsed wall time and an ETA
from observed throughput, then print a run summary.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)


def format_duration(seconds: float | None) -> str:
    """Human duration for logs (``12.4s``, ``3m 05s``, ``1h 02m 03s``).

    Args:
        seconds: Elapsed or remaining seconds. ``None`` → ``estimating``.

    Returns:
        Compact duration string.

    Example:
        >>> format_duration(None)
        'estimating'
        >>> format_duration(12.4)
        '12.4s'
        >>> format_duration(65)
        '1m 05s'
        >>> format_duration(3723)
        '1h 02m 03s'
    """
    if seconds is None:
        return "estimating"
    value = max(0.0, float(seconds))
    if value < 60:
        return f"{value:.1f}s"
    total = int(round(value))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


def format_bytes(size: int) -> str:
    """Human byte count (B / KiB / MiB / GiB).

    Example:
        >>> format_bytes(512)
        '512 B'
        >>> format_bytes(2048)
        '2.0 KiB'
        >>> format_bytes(5 * 1024 * 1024)
        '5.0 MiB'
    """
    value = float(max(0, int(size)))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024.0 or unit == "GiB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GiB"


def eta_seconds(elapsed: float, done: int, total: int) -> float | None:
    """Estimate remaining seconds from mean throughput.

    Needs at least two finished items so a single slow file does not
    dominate the first ETA.

    Example:
        >>> eta_seconds(10.0, 5, 10)
        10.0
        >>> eta_seconds(1.0, 1, 10) is None
        True
        >>> eta_seconds(1.0, 10, 10)
        0.0
    """
    if total <= 0 or done <= 0:
        return None
    remaining = max(0, int(total) - int(done))
    if remaining == 0:
        return 0.0
    if done < 2 or elapsed <= 0:
        return None
    rate = done / elapsed
    if rate <= 0:
        return None
    return remaining / rate


@dataclass
class RunStats:
    """Counters for one corpus convert or compile pass.

    Example:
        >>> RunStats(label="convert", files_total=2).files_total
        2
    """

    label: str
    files_total: int = 0
    written: int = 0
    skipped: int = 0
    cached: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0
    workers_initial: int = 1
    workers_peak: int = 1
    workers_adaptive: bool = False
    cpu_count: int = 1
    bytes_in: int = 0
    bytes_out: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    error_samples: list[str] = field(default_factory=list)

    def record_kind(self, kind: str) -> None:
        """Increment the per-datatype counter.

        Example:
            >>> stats = RunStats(label="x")
            >>> stats.record_kind("pdf")
            >>> stats.by_kind["pdf"]
            1
        """
        key = (kind or "unknown").strip() or "unknown"
        self.by_kind[key] = self.by_kind.get(key, 0) + 1


def format_run_summary(stats: RunStats) -> str:
    """Multi-line summary of a convert/compile pass.

    Example:
        >>> text = format_run_summary(
        ...     RunStats(label="convert", files_total=3, written=3,
        ...              elapsed_seconds=1.5, workers_peak=4)
        ... )
        >>> "converted" in text and "3" in text
        True
    """
    rate = 0.0
    if stats.elapsed_seconds > 0 and stats.files_total:
        rate = stats.written / stats.elapsed_seconds
    kinds = (
        ", ".join(
            f"{name}={count}" for name, count in sorted(stats.by_kind.items())
        )
        or "(none)"
    )
    mode = "adaptive" if stats.workers_adaptive else "fixed"
    lines = [
        f"Corpus {stats.label} summary",
        f"  scanned      : {stats.files_total}",
        f"  converted    : {stats.written}",
        f"  cached       : {stats.cached}",
        f"  skipped      : {stats.skipped}",
        f"  errors       : {stats.errors}",
        f"  by type      : {kinds}",
        (
            f"  workers      : peak {stats.workers_peak} "
            f"({mode}, start {stats.workers_initial}, "
            f"cpu={stats.cpu_count})"
        ),
        f"  elapsed      : {format_duration(stats.elapsed_seconds)}",
        f"  throughput   : {rate:.2f} files/s",
        f"  input        : {format_bytes(stats.bytes_in)}",
        f"  markdown     : {format_bytes(stats.bytes_out)}",
    ]
    if stats.error_samples:
        lines.append("  error samples:")
        for sample in stats.error_samples[:8]:
            lines.append(f"    - {sample}")
    return "\n".join(lines)


def log_run_summary(
    stats: RunStats, *, logger: logging.Logger | None = None
) -> None:
    """Emit :func:`format_run_summary` at INFO.

    Example:
        >>> callable(log_run_summary)
        True
    """
    log = logger or LOGGER
    log.info("%s", format_run_summary(stats))


class ProgressClock:
    """Thread-safe progress logger with elapsed time and ETA.

    Example:
        >>> clock = ProgressClock(total=2, label="convert")
        >>> clock.total
        2
    """

    def __init__(
        self,
        total: int,
        *,
        label: str = "convert",
        logger: logging.Logger | None = None,
        min_interval: float = 1.0,
    ) -> None:
        """Start a clock for ``total`` files.

        Example:
            >>> ProgressClock(total=3).total
            3
        """
        self.total = max(0, int(total))
        self.label = label
        self._log = logger or LOGGER
        self._min_interval = max(0.2, float(min_interval))
        self._lock = threading.Lock()
        self._started = time.perf_counter()
        self._done = 0
        self._last_log = 0.0

    def elapsed(self) -> float:
        """Seconds since construction.

        Example:
            >>> ProgressClock(total=1).elapsed() >= 0
            True
        """
        return max(0.0, time.perf_counter() - self._started)

    def tick(
        self,
        *,
        rel: str,
        kind: str = "",
        duration: float = 0.0,
        workers: int = 1,
        status: str = "converted",
    ) -> dict[str, Any]:
        """Record one finished file and maybe log a progress line.

        Returns:
            Snapshot with ``done``, ``elapsed``, ``remaining``.

        Example:
            >>> snap = ProgressClock(total=1).tick(rel="a.txt", status="converted")
            >>> snap["done"]
            1
        """
        with self._lock:
            self._done += 1
            elapsed = self.elapsed()
            remaining = eta_seconds(elapsed, self._done, self.total)
            snapshot = {
                "done": self._done,
                "total": self.total,
                "elapsed": elapsed,
                "remaining": remaining,
                "workers": int(workers),
            }
            now = time.perf_counter()
            pct_step = max(1, self.total // 20) if self.total else 1
            should = (
                self._done <= 1
                or self._done >= self.total
                or self.total <= 32
                or (now - self._last_log) >= self._min_interval
                or (self._done % pct_step == 0)
            )
            if should:
                self._last_log = now
                pct = 100.0 * self._done / self.total if self.total else 100.0
                eta = format_duration(remaining)
                if remaining is not None and remaining > 0:
                    eta = "~" + eta
                kind_bit = f" {kind}" if kind else ""
                self._log.info(
                    "[%s %d/%d | %.0f%%] elapsed %s remaining %s "
                    "workers %d | %s %s%s (%.2fs)",
                    self.label,
                    self._done,
                    self.total,
                    pct,
                    format_duration(elapsed),
                    eta,
                    int(workers),
                    status,
                    rel,
                    kind_bit,
                    float(duration),
                )
            return snapshot
