"""Title: compose package init

T-KEIR ontology-driven composition (Phase C).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from thot.compose.composer import compose
from thot.compose.registry import list_template_names, load_template
from thot.compose.template_models import ComposeResult

__all__ = [
    "ComposeResult",
    "compose",
    "list_template_names",
    "load_template",
]
