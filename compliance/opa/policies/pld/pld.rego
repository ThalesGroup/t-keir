# Product Liability Directive (Directive (EU) 2024/2853) — engineering evidence policy.
# Not legal advice. Full article coverage Art.4–Art.22 from audit specification.
package eu.pld

import data.eu.common as common

in_scope {
  input.pld.in_scope == true
}

attestation_get(path) = v {
  count(path) == 1
  v := object.get(input.pld.attestation, path[0], null)
}

attestation_get(path) = v {
  count(path) == 2
  outer := object.get(input.pld.attestation, path[0], {})
  v := object.get(outer, path[1], null)
}

check_passed(check) {
  check.source == "evidence"
  common.truthy(object.get(input.evidence, check.key, null))
}

check_passed(check) {
  check.source == "attestation"
  common.truthy(attestation_get(check.path))
}

check_passed(check) {
  check.source == "either"
  common.truthy(attestation_get(check.path))
}

check_passed(check) {
  check.source == "either"
  common.truthy(object.get(input.evidence, check.key, null))
}

check_passed(check) {
  check.source == "evidence_gte"
  object.get(input.evidence, check.key, 0) >= check.min
}

check_passed(check) {
  check.source == "product"
  object.get(input.product, check.key, null) == true
}

check_passed(check) {
  check.source == "either_gte"
  object.get(input.evidence, check.key, 0) >= check.min
}

check_passed(check) {
  check.source == "either_gte"
  common.truthy(attestation_get(check.path))
}

gate_reason = r {
  r := "Product/service is not in scope of the Product Liability Directive (input.pld.in_scope == false)"
}

articles = [
  {
    "id": "Art.4", "gate": "in_scope",
    "checks": [
      {"source": "product", "severity": "HIGH", "message": "Product includes software and AI systems.", "remediation": "Set product.is_software=true in overrides.", "key": "is_software"},
    ],
  },
  {
    "id": "Art.5", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Defective product — proof chain (damage/defect/causal link) supported by audit.", "remediation": "Use `make audit-report CID=…`.", "key": "correlation_id_in_code", "path": ["action_records_bind_versions"]},
    ],
  },
  {
    "id": "Art.6(1)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Product defectiveness criteria (inventory + vuln evidence).", "remediation": "Publish SBOM and trivy reports.", "key": "sbom_cyclonedx_present", "path": ["trivy_report_present"]},
    ],
  },
  {
    "id": "Art.6(2)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Legitimate expectations of product safety.", "remediation": "Ship values-secure.yaml.", "key": "values_secure_present"},
    ],
  },
  {
    "id": "Art.6(3)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Defect includes software updates introducing defects.", "remediation": "Maintain versions.lock.yaml and CHANGELOG.", "key": "versions_lock_present", "path": ["changelog_present"]},
    ],
  },
  {
    "id": "Art.7", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Economic operator liable (manufacturer / importer / authorised rep).", "remediation": "Attest economic_operator_role_documented.", "path": ["economic_operator_role_documented"]},
    ],
  },
  {
    "id": "Art.8", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Rebuttable presumptions of defect.", "remediation": "Attest rebuttable_presumptions_acknowledged.", "path": ["rebuttable_presumptions_acknowledged"]},
    ],
  },
  {
    "id": "Art.9", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Damage covered (including data corruption) — WORM integrity.", "remediation": "Run `make audit-verify`; retain WORM segments.", "key": "audit_verify_target", "path": ["audit_worm_retention_set"]},
    ],
  },
  {
    "id": "Art.10", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Exemptions from liability.", "remediation": "Attest liability_exemptions_documented.", "path": ["liability_exemptions_documented"]},
    ],
  },
  {
    "id": "Art.11(1)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "Liability limited to 10 years from market placement (version history).", "remediation": "Maintain CHANGELOG.md and SBOM history.", "key": "changelog_present", "path": ["sbom_cyclonedx_present"]},
    ],
  },
  {
    "id": "Art.12", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Disclosure of evidence — manufacturer must disclose relevant data.", "remediation": "Use `make audit-report CID=…`.", "key": "correlation_id_in_code", "path": ["action_records_bind_versions"]},
    ],
  },
  {
    "id": "Art.13", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Court power to order disclosure — process documented.", "remediation": "Attest court_disclosure_process.", "path": ["court_disclosure_process"]},
    ],
  },
  {
    "id": "Art.14", "gate": "in_scope",
    "checks": [
      {"source": "evidence_gte", "severity": "MEDIUM", "message": "Relevant evidence preserved (retention ≥ 3650 days).", "remediation": "Set AUDIT_WORM_RETENTION_DAYS >= 3650; run audit-verify.", "key": "audit_worm_retention_days", "min": 3650},
    ],
  },
  {
    "id": "Art.15", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Burden of proof (rebuttable presumption where evidence withheld).", "remediation": "Run `make audit-evidence`.", "key": "audit_evidence_dir_non_empty"},
    ],
  },
  {
    "id": "Art.16", "gate": "in_scope",
    "checks": [
      {"source": "evidence_gte", "severity": "MEDIUM", "message": "Limitation period — 3 years from awareness of damage (retention sufficient).", "remediation": "Ensure AUDIT_WORM_RETENTION_DAYS covers ≥ 3 years.", "key": "audit_worm_retention_days", "min": 1095},
    ],
  },
  {
    "id": "Art.17", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Long-stop period — 10 years from market placement (version history).", "remediation": "Maintain deploy/versions.lock.yaml version history.", "key": "versions_lock_present"},
    ],
  },
  {
    "id": "Art.18", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Right to full compensation.", "remediation": "Attest right_to_full_compensation.", "path": ["right_to_full_compensation"]},
    ],
  },
  {
    "id": "Art.22", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Contractual exclusions prohibited.", "remediation": "Attest contractual_exclusions_prohibited.", "path": ["contractual_exclusions_prohibited"]},
    ],
  },
]

violations[v] {
  in_scope
  some i
  a := articles[i]
  some j
  c := a.checks[j]
  not check_passed(c)
  v := common.violation("PLD", a.id, c.severity, c.message, c.remediation)
}

passed[p] {
  in_scope
  some i
  a := articles[i]
  some j
  c := a.checks[j]
  check_passed(c)
  p := common.pass("PLD", a.id, c.message)
}

not_applicable[n] {
  not in_scope
  some i
  a := articles[i]
  n := common.not_mandatory("PLD", a.id, gate_reason)
}

articles_covered = sort([id | id := articles[_].id])

summary = s {
  s := {
    "regulation": "PLD",
    "compliant": count(violations) == 0,
    "violations_count": count(violations),
    "passed_count": count(passed),
    "not_applicable_count": count(not_applicable),
    "compliance_score": common.score(count(passed), count(violations)),
    "violations": [v | v := violations[_]],
    "passed": [p | p := passed[_]],
    "not_applicable": [n | n := not_applicable[_]],
    "articles_covered": articles_covered,
  }
}

default allow = false

allow {
  count(violations) == 0
}
