"""Title: Cli

CLI for ingest DLQ retry and maintenance.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from thot.tools.ingest.config import ingest_settings
from thot.tools.ingest.store import IngestStore
from thot.tools.ingest.worker import IngestWorker


async def _retry_from_dlq(store: IngestStore, ingest_id: str) -> int:
    worker = IngestWorker(store)
    job = await worker.retry_from_dlq(ingest_id)
    logging.info(
        "Retry complete ingest_id=%s status=%s doc_id=%s",
        job.ingest_id,
        job.status.value,
        job.doc_id,
    )
    return 0 if job.status.value in {"succeeded", "noop"} else 1


def main(args: list[str] | None = None) -> None:
    """Parse CLI arguments and run ingest maintenance commands."""
    parser = argparse.ArgumentParser(
        description="T-KEIR ingest service CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    retry = sub.add_parser(
        "retry",
        help="Retry failed ingest jobs from the DLQ",
    )
    retry.add_argument(
        "--from-dlq",
        action="store_true",
        help="Retry using staged bytes from dlq/{ingest_id}.json",
    )
    retry.add_argument(
        "--ingest-id",
        required=True,
        help="Original ingest id recorded in the DLQ",
    )

    parsed = parser.parse_args(args)
    from thot.core.StructuredLogging import configure_text_logging

    configure_text_logging(level=logging.INFO, force=True)

    settings = ingest_settings()
    store = IngestStore(settings.root)
    store.ensure_layout()

    if parsed.command == "retry":
        if not parsed.from_dlq:
            parser.error("retry requires --from-dlq")
        try:
            code = asyncio.run(_retry_from_dlq(store, parsed.ingest_id))
        except (KeyError, ValueError, FileNotFoundError) as exc:
            logging.error("%s", exc)
            code = 1
        sys.exit(code)

    parser.error(f"Unknown command: {parsed.command}")


if __name__ == "__main__":
    main()
