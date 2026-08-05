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
    "collect": "intent:collect",
    "collect.read": "intent:collect",
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
    "collect": "inference",
    "collect.read": None,
}

WRITE_INTENTS = frozenset({"ingest", "index", "delete", "okf.export"})


def _payload_has_scope(payload: dict, scope: str) -> bool:
    """Return True when JWT payload includes ``scope``.

    Example:
        >>> from thot.governor.policy import _payload_has_scope
        >>> _payload_has_scope({"scope": "intent:search read"}, "intent:search")
        True
    """
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
    """Resolve actor id from JWT ``sub`` or fallback.

    Example:
        >>> from thot.governor.policy import _actor_from_payload
        >>> _actor_from_payload({"sub": "alice"}, "svc")
        'alice'
    """
    if not payload:
        return fallback
    sub = payload.get("sub")
    return str(sub) if sub else fallback


class PolicyEvaluator:
    """Evaluate HTTP requests against governor controls.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.governor.approvals import ApprovalQueue
        >>> from thot.governor.budgets import BudgetStore
        >>> from thot.governor.config import governor_settings
        >>> from thot.governor.flags import RuntimeFlagsStore
        >>> from thot.governor.policy import PolicyEvaluator
        >>> with tempfile.TemporaryDirectory() as td:
        ...     root = Path(td)
        ...     s = governor_settings()
        ...     ev = PolicyEvaluator(
        ...         s, RuntimeFlagsStore(root / "f.json"),
        ...         BudgetStore(root / "b.db", s), ApprovalQueue(root / "a.json"),
        ...     )
        ...     ev.evaluate_http(
        ...         method="GET", path="/search", authorization=None, service="svc"
        ...     ).result
        'allow'
    """

    def __init__(
        self,
        settings: GovernorSettings,
        flags: RuntimeFlagsStore,
        budgets: BudgetStore,
        approvals: ApprovalQueue,
    ) -> None:
        """Wire settings, flags, budgets, and approval queue.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.approvals import ApprovalQueue
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> from thot.governor.flags import RuntimeFlagsStore
            >>> from thot.governor.policy import PolicyEvaluator
            >>> with tempfile.TemporaryDirectory() as td:
            ...     s = governor_settings()
            ...     ev = PolicyEvaluator(
            ...         s, RuntimeFlagsStore(Path(td) / "f.json"),
            ...         BudgetStore(Path(td) / "b.db", s),
            ...         ApprovalQueue(Path(td) / "a.json"),
            ...     )
            ...     ev.mode in {"off", "observe", "enforce"}
            True
        """
        self.settings = settings
        self.flags = flags
        self.budgets = budgets
        self.approvals = approvals

    @property
    def mode(self) -> GovernorMode:
        """Current governor enforcement mode.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.approvals import ApprovalQueue
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> from thot.governor.flags import RuntimeFlagsStore
            >>> from thot.governor.policy import PolicyEvaluator
            >>> with tempfile.TemporaryDirectory() as td:
            ...     s = governor_settings()
            ...     PolicyEvaluator(
            ...         s, RuntimeFlagsStore(Path(td) / "f.json"),
            ...         BudgetStore(Path(td) / "b.db", s),
            ...         ApprovalQueue(Path(td) / "a.json"),
            ...     ).mode
            'observe'
        """
        return self.settings.mode

    def evaluate_http(
        self,
        *,
        method: str,
        path: str,
        authorization: str | None,
        service: str,
    ) -> PolicyDecision:
        """Return a policy decision for one HTTP request.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.approvals import ApprovalQueue
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> from thot.governor.flags import RuntimeFlagsStore
            >>> from thot.governor.policy import PolicyEvaluator
            >>> with tempfile.TemporaryDirectory() as td:
            ...     s = governor_settings()
            ...     ev = PolicyEvaluator(
            ...         s, RuntimeFlagsStore(Path(td) / "f.json"),
            ...         BudgetStore(Path(td) / "b.db", s),
            ...         ApprovalQueue(Path(td) / "a.json"),
            ...     )
            ...     ev.evaluate_http(
            ...         method="GET", path="/v1/search",
            ...         authorization=None, service="svc",
            ...     ).intent
            'search'
        """
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
        """Charge budgets after a successful write intent.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.governor.approvals import ApprovalQueue
            >>> from thot.governor.budgets import BudgetStore
            >>> from thot.governor.config import governor_settings
            >>> from thot.governor.flags import RuntimeFlagsStore
            >>> from thot.governor.policy import PolicyEvaluator
            >>> from thot.governor.models import PolicyDecision
            >>> with tempfile.TemporaryDirectory() as td:
            ...     s = governor_settings()
            ...     ev = PolicyEvaluator(
            ...         s, RuntimeFlagsStore(Path(td) / "f.json"),
            ...         BudgetStore(Path(td) / "b.db", s),
            ...         ApprovalQueue(Path(td) / "a.json"),
            ...     )
            ...     ev.consume_for_intent(
            ...         PolicyDecision(result="allow", intent="ingest", actor_id="u1")
            ...     )
            ...     snap = ev.budgets.snapshot("u1", "docs", limit=100.0)
            ...     snap.consumed >= 1.0
            True
        """
        if decision.intent not in WRITE_INTENTS:
            return
        self.budgets.consume(
            decision.actor_id,
            "docs",
            1.0,
            limit=self.settings.default_doc_budget,
        )
