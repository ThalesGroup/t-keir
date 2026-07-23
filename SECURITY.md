# Security Policy

T-KEIR ships as a local toolkit, optional HTTP services, and progressive
deployment profiles. This file explains how to report vulnerabilities and what
security controls are already part of the repository.

For platform controls and engineering details, see:

- [`docs/security.md`](docs/security.md)
- [`docs/deployment/index.md`](docs/deployment/index.md)
- [`docs/compliance/index.md`](docs/compliance/index.md)

## Supported versions

Security fixes are applied to the current active major line.

| Version | Supported |
|---------|-----------|
| 2.0.x   | ✅ |
| < 2.0   | ❌ |

## Reporting a vulnerability

Please do not open a public GitHub issue for suspected security problems.

Report vulnerabilities to: `security@opensource.thalesgroup.com`

When possible, include:

- affected version, commit, or image tag
- deployment profile (`P0`, `compose`, `k8s-dev`, `k8s-secure`, `platform`)
- reproduction steps or proof of concept
- impact assessment and any suggested mitigation

## Disclosure process

The project follows coordinated disclosure:

1. Acknowledge receipt of the report as quickly as possible.
2. Validate impact and scope.
3. Prepare a fix or mitigation.
4. Coordinate disclosure timing with the reporter when the issue is confirmed.

If a report is rejected, the maintainer response should explain whether the
finding is out of scope, not reproducible, or already mitigated elsewhere.

## Repository security controls

Current repository and CI controls include:

- lockfile verification via `make verify-lockfile`
- secret hygiene via `make check-secrets` (tracked `.env` guard + pattern scan)
- Python dependency audit via `make pip-audit`
- Trivy filesystem/config scan via `make trivy`
- OWASP Dependency-Check via `make owasp-dependency-check`
- SBOM / AIBOM generation via `make bom`
- license review via `make liccheck`
- complexity gates via `make complexity`
- GitHub Actions validation for Python, HMI, Helm, and security scans
- pre-commit / pre-push hooks for YAML/JSON hygiene and local quality gates

## Deployment guidance

For stronger security posture outside P0 local development:

- enable OIDC / Keycloak in Compose or Kubernetes profiles
- prefer `governor.mode=enforce` for controlled environments
- enable the audit store for attributable actions
- keep `.env` files out of git and use secret managers in CI/CD and production
- prefer local or in-cluster inference when data egress is restricted

## Known gaps and future work

The current repository does **not** claim full compliance or full production
hardening by default. Notable remaining gaps include:

- Full-mesh SPIFFE for non-agent services (agents use SPIRE — ADR-0008)
- full NetworkPolicy allow-listing for every service path
- deeper rollback automation for index mutations
- regulation-specific compliance evidence packs under `docs/compliance/`

These are tracked as later workstreams rather than treated as default
requirements for software development.
