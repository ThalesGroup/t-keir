#!/usr/bin/env python3
"""Title: tkeir-installer — on-demand cluster capability detection and Helm apply.

Usage:
  tkeir-installer plan [--kubeconfig PATH] [--output json|table]
  tkeir-installer apply --profile k8s-dev|k8s-secure|platform [--dry-run]
  tkeir-installer destroy [--dry-run]

Detection probes a kubeconfig context and prints which platform capabilities
already exist so the umbrella chart only deploys missing pieces.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "charts" / "tkeir"
VALUES = {
    "k8s-dev": CHART / "values-dev.yaml",
    "k8s-secure": CHART / "values-secure.yaml",
    "platform": CHART / "values-platform.yaml",
}


@dataclass
class Capability:
    name: str
    present: bool
    detail: str
    action: str


def _run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
    )


def _kubectl(args: list[str], kubeconfig: str | None) -> subprocess.CompletedProcess[str]:
    cmd = ["kubectl"]
    if kubeconfig:
        cmd += ["--kubeconfig", kubeconfig]
    cmd += args
    return _run(cmd)


def detect(kubeconfig: str | None) -> list[Capability]:
    """Probe cluster for reusable platform capabilities."""
    caps: list[Capability] = []

    def crd(name: str, label: str, reuse: str) -> None:
        res = _kubectl(["get", "crd", name], kubeconfig)
        present = res.returncode == 0
        caps.append(
            Capability(
                name=label,
                present=present,
                detail=name if present else (res.stderr.strip() or "not found"),
                action="reuse" if present else reuse,
            )
        )

    crd(
        "prometheuses.monitoring.coreos.com",
        "Prometheus Operator",
        "install kube-prometheus-stack or enable observability values",
    )
    crd(
        "certificates.cert-manager.io",
        "cert-manager",
        "install cert-manager",
    )
    crd(
        "pipelines.kubeflow.org",
        "Kubeflow Pipelines",
        "enable platform profile / kubeflow-install",
    )
    crd(
        "clusterpolicies.kyverno.io",
        "Kyverno",
        "install Kyverno + deploy/policies/image",
    )

    # IdP probe (optional issuer URL)
    issuer = os.getenv("TKEIR_OIDC_ISSUER", "").rstrip("/")
    if issuer:
        import urllib.request

        url = f"{issuer}/.well-known/openid-configuration"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
                present = resp.status == 200
        except Exception as exc:  # noqa: BLE001
            present = False
            detail = str(exc)
        else:
            detail = url
        caps.append(
            Capability(
                name="IdP / OIDC issuer",
                present=present,
                detail=detail,
                action=(
                    "keycloak.enabled=false; wire oidc.*"
                    if present
                    else "deploy Keycloak or set TKEIR_OIDC_ISSUER"
                ),
            )
        )
    else:
        caps.append(
            Capability(
                name="IdP / OIDC issuer",
                present=False,
                detail="TKEIR_OIDC_ISSUER unset",
                action="deploy Keycloak (compose auth / Helm) or set issuer",
            )
        )

    # GPU
    res = _kubectl(
        ["get", "nodes", "-o", "jsonpath={.items[*].status.allocatable.nvidia\\.com/gpu}"],
        kubeconfig,
    )
    gpu_raw = (res.stdout or "").strip()
    gpu_present = bool(gpu_raw and any(x not in {"", "0"} for x in gpu_raw.split()))
    caps.append(
        Capability(
            name="GPU (nvidia.com/gpu)",
            present=gpu_present,
            detail=gpu_raw or "none",
            action="offer inference.mode=vllm" if gpu_present else "use external/ollama",
        )
    )

    # SPIRE (deferred — report only)
    res = _kubectl(["get", "sts", "-A"], kubeconfig)
    spire = "spire-server" in (res.stdout or "")
    caps.append(
        Capability(
            name="SPIRE",
            present=spire,
            detail="detected" if spire else "absent (install for agents — ADR-0008)",
            action="reuse trust domain" if spire else "install SPIRE (agents profile)",
        )
    )

    return caps


def maturity(caps: list[Capability]) -> str:
    """Rough M1–M3 maturity from detection results."""
    names = {c.name: c.present for c in caps}
    if names.get("Kyverno") and names.get("cert-manager") and names.get("IdP / OIDC issuer"):
        if names.get("SPIRE"):
            return "M2 (secure controls + agent SPIFFE)"
        return "M2 (secure controls present; install SPIRE for agents)"
    if names.get("Prometheus Operator") or names.get("IdP / OIDC issuer"):
        return "M1 (correlated records + optional platform reuse)"
    return "M0/M1 (bootstrap cluster — install umbrella defaults)"


def cmd_plan(args: argparse.Namespace) -> int:
    if not shutil.which("kubectl"):
        print("kubectl not found on PATH", file=sys.stderr)
        return 2
    caps = detect(args.kubeconfig)
    level = maturity(caps)
    spire_present = any(c.name == "SPIRE" and c.present for c in caps)
    payload: dict[str, Any] = {
        "maturity": level,
        "capabilities": [asdict(c) for c in caps],
        "chart": str(CHART),
        "spire": "present" if spire_present else "optional-for-agents",
    }
    if args.output == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(f"Maturity: {level}")
        print(f"{'Capability':<28} {'Present':<8} Action")
        print("-" * 72)
        for c in caps:
            print(f"{c.name:<28} {str(c.present):<8} {c.action}")
        print("\nSPIRE: required for agents (ADR-0008); optional for RAG-only")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    profile = args.profile
    values = VALUES.get(profile)
    if values is None or not values.is_file():
        print(f"Unknown profile or missing values: {profile}", file=sys.stderr)
        return 2
    release = args.release
    namespace = args.namespace
    helm = [
        "helm",
        "upgrade",
        "--install",
        release,
        str(CHART),
        "--namespace",
        namespace,
        "--create-namespace",
        "-f",
        str(values),
        "--atomic",
        "--wait",
        "--timeout",
        "15m",
        "--set",
        "global.labels.tkeir\\.io/installed-by=tkeir-installer",
    ]
    if args.dry_run:
        helm.append("--dry-run")
    print(" ".join(helm))
    if args.dry_run:
        return 0
    if not shutil.which("helm"):
        print("helm not found on PATH", file=sys.stderr)
        return 2
    return subprocess.call(helm)


def cmd_destroy(args: argparse.Namespace) -> int:
    helm = [
        "helm",
        "uninstall",
        args.release,
        "--namespace",
        args.namespace,
    ]
    print(" ".join(helm))
    if args.dry_run:
        return 0
    if not shutil.which("helm"):
        print("helm not found on PATH", file=sys.stderr)
        return 2
    return subprocess.call(helm)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tkeir-installer")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Detect cluster capabilities")
    plan.add_argument("--kubeconfig", default=os.getenv("KUBECONFIG"))
    plan.add_argument("--output", choices=["table", "json"], default="table")
    plan.set_defaults(func=cmd_plan)

    apply = sub.add_parser("apply", help="helm upgrade --install umbrella")
    apply.add_argument(
        "--profile",
        choices=list(VALUES),
        default="k8s-dev",
    )
    apply.add_argument("--release", default="tkeir")
    apply.add_argument("--namespace", default="tkeir")
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(func=cmd_apply)

    destroy = sub.add_parser("destroy", help="helm uninstall umbrella")
    destroy.add_argument("--release", default="tkeir")
    destroy.add_argument("--namespace", default="tkeir")
    destroy.add_argument("--dry-run", action="store_true")
    destroy.set_defaults(func=cmd_destroy)

    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
