"""Title: Vespa retention keep-selection non-regression checks.

Mirrors the document selection used in ``vespa/vespa_app/services.xml``.
Unset fields are ``null`` in Vespa (not numeric zero).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations


def retention_keep(
    *,
    pinned: bool | None,
    freshness_ttl_seconds: int | None,
    doc_timestamp: int | None,
    now: int,
) -> bool:
    """Return True when the Vespa keep-selection would retain the document.

    Expression (per document type prefix stripped)::

        pinned = true
        or freshness_ttl_seconds = null
        or freshness_ttl_seconds <= 0
        or (freshness_ttl_seconds > 0
            and now() < doc_timestamp + freshness_ttl_seconds)

    Example:
        >>> retention_keep(
        ...     pinned=None, freshness_ttl_seconds=None, doc_timestamp=None, now=1
        ... )
        True
    """
    if pinned is True:
        return True
    if freshness_ttl_seconds is None or freshness_ttl_seconds <= 0:
        return True
    base = 0 if doc_timestamp is None else int(doc_timestamp)
    return now < base + int(freshness_ttl_seconds)


def test_unset_fields_never_expire():
    assert retention_keep(
        pinned=None,
        freshness_ttl_seconds=None,
        doc_timestamp=None,
        now=1_700_000_000,
    )


def test_explicit_zero_ttl_never_expires():
    assert retention_keep(
        pinned=False,
        freshness_ttl_seconds=0,
        doc_timestamp=0,
        now=1_700_000_000,
    )


def test_pinned_survives_expired_ttl():
    now = 1_700_000_000
    assert retention_keep(
        pinned=True,
        freshness_ttl_seconds=60,
        doc_timestamp=now - 120,
        now=now,
    )


def test_ttl_window_fresh_and_expired():
    now = 1_700_000_000
    assert retention_keep(
        pinned=False,
        freshness_ttl_seconds=3600,
        doc_timestamp=now - 10,
        now=now,
    )
    assert not retention_keep(
        pinned=False,
        freshness_ttl_seconds=3600,
        doc_timestamp=now - 4000,
        now=now,
    )


def test_naive_ttl_eq_zero_would_break_unset():
    """Document why services.xml must treat null TTL as keep."""
    ttl = None
    naive = ttl == 0  # Vespa: null == 0 → false
    assert naive is False
    assert retention_keep(
        pinned=None,
        freshness_ttl_seconds=ttl,
        doc_timestamp=None,
        now=1,
    )
