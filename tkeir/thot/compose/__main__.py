"""Title: Main

CLI: ``python -m thot.compose`` / ``make compose TEMPLATE=…``.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from thot.compose.composer import compose
from thot.compose.demo_data import demo_turtles
from thot.compose.exporters import export_markdown, export_structured_json
from thot.compose.kg import UserSpaceKG
from thot.compose.registry import list_template_names
from thot.compose.writers import DeterministicWriter
from thot.tools.search.user_space import resolve_vespa_user_space


def _load_turtles_from_dir(path: Path) -> list[str]:
    """Load Turtle / JSON-LD files from a directory.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.compose.__main__ import _load_turtles_from_dir
        >>> with tempfile.TemporaryDirectory() as td:
        ...     p = Path(td) / "demo.ttl"
        ...     _ = p.write_text("@prefix ex: <http://ex/> . ex:A a ex:T .", encoding="utf-8")
        ...     len(_load_turtles_from_dir(Path(td)))
        1
    """
    turtles: list[str] = []
    for pattern in ("*.ttl", "*.turtle", "*.jsonld", "*.json"):
        for file in sorted(path.glob(pattern)):
            turtles.append(file.read_text(encoding="utf-8"))
    return turtles


def build_parser() -> argparse.ArgumentParser:
    """Build the compose CLI parser.

    Example:
        >>> from thot.compose.__main__ import build_parser
        >>> build_parser().parse_args(["--template", "synthesis_note", "--demo"]).demo
        True
    """
    parser = argparse.ArgumentParser(
        description="Compose a grounded document from an ontology template"
    )
    parser.add_argument(
        "--template",
        default=os.getenv("TEMPLATE", "synthesis_note"),
        help="Template name under configs/templates/",
    )
    parser.add_argument(
        "--topic",
        default=os.getenv("TOPIC", "Acme"),
        help="Focus topic / entity label",
    )
    parser.add_argument(
        "--out",
        default=os.getenv("COMPOSE_OUT", ".tkeir-compose"),
        help="Output directory for .md and .json",
    )
    parser.add_argument(
        "--user-space",
        default=os.getenv("VESPA_USER_SPACE") or "",
        help="Tenant streaming group (default: resolve_vespa_user_space)",
    )
    parser.add_argument(
        "--demo",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("COMPOSE_DEMO", "1") not in {"0", "false", "False"},
        help="Use bundled demo Turtle (default on; --no-demo to disable)",
    )
    parser.add_argument(
        "--turtle-dir",
        default=os.getenv("COMPOSE_TURTLE_DIR", ""),
        help="Directory of .ttl / JSON-LD parent ontologies",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_templates",
        help="List template names and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run template composition and write markdown + JSON.

    Example:
        >>> import contextlib
        >>> import io
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.compose.__main__ import main
        >>> with tempfile.TemporaryDirectory() as td:
        ...     buf = io.StringIO()
        ...     with contextlib.redirect_stdout(buf):
        ...         code = main([
        ...             "--template", "synthesis_note",
        ...             "--topic", "Acme",
        ...             "--demo",
        ...             "--out", td,
        ...         ])
        ...     code == 0 and (Path(td) / "synthesis_note.md").is_file()
        True
    """
    args = build_parser().parse_args(argv)
    if args.list_templates:
        for name in list_template_names():
            print(name)
        return 0

    demo = bool(args.demo)
    space = args.user_space or resolve_vespa_user_space(None)
    kg = UserSpaceKG(space, use_process_cache=False)

    turtles: list[str] = []
    doc_ids: list[str] = []
    if args.turtle_dir:
        root = Path(args.turtle_dir)
        turtles = _load_turtles_from_dir(root)
        doc_ids = [p.stem for p in root.glob("*") if p.is_file()]
    if demo or not turtles:
        turtles = demo_turtles()
        doc_ids = ["doc_a"]

    kg.load(turtles, document_ids=doc_ids)
    result = compose(
        args.template,
        kg=kg,
        topic=args.topic,
        writer=DeterministicWriter(),
    )

    out_dir = Path(args.out)
    md_path = export_markdown(result, out_dir / f"{args.template}.md")
    json_path = export_structured_json(
        result, out_dir / f"{args.template}.json"
    )

    summary = {
        "template": result.template,
        "user_space": result.user_space,
        "topic": result.topic,
        "markdown": str(md_path),
        "json": str(json_path),
        "filled_slots": sorted(result.structured_json.keys()),
        "citations_map": result.citations_map,
        "unfilled": result.unfilled,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    # Checkpoint: every filled slot lists chunk_ids (or we already unfilled it).
    for name, chunks in result.citations_map.items():
        if name in result.structured_json and not chunks:
            # document-only provenance is allowed if docs were recorded on fill
            fill = next((f for f in result.fills if f.name == name), None)
            if fill and fill.provenance.document_ids:
                continue
            print(
                f"ERROR: filled slot {name!r} missing chunk_ids",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
