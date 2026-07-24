"""Title: Policy

Policy evaluation — scopes, kill switch, budgets.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.action.middleware import intent_for_path
from thot.governor.approvals import ApprovalQueue
from thot.governor.auth import extract_bearer_payload
from thot.governor.budgets import BudgetStore
from thot.governor.config import GovernorMode, GovernorSettings
from thot.governor.flags import RuntimeFlagsStore
from thot.governor.models import KillScope, PolicyDecision

INTENT_SCOPE = {
    "search": "intent:search",
    "ingest": "intent:ingest",
    "index": "intent:index",
    "delete": "intent:delete",
    "audit.read": "intent:audit.read",
    "agent.run": "intent:agent.run",
    "generate": "intent:generate",
    "tool.invoke": "intent:tool.invoke",
    "okf.export": "intent:okf.export",
}

INTENT_KILL_SCOPE: dict[str, KillScope | None] = {
    "search": "inference",
    "ingest": "ingest",
    "index": "index",
    "delete": "index",
    "audit.read": None,
    "agent.run": "agents",
    "generate": "agents",
    "tool.invoke": "agents",
    "okf.export": "inference",
}

WRITE_INTENTS = frozenset({"ingest", "index", "delete", "okf.export"})


def _payload_has_scope(payload: dict, scope: str) -> bool:
    raw = payload.get("scope")
    if isinstance(raw, str) and scope in raw.split():
        return True
    scopes = payload.get("scp")
    if isinstance(scopes, list) and scope in scopes:
        return True
    if scope == "intent:admin.override":
        resource_access = payload.get("resource_access")
        if isinstance(resource_access, dict):
            for client in resource_access.values():
                if not isinstance(client, dict):
                    continue
                roles = client.get("roles")
                if isinstance(roles, list) and "tkeir-admin" in roles:
                    return True
    return False


def _actor_from_payload(payload: dict | None, fallback: str) -> str:
    if not payload:
        return fallback
    sub = payload.get("sub")
    return str(sub) if sub else fallback


class PolicyEvaluator:
    """Evaluate HTTP requests against governor controls."""

    def __init__(
        self,
        settings: GovernorSettings,
        flags: RuntimeFlagsStore,
        budgets: BudgetStore,
        approvals: ApprovalQueue,
    ) -> None:
        self.settings = settings
        self.flags = flags
        self.budgets = budgets
        self.approvals = approvals

    @property
    def mode(self) -> GovernorMode:
        return self.settings.mode

    def evaluate_http(
        self,
        *,
        method: str,
        path: str,
        authorization: str | None,
        service: str,
    ) -> PolicyDecision:
        """Return a policy decision for one HTTP request."""
        if self.settings.mode == "off":
            return PolicyDecision(result="allow", actor_id=service)

        intent = intent_for_path(path)
        payload = extract_bearer_payload(authorization)
        actor_id = _actor_from_payload(payload, service)
        rules: list[str] = []
        required_scope = INTENT_SCOPE.get(intent, "intent:search")

        if payload and _payload_has_scope(payload, "intent:admin.override"):
            rules.append("admin.override")
            return PolicyDecision(
                result="allow",
                rules_fired=rules,
                actor_id=actor_id,
                intent=intent,
                message="admin override",
            )

        kill_scope = INTENT_KILL_SCOPE.get(intent)
        if kill_scope and self.flags.is_killed(kill_scope):
            rules.append(f"kill:{kill_scope}")
            return PolicyDecision(
                result="deny",
                rules_fired=rules,
                kill_scope=kill_scope,
                actor_id=actor_id,
                intent=intent,
                message=f"kill switch active for {kill_scope}",
            )

        if payload is not None and not _payload_has_scope(
            payload, required_scope
        ):
            rules.append("scope.mismatch")
            return PolicyDecision(
                result="escalate",
                rules_fired=rules,
                actor_id=actor_id,
                intent=intent,
                message=f"missing scope {required_scope}",
            )

        if intent in WRITE_INTENTS and method.upper() in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            budget = self.budgets.snapshot(
                actor_id,
                "docs",
                limit=self.settings.default_doc_budget,
            )
            if budget.blocked:
                rules.append("budget.exhausted")
                if self.settings.mode == "enforce":
                    return PolicyDecision(
                        result="deny",
                        rules_fired=rules,
                        budget=budget,
                        actor_id=actor_id,
                        intent=intent,
                        message="document budget exhausted",
                    )
                return PolicyDecision(
                    result="escalate",
                    rules_fired=rules,
                    budget=budget,
                    actor_id=actor_id,
                    intent=intent,
                    message="document budget exhausted (observe)",
                )
            if budget.throttled:
                rules.append("budget.throttle")

        return PolicyDecision(
            result="allow",
            rules_fired=rules,
            actor_id=actor_id,
            intent=intent,
        )

    def consume_for_intent(self, decision: PolicyDecision) -> None:
        """Charge budgets after a successful write intent."""
        if decision.intent not in WRITE_INTENTS:
            return
        self.budgets.consume(
            decision.actor_id,
            "docs",
            1.0,
            limit=self.settings.default_doc_budget,
        )
