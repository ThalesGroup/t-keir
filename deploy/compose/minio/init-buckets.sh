#!/usr/bin/env bash
# Create MinIO buckets with object-lock for WORM audit + ingest raw/staging.
set -euo pipefail

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-minioadmin}"
WORM_RETENTION_DAYS="${AUDIT_WORM_RETENTION_DAYS:-30}"

echo "Waiting for MinIO at ${MINIO_ENDPOINT}..."
until mc alias set local "${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null 2>&1; do
  sleep 2
done

# Object-lock must be enabled at bucket creation.
mc mb --with-lock local/tkeir-worm || true
mc retention set --default COMPLIANCE "${WORM_RETENTION_DAYS}d" local/tkeir-worm || true

mc mb local/tkeir-raw || true
mc mb local/tkeir-staging || true
mc mb local/tkeir-dlq || true

echo "MinIO buckets ready (worm retention=${WORM_RETENTION_DAYS}d COMPLIANCE)."
