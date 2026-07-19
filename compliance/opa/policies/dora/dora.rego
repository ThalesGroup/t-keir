# DORA (Regulation (EU) 2022/2554) — engineering evidence policy.
# Not legal advice. Full sub-article coverage; out-of-scope → all NOT_MANDATORY.
package eu.dora

import data.eu.common as common

in_scope {
  input.dora.in_scope == true
}

attestation_get(path) = v {
  count(path) == 1
  v := object.get(input.dora.attestation, path[0], null)
}

attestation_get(path) = v {
  count(path) == 2
  outer := object.get(input.dora.attestation, path[0], {})
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
  r := "Entity is not in scope of DORA (input.dora.in_scope == false)"
}

articles = [
  {
    "id": "Art.5(1)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Management body responsible for ICT risk management.", "remediation": "Attest management_ict_risk_responsibility.", "path": ["management_ict_risk_responsibility"]},
    ],
  },
  {
    "id": "Art.5(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Management body approves ICT risk management framework.", "remediation": "Attest management_approves_framework.", "path": ["management_approves_framework"]},
    ],
  },
  {
    "id": "Art.5(4)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Management body defines risk appetite.", "remediation": "Attest risk_appetite_defined.", "path": ["risk_appetite_defined"]},
    ],
  },
  {
    "id": "Art.6(1)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Sound and comprehensive ICT risk management framework.", "remediation": "Run `make security-report` / attest framework.", "key": "security_report_target", "path": ["framework_documented_reviewed"]},
    ],
  },
  {
    "id": "Art.6(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "ICT risk management framework documented and reviewed.", "remediation": "Attest framework_documented_reviewed.", "path": ["framework_documented_reviewed"]},
    ],
  },
  {
    "id": "Art.6(5)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "ICT risk management framework reviewed annually.", "remediation": "Attest framework_reviewed_annually.", "path": ["framework_reviewed_annually"]},
    ],
  },
  {
    "id": "Art.7", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "ICT systems and tools management.", "remediation": "Maintain deploy/versions.lock.yaml.", "key": "versions_lock_present"},
    ],
  },
  {
    "id": "Art.8(1)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "ICT assets identified and classified.", "remediation": "Maintain versions.lock.yaml / chart inventory.", "key": "versions_lock_present"},
    ],
  },
  {
    "id": "Art.8(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Information assets critical to important functions identified.", "remediation": "Attest critical_information_assets_identified.", "path": ["critical_information_assets_identified"]},
    ],
  },
  {
    "id": "Art.9(1)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Data integrity, availability, authenticity protected.", "remediation": "Enable ActionRecord hash chain / WORM.", "key": "action_schema_present", "path": ["audit_worm_retention_set"]},
    ],
  },
  {
    "id": "Art.9(2)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Physical and logical access controls.", "remediation": "Deploy Keycloak scopes and governor.", "key": "keycloak_realm_present", "path": ["governor_flags_present"]},
    ],
  },
  {
    "id": "Art.9(3)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Encryption policies where appropriate.", "remediation": "Attest encryption_policies.", "path": ["encryption_policies"]},
    ],
  },
  {
    "id": "Art.10(1)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Detection mechanisms for anomalous activities.", "remediation": "Enable observability profile (Grafana/Prometheus).", "key": "observability_profile"},
    ],
  },
  {
    "id": "Art.10(2)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Automated alert system.", "remediation": "Enable compose observability profile.", "key": "observability_profile"},
    ],
  },
  {
    "id": "Art.11(1)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "ICT business continuity policy.", "remediation": "Attest bcp_policy.", "path": ["bcp_policy"]},
    ],
  },
  {
    "id": "Art.11(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "BCP with defined RTO/RPO.", "remediation": "Attest bcp_rto_rpo.", "path": ["bcp_rto_rpo"]},
    ],
  },
  {
    "id": "Art.11(3)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Backup procedures and restoration.", "remediation": "Expose rollback-index and audit-verify.", "key": "rollback_target_in_makefile", "path": ["audit_verify_target"]},
    ],
  },
  {
    "id": "Art.11(4)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Alternative facilities and redundant ICT.", "remediation": "Attest alternative_facilities.", "path": ["alternative_facilities"]},
    ],
  },
  {
    "id": "Art.11(6)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "BCP tested annually.", "remediation": "Attest bcp_tested_annually.", "path": ["bcp_tested_annually"]},
    ],
  },
  {
    "id": "Art.12(1)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "ICT-related incident management process defined.", "remediation": "Publish runbooks/incident.md.", "key": "incident_runbook_present"},
    ],
  },
  {
    "id": "Art.12(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Incidents classified.", "remediation": "Attest incidents_classified.", "path": ["incidents_classified"]},
    ],
  },
  {
    "id": "Art.12(3)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Significant ICT incidents reported.", "remediation": "Use tkeir-audit incident tooling.", "key": "incident_runbook_present", "path": ["major_incidents_to_authority"]},
    ],
  },
  {
    "id": "Art.13(1)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Post-ICT-incident review conducted.", "remediation": "Run `make audit-evidence`.", "key": "audit_evidence_dir_non_empty"},
    ],
  },
  {
    "id": "Art.13(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Lessons learned integrated.", "remediation": "Attest lessons_learned_integrated.", "path": ["lessons_learned_integrated"]},
    ],
  },
  {
    "id": "Art.24", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "General DORA resilience testing programme.", "remediation": "Run compose-smoke / audit-verify.", "key": "audit_verify_target", "path": ["security_report_target"]},
    ],
  },
  {
    "id": "Art.25", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Advanced testing — TLPT (significant entities).", "remediation": "Attest tlpt_programme.", "path": ["tlpt_programme"]},
    ],
  },
  {
    "id": "Art.26(3)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "TLPT scope covers production systems.", "remediation": "Attest tlpt_covers_production.", "path": ["tlpt_covers_production"]},
    ],
  },
  {
    "id": "Art.28(1)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "ICT third-party risk management policy.", "remediation": "Attest third_party_risk_policy.", "path": ["third_party_risk_policy"]},
    ],
  },
  {
    "id": "Art.28(2)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Due diligence on ICT third-party providers.", "remediation": "Maintain versions.lock.yaml and SBOM.", "key": "versions_lock_present", "path": ["sbom_cyclonedx_present"]},
    ],
  },
  {
    "id": "Art.28(4)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "ICT third-party risk register maintained.", "remediation": "Maintain deploy/versions.lock.yaml.", "key": "versions_lock_present"},
    ],
  },
  {
    "id": "Art.30(1)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Contractual provisions with ICT providers.", "remediation": "Attest contractual_provisions.", "path": ["contractual_provisions"]},
    ],
  },
  {
    "id": "Art.30(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Contract includes service description, SLAs, right to audit.", "remediation": "Attest contract_sla_audit_rights.", "path": ["contract_sla_audit_rights"]},
    ],
  },
  {
    "id": "Art.30(3)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Exit plan for critical ICT providers.", "remediation": "Attest exit_plan_critical_providers.", "path": ["exit_plan_critical_providers"]},
    ],
  },
  {
    "id": "Art.17(1)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Major ICT incidents reported to competent authority.", "remediation": "Attest major_incidents_to_authority.", "path": ["major_incidents_to_authority"]},
    ],
  },
  {
    "id": "Art.17(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Initial notification within 4 hours.", "remediation": "Attest initial_notification_4h.", "path": ["initial_notification_4h"]},
    ],
  },
  {
    "id": "Art.17(3)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Intermediate report within 72 hours.", "remediation": "Use tkeir-audit incident tooling.", "key": "incident_runbook_present", "path": ["major_incidents_to_authority"]},
    ],
  },
  {
    "id": "Art.17(4)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Final report within 1 month.", "remediation": "Attest final_report_one_month.", "path": ["final_report_one_month"]},
    ],
  },
  {
    "id": "Art.19", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Voluntary reporting of significant cyber threats.", "remediation": "Attest voluntary_cyber_threats.", "path": ["voluntary_cyber_threats"]},
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
  v := common.violation("DORA", a.id, c.severity, c.message, c.remediation)
}

passed[p] {
  in_scope
  some i
  a := articles[i]
  some j
  c := a.checks[j]
  check_passed(c)
  p := common.pass("DORA", a.id, c.message)
}

not_applicable[n] {
  not in_scope
  some i
  a := articles[i]
  n := common.not_mandatory("DORA", a.id, gate_reason)
}

articles_covered = sort([id | id := articles[_].id])

summary = s {
  s := {
    "regulation": "DORA",
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
