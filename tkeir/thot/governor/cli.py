"""Title: Cli

CLI for governor flags, kill switch, and budgets.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import cast

from thot.governor.approvals import ApprovalQueue
from thot.governor.budgets import BudgetStore
from thot.governor.config import governor_settings
from thot.governor.flags import RuntimeFlagsStore
from thot.governor.models import KillScope


def main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="T-KEIR governor CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("flags", help="Show runtime flags")

    kill = sub.add_parser("kill", help="Toggle kill switch")
    kill.add_argument(
        "--scope",
        choices=["all", "ingest", "index", "inference", "hmi-write"],
        required=True,
    )
    kill.add_argument("--active", choices=["true", "false"], default="true")
    kill.add_argument("--reason", default="cli")

    budgets = sub.add_parser("budgets", help="Show budget snapshots")
    budgets.add_argument("--actor", default="anonymous")

    parsed = parser.parse_args(args)
    from thot.core.StructuredLogging import configure_text_logging
    configure_text_logging(level=logging.INFO, force=True)
    settings = governor_settings()
    flags = RuntimeFlagsStore(settings.flags_path)
    budgets_store = BudgetStore(settings.budget_db_path, settings)
    _ = ApprovalQueue(settings.approvals_path)

    try:
        if parsed.command == "flags":
            print(
                json.dumps(
                    flags.snapshot().model_dump(by_alias=True, mode="json"),
                    indent=2,
                )
            )
            sys.exit(0)
        if parsed.command == "kill":
            updated = flags.set_kill(
                cast(KillScope, parsed.scope),
                active=parsed.active == "true",
                reason=parsed.reason,
                actor="cli",
            )
            print(
                json.dumps(
                    updated.model_dump(by_alias=True, mode="json"), indent=2
                )
            )
            sys.exit(0)
        if parsed.command == "budgets":
            docs = budgets_store.snapshot(
                parsed.actor,
                "docs",
                limit=settings.default_doc_budget,
            )
            tokens = budgets_store.snapshot(
                parsed.actor,
                "llm_tokens",
                limit=settings.default_llm_token_budget,
            )
            print(
                json.dumps(
                    [
                        docs.model_dump(mode="json"),
                        tokens.model_dump(mode="json"),
                    ],
                    indent=2,
                )
            )
            sys.exit(0)
    finally:
        budgets_store.close()


if __name__ == "__main__":
    main()
