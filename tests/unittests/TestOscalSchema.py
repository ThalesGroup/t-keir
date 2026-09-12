"""NIST OSCAL JSON Schema validation for T-KEIR audit artefacts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
OSCAL = ROOT / "compliance" / "opa" / "oscal"
sys.path.insert(0, str(OSCAL))

from opa_to_oscal import (  # noqa: E402
    SSP_UUID,
    build_assessment_results,
    build_poam,
    oscal_datetime,
)
from validate_oscal import (  # noqa: E402
    SCHEMA_DIR,
    detect_model,
    iter_errors,
    load_schema,
    validate_document,
)


class TestOscalDatetime(unittest.TestCase):
    def test_zulu_offset(self) -> None:
        stamp = oscal_datetime()
        self.assertTrue(stamp.endswith("Z"))
        self.assertNotIn("+00:00", stamp)


class TestNistSchemasPresent(unittest.TestCase):
    def test_release_assets_on_disk(self) -> None:
        for name in (
            "oscal_assessment-results_schema.json",
            "oscal_poam_schema.json",
            "oscal_assessment-plan_schema.json",
            "oscal_catalog_schema.json",
            "oscal_profile_schema.json",
            "oscal_ssp_schema.json",
            "oscal_component_schema.json",
        ):
            path = SCHEMA_DIR / name
            self.assertTrue(path.is_file(), msg=path)
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                schema.get("$schema"),
                "http://json-schema.org/draft-07/schema#",
            )


class TestGeneratedAssessmentResults(unittest.TestCase):
    def test_fixture_roundtrip_schema(self) -> None:
        fixture = {
            "summary": {
                "passed": [
                    {
                        "article": "Art.12(1)",
                        "regulation": "AI Act",
                        "message": "Logging implemented.",
                    }
                ],
                "not_applicable": [
                    {
                        "article": "Art.26",
                        "regulation": "AI Act",
                        "reason": "Not a high-risk system",
                    }
                ],
                "violations": [
                    {
                        "article": "Art.14(1)",
                        "regulation": "AI Act",
                        "severity": "HIGH",
                        "message": "Human oversight gap",
                        "remediation": "Enable governor kill switch.",
                    }
                ],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            (results / "opa-ai_act.json").write_text(
                json.dumps(fixture), encoding="utf-8"
            )
            ar = build_assessment_results(results, SSP_UUID, "test-1")
            findings = ar["assessment-results"]["results"][0].get("findings") or []
            poam = build_poam(findings, "test-1")

        self.assertEqual(detect_model(ar), "assessment-results")
        self.assertEqual(detect_model(poam), "plan-of-action-and-milestones")
        ar_errors = iter_errors(ar, load_schema("assessment-results"))
        poam_errors = iter_errors(poam, load_schema("plan-of-action-and-milestones"))
        self.assertEqual(ar_errors, [], msg="\n".join(ar_errors))
        self.assertEqual(poam_errors, [], msg="\n".join(poam_errors))

        methods = ar["assessment-results"]["results"][0]["observations"][0]["methods"]
        self.assertEqual(methods, ["TEST"])
        finding = ar["assessment-results"]["results"][0]["findings"][0]
        self.assertNotIn("risks", finding)
        self.assertIn("related-risks", finding)


class TestStaticOscalLayer(unittest.TestCase):
    def test_ssp_and_assessment_plan(self) -> None:
        for rel in (
            "ssp/tkeir_ssp.json",
            "assessments/assessment_plan.json",
        ):
            path = OSCAL / rel
            model, errors = validate_document(path)
            self.assertTrue(model)
            self.assertEqual(errors, [], msg=f"{rel}:\n" + "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
