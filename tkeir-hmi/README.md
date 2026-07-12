# T-KEIR HMI

See [tkeir/docs/hmi.md](../tkeir/docs/hmi.md) for full documentation.

```bash
cd tkeir-hmi
npm install
npm run dev
```

Requires the RAG API: `cd vespa && make rag` (port 8090).

The dev UI proxies `/api/*` to the RAG server via a Next.js API route (see
[tkeir/docs/hmi.md](../tkeir/docs/hmi.md)).
