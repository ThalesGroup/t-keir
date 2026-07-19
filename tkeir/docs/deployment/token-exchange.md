# Token exchange (RFC 8693)

T-KEIR governors mint **constrained action tokens** (`POST /governor/token`)
with TTL ≤ 300s. In production IdPs, exchange a Keycloak access token for
these tokens using [RFC 8693](https://datatracker.ietf.org/doc/html/rfc8693)
token exchange so the delegation chain is recorded on ActionRecords.

## Dev path (Compose)

1. Obtain a Keycloak access token for `demo-admin` (realm `tkeir`).
2. Call governor with that bearer (when `GOVERNOR_AUTH_ENABLED=true`).
3. Mint an action token; pass it to downstream tools as
   `Authorization: Bearer <action-token>` (or a dedicated header).
4. Revoke via `POST /governor/revoke` — effective immediately against the
   governor revoke list.

Full Keycloak→Keycloak internal token-exchange client configuration is
operator-owned (enable token exchange on the realm / clients). The governor
`delegation_note` field on mint responses documents the intended hop.

## Helm

Enable the bundled Keycloak subchart (dev only):

```bash
helm upgrade --install tkeir deploy/charts/tkeir \
  -f deploy/charts/tkeir/values-dev.yaml \
  --set keycloak.enabled=true
```

Or set `keycloak.useExisting=true` and point `oidc.issuer` at an external IdP.
Export a running realm with `make keycloak-export-realm`.
