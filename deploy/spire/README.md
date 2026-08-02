# SPIRE / SPIFFE (agent workload identity)

Compose and config stubs for SPIRE so `tkeir-agent` can obtain a SPIFFE ID
per [ADR-0008](../../docs/adr/0008-spire-agent-identity.md).

## Trust domain

Default: `tkeir.local` (`SPIFFE_TRUST_DOMAIN`).

Agent IDs: `spiffe://tkeir.local/agent/{name}` (e.g. `researcher`, `tkeir-agent`).

## Compose

```bash
# SPIRE server + agent (healthcheck + automatic join token)
make spire-up
```

`make spire-up` starts the Compose `spire` profile, waits until the server is
**healthy**, mints a join token for `spiffe://tkeir.local/spire-agent`, and
recreates the agent with `-joinToken`.

The SPIRE images are distroless (no `/bin/sh`). Healthchecks must use:

```text
/opt/spire/bin/spire-server healthcheck -socketPath /tmp/spire-server/private/api.sock
```

not a shell TCP probe.

Agents with workload identity (dev synthesize if socket not yet registered):

```bash
make compose-up PROFILES=spire,agents,governor,auth
```

Env on `tkeir-agent`:

| Variable | Role |
|----------|------|
| `SPIFFE_MODE` | `off` \| `dev` \| `workload` |
| `SPIFFE_TRUST_DOMAIN` | Trust domain (default `tkeir.local`) |
| `SPIFFE_ID` | Explicit SVID ID (Compose inject) |
| `SPIFFE_ENDPOINT_SOCKET` | Workload API unix socket |
| `SPIFFE_ENFORCE` | Require allowed agent SPIFFE ID |
| `SPIFFE_AGENT_ID_PREFIX` | Allow-list prefixes (comma-separated) |

## Layout

| Path | Purpose |
|------|---------|
| `server.conf` | SPIRE server (trust domain `tkeir.local`) |
| `agent.conf` | SPIRE agent → Workload API socket |
| `register-agent-entries.sh` | Register agent workload entries after join |
| `Dockerfile` notes | Images pinned in `deploy/versions.lock.yaml` |

## Local without SPIRE containers

```bash
export SPIFFE_MODE=dev
export SPIFFE_ENFORCE=false   # or true once testing mastering
# IDs become spiffe://tkeir.local/agent/<agent_yaml_name>
```

## Kubernetes

Chart wiring lands with the secure profile; until then mount a SPIRE Agent
Workload API socket (or projected SVID) into the `tkeir-agent` Deployment and
set `SPIFFE_MODE=workload`.
