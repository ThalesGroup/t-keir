#!/usr/bin/env python3
"""Title: Input generator

Scan the T-KEIR repository and emit OPA input JSON for EU compliance audit.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


def _exists(root: Path, rel: str) -> bool:
    return (root / rel).exists()


def _dir_non_empty(root: Path, rel: str) -> bool:
    path = root / rel
    if not path.is_dir():
        return False
    return any(path.iterdir())


def _any_glob(root: Path, pattern: str) -> bool:
    return any(root.glob(pattern))


def _file_contains(root: Path, rel: str, pattern: str) -> bool:
    path = root / rel
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return re.search(pattern, text) is not None


def _any_file_contains(root: Path, glob_pat: str, pattern: str) -> bool:
    for path in root.glob(glob_pat):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if re.search(pattern, text):
            return True
    return False


def _tree_contains(root: Path, rel: str, pattern: str) -> bool:
    base = root / rel
    if not base.exists():
        return False
    if base.is_file():
        return _file_contains(root, rel, pattern)
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if re.search(pattern, text):
            return True
    return False


def determine_ai_act_category(classification: dict[str, Any]) -> str:
    """Compute AI Act risk category from classification flags."""
    prohibited = classification.get("prohibited_practices") or {}
    if any(bool(v) for v in prohibited.values()):
        return "UNACCEPTABLE"
    if classification.get("is_gpai_model"):
        if classification.get("gpai_systemic_risk"):
            return "GPAI_SYSTEMIC"
        return "GPAI_STANDARD"
    if classification.get("annex_iii_applies") or classification.get(
        "safety_component_regulated_product"
    ):
        return "HIGH_RISK"
    if classification.get(
        "intended_interaction_with_natural_persons"
    ) or classification.get("processes_biometric_data"):
        return "LIMITED_RISK"
    return "MINIMAL_RISK"


def collect_evidence(root: Path) -> dict[str, bool]:
    """Detect repository artefacts. Missing paths map to False (not null)."""
    return {
        # Security / SBOM
        "sbom_cyclonedx_present": _exists(root, "reports/bom/bom.json")
        or _any_glob(root, "reports/bom/*.json"),
        "aibom_present": _any_glob(root, "reports/bom/*aibom*")
        or _any_glob(root, "reports/bom/*AIBOM*"),
        "trivy_report_present": _any_glob(root, "reports/security/trivy-*.txt")
        or _any_glob(root, "reports/security/*trivy*"),
        "pip_audit_run_in_ci": _any_file_contains(
            root, ".github/workflows/*", r"pip-audit"
        )
        or _file_contains(root, "Makefile", r"pip-audit"),
        "owasp_dc_present": _dir_non_empty(root, "reports/dependency-check")
        or _dir_non_empty(root, "reports/security/dependency-check"),
        "security_manifest_present": _exists(root, "reports/security/manifest.json"),
        "images_signed": _any_file_contains(
            root, ".github/workflows/*", r"cosign|images-sign"
        )
        or _file_contains(root, "Makefile", r"images-sign"),
        # CRA supply chain
        "versions_lock_present": _exists(root, "deploy/versions.lock.yaml"),
        "security_md_present": _exists(root, "SECURITY.md"),
        "changelog_present": _exists(root, "CHANGELOG.md"),
        # AI Act docs / evidence packs
        "annex_iv_dir_non_empty": _dir_non_empty(root, "reports/compliance/annex-iv"),
        "audit_evidence_dir_non_empty": _dir_non_empty(root, "reports/evidence"),
        "beir_eval_report_present": _exists(root, "tkeir/docs/evaluation_report.md"),
        "action_schema_present": _exists(
            root, "tkeir/thot/action/schemas/action.v1.json"
        ),
        # Human oversight
        "governor_flags_present": _exists(root, "tkeir/thot/governor/flags.py"),
        "governor_approvals_present": _exists(root, "tkeir/thot/governor/approvals.py"),
        "governor_tokens_present": _exists(root, "tkeir/thot/governor/tokens.py"),
        "kill_switch_runbook_present": _exists(
            root, "tkeir/docs/runbooks/kill-switch.md"
        ),
        "hmi_admin_page_present": _exists(root, "tkeir-hmi/app/admin/page.tsx")
        or _any_glob(root, "tkeir-hmi/**/admin*"),
        # GDPR / audit
        "privacy_py_present": _exists(root, "tkeir/thot/audit/privacy.py"),
        "ingest_manifest_schema": _exists(
            root, "tkeir/thot/ingest/schemas/ingest.manifest.v1.json"
        ),
        "audit_worm_retention_set": _file_contains(
            root, "deploy/compose/.env.example", r"AUDIT_WORM_RETENTION_DAYS"
        ),
        "audit_worm_retention_days": _parse_worm_days(root),
        # NIS2
        "incident_runbook_present": _exists(root, "tkeir/docs/runbooks/incident.md"),
        "networkpolicy_template": _exists(
            root, "deploy/charts/tkeir/templates/networkpolicy.yaml"
        ),
        "keycloak_realm_present": _exists(root, "deploy/keycloak/realm-tkeir.json"),
        "values_secure_present": _exists(
            root, "deploy/charts/tkeir/values-secure.yaml"
        ),
        "compose_auth_profile": _tree_contains(root, "deploy/compose", r"\bauth\b"),
        "observability_profile": _tree_contains(
            root, "deploy/compose", r"grafana|prometheus"
        ),
        # DORA / Makefile targets
        "rollback_target_in_makefile": _file_contains(
            root, "Makefile", r"rollback-index"
        ),
        "audit_verify_target": _file_contains(root, "Makefile", r"audit-verify"),
        "governor_kill_target": _file_contains(root, "Makefile", r"governor-kill"),
        "security_report_target": _file_contains(root, "Makefile", r"security-report"),
        "beir_eval_target": _file_contains(root, "Makefile", r"beir-eval"),
        "ci_security_workflow": _any_glob(root, ".github/workflows/security.yml")
        or _any_glob(root, ".github/workflows/*security*"),
        # PLD / correlation
        "correlation_id_in_code": _tree_contains(root, "tkeir", r"X-Correlation-Id"),
        "action_records_bind_versions": _exists(
            root, "tkeir/thot/action/schemas/action.v1.json"
        ),
        "compliance_gdpr_doc": _exists(root, "tkeir/docs/compliance/gdpr.md"),
        "values_dev_present": _exists(root, "deploy/charts/tkeir/values-dev.yaml"),
    }


def _parse_worm_days(root: Path) -> int:
    path = root / "deploy/compose/.env.example"
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"AUDIT_WORM_RETENTION_DAYS\s*=\s*(\d+)", text)
    if not match:
        return 0
    return int(match.group(1))


def _load_overrides(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML required to load overrides.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"overrides must be a mapping: {path}")
    return data


def build_input(repo: Path, overrides_path: Path) -> dict[str, Any]:
    overrides = _load_overrides(overrides_path)
    evidence = collect_evidence(repo)

    product = dict(overrides.get("product") or {})
    ai_ov = dict(overrides.get("ai_act") or {})
    classification = dict(ai_ov.get("classification") or {})
    prohibited = dict(classification.get("prohibited_practices") or {})
    classification["prohibited_practices"] = {
        "subliminal_manipulation": bool(prohibited.get("subliminal_manipulation")),
        "exploits_vulnerabilities": bool(prohibited.get("exploits_vulnerabilities")),
        "social_scoring_public_authority": bool(
            prohibited.get("social_scoring_public_authority")
        ),
        "real_time_biometric_public_space": bool(
            prohibited.get("real_time_biometric_public_space")
        ),
        "emotion_recognition_workplace_education": bool(
            prohibited.get("emotion_recognition_workplace_education")
        ),
        "biometric_categorisation_sensitive_attributes": bool(
            prohibited.get("biometric_categorisation_sensitive_attributes")
        ),
        "predictive_policing_individual": bool(
            prohibited.get("predictive_policing_individual")
        ),
    }
    classification.setdefault("is_ai_system", True)
    classification.setdefault("is_gpai_model", False)
    classification.setdefault("gpai_systemic_risk", False)
    classification.setdefault("annex_iii_applies", False)
    classification.setdefault("safety_component_regulated_product", False)
    classification.setdefault("intended_interaction_with_natural_persons", False)
    classification.setdefault("processes_biometric_data", False)

    override_cat = classification.get("determined_category")
    if override_cat in (
        None,
        "",
        "null",
    ):
        classification["determined_category"] = determine_ai_act_category(
            classification
        )
    else:
        classification["determined_category"] = str(override_cat)

    payload: dict[str, Any] = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repo_root": str(repo.resolve()),
            "tool": "tkeir-eu-compliance-audit",
        },
        "product": product,
        "evidence": evidence,
        "ai_act": {
            "classification": classification,
            "attestation": ai_ov.get("attestation") or {},
        },
        "cra": {"attestation": (overrides.get("cra") or {}).get("attestation") or {}},
        "gdpr": {"attestation": (overrides.get("gdpr") or {}).get("attestation") or {}},
        "nis2": {
            "entity_type": (overrides.get("nis2") or {}).get(
                "entity_type", "OUT_OF_SCOPE"
            ),
            "attestation": (overrides.get("nis2") or {}).get("attestation") or {},
        },
        "dora": {
            "in_scope": bool((overrides.get("dora") or {}).get("in_scope", False)),
            "attestation": (overrides.get("dora") or {}).get("attestation") or {},
        },
        "pld": {
            "in_scope": bool((overrides.get("pld") or {}).get("in_scope", True)),
            "attestation": (overrides.get("pld") or {}).get("attestation") or {},
        },
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument(
        "--overrides",
        type=Path,
        default=Path("compliance/opa/overrides.yaml"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    payload = build_input(
        repo, args.overrides if args.overrides.is_absolute() else repo / args.overrides
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(f"[eu-audit] wrote {args.output}")
    print(
        f"[eu-audit] AI Act category: "
        f"{payload['ai_act']['classification']['determined_category']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
