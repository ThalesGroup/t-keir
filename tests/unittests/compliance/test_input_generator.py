"""Title: Input generator

Unit tests for input_generator category logic (no OPA required).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MOD_PATH = REPO / "compliance" / "opa" / "collectors" / "input_generator.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("input_generator", MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_determine_category_prohibited():
    mod = _load_mod()
    cat = mod.determine_ai_act_category(
        {
            "prohibited_practices": {"subliminal_manipulation": True},
            "is_gpai_model": False,
        }
    )
    assert cat == "UNACCEPTABLE"


def test_determine_category_gpai_systemic():
    mod = _load_mod()
    assert (
        mod.determine_ai_act_category(
            {
                "prohibited_practices": {},
                "is_gpai_model": True,
                "gpai_systemic_risk": True,
            }
        )
        == "GPAI_SYSTEMIC"
    )


def test_determine_category_high_risk():
    mod = _load_mod()
    assert (
        mod.determine_ai_act_category(
            {
                "prohibited_practices": {},
                "is_gpai_model": False,
                "annex_iii_applies": True,
            }
        )
        == "HIGH_RISK"
    )


def test_determine_category_limited():
    mod = _load_mod()
    assert (
        mod.determine_ai_act_category(
            {
                "prohibited_practices": {},
                "is_gpai_model": False,
                "annex_iii_applies": False,
                "intended_interaction_with_natural_persons": True,
            }
        )
        == "LIMITED_RISK"
    )


def test_determine_category_minimal():
    mod = _load_mod()
    assert (
        mod.determine_ai_act_category(
            {
                "prohibited_practices": {},
                "is_gpai_model": False,
                "annex_iii_applies": False,
                "intended_interaction_with_natural_persons": False,
                "processes_biometric_data": False,
            }
        )
        == "MINIMAL_RISK"
    )
