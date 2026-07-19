"""Filesystem run store mirroring ingest jobs layout."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from thot.action.models import utc_now_rfc3339
from thot.agent.models import RunState, StepRecord


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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
        self.root = root
        self.runs_dir = root / "runs"
        self.jobs_dir = root / "jobs"
        self.dlq_dir = root / "dlq"

    def ensure_layout(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.dlq_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def state_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.manifest.json"

    def steps_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "steps"

    def blackboard_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "blackboard.json"

    def write_state(self, state: RunState) -> Path:
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
        path = self.state_path(run_id)
        if not path.is_file():
            return None
        return RunState.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )

    def write_step(self, run_id: str, step: StepRecord) -> Path:
        path = self.steps_dir(run_id) / f"{step.step_index:03d}.json"
        _atomic_write_json(path, step.model_dump(mode="json"))
        return path

    def list_steps(self, run_id: str) -> list[StepRecord]:
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
        state = self.read_state(run_id)
        if state is None:
            return None
        state.cancel_requested = True
        if state.status == "queued":
            state.status = "cancelled"
            state.ended_at = utc_now_rfc3339()
        self.write_state(state)
        return state
