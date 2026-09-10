"""Title: Adaptive corpus thread pool

Choose and grow a thread count from CPU, file mix, and observed job
duration so conversion saturates the machine without a fixed guess.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

# PDFs, Office, rasters, and archives dominate wall time (OCR / extract).
HEAVY_SUFFIXES = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".webp",
        ".tif",
        ".tiff",
        ".svg",
    }
)
_ABS_MAX_WORKERS = 64


def available_cpus() -> int:
    """Logical CPU count (at least 1).

    Example:
        >>> available_cpus() >= 1
        True
    """
    return max(1, int(os.cpu_count() or 1))


def is_heavy_source(path: Path) -> bool:
    """Return True when ``path`` is typically expensive to convert.

    Example:
        >>> is_heavy_source(Path("report.PDF"))
        True
        >>> is_heavy_source(Path("note.txt"))
        False
    """
    return path.suffix.lower() in HEAVY_SUFFIXES


@dataclass(frozen=True)
class WorkerPlan:
    """Initial / max / min thread counts for one corpus run.

    Example:
        >>> WorkerPlan(2, 8, 1, True, 4, 0, 10).adaptive
        True
    """

    initial: int
    maximum: int
    minimum: int
    adaptive: bool
    cpu_count: int
    heavy_files: int
    total_files: int

    @property
    def pool_size(self) -> int:
        """ThreadPoolExecutor size (the adaptive cap).

        Example:
            >>> WorkerPlan(2, 8, 1, True, 4, 0, 10).pool_size
            8
        """
        return max(1, self.maximum)


def plan_workers(
    files: list[Path],
    *,
    requested: int | None = None,
    ocr_enabled: bool = True,
    captions: bool = True,
    cpu_count: int | None = None,
) -> WorkerPlan:
    """Pick thread bounds from CPU, file mix, and an optional override.

    ``requested`` ``None`` or ``0`` means adaptive. A positive value is a
    fixed pool (no runtime growth). Heavy PDF/image jobs start conservative
    then grow; text-only trees oversubscribe for I/O.

    Example:
        >>> from pathlib import Path
        >>> plan = plan_workers([Path("a.txt"), Path("b.txt")], requested=1)
        >>> plan.initial, plan.maximum, plan.adaptive
        (1, 1, False)
        >>> auto = plan_workers([Path("a.txt")] * 8, requested=0, cpu_count=4)
        >>> auto.adaptive and auto.maximum >= auto.initial >= 1
        True
    """
    total = len(files)
    cpus = max(
        1, int(cpu_count if cpu_count is not None else available_cpus())
    )
    heavy = sum(1 for path in files if is_heavy_source(path))
    if total <= 1:
        return WorkerPlan(
            initial=1,
            maximum=1,
            minimum=1,
            adaptive=False,
            cpu_count=cpus,
            heavy_files=heavy,
            total_files=total,
        )
    if requested is not None and int(requested) > 0:
        width = min(int(requested), total)
        return WorkerPlan(
            initial=width,
            maximum=width,
            minimum=width,
            adaptive=False,
            cpu_count=cpus,
            heavy_files=heavy,
            total_files=total,
        )
    abs_max = min(total, max(cpus * 4, 8), _ABS_MAX_WORKERS)
    ratio = heavy / total if total else 0.0
    if ocr_enabled and captions and ratio >= 0.3:
        maximum = min(abs_max, max(cpus * 2, 4))
        initial = min(max(2, cpus), maximum)
    elif ratio >= 0.4:
        maximum = min(abs_max, cpus * 2)
        initial = min(max(2, cpus), maximum)
    else:
        maximum = abs_max
        initial = min(max(2, cpus * 2), maximum)
    initial = max(1, min(initial, total, maximum))
    maximum = max(initial, min(maximum, total))
    return WorkerPlan(
        initial=initial,
        maximum=maximum,
        minimum=1,
        adaptive=True,
        cpu_count=cpus,
        heavy_files=heavy,
        total_files=total,
    )


class AdaptiveLimiter:
    """Semaphore that grows toward ``maximum`` when jobs keep finishing.

    Extra permits are released after fast-enough completions so in-flight
    work climbs toward the CPU-based cap (throughput, not wall-clock
    padding). A fixed plan uses ``initial == maximum`` and never grows.

    Example:
        >>> limiter = AdaptiveLimiter(initial=1, maximum=3, minimum=1)
        >>> limiter.current
        1
        >>> limiter.acquire()
        >>> limiter.release(0.01, remaining=10)
        >>> limiter.current >= 1
        True
    """

    def __init__(
        self,
        *,
        initial: int,
        maximum: int,
        minimum: int = 1,
    ) -> None:
        """Create a limiter with ``initial`` in-flight permits.

        Example:
            >>> AdaptiveLimiter(initial=2, maximum=8).current
            2
        """
        self.minimum = max(1, int(minimum))
        self.maximum = max(self.minimum, int(maximum))
        self.current = max(self.minimum, min(int(initial), self.maximum))
        self.peak = self.current
        self.grows = 0
        self._sema = threading.Semaphore(self.current)
        self._lock = threading.Lock()
        self._durations: deque[float] = deque(maxlen=8)
        self._since_grow = 0

    def acquire(self) -> None:
        """Take one in-flight slot (blocks when at the current cap).

        Example:
            >>> AdaptiveLimiter(initial=1, maximum=1).acquire() is None
            True
        """
        self._sema.acquire()

    def release(self, duration: float, remaining: int) -> None:
        """Free a slot and maybe grow the cap from recent durations.

        Example:
            >>> limiter = AdaptiveLimiter(initial=1, maximum=1)
            >>> limiter.acquire()
            >>> limiter.release(0.2, remaining=0)
            >>> limiter.current
            1
        """
        with self._lock:
            self._durations.append(max(0.0, float(duration)))
            self._maybe_grow(int(remaining))
        self._sema.release()

    def _maybe_grow(self, remaining: int) -> None:
        """Add one permit when the window looks healthy and work remains.

        Example:
            >>> limiter = AdaptiveLimiter(initial=1, maximum=2)
            >>> limiter.acquire()
            >>> limiter.release(0.01, remaining=5)
            >>> limiter.acquire()
            >>> limiter.release(0.01, remaining=5)
            >>> limiter.current >= 1
            True
        """
        if self.current >= self.maximum:
            return
        if remaining < 2:
            return
        self._since_grow += 1
        if len(self._durations) < 2:
            return
        mean = sum(self._durations) / len(self._durations)
        # Grow when jobs complete (even slow OCR): parallel tesseract helps.
        # Require a couple of samples between grows so we do not jump to
        # the cap on the first two tiny text files in a mixed tree.
        need = 1 if mean < 0.5 else 2
        if self._since_grow < need:
            return
        self.current += 1
        self.peak = max(self.peak, self.current)
        self.grows += 1
        self._since_grow = 0
        self._sema.release()
