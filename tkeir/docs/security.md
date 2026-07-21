# Security

T-KEIR runs an in-process document analysis pipeline (`tkeir-pipeline`) and,
optionally, HTTP services (`tkeir-rag`, HMI, and future ingest/audit/governor
components). Task configuration files no longer expose HTTP `network` or
`runtime` sections.

This page describes **engineering controls**. It is not a compliance
attestation or legal advice. Regulation-oriented mappings live under
[Compliance](compliance/index.md) (authored as evidence packs land).

## Input and output paths

- Restrict read access on input directories and write access on output
  directories to trusted users.
- Pipeline output JSON may contain extracted document text; treat output
  directories with the same confidentiality level as source documents.
- The same confidentiality note applies to object-storage prefixes used by
  ingestion (`staging/`, `dlq/`) once the ingest profile is enabled.

## External services (data egress)

Some optional features contact external systems when enabled:

- **PDF OCR (`llm` mode)** — sends rendered page images to an OpenAI-compatible
  API when `ocr.llm-api-key` or `OPENAI_API_KEY` is set. Recorded in ingest
  manifests when that path exists.
- **`PROVIDER=openai` (or remote vLLM)** — query/document text and embeddings
  leave the local boundary according to the provider contract.
- **Annotation resource downloads** — tokenizer preparation may fetch remote
  lists when `download.url` is present in annotation configuration.

Review those settings before production use. Prefer local
`PROVIDER=ollama` (or in-cluster vLLM) when data must stay on-prem.

## Identity and access (target platform)

P0 local development may run without authentication. From **P1 Compose
`auth`** onward, **Keycloak** (realm `tkeir`) is the default IdP for human and
machine clients; customers may bring their own OIDC issuer
(`keycloak.useExisting` / `oidc.*`).

- Client scopes encode action intents (`intent:search`, `intent:ingest`, …).
- Services validate audience and expiry; the governor maps scopes to declared
  intents ([Mastering of Action](regularity-component/action-mastering.md)).
- Vespa **streaming groups** isolate corpora per principal
  (`preferred_username` → `email` → `sub`; auth-off uses `dev@tkeir`) —
  see [Vespa RAG](tools/vespa_rag.md#user-space-streaming-group).
- Do not rely on a generic “API gateway in front” as the only control once the
  platform profiles are in use — gateway TLS/rate-limits remain complementary.

## Correlation and audit

Every HTTP response from platform services carries `X-Correlation-Id` (W3C
trace-id). ActionRecords and the two-tier audit store (hot PostgreSQL + WORM
object lock) are described in [Identity of Action](regularity-component/action-identiy.md).

## Supply chain and containers (progressive)

- Third-party pins: `deploy/versions.lock.yaml`.
- Images published as `ghcr.io/thalesgroup/t-keir/*`, multi-arch, non-root,
  digest-pinned bases; Cosign signing in CI (Workstream I).
- P3 adds image verification (Kyverno), sealed-secrets, NetworkPolicies /
  Cilium, and PSS `restricted`.

## Secrets

Never commit `.env` or credentials (`make check-secrets`). The scanner rejects
tracked credential files and common secret patterns; dev placeholders in
`.env.example`, Keycloak realm exports, and Helm dev values are allowlisted.
Kubernetes secrets use sealed-secrets (default) or SOPS+age; charts accept
`existingSecret`.

## Time

Use synchronized clocks (NTP/chrony). Audit timestamps are RFC 3339 UTC.
Untrustworthy time weakens log correlation for operations and regulation-oriented
evidence.

## Related

- [Deployment profiles](deployment/index.md)
- [ADR-0001](adr/0001-platform-architecture.md)
- Root `SECURITY.md` (vulnerability disclosure)
