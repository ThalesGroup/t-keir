# Vespa document retention (TTL + pin)

Opt-in retention for passage documents in the `global` (index) and `user`
(streaming) schemas. Both inherit the fields from `doc_base`.

Full background: [Vespa document expiry](https://docs.vespa.ai/en/schemas/documents.html#document-expiry).

## New fields

| Field | Type | Default when omitted | Role |
|-------|------|----------------------|------|
| `doc_timestamp` | `long` | unset (`null`) | Unix epoch seconds (TTL base) |
| `freshness_ttl_seconds` | `int` | unset (`null`) | TTL window; `0` or unset ⇒ never expire |
| `pinned` | `bool` | unset (`null`) | When `true`, never expire |
| `pin_reason` | `string` | unset | Why the document is pinned |
| `source_type` | `string` | unset | Provenance label (`ingest`, `beir`, …) |

Vespa schemas **cannot** declare field default values. Omitted fields are
`null` at selection time — they are **not** numeric zero.

## Non-regression guarantee

If **none** of the retention fields are set at ingest (today’s feed path),
the document is kept forever. Behaviour matches pre-retention deployments.

Keep-selection (services.xml, both content clusters):

```text
pinned = true
OR freshness_ttl_seconds = null
OR freshness_ttl_seconds <= 0
OR (freshness_ttl_seconds > 0 AND now() < doc_timestamp + freshness_ttl_seconds)
```

| Feed state | Kept? |
|------------|-------|
| All retention fields omitted | **Yes** |
| `freshness_ttl_seconds = 0` (and any `doc_timestamp`) | **Yes** |
| `pinned = true` | **Yes** |
| `freshness_ttl_seconds > 0` and still inside window | **Yes** |
| `freshness_ttl_seconds > 0` and past window, not pinned | **No** (GC) |

> **Why not the naive `ttl == 0` alone?**  
> Unset integers are `null`, and `null == 0` is false in Vespa’s document
> selector language. Without an explicit `= null` (or `<= 0` after a null
> check), enabling garbage collection would purge every legacy document.

## How to pin a document

At put/update time set:

```json
{
  "pinned": true,
  "pin_reason": "golden-eval-fixture"
}
```

Pinned documents survive even when `freshness_ttl_seconds > 0` and the TTL
window has elapsed.

## How to set a TTL at ingest

```json
{
  "doc_timestamp": 1735689600,
  "freshness_ttl_seconds": 86400,
  "source_type": "collector"
}
```

- `doc_timestamp`: Unix epoch **seconds** (not milliseconds).
- `freshness_ttl_seconds`: positive integer lifetime from that timestamp.
- Omit both (or set TTL to `0`) for permanent retention without pinning.

## Where expiry is configured

Vespa does **not** support a schema-level `document-expiry { … }` block.
Retention is enforced via:

- `vespa/vespa_app/services.xml` → `<documents garbage-collection="true"
  garbage-collection-interval="3600">` + per-type `selection="…"`
- Shared field definitions in `vespa/vespa_app/schemas/templates/doc_base.sd.j2`
  (regenerated into `doc_base.sd` / inherited by `global.sd` and `user.sd`
  via `make schemas`)

GC interval defaults to **3600 s**. Proton flush/compaction is tuned under
`<engine><proton><tuning><searchnode>` so compaction I/O is less likely to
spike search latency.

## Compaction lag caveat

Logical deletion (document no longer selected by the keep expression) is
effectively instant for search once GC has processed the document.
**Physical disk reclaim** happens on later proton flush / compaction cycles
and can lag by **hours** under load. Do not assume immediate disk free space
after TTL expiry.

## Optional ranking freshness (`rag.yaml`)

```yaml
ranking:
  freshness:
    enabled: false          # leave false unless you intend to change scores
    field: doc_timestamp
    max_age_seconds: 604800 # 7 days
    weight: 0.25
```

**Warning:** setting `ranking.freshness.enabled: true` changes ranking
scores. Validate with `make beir-smoke` (and any domain eval you rely on)
before production use. Default `enabled: false` is the non-regression path.

## Deploy checklist

1. `make schemas` (or `make schemas-check` in CI)
2. Redeploy the Vespa application package (`make bootstrap` / Compose
   `compose-bootstrap`)
3. Confirm existing corpora still return hits with no retention fields set
4. Only then feed documents with TTL / pin metadata
