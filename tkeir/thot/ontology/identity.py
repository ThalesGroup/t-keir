"""Title: Canonical ontology concept identity.

One ID strategy for the whole product. Labels are never identifiers.
Existing business-ontology ``concept_id`` values and legacy JSON
``PATH:value`` tokens are preserved so already-indexed chunks keep matching.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import re
from typing import Final

# Namespaces. Do not mint IDs outside this module.
NS_JSON_ATTRIBUTE: Final = "json:attribute:"
NS_JSON_VALUE: Final = "json:value:"
NS_DOC: Final = "doc:"
NS_PRED: Final = "pred:"
NS_BIZ: Final = "biz:"

PRED_HAS_VALUE: Final = "pred:has_value"
PRED_BROADER: Final = "pred:broader"
PRED_NARROWER: Final = "pred:narrower"
PRED_RELATED: Final = "pred:related"

_NON_ID = re.compile(r"[^a-zA-Z0-9._\-:/]+")
_MULTI_DASH = re.compile(r"-{2,}")
_LEGACY_PATH = re.compile(r"[^\w]+")
_LEGACY_VALUE = re.compile(r"[^\w.\-]+")
_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-/]{0,179}$")


def sanitize_id_part(raw: str, *, max_len: int = 120) -> str:
    """Normalize one path/value/label fragment for use inside an ID.

    Example:
        >>> from thot.ontology.identity import sanitize_id_part
        >>> sanitize_id_part("Customer Country")
        'customer.country'
        >>> sanitize_id_part("  Kubernetes  ")
        'kubernetes'
    """
    text = (raw or "").strip().replace(" ", ".")
    text = _NON_ID.sub("-", text)
    text = _MULTI_DASH.sub("-", text).strip(".-_:")
    return text[:max_len].casefold() or "unnamed"


def is_stable_id(raw: str) -> bool:
    """True when ``raw`` is already a compact identifier (not a sentence).

    Example:
        >>> from thot.ontology.identity import is_stable_id
        >>> is_stable_id("C4ISR")
        True
        >>> is_stable_id("technology:kubernetes")
        True
        >>> is_stable_id("How is Kubernetes deployed in production?")
        False
    """
    text = (raw or "").strip()
    if not text or " " in text or len(text) > 180:
        return False
    return bool(_STABLE_ID.match(text))


def preserve_or_mint(raw: str, *, namespace: str = NS_DOC) -> str:
    """Keep a stable ID as-is; otherwise mint ``namespace + sanitized``.

    Expert ``concept_id`` values (``C4ISR``, ``MARITIME``) stay unchanged.

    Example:
        >>> from thot.ontology.identity import preserve_or_mint
        >>> preserve_or_mint("C4ISR")
        'C4ISR'
        >>> preserve_or_mint("Acme Corp")
        'doc:acme.corp'
    """
    text = (raw or "").strip()
    if not text:
        return f"{namespace}unnamed"
    if is_stable_id(text):
        return text[:180]
    return f"{namespace}{sanitize_id_part(text)}"[:180]


def json_attribute_id(path: str) -> str:
    """Stable ID for a JSON attribute / dotted path.

    Example:
        >>> from thot.ontology.identity import json_attribute_id
        >>> json_attribute_id("customer.country")
        'json:attribute:customer.country'
    """
    path_id = sanitize_id_part(path, max_len=160) or "path"
    return f"{NS_JSON_ATTRIBUTE}{path_id}"[:180]


def json_value_id(path: str, value: str) -> str:
    """Stable ID for a JSON attribute/value pair.

    Example:
        >>> from thot.ontology.identity import json_value_id
        >>> json_value_id("customer.country", "France")
        'json:value:customer.country=france'
    """
    path_id = sanitize_id_part(path, max_len=100) or "path"
    val_id = sanitize_id_part(value, max_len=60) or "value"
    return f"{NS_JSON_VALUE}{path_id}={val_id}"[:180]


def legacy_json_value_id(path: str, value: str) -> str | None:
    """Backward-compatible ``PATH:value`` token used in existing indexes.

    Example:
        >>> from thot.ontology.identity import legacy_json_value_id
        >>> legacy_json_value_id("domain", "osint")
        'DOMAIN:osint'
    """
    text = (value or "").strip()
    if not text or len(text) > 120:
        return None
    if len(text) > 64 and " " in text:
        return None
    path_key = _LEGACY_PATH.sub("_", path).strip("_").upper()
    val_key = _LEGACY_VALUE.sub("_", text).strip("._")
    if not path_key or not val_key:
        return None
    return f"{path_key}:{val_key}"[:180]


def predicate_id(raw: str) -> str:
    """Stable predicate ID. Known ``pred:*`` values are preserved.

    Example:
        >>> from thot.ontology.identity import predicate_id, PRED_HAS_VALUE
        >>> predicate_id("has_value")
        'pred:has_value'
        >>> predicate_id(PRED_HAS_VALUE)
        'pred:has_value'
        >>> predicate_id("implements")
        'pred:implements'
    """
    text = (raw or "").strip()
    if text.startswith(NS_PRED) and is_stable_id(text):
        return text[:180]
    return f"{NS_PRED}{sanitize_id_part(text) or 'related'}"[:180]


def relation_key(
    subject_id: str, predicate_id_value: str, object_id: str
) -> str:
    """Compact ``s|p|o`` key for Vespa ``array<string>`` exact-match.

    Example:
        >>> from thot.ontology.identity import relation_key, PRED_HAS_VALUE
        >>> relation_key("a", PRED_HAS_VALUE, "b")
        'a|pred:has_value|b'
    """
    subj = (subject_id or "").strip()
    pred = predicate_id(predicate_id_value)
    obj = (object_id or "").strip()
    return f"{subj}|{pred}|{obj}"[:500]


def parse_relation_key(key: str) -> tuple[str, str, str] | None:
    """Split a compact relation key. Returns None when malformed.

    Example:
        >>> from thot.ontology.identity import parse_relation_key
        >>> parse_relation_key("a|pred:has_value|b")
        ('a', 'pred:has_value', 'b')
        >>> parse_relation_key("bad") is None
        True
    """
    parts = (key or "").split("|", 2)
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]
