"""Title: Optional S3-compatible PUT (MinIO) using AWS Signature Version 4.

Used by the audit WORM store when ``AUDIT_WORM_S3_ENDPOINT`` is set.
Keeps boto3 out of the core dependency set.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

LOGGER = logging.getLogger(__name__)


def _sign_key(secret: str, datestamp: str, region: str, service: str) -> bytes:
    """Derive AWS SigV4 signing key for one request.

    Example:
        >>> from thot.audit.s3_put import _sign_key
        >>> key = _sign_key("secret", "20260101", "us-east-1", "s3")
        >>> len(key) == 32
        True
    """

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k_date = _hmac(("AWS4" + secret).encode("utf-8"), datestamp)
    k_region = hmac.new(
        k_date, region.encode("utf-8"), hashlib.sha256
    ).digest()
    k_service = hmac.new(
        k_region, service.encode("utf-8"), hashlib.sha256
    ).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def s3_settings_from_env() -> dict[str, Any] | None:
    """Return S3 settings when endpoint is configured; otherwise None.

    Example:
        >>> import os
        >>> from thot.audit.s3_put import s3_settings_from_env
        >>> _ = os.environ.pop("AUDIT_WORM_S3_ENDPOINT", None)
        >>> s3_settings_from_env() is None
        True
        >>> os.environ["AUDIT_WORM_S3_ENDPOINT"] = "http://minio:9000"
        >>> cfg = s3_settings_from_env()
        >>> cfg is not None and cfg["bucket"] == "tkeir-worm"
        True
        >>> del os.environ["AUDIT_WORM_S3_ENDPOINT"]
    """
    endpoint = (os.getenv("AUDIT_WORM_S3_ENDPOINT") or "").rstrip("/")
    if not endpoint:
        return None
    return {
        "endpoint": endpoint,
        "bucket": os.getenv("AUDIT_WORM_S3_BUCKET", "tkeir-worm"),
        "access_key": os.getenv(
            "AUDIT_WORM_S3_ACCESS_KEY",
            os.getenv("MINIO_ROOT_USER", "minioadmin"),
        ),
        "secret_key": os.getenv(
            "AUDIT_WORM_S3_SECRET_KEY",
            os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
        ),
        "region": os.getenv("AUDIT_WORM_S3_REGION", "us-east-1"),
        "prefix": os.getenv("AUDIT_WORM_S3_PREFIX", "segments/").lstrip("/"),
    }


def put_object(
    *,
    endpoint: str,
    bucket: str,
    key: str,
    body: bytes,
    access_key: str,
    secret_key: str,
    region: str = "us-east-1",
    content_type: str = "application/octet-stream",
    extra_headers: dict[str, str] | None = None,
) -> str:
    """PUT an object to an S3-compatible endpoint (path-style).

    Returns:
        ``s3://bucket/key`` URI on success.

    Example:
        >>> import inspect
        >>> from thot.audit.s3_put import put_object
        >>> inspect.isfunction(put_object)
        True
    """
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = parsed.netloc or parsed.path
    scheme = parsed.scheme or "http"
    path = f"/{bucket}/{key.lstrip('/')}"
    url = f"{scheme}://{host}{path}"

    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()

    headers: dict[str, str] = {
        "Host": host,
        "Content-Type": content_type,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if extra_headers:
        headers.update(extra_headers)

    signed_header_names = sorted(k.lower() for k in headers)
    lower_map = {k.lower(): headers[k].strip() for k in headers}
    canonical_headers = "".join(
        f"{name}:{lower_map[name]}\n" for name in signed_header_names
    )
    signed_headers = ";".join(signed_header_names)

    canonical_request = "\n".join(
        [
            "PUT",
            path,
            "",
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{datestamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _sign_key(secret_key, datestamp, region, "s3")
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    request = urllib.request.Request(
        url, data=body, method="PUT", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:  # noqa: S310
            if resp.status not in (200, 201, 204):
                raise RuntimeError(f"S3 PUT failed with status {resp.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"S3 PUT HTTP {exc.code}: {detail}") from exc

    return f"s3://{bucket}/{key.lstrip('/')}"


def _retain_until() -> str:
    """Compute object-lock retain-until timestamp from env retention days.

    Example:
        >>> import os
        >>> from thot.audit.s3_put import _retain_until
        >>> ts = _retain_until()
        >>> ts.endswith("Z") and "T" in ts
        True
    """
    days = int(os.getenv("AUDIT_WORM_RETENTION_DAYS", "30"))
    until = datetime.now(timezone.utc).timestamp() + days * 86400
    return datetime.fromtimestamp(until, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def mirror_worm_segment(
    *,
    segment_id: str,
    compressed: bytes,
    sha_sidecar: bytes,
) -> str | None:
    """Upload segment + sha256 sidecar when S3 env is configured.

    Returns:
        S3 URI of the segment, or None when S3 is not configured.

    Example:
        >>> import os
        >>> from thot.audit.s3_put import mirror_worm_segment
        >>> _ = os.environ.pop("AUDIT_WORM_S3_ENDPOINT", None)
        >>> mirror_worm_segment(
        ...     segment_id="demo", compressed=b"x", sha_sidecar=b"y"
        ... ) is None
        True
    """
    cfg = s3_settings_from_env()
    if cfg is None:
        return None
    prefix = str(cfg["prefix"])
    seg_key = f"{prefix}{segment_id}.jsonl.gz"
    sha_key = f"{prefix}{segment_id}.sha256"
    extra: dict[str, str] | None = None
    if os.getenv("AUDIT_WORM_S3_OBJECT_LOCK", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }:
        extra = {
            "x-amz-object-lock-mode": "COMPLIANCE",
            "x-amz-object-lock-retain-until-date": _retain_until(),
        }
    uri = put_object(
        endpoint=str(cfg["endpoint"]),
        bucket=str(cfg["bucket"]),
        key=seg_key,
        body=compressed,
        access_key=str(cfg["access_key"]),
        secret_key=str(cfg["secret_key"]),
        region=str(cfg["region"]),
        content_type="application/gzip",
        extra_headers=extra,
    )
    put_object(
        endpoint=str(cfg["endpoint"]),
        bucket=str(cfg["bucket"]),
        key=sha_key,
        body=sha_sidecar,
        access_key=str(cfg["access_key"]),
        secret_key=str(cfg["secret_key"]),
        region=str(cfg["region"]),
        content_type="text/plain",
    )
    LOGGER.info("WORM segment mirrored to %s", uri)
    return uri
