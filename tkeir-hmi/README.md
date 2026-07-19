# T-KEIR HMI

See [tkeir/docs/hmi.md](../tkeir/docs/hmi.md) for full documentation.

```bash
cd tkeir-hmi
npm install
npm run dev
```

Requires the RAG API: `make rag` from the repo root (port 8090).

The dev UI proxies `/api/*` to the RAG server via a Next.js API route (see
[tkeir/docs/hmi.md](../tkeir/docs/hmi.md)).

## Auth (optional)

Set `AUTH_ENABLED=true` plus Keycloak issuer/client env vars to require OIDC
login (Compose `auth` profile). Default local `npm run dev` stays anonymous.

## Correlation ID

RAG answers show `X-Correlation-Id` with copy + link to `/admin?correlation_id=…`.
