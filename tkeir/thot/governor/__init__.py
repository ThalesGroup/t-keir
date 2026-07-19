"""Runtime governor — enforce mode, budgets, kill switch, approvals.

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2026 by THALES
All Rights Reserved.
"""

from thot.governor.client import GovernorClient
from thot.governor.config import governor_settings
from thot.governor.models import KillScope, RuntimeFlags
from thot.governor.wiring import wire_governor_middleware

__all__ = [
    "GovernorClient",
    "KillScope",
    "RuntimeFlags",
    "governor_settings",
    "wire_governor_middleware",
]
