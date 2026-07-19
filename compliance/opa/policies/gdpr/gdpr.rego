# GDPR (Regulation (EU) 2016/679) — engineering evidence policy.
# Not legal advice. Full sub-article coverage; processing always assumed.
package eu.gdpr

import data.eu.common as common

attestation_get(path) = v {
  count(path) == 1
  v := object.get(input.gdpr.attestation, path[0], null)
}

attestation_get(path) = v {
  count(path) == 2
  outer := object.get(input.gdpr.attestation, path[0], {})
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
  article.gate == "all"
}

articles = [
  {
    "id": "Art.5(1)(a)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Lawfulness, fairness, transparency.", "remediation": "Attest lawfulness_fairness_transparency.", "path": ["lawfulness_fairness_transparency"]},
    ],
  },
  {
    "id": "Art.5(1)(b)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Purpose limitation.", "remediation": "Attest purpose_limitation.", "path": ["purpose_limitation"]},
    ],
  },
  {
    "id": "Art.5(1)(c)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Data minimisation (request_hash only).", "remediation": "Keep ActionRecord request_hash-only by default.", "key": "action_schema_present"},
    ],
  },
  {
    "id": "Art.5(1)(d)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Accuracy.", "remediation": "Attest accuracy.", "path": ["accuracy"]},
    ],
  },
  {
    "id": "Art.5(1)(e)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Storage limitation (retention configured).", "remediation": "Configure AUDIT_WORM_RETENTION_DAYS.", "key": "audit_worm_retention_set"},
    ],
  },
  {
    "id": "Art.5(1)(f)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Integrity and confidentiality.", "remediation": "Ship privacy.py and WORM hash chain.", "key": "privacy_py_present", "path": ["audit_worm_retention_set"]},
    ],
  },
  {
    "id": "Art.5(2)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Accountability demonstrated.", "remediation": "Run `make audit-evidence`.", "key": "audit_evidence_dir_non_empty"},
    ],
  },
  {
    "id": "Art.6", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Legal basis for processing documented.", "remediation": "Attest legal_basis_documented.", "path": ["legal_basis_documented"]},
    ],
  },
  {
    "id": "Art.9(1)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Special categories not processed without Art.9(2) basis.", "remediation": "Attest special_categories_basis.", "path": ["special_categories_basis"]},
    ],
  },
  {
    "id": "Art.12", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Transparent communication to data subjects.", "remediation": "Attest transparent_communication.", "path": ["transparent_communication"]},
    ],
  },
  {
    "id": "Art.13", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Information provided at collection.", "remediation": "Attest information_at_collection.", "path": ["information_at_collection"]},
    ],
  },
  {
    "id": "Art.14", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Information where data not collected from subject.", "remediation": "Attest information_not_from_subject.", "path": ["information_not_from_subject"]},
    ],
  },
  {
    "id": "Art.15", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Right of access implemented.", "remediation": "Attest right_of_access.", "path": ["right_of_access"]},
    ],
  },
  {
    "id": "Art.16", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Right to rectification.", "remediation": "Attest right_to_rectification.", "path": ["right_to_rectification"]},
    ],
  },
  {
    "id": "Art.17", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Right to erasure — crypto-shredding.", "remediation": "Ship thot/audit/privacy.py (`tkeir-audit forget`).", "key": "privacy_py_present"},
    ],
  },
  {
    "id": "Art.18", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Right to restriction of processing.", "remediation": "Attest right_to_restriction.", "path": ["right_to_restriction"]},
    ],
  },
  {
    "id": "Art.19", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Notification obligation on erasure/restriction.", "remediation": "Attest notification_on_erasure.", "path": ["notification_on_erasure"]},
    ],
  },
  {
    "id": "Art.20", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Right to data portability.", "remediation": "Attest right_to_portability.", "path": ["right_to_portability"]},
    ],
  },
  {
    "id": "Art.21", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Right to object.", "remediation": "Attest right_to_object.", "path": ["right_to_object"]},
    ],
  },
  {
    "id": "Art.22", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Automated decision-making safeguards / human approval.", "remediation": "Attest automated_decision_safeguards; use governor approvals.", "key": "governor_approvals_present", "path": ["automated_decision_safeguards"]},
    ],
  },
  {
    "id": "Art.24", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Controller responsibility and accountability.", "remediation": "Run `make audit-evidence` / maintain gdpr.md.", "key": "audit_evidence_dir_non_empty", "path": ["compliance_gdpr_doc"]},
    ],
  },
  {
    "id": "Art.25", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Data protection by design and by default.", "remediation": "Ship privacy.py and ActionRecord minimisation.", "key": "privacy_py_present", "path": ["action_schema_present"]},
    ],
  },
  {
    "id": "Art.26", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Joint controller agreement.", "remediation": "Attest joint_controller_agreement.", "path": ["joint_controller_agreement"]},
    ],
  },
  {
    "id": "Art.27", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Representative in EU designated.", "remediation": "Attest representative_in_eu.", "path": ["representative_in_eu"]},
    ],
  },
  {
    "id": "Art.28", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Processor agreement in place.", "remediation": "Attest processor_agreement.", "path": ["processor_agreement"]},
    ],
  },
  {
    "id": "Art.29", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Processing under controller/processor authority only.", "remediation": "Attest processing_under_authority_only.", "path": ["processing_under_authority_only"]},
    ],
  },
  {
    "id": "Art.30", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Records of processing activities (RoPA).", "remediation": "Attest records_of_processing.", "path": ["records_of_processing"]},
    ],
  },
  {
    "id": "Art.31", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Cooperation with supervisory authority.", "remediation": "Attest cooperation_supervisory_authority.", "path": ["cooperation_supervisory_authority"]},
    ],
  },
  {
    "id": "Art.32(1)(a)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Pseudonymisation and encryption.", "remediation": "Ship thot/audit/privacy.py with envelope keys outside WORM.", "key": "privacy_py_present"},
    ],
  },
  {
    "id": "Art.32(1)(b)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Ongoing confidentiality, integrity, availability.", "remediation": "Enable WORM + hot store hash chain.", "key": "audit_worm_retention_set"},
    ],
  },
  {
    "id": "Art.32(1)(c)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Ability to restore data after incident.", "remediation": "Expose rollback-index and audit-verify.", "key": "rollback_target_in_makefile", "path": ["audit_verify_target"]},
    ],
  },
  {
    "id": "Art.32(1)(d)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Process for regular testing.", "remediation": "Run audit-verify and security-report.", "key": "audit_verify_target", "path": ["security_report_target"]},
    ],
  },
  {
    "id": "Art.33", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Data breach notification to SA ≤72h.", "remediation": "Attest breach_notification_72h.", "path": ["breach_notification_72h"]},
    ],
  },
  {
    "id": "Art.34", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Communication to data subjects.", "remediation": "Attest communicate_to_subjects.", "path": ["communicate_to_subjects"]},
    ],
  },
  {
    "id": "Art.35", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Data protection impact assessment (DPIA).", "remediation": "Attest dpia.", "path": ["dpia"]},
    ],
  },
  {
    "id": "Art.36", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Prior consultation with supervisory authority.", "remediation": "Attest prior_consultation.", "path": ["prior_consultation"]},
    ],
  },
  {
    "id": "Art.37", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "DPO designated where required.", "remediation": "Attest dpo_designated.", "path": ["dpo_designated"]},
    ],
  },
  {
    "id": "Art.38", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "DPO position and resources.", "remediation": "Attest dpo_position_resources.", "path": ["dpo_position_resources"]},
    ],
  },
  {
    "id": "Art.39", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "DPO tasks.", "remediation": "Attest dpo_tasks.", "path": ["dpo_tasks"]},
    ],
  },
  {
    "id": "Art.44", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Transfers only with adequate protection.", "remediation": "Attest transfers_adequate_protection.", "path": ["transfers_adequate_protection"]},
    ],
  },
  {
    "id": "Art.45", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Adequacy decision basis.", "remediation": "Attest adequacy_decision_basis.", "path": ["adequacy_decision_basis"]},
    ],
  },
  {
    "id": "Art.46", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Appropriate safeguards (SCCs, BCR).", "remediation": "Attest appropriate_safeguards.", "path": ["appropriate_safeguards"]},
    ],
  },
  {
    "id": "Art.49", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Derogations for specific situations.", "remediation": "Attest transfer_derogations.", "path": ["transfer_derogations"]},
    ],
  },
]

violations[v] {
  some i
  a := articles[i]
  some j
  c := a.checks[j]
  not check_passed(c)
  v := common.violation("GDPR", a.id, c.severity, c.message, c.remediation)
}

passed[p] {
  some i
  a := articles[i]
  some j
  c := a.checks[j]
  check_passed(c)
  p := common.pass("GDPR", a.id, c.message)
}

not_applicable = set()

articles_covered = sort([id | id := articles[_].id])

summary = s {
  s := {
    "regulation": "GDPR",
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
