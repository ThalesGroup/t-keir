"""Title: Per-user workspace tree under ``workspace/users/<space>/``.

Demo filesystem layout for analyst file import / browse / delete. Each
authenticated principal gets an isolated directory; catalog.json maps
relative paths to ingest + Vespa passage ids for streaming unindex.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from thot.action.models import utc_now_rfc3339

LOGGER = logging.getLogger(__name__)

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._@+=\- ]+$")
_CATALOG_LOCKS: dict[str, threading.RLock] = {}
_CATALOG_LOCKS_GUARD = threading.Lock()


def _catalog_lock_for(user_space: str) -> threading.RLock:
    """Per-user-space re-entrant lock for catalog read-modify-write.

    Example:
        >>> lock = _catalog_lock_for("demo@tkeir")
        >>> lock.acquire()
        True
        >>> lock.release()
    """
    with _CATALOG_LOCKS_GUARD:
        lock = _CATALOG_LOCKS.get(user_space)
        if lock is None:
            lock = threading.RLock()
            _CATALOG_LOCKS[user_space] = lock
        return lock


def _normalize_space(user_space: str) -> str:
    """Filesystem/Vespa-safe user space (mirrors vespa normalize without heavy imports).

    Example:
        >>> _normalize_space(" Demo User ")
        'Demo_User'
    """
    value = (user_space or "dev@tkeir").strip() or "dev@tkeir"
    return re.sub(r"[^A-Za-z0-9._@+-]+", "_", value)[:200]


def workspace_root(explicit: Path | str | None = None) -> Path:
    """Resolve demo workspace root (``TKEIR_WORKSPACE`` or repo ``workspace/``).

    Example:
        >>> from thot.tools.ingest.user_workspace import workspace_root
        >>> workspace_root("/tmp/ws").name
        'ws'
    """
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.getenv("TKEIR_WORKSPACE") or os.getenv("WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    from thot.core.TkeirPaths import repo_root

    return (Path(repo_root()) / "workspace").resolve()


def _fs_safe_space(user_space: str) -> str:
    """Filesystem-safe directory name for a Vespa user space.

    Example:
        >>> _fs_safe_space("demo@tkeir")
        'demo@tkeir'
    """
    return _normalize_space(user_space) or "user"


def sanitize_relative_path(
    raw: str | None, *, allow_empty: bool = True
) -> str:
    """Normalize a user-relative path; reject traversal and absolute paths.

    Example:
        >>> from thot.tools.ingest.user_workspace import sanitize_relative_path
        >>> sanitize_relative_path("reports/a.md")
        'reports/a.md'
    """
    text = (raw or "").strip().replace("\\", "/")
    if not text or text in {".", "./"}:
        if allow_empty:
            return ""
        raise ValueError("path is required")
    if text.startswith("/") or text.startswith("~"):
        raise ValueError("absolute paths are not allowed")
    parts: list[str] = []
    for segment in text.split("/"):
        if not segment or segment == ".":
            continue
        if segment == "..":
            raise ValueError("path traversal is not allowed")
        if not _SAFE_SEGMENT.match(segment):
            raise ValueError(f"invalid path segment: {segment!r}")
        parts.append(segment)
    return "/".join(parts)


@dataclass
class WorkspaceFileRecord:
    """Catalog entry for one imported file."""

    path: str
    source_ref: str
    ingest_id: str | None = None
    doc_id: str | None = None
    passage_ids: list[str] = field(default_factory=list)
    status: str = "pending"
    size_bytes: int = 0
    content_type: str | None = None
    updated_at: str = ""
    # Provenance when copied across user workspaces (e.g. analyst → commander).
    copied_from_user: str | None = None
    copied_from_path: str | None = None
    copied_from_source_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the catalog record to a plain dict.

        Example:
            >>> from thot.tools.ingest.user_workspace import WorkspaceFileRecord
            >>> WorkspaceFileRecord(path="a.md", source_ref="s").to_dict()["path"]
            'a.md'
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceFileRecord:
        """Build a record from a catalog JSON object.

        Example:
            >>> from thot.tools.ingest.user_workspace import WorkspaceFileRecord
            >>> WorkspaceFileRecord.from_dict({"path": "a.md", "source_ref": "s"}).path
            'a.md'
        """
        return cls(
            path=str(data.get("path") or ""),
            source_ref=str(data.get("source_ref") or ""),
            ingest_id=(
                str(data["ingest_id"]) if data.get("ingest_id") else None
            ),
            doc_id=(str(data["doc_id"]) if data.get("doc_id") else None),
            passage_ids=[str(x) for x in data.get("passage_ids") or [] if x],
            status=str(data.get("status") or "pending"),
            size_bytes=int(data.get("size_bytes") or 0),
            content_type=(
                str(data["content_type"]) if data.get("content_type") else None
            ),
            updated_at=str(data.get("updated_at") or ""),
            copied_from_user=(
                str(data["copied_from_user"])
                if data.get("copied_from_user")
                else None
            ),
            copied_from_path=(
                str(data["copied_from_path"])
                if data.get("copied_from_path")
                else None
            ),
            copied_from_source_ref=(
                str(data["copied_from_source_ref"])
                if data.get("copied_from_source_ref")
                else None
            ),
        )


class UserWorkspace:
    """Manage ``workspace/users/<space>/{files,okf}`` + ``catalog.json``.

    Layout (MinIO-ready object key prefix later)::

        workspace/users/<space>/
          files/           # My files
          catalog.json
          okf/<bundle_id>/ # OKF / LLM Wiki bundles for this user
    """

    def __init__(
        self,
        user_space: str,
        *,
        root: Path | str | None = None,
    ) -> None:
        """Bind a workspace to ``user_space`` under ``root``.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.user_space
            'demo@tkeir'
        """
        self.user_space = _normalize_space(user_space)
        self.root = workspace_root(root)
        self.user_dir = self.root / "users" / _fs_safe_space(self.user_space)
        self.files_dir = self.user_dir / "files"
        self.okf_dir = self.user_dir / "okf"
        self.catalog_path = self.user_dir / "catalog.json"

    def ensure_layout(self) -> None:
        """Create files tree, catalog, and run inbox migration.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     ws.files_dir.is_dir()
            True
        """
        self._ensure_dirs()
        if not self.catalog_path.is_file():
            self._write_catalog({})
        self._migrate_inbox_to_received()

    def _ensure_dirs(self) -> None:
        """Create workspace files directories (including ``received/``).

        Example:
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws._ensure_dirs()
            ...     ws.files_dir.is_dir()
            True
        """
        self.files_dir.mkdir(parents=True, exist_ok=True)
        (self.files_dir / "received").mkdir(parents=True, exist_ok=True)

    def _read_catalog(self) -> dict[str, WorkspaceFileRecord]:
        """Load catalog without running inbox migration (safe under catalog lock).

        Example:
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     ws._read_catalog()
            {}
        """
        self._ensure_dirs()
        return self._read_catalog_unlocked()

    def _read_catalog_unlocked(self) -> dict[str, WorkspaceFileRecord]:
        """Load catalog.json without mkdir/migrate side effects.

        Example:
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws._read_catalog_unlocked()
            {}
        """
        if not self.catalog_path.is_file():
            return {}
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        files = raw.get("files") if isinstance(raw, dict) else None
        if not isinstance(files, dict):
            return {}
        out: dict[str, WorkspaceFileRecord] = {}
        for key, value in files.items():
            if isinstance(value, dict):
                out[str(key)] = WorkspaceFileRecord.from_dict(value)
        return out

    def _migrate_inbox_to_received(self) -> None:
        """Move legacy ``files/inbox/`` into dedicated ``files/received/``.

        Older shares used a deep ``inbox/<sender>/…`` tree that was easy to
        miss in My files. New copies use ``received/<sender>/<basename>``.

        Example:
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     ws._migrate_inbox_to_received()  # no-op when inbox absent
        """
        inbox = self.files_dir / "inbox"
        received = self.files_dir / "received"
        received.mkdir(parents=True, exist_ok=True)
        if inbox.is_dir():
            for child in list(inbox.iterdir()):
                dest = received / child.name
                if dest.exists():
                    # Merge: move nested files into existing sender folder.
                    if child.is_dir() and dest.is_dir():
                        for nested in child.rglob("*"):
                            if not nested.is_file():
                                continue
                            target_file = dest / nested.name
                            if target_file.exists():
                                continue
                            try:
                                target_file.parent.mkdir(
                                    parents=True, exist_ok=True
                                )
                                shutil.move(str(nested), str(target_file))
                            except OSError:
                                LOGGER.warning(
                                    "could not merge %s → %s",
                                    nested,
                                    target_file,
                                    exc_info=True,
                                )
                    continue
                try:
                    shutil.move(str(child), str(dest))
                except OSError:
                    LOGGER.warning(
                        "could not migrate %s → %s", child, dest, exc_info=True
                    )
            try:
                if inbox.exists() and not any(inbox.rglob("*")):
                    shutil.rmtree(inbox, ignore_errors=True)
                elif inbox.exists() and not any(inbox.iterdir()):
                    inbox.rmdir()
            except OSError:
                pass

        # Flatten sender trees so files sit directly under received/<sender>/.
        if received.is_dir():
            for sender_dir in list(received.iterdir()):
                if not sender_dir.is_dir():
                    continue
                for nested in list(sender_dir.rglob("*")):
                    if not nested.is_file() or nested.parent == sender_dir:
                        continue
                    dest_file = sender_dir / nested.name
                    if dest_file.exists():
                        continue
                    try:
                        shutil.move(str(nested), str(dest_file))
                    except OSError:
                        LOGGER.warning(
                            "could not flatten %s → %s",
                            nested,
                            dest_file,
                            exc_info=True,
                        )
                # Drop empty residual directories under the sender folder.
                for dirpath in sorted(
                    (p for p in sender_dir.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts),
                    reverse=True,
                ):
                    try:
                        dirpath.rmdir()
                    except OSError:
                        pass

        with _catalog_lock_for(self.user_space):
            files = self._read_catalog_unlocked()
            changed = False
            rewritten: dict[str, WorkspaceFileRecord] = {}
            for key, record in files.items():
                new_key = key
                if new_key.startswith("inbox/"):
                    new_key = "received/" + new_key[len("inbox/") :]
                # Flatten received/<sender>/a/b/file.md → received/<sender>/file.md
                parts = new_key.split("/")
                if len(parts) > 3 and parts[0] == "received" and parts[1]:
                    new_key = f"received/{parts[1]}/{parts[-1]}"
                if new_key != key:
                    if new_key in rewritten or (
                        new_key in files and new_key != key
                    ):
                        rewritten[key] = record
                        continue
                    record.path = new_key
                    record.source_ref = self.source_ref_for(new_key)
                    rewritten[new_key] = record
                    changed = True
                else:
                    rewritten[key] = record
            if changed:
                self._write_catalog(rewritten)

    def ensure_okf_layout(self) -> Path:
        """Ensure ``users/<space>/okf`` exists; return that directory.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_okf_layout().name
            'okf'
        """
        self.okf_dir.mkdir(parents=True, exist_ok=True)
        return self.okf_dir

    def okf_bundle_dir(self, bundle_id: str) -> Path:
        """Absolute path for one OKF bundle directory (does not create it).

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.okf_bundle_dir("bundle-1").name
            'bundle-1'
        """
        bid = (bundle_id or "").strip()
        if not bid or "/" in bid or ".." in bid or bid in {".", ".."}:
            raise ValueError(f"invalid bundle_id: {bundle_id!r}")
        return self.okf_dir / bid

    def source_ref_for(self, relative_path: str) -> str:
        """Stable Vespa ``source_ref`` / ``source_doc_id`` for a workspace file.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.source_ref_for("a.md").startswith("user:demo@tkeir:")
            True
        """
        rel = sanitize_relative_path(relative_path, allow_empty=False)
        return f"user:{self.user_space}:{rel}"

    def resolve_file(self, relative_path: str) -> Path:
        """Resolve a safe absolute path under ``files/``.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     ws.resolve_file("a.md").name
            'a.md'
        """
        rel = sanitize_relative_path(relative_path, allow_empty=False)
        path = (self.files_dir / rel).resolve()
        if not str(path).startswith(str(self.files_dir.resolve())):
            raise ValueError("path escapes workspace")
        return path

    def _write_catalog(self, files: dict[str, WorkspaceFileRecord]) -> None:
        """Persist the workspace catalog atomically.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import WorkspaceFileRecord
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws._write_catalog({"a.md": WorkspaceFileRecord(path="a.md", source_ref="s")})
            ...     ws.catalog_path.is_file()
            True
        """
        self.user_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "user_space": self.user_space,
            "updated_at": utc_now_rfc3339(),
            "files": {
                key: rec.to_dict() for key, rec in sorted(files.items())
            },
        }
        tmp = self.catalog_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.catalog_path)

    def upsert_record(
        self, record: WorkspaceFileRecord
    ) -> WorkspaceFileRecord:
        """Insert or update one catalog entry.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace, WorkspaceFileRecord
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     rec = ws.upsert_record(WorkspaceFileRecord(path="a.md", source_ref="s"))
            ...     rec.path
            'a.md'
        """
        with _catalog_lock_for(self.user_space):
            files = self._read_catalog()
            record.updated_at = utc_now_rfc3339()
            files[record.path] = record
            self._write_catalog(files)
            return record

    def get_record(self, relative_path: str) -> WorkspaceFileRecord | None:
        """Return the catalog entry for ``relative_path``, if any.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace, WorkspaceFileRecord
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     _ = ws.upsert_record(WorkspaceFileRecord(path="a.md", source_ref="s"))
            ...     ws.get_record("a.md").source_ref
            's'
        """
        rel = sanitize_relative_path(relative_path, allow_empty=False)
        with _catalog_lock_for(self.user_space):
            return self._read_catalog().get(rel)

    def remove_record(self, relative_path: str) -> WorkspaceFileRecord | None:
        """Remove a catalog entry and return the previous record.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace, WorkspaceFileRecord
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     _ = ws.upsert_record(WorkspaceFileRecord(path="a.md", source_ref="s"))
            ...     ws.remove_record("a.md").path
            'a.md'
        """
        rel = sanitize_relative_path(relative_path, allow_empty=False)
        with _catalog_lock_for(self.user_space):
            files = self._read_catalog()
            record = files.pop(rel, None)
            if record is not None:
                self._write_catalog(files)
            return record

    def iter_indexing_records(self) -> list[WorkspaceFileRecord]:
        """Return catalog entries still marked ``indexing``.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     ws.iter_indexing_records()
            []
        """
        with _catalog_lock_for(self.user_space):
            return [
                rec
                for rec in self._read_catalog().values()
                if rec.status == "indexing" and rec.ingest_id
            ]

    def mkdir(self, relative_path: str) -> str:
        """Create a directory under ``files/`` and return its relative path.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     ws.mkdir("reports")
            'reports'
        """
        rel = sanitize_relative_path(relative_path, allow_empty=False)
        path = self.resolve_file(rel)
        path.mkdir(parents=True, exist_ok=True)
        return rel

    def read_file_bytes(self, relative_path: str) -> bytes:
        """Read file bytes from the workspace tree.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     _ = ws.write_file("a.md", b"hello")
            ...     ws.read_file_bytes("a.md")
            b'hello'
        """
        path = self.resolve_file(relative_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"workspace file not found: {relative_path}"
            )
        return path.read_bytes()

    def write_file(
        self,
        relative_path: str,
        content: bytes,
        *,
        content_type: str | None = None,
        ingest_id: str | None = None,
        status: str = "pending",
        copied_from_user: str | None = None,
        copied_from_path: str | None = None,
        copied_from_source_ref: str | None = None,
    ) -> WorkspaceFileRecord:
        """Write bytes to ``files/`` and upsert the catalog entry.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.write_file("a.md", b"hello").status
            'pending'
        """
        rel = sanitize_relative_path(relative_path, allow_empty=False)
        # Legacy share prefix — always land under the dedicated received/ tree.
        if rel.startswith("inbox/"):
            rel = "received/" + rel[len("inbox/") :]
        path = self.resolve_file(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        record = WorkspaceFileRecord(
            path=rel,
            source_ref=self.source_ref_for(rel),
            ingest_id=ingest_id,
            status=status,
            size_bytes=len(content),
            content_type=content_type,
            updated_at=utc_now_rfc3339(),
            copied_from_user=copied_from_user,
            copied_from_path=copied_from_path,
            copied_from_source_ref=copied_from_source_ref,
        )
        return self.upsert_record(record)

    def delete_file(self, relative_path: str) -> WorkspaceFileRecord | None:
        """Delete a file or directory and remove its catalog entry.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     _ = ws.write_file("a.md", b"hello")
            ...     ws.delete_file("a.md").path
            'a.md'
        """
        rel = sanitize_relative_path(relative_path, allow_empty=False)
        path = self.resolve_file(rel)
        record = self.remove_record(rel)
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        return record

    def list_dir(self, relative_path: str = "") -> dict[str, Any]:
        """List one directory; include catalog metadata for files.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     _ = ws.write_file("a.md", b"hello")
            ...     ws.list_dir("")["user_space"]
            'demo@tkeir'
        """
        rel = sanitize_relative_path(relative_path, allow_empty=True)
        base = self.files_dir if not rel else self.resolve_file(rel)
        self.ensure_layout()
        if not base.exists():
            return {
                "user_space": self.user_space,
                "path": rel,
                "entries": [],
            }
        if not base.is_dir():
            raise ValueError("not a directory")
        catalog = self._read_catalog()
        entries: list[dict[str, Any]] = []
        for child in sorted(
            base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
        ):
            child_rel = (
                f"{rel}/{child.name}".lstrip("/") if rel else child.name
            )
            if child.is_dir():
                entries.append(
                    {
                        "name": child.name,
                        "path": child_rel,
                        "kind": "directory",
                    }
                )
                continue
            meta = catalog.get(child_rel)
            entries.append(
                {
                    "name": child.name,
                    "path": child_rel,
                    "kind": "file",
                    "size_bytes": child.stat().st_size,
                    "status": meta.status if meta else "untracked",
                    "source_ref": meta.source_ref if meta else None,
                    "ingest_id": meta.ingest_id if meta else None,
                    "passage_count": len(meta.passage_ids) if meta else 0,
                    "updated_at": meta.updated_at if meta else None,
                    "copied_from_user": (
                        meta.copied_from_user if meta else None
                    ),
                    "copied_from_path": (
                        meta.copied_from_path if meta else None
                    ),
                }
            )
        return {
            "user_space": self.user_space,
            "path": rel,
            "entries": entries,
        }

    def sync_from_analyzed(
        self,
        relative_path: str,
        analyzed: dict[str, Any] | None,
        *,
        status: str = "indexed",
    ) -> WorkspaceFileRecord | None:
        """Fill passage_ids / doc_id from an analyzed ingest document.

        Example:
            >>> import tempfile
            >>> from thot.tools.ingest.user_workspace import UserWorkspace, WorkspaceFileRecord
            >>> with tempfile.TemporaryDirectory() as temp_dir:
            ...     ws = UserWorkspace("demo@tkeir", root=temp_dir)
            ...     ws.ensure_layout()
            ...     _ = ws.upsert_record(WorkspaceFileRecord(path="a.md", source_ref="s"))
            ...     synced = ws.sync_from_analyzed("a.md", {"golden_chunks": [{"chunk_id": "c1"}]})
            ...     synced.passage_ids
            ['c1']
        """
        record = self.get_record(relative_path)
        if record is None:
            return None
        if not isinstance(analyzed, dict):
            return record
        chunks = analyzed.get("golden_chunks") or []
        passage_ids = [
            str(chunk.get("chunk_id"))
            for chunk in chunks
            if isinstance(chunk, dict) and chunk.get("chunk_id")
        ]
        record.passage_ids = passage_ids
        record.doc_id = (
            str(
                analyzed.get("doc_id")
                or analyzed.get("content_digest")
                or record.doc_id
                or ""
            )
            or record.doc_id
        )
        record.status = status if passage_ids else record.status
        return self.upsert_record(record)
