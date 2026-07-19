# NIS2 (Directive (EU) 2022/2555) — engineering evidence policy.
# Not legal advice. Full sub-article coverage; OUT_OF_SCOPE → all NOT_MANDATORY.
package eu.nis2

import data.eu.common as common

entity_type = t {
  t := input.nis2.entity_type
}

in_scope {
  entity_type == "ESSENTIAL"
}

in_scope {
  entity_type == "IMPORTANT"
}

attestation_get(path) = v {
  count(path) == 1
  v := object.get(input.nis2.attestation, path[0], null)
}

attestation_get(path) = v {
  count(path) == 2
  outer := object.get(input.nis2.attestation, path[0], {})
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

gate_ok(article) {
  article.gate == "in_scope"
  in_scope
}

gate_reason = r {
  r := sprintf("Entity is OUT_OF_SCOPE for NIS2 (entity_type: %s)", [entity_type])
}

articles = [
  {
    "id": "Art.20(1)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Management body approves cybersecurity measures.", "remediation": "Attest management_approves_cyber_measures.", "path": ["management_approves_cyber_measures"]},
    ],
  },
  {
    "id": "Art.20(2)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Management body members trained on cybersecurity.", "remediation": "Attest management_trained.", "path": ["management_trained"]},
    ],
  },
  {
    "id": "Art.20(3)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Management body responsible for infringements.", "remediation": "Attest management_liable_infringements.", "path": ["management_liable_infringements"]},
    ],
  },
  {
    "id": "Art.21(1)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Technical and organisational measures proportionate to risk.", "remediation": "Run `make security-report`.", "key": "security_report_target", "path": ["values_secure_present"]},
    ],
  },
  {
    "id": "Art.21(2)(a)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Risk analysis and information system security policies.", "remediation": "Ship values-secure.yaml.", "key": "values_secure_present"},
    ],
  },
  {
    "id": "Art.21(2)(b)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Incident handling procedures.", "remediation": "Publish runbooks/incident.md.", "key": "incident_runbook_present"},
    ],
  },
  {
    "id": "Art.21(2)(c)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Business continuity — backup, DR, crisis management.", "remediation": "Expose rollback-index and audit-verify.", "key": "rollback_target_in_makefile", "path": ["audit_verify_target"]},
    ],
  },
  {
    "id": "Art.21(2)(d)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Supply chain security.", "remediation": "Maintain versions.lock.yaml and SBOM.", "key": "versions_lock_present", "path": ["sbom_cyclonedx_present"]},
    ],
  },
  {
    "id": "Art.21(2)(e)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Security in network system acquisition and development.", "remediation": "Enable CI security.yml / trivy.", "key": "ci_security_workflow", "path": ["trivy_report_present"]},
    ],
  },
  {
    "id": "Art.21(2)(f)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Policies and procedures to assess security measures.", "remediation": "Run `make audit-evidence`.", "key": "audit_evidence_dir_non_empty"},
    ],
  },
  {
    "id": "Art.21(2)(g)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Cyber hygiene practices and training.", "remediation": "Attest cyber_hygiene_training.", "path": ["cyber_hygiene_training"]},
    ],
  },
  {
    "id": "Art.21(2)(h)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Cryptography and encryption policies.", "remediation": "Attest cryptography_policies.", "path": ["cryptography_policies"]},
    ],
  },
  {
    "id": "Art.21(2)(i)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Human resources security, access control, asset management.", "remediation": "Deploy Keycloak realm.", "key": "keycloak_realm_present"},
    ],
  },
  {
    "id": "Art.21(2)(j)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Multi-factor authentication or continuous authentication.", "remediation": "Enable compose auth profile / Keycloak MFA.", "key": "compose_auth_profile"},
    ],
  },
  {
    "id": "Art.21(2)(k)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Secured emergency communications.", "remediation": "Attest secured_emergency_communications.", "path": ["secured_emergency_communications"]},
    ],
  },
  {
    "id": "Art.21(3)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Proportionality to risk level.", "remediation": "Attest proportionality_documented.", "path": ["proportionality_documented"]},
    ],
  },
  {
    "id": "Art.21(4)", "gate": "in_scope",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Network segmentation.", "remediation": "Ship networkpolicy.yaml.", "key": "networkpolicy_template"},
    ],
  },
  {
    "id": "Art.23(1)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Significant incidents reported to CSIRT/authority.", "remediation": "Attest significant_incidents_reported.", "path": ["significant_incidents_reported"]},
    ],
  },
  {
    "id": "Art.23(3)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Early warning within 24h.", "remediation": "Use tkeir-audit incident --kind early-warning.", "key": "incident_runbook_present", "path": ["significant_incidents_reported"]},
    ],
  },
  {
    "id": "Art.23(4)", "gate": "in_scope",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Incident notification within 72h.", "remediation": "Use tkeir-audit incident tooling.", "key": "incident_runbook_present", "path": ["significant_incidents_reported"]},
    ],
  },
  {
    "id": "Art.23(5)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Final report within 1 month.", "remediation": "Attest final_report_one_month.", "path": ["final_report_one_month"]},
    ],
  },
  {
    "id": "Art.23(6)", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Cyber threats reported (voluntary).", "remediation": "Attest cyber_threats_voluntary.", "path": ["cyber_threats_voluntary"]},
    ],
  },
  {
    "id": "Art.24", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Use of European cybersecurity certification schemes.", "remediation": "Attest european_certification_schemes.", "path": ["european_certification_schemes"]},
    ],
  },
  {
    "id": "Art.26", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Jurisdiction — entity registered in member state.", "remediation": "Attest jurisdiction_member_state.", "path": ["jurisdiction_member_state"]},
    ],
  },
  {
    "id": "Art.27", "gate": "in_scope",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Entity registered with national authority.", "remediation": "Attest registered_with_national_authority.", "path": ["registered_with_national_authority"]},
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
  v := common.violation("NIS2", a.id, c.severity, c.message, c.remediation)
}

passed[p] {
  in_scope
  some i
  a := articles[i]
  some j
  c := a.checks[j]
  check_passed(c)
  p := common.pass("NIS2", a.id, c.message)
}

not_applicable[n] {
  not in_scope
  some i
  a := articles[i]
  n := common.not_mandatory("NIS2", a.id, gate_reason)
}

articles_covered = sort([id | id := articles[_].id])

summary = s {
  s := {
    "regulation": "NIS2",
    "entity_type": entity_type,
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
