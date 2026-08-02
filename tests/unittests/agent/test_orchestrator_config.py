"""Title: Orchestrator usecase config unit tests

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from pathlib import Path

from thot.agent.orchestrator_config import (
    clear_orchestrator_config_cache,
    load_orchestrator_config,
    orchestrator_config_paths,
)


def test_orchestrator_config_paths_discover_packs():
    paths = orchestrator_config_paths()
    names = {path.parent.name for path in paths}
    assert "osint" in names
    assert "enterprise" in names


def test_load_osint_orchestrator_config():
    clear_orchestrator_config_cache()
    cfg = load_orchestrator_config(usecase="osint")
    assert cfg.default_report_form == "intsum"
    assert cfg.template_for("commander_brief") == "otan_commander_brief"
    assert "otan_intsum slots" in cfg.slot_hint_for("intsum")


def test_load_enterprise_orchestrator_config():
    clear_orchestrator_config_cache()
    cfg = load_orchestrator_config(usecase="enterprise")
    assert cfg.default_report_form == "risk_summary"
    assert cfg.template_for("field_report") == "ent_field_report"
    assert cfg.template_for("decision_brief") == "ent_decision_brief"
    assert "ent_board_sitrep slots" in cfg.slot_hint_for("board_sitrep")


def test_merged_config_keeps_both_usecase_forms(tmp_path: Path):
    clear_orchestrator_config_cache()
    cfg = load_orchestrator_config(usecase="enterprise")
    # Enterprise defaults, but OSINT forms remain available when both packs exist.
    assert cfg.template_for("intsum") == "otan_intsum"
    assert cfg.template_for("risk_summary") == "ent_risk_summary"
