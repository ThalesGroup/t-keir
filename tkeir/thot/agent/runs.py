"""Title: Runs

Filesystem run store mirroring ingest jobs layout.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from thot.action.models import utc_now_rfc3339
from thot.agent.models import RunState, StepRecord


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` atomically via a ``.tmp`` file.

    Args:
        path: Destination JSON file (parent directories are created).
        payload: Serializable mapping written with ``indent=2``.

    Example:
        >>> import json
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.runs import _atomic_write_json
        >>> with tempfile.TemporaryDirectory() as td:
        ...     target = Path(td) / "sub" / "data.json"
        ...     _atomic_write_json(target, {"k": 1})
        ...     json.loads(target.read_text(encoding="utf-8"))["k"]
        1
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


class RunStore:
    """Manage ``runs/{run_id}/``, ``jobs/``, ``dlq/``.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.runs import RunStore
        >>> from thot.agent.models import RunState
        >>> with tempfile.TemporaryDirectory() as td:
        ...     store = RunStore(Path(td))
        ...     store.ensure_layout()
        ...     state = RunState(goal="g", user_space="dev@tkeir")
        ...     _ = store.write_state(state)
        ...     store.read_state(state.run_id).goal
        'g'
    """

    def __init__(self, root: Path) -> None:
        """Bind a run store to ``root``.

        Args:
            root: Base directory for ``runs/``, ``jobs/``, and ``dlq/`` trees.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.jobs_dir.name
            'jobs'
        """
        self.root = root
        self.runs_dir = root / "runs"
        self.jobs_dir = root / "jobs"
        self.dlq_dir = root / "dlq"

    def ensure_layout(self) -> None:
        """Create ``runs/``, ``jobs/``, and ``dlq/`` under the store root.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.ensure_layout()
            ...     store.runs_dir.is_dir() and store.dlq_dir.is_dir()
            True
        """
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.dlq_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        """Return ``runs/{run_id}/``.

        Args:
            run_id: Persisted run identifier.

        Returns:
            Directory path for one run's artifacts.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.run_dir("abc").name
            'abc'
        """
        return self.runs_dir / run_id

    def state_path(self, run_id: str) -> Path:
        """Return ``runs/{run_id}/run.manifest.json``.

        Args:
            run_id: Persisted run identifier.

        Returns:
            Path to the run manifest JSON file.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.state_path("r1").name
            'run.manifest.json'
        """
        return self.run_dir(run_id) / "run.manifest.json"

    def steps_dir(self, run_id: str) -> Path:
        """Return ``runs/{run_id}/steps/``.

        Args:
            run_id: Persisted run identifier.

        Returns:
            Directory path for step JSON records.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.steps_dir("r1").name
            'steps'
        """
        return self.run_dir(run_id) / "steps"

    def blackboard_path(self, run_id: str) -> Path:
        """Return ``runs/{run_id}/blackboard.json``.

        Args:
            run_id: Persisted run identifier.

        Returns:
            Path to the shared blackboard JSON file.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     store.blackboard_path("r1").name
            'blackboard.json'
        """
        return self.run_dir(run_id) / "blackboard.json"

    def write_state(self, state: RunState) -> Path:
        """Persist ``state`` and mirror a job index entry.

        Initializes an empty blackboard when missing and bumps ``updated_at``.

        Args:
            state: Run manifest to write.

        Returns:
            Path to ``run.manifest.json``.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.models import RunState
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     state = RunState(goal="analyze", user_space="dev@tkeir")
            ...     path = store.write_state(state)
            ...     path.is_file() and store.jobs_dir.joinpath(
            ...         f"{state.run_id}.json"
            ...     ).is_file()
            True
        """
        state.updated_at = utc_now_rfc3339()
        path = self.state_path(state.run_id)
        self.steps_dir(state.run_id).mkdir(parents=True, exist_ok=True)
        if not self.blackboard_path(state.run_id).is_file():
            _atomic_write_json(
                self.blackboard_path(state.run_id),
                {"entries": []},
            )
        _atomic_write_json(path, state.model_dump(by_alias=True, mode="json"))
        _atomic_write_json(
            self.jobs_dir / f"{state.run_id}.json",
            {
                "run_id": state.run_id,
                "status": state.status,
                "updated_at": state.updated_at,
            },
        )
        return path

    def read_state(self, run_id: str) -> RunState | None:
        """Load a run manifest when present.

        Args:
            run_id: Persisted run identifier.

        Returns:
            Parsed :class:`RunState`, or ``None`` when the manifest is missing.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.models import RunState
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     state = RunState(goal="read-back", user_space="dev@tkeir")
            ...     _ = store.write_state(state)
            ...     store.read_state(state.run_id).goal
            'read-back'
        """
        path = self.state_path(run_id)
        if not path.is_file():
            return None
        return RunState.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )

    def write_step(self, run_id: str, step: StepRecord) -> Path:
        """Persist one step under ``steps/NNN.json``.

        Args:
            run_id: Persisted run identifier.
            step: Step record (``step_index`` selects the filename).

        Returns:
            Path to the written step JSON file.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.models import RunState, StepRecord
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     state = RunState(goal="g", user_space="dev@tkeir")
            ...     _ = store.write_state(state)
            ...     path = store.write_step(
            ...         state.run_id, StepRecord(step_index=0)
            ...     )
            ...     path.name
            '000.json'
        """
        path = self.steps_dir(run_id) / f"{step.step_index:03d}.json"
        _atomic_write_json(path, step.model_dump(mode="json"))
        return path

    def list_steps(self, run_id: str) -> list[StepRecord]:
        """Return step records sorted by filename.

        Args:
            run_id: Persisted run identifier.

        Returns:
            Parsed :class:`StepRecord` list (empty when ``steps/`` is absent).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.models import RunState, StepRecord
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     state = RunState(goal="g", user_space="dev@tkeir")
            ...     _ = store.write_state(state)
            ...     _ = store.write_step(state.run_id, StepRecord(step_index=1))
            ...     _ = store.write_step(state.run_id, StepRecord(step_index=0))
            ...     [s.step_index for s in store.list_steps(state.run_id)]
            [0, 1]
        """
        directory = self.steps_dir(run_id)
        if not directory.is_dir():
            return []
        steps: list[StepRecord] = []
        for path in sorted(directory.glob("*.json")):
            steps.append(
                StepRecord.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            )
        return steps

    def append_blackboard(self, run_id: str, entry: dict[str, Any]) -> None:
        """Append one timestamped entry to the run blackboard.

        Args:
            run_id: Persisted run identifier.
            entry: Mapping merged with an ``at`` RFC3339 timestamp.

        Example:
            >>> import json
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.models import RunState
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     state = RunState(goal="g", user_space="dev@tkeir")
            ...     _ = store.write_state(state)
            ...     store.append_blackboard(state.run_id, {"note": "hello"})
            ...     data = json.loads(
            ...         store.blackboard_path(state.run_id).read_text(encoding="utf-8")
            ...     )
            ...     data["entries"][-1]["note"]
            'hello'
        """
        path = self.blackboard_path(run_id)
        data: dict[str, Any] = {"entries": []}
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        entries = list(data.get("entries") or [])
        entries.append({**entry, "at": utc_now_rfc3339()})
        _atomic_write_json(path, {"entries": entries})

    def move_to_dlq(self, run_id: str, reason: str) -> Path:
        """Archive a run snapshot under ``dlq/{run_id}.json``.

        Args:
            run_id: Persisted run identifier.
            reason: Human-readable failure or rejection reason.

        Returns:
            Path to the DLQ JSON payload.

        Example:
            >>> import json
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.models import RunState
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     state = RunState(goal="g", user_space="dev@tkeir")
            ...     _ = store.write_state(state)
            ...     path = store.move_to_dlq(state.run_id, "budget exceeded")
            ...     json.loads(path.read_text(encoding="utf-8"))["reason"]
            'budget exceeded'
        """
        state = self.read_state(run_id)
        payload = {
            "run_id": run_id,
            "reason": reason,
            "state": (
                state.model_dump(by_alias=True, mode="json") if state else None
            ),
        }
        path = self.dlq_dir / f"{run_id}.json"
        _atomic_write_json(path, payload)
        return path

    def request_cancel(self, run_id: str) -> RunState | None:
        """Set ``cancel_requested`` and cancel queued runs immediately.

        Args:
            run_id: Persisted run identifier.

        Returns:
            Updated :class:`RunState`, or ``None`` when the run is unknown.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.agent.models import RunState
            >>> from thot.agent.runs import RunStore
            >>> with tempfile.TemporaryDirectory() as td:
            ...     store = RunStore(Path(td))
            ...     state = RunState(goal="g", user_space="dev@tkeir", status="queued")
            ...     _ = store.write_state(state)
            ...     updated = store.request_cancel(state.run_id)
            ...     updated.status
            'cancelled'
        """
        state = self.read_state(run_id)
        if state is None:
            return None
        state.cancel_requested = True
        if state.status == "queued":
            state.status = "cancelled"
            state.ended_at = utc_now_rfc3339()
        self.write_state(state)
        return state
