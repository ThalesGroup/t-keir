"""Title: Cli

CLI for audit reports, verification, archive, and GDPR forget.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

from thot.audit.archiver import archive_unarchived
from thot.audit.config import audit_settings
from thot.audit.hot_store import open_hot_store
from thot.audit.privacy import SubjectKeyStore
from thot.audit.report import load_report, render_html
from thot.audit.verify import verify_store
from thot.audit.worm_store import WormSegmentStore


def main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="T-KEIR audit CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Render audit report")
    report.add_argument("--correlation-id", required=True)
    report.add_argument("--format", choices=["json", "html"], default="json")

    summary = sub.add_parser("summary", help="Recent action summary")
    summary.add_argument("--last", default="24h")

    sub.add_parser("verify", help="Verify hot + WORM hash chains")

    sub.add_parser("archive", help="Export unarchived records to WORM")

    forget = sub.add_parser("forget", help="Crypto-shred subject envelope key")
    forget.add_argument("--subject", required=True)

    incident = sub.add_parser(
        "incident",
        help="Emit NIS2-style early-warning / 72h notification stubs (JSON)",
    )
    incident.add_argument(
        "--since",
        help="RFC3339 lower bound (default: last 72h)",
        default="",
    )
    incident.add_argument(
        "--kind",
        choices=["early-warning", "72h", "final"],
        default="early-warning",
    )

    parsed = parser.parse_args(args)
    from thot.core.StructuredLogging import configure_text_logging
    configure_text_logging(level=logging.INFO, force=True)
    settings = audit_settings()
    hot = open_hot_store(settings.hot_store_url)
    if hot is None:
        logging.error("AUDIT_HOT_STORE_URL is not configured")
        sys.exit(1)
    worm = WormSegmentStore(settings.worm_root)
    keys = SubjectKeyStore(settings.subject_keys_path)

    try:
        if parsed.command == "report":
            payload = load_report(hot, parsed.correlation_id)
            if parsed.format == "html":
                print(render_html(payload))
            else:
                print(json.dumps(payload, indent=2))
            sys.exit(0)
        if parsed.command == "summary":
            hours = int(parsed.last.rstrip("h"))
            since = (
                (datetime.now(timezone.utc) - timedelta(hours=hours))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            records = hot.query(occurred_from=since, limit=500)
            print(
                json.dumps(
                    {
                        "since": since,
                        "count": len(records),
                        "intents": sorted(
                            {record.intent.declared for record in records}
                        ),
                    },
                    indent=2,
                )
            )
            sys.exit(0)
        if parsed.command == "verify":
            result = verify_store(hot, worm)
            print(json.dumps(result.__dict__, indent=2))
            sys.exit(0 if result.ok else 1)
        if parsed.command == "archive":
            segment = archive_unarchived(hot, worm)
            print(json.dumps({"segment_id": segment}, indent=2))
            sys.exit(0)
        if parsed.command == "forget":
            ok = keys.forget(parsed.subject)
            if not ok:
                logging.error("Unknown subject: %s", parsed.subject)
                sys.exit(1)
            sys.exit(0)
        if parsed.command == "incident":
            if parsed.since:
                since = parsed.since
            else:
                since = (
                    (datetime.now(timezone.utc) - timedelta(hours=72))
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z")
                )
            records = hot.query(occurred_from=since, limit=1000)
            template = {
                "schema": "tkeir.audit.incident.v1",
                "kind": parsed.kind,
                "disclaimer": (
                    "Engineering stub — not legal advice / not a filing"
                ),
                "since": since,
                "generated_at": (
                    datetime.now(timezone.utc)
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z")
                ),
                "record_count": len(records),
                "correlation_ids": sorted(
                    {
                        r.correlation_id
                        for r in records
                        if getattr(r, "correlation_id", None)
                    }
                )[:50],
                "intents": sorted({r.intent.declared for r in records}),
                "next_steps": [
                    "Attach make audit-evidence output",
                    "Run make audit-verify",
                    "Follow docs/runbooks/incident.md",
                ],
            }
            print(json.dumps(template, indent=2))
            sys.exit(0)
    finally:
        hot.close()
        keys.close()


if __name__ == "__main__":
    main()
