# EU Cyber Resilience Act (Regulation (EU) 2024/2847) — engineering evidence policy.
# Not legal advice. Full sub-article / Annex I clause coverage.
package eu.cra

import data.eu.common as common

role = r {
  r := input.product.role
}

attestation_get(path) = v {
  count(path) == 1
  v := object.get(input.cra.attestation, path[0], null)
}

attestation_get(path) = v {
  count(path) == 2
  outer := object.get(input.cra.attestation, path[0], {})
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

gate_ok(article) {
  article.gate == "importer"
  role == "importer"
}

gate_ok(article) {
  article.gate == "distributor"
  role == "distributor"
}

gate_reason(gate) = r {
  gate == "importer"
  r := sprintf("Applies only to importers (current role: %s)", [role])
}

gate_reason(gate) = r {
  gate == "distributor"
  r := sprintf("Applies only to distributors (current role: %s)", [role])
}

articles = [
  {
    "id": "AnnexI.PartI.1(a)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "No known exploitable vulnerabilities at market placement.", "remediation": "Run `make trivy` and `make pip-audit`.", "key": "trivy_report_present", "path": ["pip_audit_run_in_ci"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(b)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Secure by default configuration.", "remediation": "Ship values-secure.yaml / values-dev.yaml.", "key": "values_secure_present", "path": ["values_dev_present"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(c)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Protection against unauthorised access (Keycloak realm/JWT).", "remediation": "Deploy Keycloak realm-tkeir.json.", "key": "keycloak_realm_present"},
    ],
  },
  {
    "id": "AnnexI.PartI.1(d)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Protection of confidentiality of data in transit and at rest.", "remediation": "Attest confidentiality_in_transit_at_rest.", "path": ["confidentiality_in_transit_at_rest"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(e)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Data integrity protection (ActionRecord hash chain / WORM).", "remediation": "Enable ActionRecords and WORM retention.", "key": "action_schema_present", "path": ["audit_worm_retention_set"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(f)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Availability protection against DoS.", "remediation": "Attest availability_dos_protection.", "path": ["availability_dos_protection"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(g)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Minimise attack surface (NetworkPolicy).", "remediation": "Ship networkpolicy.yaml template.", "key": "networkpolicy_template"},
    ],
  },
  {
    "id": "AnnexI.PartI.1(h)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Ability to log and monitor security events.", "remediation": "Run `make audit-report` / archive.", "key": "audit_evidence_dir_non_empty", "path": ["audit_verify_target"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(i)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Possibility to reset to factory default securely.", "remediation": "Attest factory_reset_secure.", "path": ["factory_reset_secure"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(j)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Security update mechanism.", "remediation": "Use images-sign and versions.lock.yaml.", "key": "images_signed", "path": ["versions_lock_present"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(k)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Signed update mechanism (Cosign).", "remediation": "Run `make images-sign`.", "key": "images_signed"},
    ],
  },
  {
    "id": "AnnexI.PartI.1(l)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Consistent security across product lifetime (CHANGELOG).", "remediation": "Publish CHANGELOG.md.", "key": "changelog_present"},
    ],
  },
  {
    "id": "AnnexI.PartI.1(m)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "No third-party data collection beyond functionality.", "remediation": "Attest no_unnecessary_third_party_collection.", "path": ["no_unnecessary_third_party_collection"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(n)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Return to secure state after disruption.", "remediation": "Expose rollback-index and governor-kill.", "key": "rollback_target_in_makefile", "path": ["governor_kill_target"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(o)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Encryption of data at rest and in transit.", "remediation": "Attest encryption_at_rest_and_transit.", "path": ["encryption_at_rest_and_transit"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(p)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Minimum necessary data processing (request_hash).", "remediation": "Keep ActionRecord request_hash-only by default.", "key": "action_schema_present"},
    ],
  },
  {
    "id": "AnnexI.PartI.1(q)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Protect special category data.", "remediation": "Ship privacy.py and compliance/gdpr.md.", "key": "privacy_py_present", "path": ["compliance_gdpr_doc"]},
    ],
  },
  {
    "id": "AnnexI.PartI.1(r)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Access control mechanisms.", "remediation": "Deploy Keycloak scopes → intents and governor policy.", "key": "keycloak_realm_present", "path": ["governor_flags_present"]},
    ],
  },
  {
    "id": "AnnexI.PartII.1", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "SBOM maintained.", "remediation": "Publish CycloneDX SBOM (`make bom`).", "key": "sbom_cyclonedx_present"},
    ],
  },
  {
    "id": "AnnexI.PartII.2", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Vulnerabilities identified and documented.", "remediation": "Run pip-audit, trivy, owasp-dependency-check.", "key": "trivy_report_present", "path": ["pip_audit_run_in_ci"]},
    ],
  },
  {
    "id": "AnnexI.PartII.3", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Vulnerabilities addressed without delay (CI gate).", "remediation": "Keep pip-audit in CI (`make ci`).", "key": "pip_audit_run_in_ci", "path": ["ci_security_workflow"]},
    ],
  },
  {
    "id": "AnnexI.PartII.4", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Coordinated vulnerability disclosure (CVD).", "remediation": "Publish SECURITY.md.", "key": "security_md_present"},
    ],
  },
  {
    "id": "AnnexI.PartII.5", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Security updates distributed free of charge.", "remediation": "Attest security_updates_free_of_charge.", "path": ["security_updates_free_of_charge"]},
    ],
  },
  {
    "id": "AnnexI.PartII.6", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Actively exploited vulnerabilities reported to ENISA.", "remediation": "Attest enisa_actively_exploited_reported.", "path": ["enisa_actively_exploited_reported"]},
    ],
  },
  {
    "id": "AnnexI.PartII.7", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Actively exploited vulnerabilities reported within 24h.", "remediation": "Attest enisa_report_within_24h.", "path": ["enisa_report_within_24h"]},
    ],
  },
  {
    "id": "Art.6(1)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Product category determined (Annex III or IV).", "remediation": "Set product.cra_class and maintain versions.lock.yaml.", "key": "versions_lock_present"},
    ],
  },
  {
    "id": "Art.6(2)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Class I products: self-assessment or standard.", "remediation": "Attest Class I conformity approach.", "path": ["eu_declaration_of_conformity"]},
    ],
  },
  {
    "id": "Art.6(3)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Class II products: notified body.", "remediation": "Attest Class II notified-body path when applicable.", "path": ["eu_declaration_of_conformity"]},
    ],
  },
  {
    "id": "Art.13(1)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Product integrates security by design.", "remediation": "Ship values-secure.yaml.", "key": "values_secure_present"},
    ],
  },
  {
    "id": "Art.13(2)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Due diligence on third-party components.", "remediation": "Maintain versions.lock.yaml and SBOM.", "key": "versions_lock_present", "path": ["sbom_cyclonedx_present"]},
    ],
  },
  {
    "id": "Art.13(3)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "No known exploitable vuln at market placement.", "remediation": "Run trivy and pip-audit.", "key": "trivy_report_present", "path": ["pip_audit_run_in_ci"]},
    ],
  },
  {
    "id": "Art.13(4)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Security updates without undue delay.", "remediation": "Enable CI security.yml workflow.", "key": "ci_security_workflow"},
    ],
  },
  {
    "id": "Art.13(5)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Actively exploited vulnerabilities addressed within 24h.", "remediation": "Attest 24h response path.", "path": ["enisa_report_within_24h"]},
    ],
  },
  {
    "id": "Art.13(6)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Product-level security tests.", "remediation": "Run trivy / owasp-dependency-check.", "key": "trivy_report_present", "path": ["owasp_dc_present"]},
    ],
  },
  {
    "id": "Art.13(7)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Technical documentation prepared (Annex VII).", "remediation": "Run `make annex-iv`.", "key": "annex_iv_dir_non_empty"},
    ],
  },
  {
    "id": "Art.13(8)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "EU declaration of conformity prepared.", "remediation": "Attest eu_declaration_of_conformity.", "path": ["eu_declaration_of_conformity"]},
    ],
  },
  {
    "id": "Art.13(9)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "CE marking affixed.", "remediation": "Attest ce_marking_affixed.", "path": ["ce_marking_affixed"]},
    ],
  },
  {
    "id": "Art.13(10)", "gate": "all",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "Support period defined and communicated.", "remediation": "Publish CHANGELOG and attest support_period_defined.", "key": "changelog_present", "path": ["support_period_defined"]},
    ],
  },
  {
    "id": "Art.13(11)", "gate": "all",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Contact point for security issues published.", "remediation": "Publish SECURITY.md.", "key": "security_md_present"},
    ],
  },
  {
    "id": "Art.13(12)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Information to users provided.", "remediation": "Attest information_to_users.", "path": ["information_to_users"]},
    ],
  },
  {
    "id": "Art.14(1)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Actively exploited vulnerabilities notified to ENISA.", "remediation": "Attest enisa_actively_exploited_reported.", "path": ["enisa_actively_exploited_reported"]},
    ],
  },
  {
    "id": "Art.14(2)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Early warning within 24h.", "remediation": "Attest early_warning_24h.", "path": ["early_warning_24h"]},
    ],
  },
  {
    "id": "Art.14(3)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Notification within 72h.", "remediation": "Attest notification_72h.", "path": ["notification_72h"]},
    ],
  },
  {
    "id": "Art.14(4)", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Final report within 14 days.", "remediation": "Attest final_report_14_days.", "path": ["final_report_14_days"]},
    ],
  },
  {
    "id": "Art.20", "gate": "all",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Authorised representative designated (non-EU).", "remediation": "Attest authorised_representative_non_eu.", "path": ["authorised_representative_non_eu"]},
    ],
  },
  {
    "id": "Art.21", "gate": "importer",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Importer obligations fulfilled.", "remediation": "Verify DoC/CE marking before import.", "path": ["eu_declaration_of_conformity"]},
    ],
  },
  {
    "id": "Art.22", "gate": "distributor",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Distributor obligations fulfilled.", "remediation": "Verify CE marking before distribution.", "path": ["ce_marking_affixed"]},
    ],
  },
]

violations[v] {
  some i
  a := articles[i]
  gate_ok(a)
  some j
  c := a.checks[j]
  not check_passed(c)
  v := common.violation("CRA", a.id, c.severity, c.message, c.remediation)
}

passed[p] {
  some i
  a := articles[i]
  gate_ok(a)
  some j
  c := a.checks[j]
  check_passed(c)
  p := common.pass("CRA", a.id, c.message)
}

not_applicable[n] {
  some i
  a := articles[i]
  not gate_ok(a)
  n := common.not_mandatory("CRA", a.id, gate_reason(a.gate))
}

articles_covered = sort([id | id := articles[_].id])

summary = s {
  s := {
    "regulation": "CRA",
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
