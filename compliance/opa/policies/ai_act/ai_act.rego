# EU AI Act (Regulation (EU) 2024/1689) — engineering evidence policy.
# Not legal advice. Full sub-article coverage per compliance audit specification.
package eu.ai_act

import data.eu.common as common

category = c {
  c := input.ai_act.classification.determined_category
}

is_ai_system {
  input.ai_act.classification.is_ai_system == true
}

processes_biometric_data {
  input.ai_act.classification.processes_biometric_data == true
}

emotion_recognition_used {
  input.ai_act.classification.emotion_recognition == true
}

biometric_categorisation_used {
  input.ai_act.classification.biometric_categorisation == true
}

role = r {
  r := input.product.role
}

uses_notified_body {
  input.ai_act.attestation.conformity_assessment.uses_notified_body == true
}

prohibited_practices = p {
  p := input.ai_act.classification.prohibited_practices
}

any_prohibited_true {
  some k
  prohibited_practices[k] == true
}

attestation_get(path) = v {
  count(path) == 1
  v := object.get(input.ai_act.attestation, path[0], null)
}

attestation_get(path) = v {
  count(path) == 2
  outer := object.get(input.ai_act.attestation, path[0], {})
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
  article.gate == "high_risk"
  category == "HIGH_RISK"
}

gate_ok(article) {
  article.gate == "high_risk_biometric"
  category == "HIGH_RISK"
  processes_biometric_data
}

gate_ok(article) {
  article.gate == "high_risk_importer"
  category == "HIGH_RISK"
  role == "importer"
}

gate_ok(article) {
  article.gate == "high_risk_distributor"
  category == "HIGH_RISK"
  role == "distributor"
}

gate_ok(article) {
  article.gate == "high_risk_notified_body"
  category == "HIGH_RISK"
  uses_notified_body
}

gate_ok(article) {
  article.gate == "limited_or_high"
  category == "LIMITED_RISK"
}

gate_ok(article) {
  article.gate == "limited_or_high"
  category == "HIGH_RISK"
}

gate_ok(article) {
  article.gate == "limited_or_high_emotion"
  category == "LIMITED_RISK"
  emotion_recognition_used
}

gate_ok(article) {
  article.gate == "limited_or_high_emotion"
  category == "HIGH_RISK"
  emotion_recognition_used
}

gate_ok(article) {
  article.gate == "limited_or_high_biometric_cat"
  category == "LIMITED_RISK"
  biometric_categorisation_used
}

gate_ok(article) {
  article.gate == "limited_or_high_biometric_cat"
  category == "HIGH_RISK"
  biometric_categorisation_used
}

gate_ok(article) {
  article.gate == "gpai"
  category == "GPAI_STANDARD"
}

gate_ok(article) {
  article.gate == "gpai"
  category == "GPAI_SYSTEMIC"
}

gate_ok(article) {
  article.gate == "gpai_systemic"
  category == "GPAI_SYSTEMIC"
}

gate_ok(article) {
  article.gate == "ai_system_active"
  is_ai_system
  category != "UNACCEPTABLE"
}

gate_reason(gate) = r {
  gate == "high_risk"
  r := sprintf("Applies only to HIGH_RISK AI systems (current category: %s)", [category])
}

gate_reason(gate) = r {
  gate == "high_risk_biometric"
  r := sprintf("Applies only to HIGH_RISK systems processing biometric data (category: %s)", [category])
}

gate_reason(gate) = r {
  gate == "high_risk_importer"
  r := sprintf("Applies only to importers of HIGH_RISK systems (role: %s, category: %s)", [role, category])
}

gate_reason(gate) = r {
  gate == "high_risk_distributor"
  r := sprintf("Applies only to distributors of HIGH_RISK systems (role: %s, category: %s)", [role, category])
}

gate_reason(gate) = r {
  gate == "high_risk_notified_body"
  r := sprintf("Applies only when a notified body is used for HIGH_RISK conformity assessment (category: %s)", [category])
}

gate_reason(gate) = r {
  gate == "limited_or_high"
  r := sprintf("Applies only to LIMITED_RISK or HIGH_RISK systems (current category: %s)", [category])
}

gate_reason(gate) = r {
  gate == "limited_or_high_emotion"
  r := sprintf("Applies only when emotion recognition is used under LIMITED_RISK/HIGH_RISK (category: %s)", [category])
}

gate_reason(gate) = r {
  gate == "limited_or_high_biometric_cat"
  r := sprintf("Applies only when biometric categorisation is used under LIMITED_RISK/HIGH_RISK (category: %s)", [category])
}

gate_reason(gate) = r {
  gate == "gpai"
  r := sprintf("Applies only to GPAI models (current category: %s)", [category])
}

gate_reason(gate) = r {
  gate == "gpai_systemic"
  r := sprintf("Applies only to GPAI models with systemic risk (current category: %s)", [category])
}

gate_reason(gate) = r {
  gate == "ai_system_active"
  r := sprintf("Applies only to active non-prohibited AI systems (category: %s)", [category])
}

articles = [
  {
    "id": "Art.6", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "High-risk classification is documented (Annex III / Art.6).", "remediation": "Document annex_iii_applies and Annex IV classification rationale (`make annex-iv`).", "key": "annex_iv_dir_non_empty", "path": ["risk_management_system"]},
    ],
  },
  {
    "id": "Art.7", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Classification rules for high-risk AI are applied and recorded.", "remediation": "Track Annex III amendments and record classification outcomes in the Annex IV file.", "key": "annex_iv_dir_non_empty"},
    ],
  },
  {
    "id": "Art.9(1)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Risk management system established.", "remediation": "Satisfy the control: attest risk_management_system", "path": ["risk_management_system"]},
    ],
  },
  {
    "id": "Art.9(2)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Risk management covers identification, estimation and evaluation.", "remediation": "Satisfy the control: attest risk_mgmt_identification_estimation_evaluation", "path": ["risk_mgmt_identification_estimation_evaluation"]},
    ],
  },
  {
    "id": "Art.9(3)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Residual risks tested after market placement.", "remediation": "Run `make audit-evidence` and attest residual_risk_tested_post_market.", "key": "audit_evidence_dir_non_empty", "path": ["residual_risk_tested_post_market"]},
    ],
  },
  {
    "id": "Art.9(4)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Risk management measures adopted.", "remediation": "Satisfy the control: attest risk_management_measures_adopted", "path": ["risk_management_measures_adopted"]},
    ],
  },
  {
    "id": "Art.9(5)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Testing against defined metrics before market placement.", "remediation": "Run `make beir-eval`.", "key": "beir_eval_report_present", "path": ["conformity_assessment_standards"]},
    ],
  },
  {
    "id": "Art.9(6)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Testing on real-world conditions where applicable.", "remediation": "Run `make beir-eval` / publish evaluation_report.md.", "key": "beir_eval_report_present"},
    ],
  },
  {
    "id": "Art.9(7)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "Serious incident testing feedback loop in place.", "remediation": "Run `make audit-evidence` and attest feedback_loop_controls.", "key": "audit_evidence_dir_non_empty", "path": ["feedback_loop_controls"]},
    ],
  },
  {
    "id": "Art.9(8)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Conformity assessment standards applied.", "remediation": "Satisfy the control: attest conformity_assessment_standards", "path": ["conformity_assessment_standards"]},
    ],
  },
  {
    "id": "Art.10(1)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Training/validation/test data governance via AIBOM.", "remediation": "Publish AIBOM under reports/bom/ (`make bom`).", "key": "aibom_present"},
    ],
  },
  {
    "id": "Art.10(2)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Data governance practices documented in AIBOM entries.", "remediation": "Publish AIBOM entries under reports/bom/.", "key": "aibom_present"},
    ],
  },
  {
    "id": "Art.10(3)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Data relevant, representative, free of errors (inventory present).", "remediation": "Publish SBOM/AIBOM under reports/bom/.", "key": "sbom_cyclonedx_present"},
    ],
  },
  {
    "id": "Art.10(4)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Examination for biases performed.", "remediation": "Satisfy the control: attest data_bias_examination", "path": ["data_bias_examination"]},
    ],
  },
  {
    "id": "Art.10(5)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Special-category data processing justified.", "remediation": "Document Art.10(5) justification; maintain compliance/gdpr.md.", "key": "compliance_gdpr_doc", "path": ["special_category_data_justified"]},
    ],
  },
  {
    "id": "Art.11(1)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Technical documentation drawn up (Annex IV).", "remediation": "Run `make annex-iv`.", "key": "annex_iv_dir_non_empty"},
    ],
  },
  {
    "id": "Art.11(2)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Technical documentation kept up to date.", "remediation": "Keep reports/compliance/annex-iv/ non-empty and current.", "key": "annex_iv_dir_non_empty"},
    ],
  },
  {
    "id": "Art.12(1)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Automatic logging enabled throughout lifecycle.", "remediation": "Ship action.v1.json ActionRecord schema.", "key": "action_schema_present"},
    ],
  },
  {
    "id": "Art.12(2)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "Logs automatically generated.", "remediation": "Enable dual audit sink / hot store and retain evidence.", "key": "audit_evidence_dir_non_empty", "path": ["action_schema_present"]},
    ],
  },
  {
    "id": "Art.12(3)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "Logs kept for period appropriate to intended purpose.", "remediation": "Configure AUDIT_WORM_RETENTION_DAYS.", "key": "audit_worm_retention_set", "path": ["action_schema_present"]},
    ],
  },
  {
    "id": "Art.12(4)", "gate": "high_risk_biometric",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Biometric identification system logging specifics present.", "remediation": "Extend biometric ID logging per Art.12(4).", "key": "audit_evidence_dir_non_empty"},
    ],
  },
  {
    "id": "Art.13(1)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "System designed to be sufficiently transparent.", "remediation": "Satisfy the control: attest system_sufficiently_transparent", "path": ["system_sufficiently_transparent"]},
    ],
  },
  {
    "id": "Art.13(2)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Instructions for use provided.", "remediation": "Satisfy the control: attest instructions_for_use_provided", "path": ["instructions_for_use_provided"]},
    ],
  },
  {
    "id": "Art.13(3)(a)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Instructions include provider identity and contact.", "remediation": "Satisfy the control: attest instructions_provider_identity", "path": ["instructions_provider_identity"]},
    ],
  },
  {
    "id": "Art.13(3)(b)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Instructions include capabilities and limitations.", "remediation": "Satisfy the control: attest instructions_capabilities_limitations", "path": ["instructions_capabilities_limitations"]},
    ],
  },
  {
    "id": "Art.13(3)(c)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Instructions include expected accuracy levels.", "remediation": "Publish evaluation_report.md via `make beir-eval`.", "key": "beir_eval_report_present"},
    ],
  },
  {
    "id": "Art.13(3)(d)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Instructions include human oversight measures.", "remediation": "Publish runbooks/kill-switch.md.", "key": "kill_switch_runbook_present"},
    ],
  },
  {
    "id": "Art.13(3)(e)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "LOW", "message": "Instructions include computational resource requirements.", "remediation": "Satisfy the control: attest instructions_compute_resources", "path": ["instructions_compute_resources"]},
    ],
  },
  {
    "id": "Art.14(1)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Human oversight measures built in (governor flags).", "remediation": "Ship tkeir/thot/governor/flags.py.", "key": "governor_flags_present"},
    ],
  },
  {
    "id": "Art.14(2)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "System designed for human oversight implementation.", "remediation": "Ship HMI /admin and governor enforce mode.", "key": "hmi_admin_page_present", "path": ["governor_flags_present"]},
    ],
  },
  {
    "id": "Art.14(3)(a)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Oversight persons can understand capabilities and limitations.", "remediation": "Satisfy the control: attest oversight_understand_capabilities", "path": ["oversight_understand_capabilities"]},
    ],
  },
  {
    "id": "Art.14(3)(b)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "Oversight persons can detect anomalies.", "remediation": "Expose audit-report / incident tooling.", "key": "audit_evidence_dir_non_empty", "path": ["audit_verify_target"]},
    ],
  },
  {
    "id": "Art.14(3)(c)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Oversight persons can interrupt the system.", "remediation": "Expose `make governor-kill`.", "key": "governor_kill_target", "path": ["kill_switch_runbook_present"]},
    ],
  },
  {
    "id": "Art.14(3)(d)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Oversight persons can override output.", "remediation": "Ship governor/approvals.py.", "key": "governor_approvals_present"},
    ],
  },
  {
    "id": "Art.14(3)(e)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Oversight persons can decide not to use output.", "remediation": "Ship HMI /admin approval queue.", "key": "hmi_admin_page_present"},
    ],
  },
  {
    "id": "Art.14(4)", "gate": "high_risk_biometric",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Specific oversight measures for biometric systems.", "remediation": "Require human verification UI for biometric outputs.", "key": "hmi_admin_page_present"},
    ],
  },
  {
    "id": "Art.14(5)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Automated control measures for fully automated deployment.", "remediation": "Ship governor flags for automated control.", "key": "governor_flags_present"},
    ],
  },
  {
    "id": "Art.15(1)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Appropriate accuracy, robustness and cybersecurity.", "remediation": "Run `make beir-eval` and `make trivy`.", "key": "beir_eval_report_present", "path": ["trivy_report_present"]},
    ],
  },
  {
    "id": "Art.15(2)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Performance metrics declared.", "remediation": "Publish tkeir/docs/evaluation_report.md.", "key": "beir_eval_report_present"},
    ],
  },
  {
    "id": "Art.15(3)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Resilience against adversarial inputs.", "remediation": "Satisfy the control: attest adversarial_resilience", "path": ["adversarial_resilience"]},
    ],
  },
  {
    "id": "Art.15(4)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Technical measures against feedback-loop risks.", "remediation": "Satisfy the control: attest feedback_loop_controls", "path": ["feedback_loop_controls"]},
    ],
  },
  {
    "id": "Art.15(5)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Cybersecurity measures in place.", "remediation": "Run `make security-report` / `make bom`.", "key": "security_report_target", "path": ["trivy_report_present"]},
    ],
  },
  {
    "id": "Art.16(a)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Quality management system implemented.", "remediation": "Satisfy the control: attest quality_management_system", "path": ["quality_management_system"]},
    ],
  },
  {
    "id": "Art.16(b)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Technical documentation drawn up.", "remediation": "Run `make annex-iv`.", "key": "annex_iv_dir_non_empty"},
    ],
  },
  {
    "id": "Art.16(c)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Logging capability implemented.", "remediation": "Ship ActionRecord schema / hot store.", "key": "action_schema_present"},
    ],
  },
  {
    "id": "Art.16(d)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Conformity assessment performed.", "remediation": "Satisfy the control: attest conformity_assessment.performed", "path": ["conformity_assessment", "performed"]},
    ],
  },
  {
    "id": "Art.16(e)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "EU declaration of conformity drawn up.", "remediation": "Satisfy the control: attest eu_declaration_of_conformity", "path": ["eu_declaration_of_conformity"]},
    ],
  },
  {
    "id": "Art.16(f)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "CE marking affixed.", "remediation": "Satisfy the control: attest ce_marking_affixed", "path": ["ce_marking_affixed"]},
    ],
  },
  {
    "id": "Art.16(g)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Registration in EU database.", "remediation": "Satisfy the control: attest eu_database_registration", "path": ["eu_database_registration"]},
    ],
  },
  {
    "id": "Art.16(h)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Corrective actions taken without undue delay.", "remediation": "Expose rollback-index and governor-kill.", "key": "rollback_target_in_makefile", "path": ["governor_kill_target"]},
    ],
  },
  {
    "id": "Art.16(i)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Competent authorities informed of serious incidents.", "remediation": "Use tkeir-audit incident --kind early-warning / serious.", "key": "incident_runbook_present", "path": ["serious_incident_report_within_15_days"]},
    ],
  },
  {
    "id": "Art.16(j)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Competent authorities informed upon request.", "remediation": "Satisfy the control: attest competent_authorities_on_request", "path": ["competent_authorities_on_request"]},
    ],
  },
  {
    "id": "Art.17(1)(a)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "QMS covers strategy for regulatory compliance.", "remediation": "Satisfy the control: attest qms_regulatory_strategy", "path": ["qms_regulatory_strategy"]},
    ],
  },
  {
    "id": "Art.17(1)(b)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "QMS covers techniques for design development.", "remediation": "Satisfy the control: attest qms_design_techniques", "path": ["qms_design_techniques"]},
    ],
  },
  {
    "id": "Art.17(1)(c)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "QMS covers system testing and validation.", "remediation": "Run beir-eval and audit-verify.", "key": "beir_eval_report_present", "path": ["audit_verify_target"]},
    ],
  },
  {
    "id": "Art.17(1)(d)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "QMS covers technical documentation.", "remediation": "Run `make annex-iv`.", "key": "annex_iv_dir_non_empty"},
    ],
  },
  {
    "id": "Art.17(1)(e)", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "QMS covers data management.", "remediation": "Publish AIBOM under reports/bom/.", "key": "aibom_present"},
    ],
  },
  {
    "id": "Art.17(1)(f)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "QMS covers risk management.", "remediation": "Satisfy the control: attest risk_management_system", "path": ["risk_management_system"]},
    ],
  },
  {
    "id": "Art.17(1)(g)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "QMS covers post-market monitoring.", "remediation": "Run `make audit-evidence` / `make audit-report`.", "key": "audit_evidence_dir_non_empty", "path": ["feedback_loop_controls"]},
    ],
  },
  {
    "id": "Art.17(1)(h)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "QMS covers serious incident reporting.", "remediation": "Use tkeir-audit incident tooling.", "key": "incident_runbook_present", "path": ["serious_incident_report_within_15_days"]},
    ],
  },
  {
    "id": "Art.17(2)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "QMS implemented and documented.", "remediation": "Satisfy the control: attest qms_documented", "path": ["qms_documented"]},
    ],
  },
  {
    "id": "Art.18", "gate": "high_risk",
    "checks": [
      {"source": "either_gte", "severity": "MEDIUM", "message": "Technical documentation retained 10 years (or attested).", "remediation": "Set AUDIT_WORM_RETENTION_DAYS >= 3650 or attest retention.", "key": "audit_worm_retention_days", "path": ["qms_documented"], "min": 3650},
    ],
  },
  {
    "id": "Art.19", "gate": "high_risk",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Automatically generated logs kept by provider.", "remediation": "Configure AUDIT_WORM_RETENTION_DAYS.", "key": "audit_worm_retention_set"},
    ],
  },
  {
    "id": "Art.20(1)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Serious incidents reported to authorities.", "remediation": "Use tkeir-audit incident --kind serious.", "key": "incident_runbook_present", "path": ["serious_incident_report_within_15_days"]},
    ],
  },
  {
    "id": "Art.20(2)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "CRITICAL", "message": "Serious incident reported within 15 days of becoming aware.", "remediation": "Satisfy the control: attest serious_incident_report_within_15_days", "path": ["serious_incident_report_within_15_days"]},
    ],
  },
  {
    "id": "Art.21", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Cooperation with competent authorities.", "remediation": "Satisfy the control: attest competent_authorities_on_request", "path": ["competent_authorities_on_request"]},
    ],
  },
  {
    "id": "Art.22", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Authorised representative designated (non-EU providers).", "remediation": "Satisfy the control: attest authorised_representative_non_eu", "path": ["authorised_representative_non_eu"]},
    ],
  },
  {
    "id": "Art.23(1)", "gate": "high_risk_importer",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Importers verify CE marking and Annex IV / DoC.", "remediation": "Verify CE marking and Annex IV before import.", "path": ["eu_declaration_of_conformity"]},
    ],
  },
  {
    "id": "Art.24(1)", "gate": "high_risk_distributor",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Distributors verify CE marking.", "remediation": "Verify CE marking before making available.", "path": ["ce_marking_affixed"]},
    ],
  },
  {
    "id": "Art.25(1)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Deployer obligations for inputs under their control.", "remediation": "Satisfy the control: attest deployer_uses_per_instructions", "path": ["deployer_uses_per_instructions"]},
    ],
  },
  {
    "id": "Art.25(3)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Deployers use system according to instructions.", "remediation": "Satisfy the control: attest deployer_uses_per_instructions", "path": ["deployer_uses_per_instructions"]},
    ],
  },
  {
    "id": "Art.25(5)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Deployers implement human oversight.", "remediation": "Ship governor approvals and HMI /admin.", "key": "governor_approvals_present", "path": ["hmi_admin_page_present"]},
    ],
  },
  {
    "id": "Art.25(6)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Deployers inform affected persons.", "remediation": "Satisfy the control: attest deployer_informs_affected_persons", "path": ["deployer_informs_affected_persons"]},
    ],
  },
  {
    "id": "Art.25(9)", "gate": "high_risk",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "Deployers perform DPIA where required.", "remediation": "Maintain compliance/gdpr.md and attest deployer_dpia.", "key": "compliance_gdpr_doc", "path": ["deployer_dpia"]},
    ],
  },
  {
    "id": "Art.26(1)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "EU declaration of conformity drawn up.", "remediation": "Satisfy the control: attest eu_declaration_of_conformity", "path": ["eu_declaration_of_conformity"]},
    ],
  },
  {
    "id": "Art.26(2)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "EU DoC contains information from Annex V.", "remediation": "Satisfy the control: attest eu_declaration_of_conformity", "path": ["eu_declaration_of_conformity"]},
    ],
  },
  {
    "id": "Art.27(1)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "CE marking affixed before market placement.", "remediation": "Satisfy the control: attest ce_marking_affixed", "path": ["ce_marking_affixed"]},
    ],
  },
  {
    "id": "Art.27(2)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "CE marking requirements (visible, legible, indelible).", "remediation": "Satisfy the control: attest ce_marking_affixed", "path": ["ce_marking_affixed"]},
    ],
  },
  {
    "id": "Art.28", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "High-risk AI systems registered in EU database.", "remediation": "Satisfy the control: attest eu_database_registration", "path": ["eu_database_registration"]},
    ],
  },
  {
    "id": "Art.29(1)", "gate": "high_risk",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Fundamental rights impact assessment performed.", "remediation": "Satisfy the control: attest fundamental_rights_impact_assessment", "path": ["fundamental_rights_impact_assessment"]},
    ],
  },
  {
    "id": "Art.33", "gate": "high_risk_notified_body",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Notified body designated and notified.", "remediation": "Satisfy the control: attest conformity_assessment.notified_body_designated", "path": ["conformity_assessment", "notified_body_designated"]},
    ],
  },
  {
    "id": "Art.34", "gate": "high_risk_notified_body",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Notified body organisational requirements met.", "remediation": "Satisfy the control: attest conformity_assessment.notified_body_org_requirements", "path": ["conformity_assessment", "notified_body_org_requirements"]},
    ],
  },
  {
    "id": "Art.43(1)", "gate": "high_risk_notified_body",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Conformity assessment procedure followed.", "remediation": "Satisfy the control: attest conformity_assessment.procedure_followed", "path": ["conformity_assessment", "procedure_followed"]},
    ],
  },
  {
    "id": "Art.43(2)", "gate": "high_risk_notified_body",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Harmonised standards applied or CS used.", "remediation": "Satisfy the control: attest conformity_assessment.harmonised_standards_or_cs", "path": ["conformity_assessment", "harmonised_standards_or_cs"]},
    ],
  },
  {
    "id": "Art.43(4)", "gate": "high_risk_notified_body",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Third-party assessment where required.", "remediation": "Satisfy the control: attest conformity_assessment.third_party_assessment", "path": ["conformity_assessment", "third_party_assessment"]},
    ],
  },
  {
    "id": "Art.50(1)", "gate": "limited_or_high",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Persons informed they are interacting with AI.", "remediation": "Satisfy the control: attest transparency.persons_informed_interacting_with_ai", "path": ["transparency", "persons_informed_interacting_with_ai"]},
    ],
  },
  {
    "id": "Art.50(2)", "gate": "limited_or_high_emotion",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Emotion recognition disclosure to natural persons.", "remediation": "Disclose emotion-recognition use to affected persons.", "path": ["transparency", "persons_informed_interacting_with_ai"]},
    ],
  },
  {
    "id": "Art.50(3)", "gate": "limited_or_high_biometric_cat",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Biometric categorisation disclosure to natural persons.", "remediation": "Disclose biometric categorisation use to affected persons.", "path": ["transparency", "persons_informed_interacting_with_ai"]},
    ],
  },
  {
    "id": "Art.50(4)", "gate": "limited_or_high",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "AI-generated content labelling.", "remediation": "Satisfy the control: attest transparency.ai_generated_content_labelling", "path": ["transparency", "ai_generated_content_labelling"]},
    ],
  },
  {
    "id": "Art.53(1)(a)", "gate": "gpai",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Technical documentation provided to downstream providers (AIBOM).", "remediation": "Publish AIBOM under reports/bom/.", "key": "aibom_present"},
    ],
  },
  {
    "id": "Art.53(1)(b)", "gate": "gpai",
    "checks": [
      {"source": "evidence", "severity": "HIGH", "message": "Information and documentation for downstream providers.", "remediation": "Run `make annex-iv`.", "key": "annex_iv_dir_non_empty"},
    ],
  },
  {
    "id": "Art.53(1)(c)", "gate": "gpai",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Copyright compliance policy.", "remediation": "Satisfy the control: attest gpai.copyright_compliance_policy", "path": ["gpai", "copyright_compliance_policy"]},
    ],
  },
  {
    "id": "Art.53(1)(d)", "gate": "gpai",
    "checks": [
      {"source": "evidence", "severity": "MEDIUM", "message": "Summary of training data published.", "remediation": "Publish training-data summary via AIBOM.", "key": "aibom_present"},
    ],
  },
  {
    "id": "Art.53(2)", "gate": "gpai",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Copyright compliance obligations.", "remediation": "Satisfy the control: attest gpai.copyright_obligations", "path": ["gpai", "copyright_obligations"]},
    ],
  },
  {
    "id": "Art.54", "gate": "gpai",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Authorised representative for non-EU GPAI providers.", "remediation": "Satisfy the control: attest gpai.authorised_representative_non_eu", "path": ["gpai", "authorised_representative_non_eu"]},
    ],
  },
  {
    "id": "Art.55(1)(a)", "gate": "gpai_systemic",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Model evaluation per standardised protocols.", "remediation": "Satisfy the control: attest gpai.model_evaluation_protocols", "path": ["gpai", "model_evaluation_protocols"]},
    ],
  },
  {
    "id": "Art.55(1)(b)", "gate": "gpai_systemic",
    "checks": [
      {"source": "attestation", "severity": "HIGH", "message": "Adversarial testing (red-teaming).", "remediation": "Satisfy the control: attest gpai.adversarial_red_teaming", "path": ["gpai", "adversarial_red_teaming"]},
    ],
  },
  {
    "id": "Art.55(1)(c)", "gate": "gpai_systemic",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Serious incidents reported to AI Office within 2 weeks.", "remediation": "Use tkeir-audit incident --kind ai-office.", "key": "incident_runbook_present", "path": ["serious_incident_report_within_15_days"]},
    ],
  },
  {
    "id": "Art.55(1)(d)", "gate": "gpai_systemic",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Cybersecurity protection for systemic-risk GPAI.", "remediation": "Run `make security-report` / `make trivy`.", "key": "security_report_target", "path": ["trivy_report_present"]},
    ],
  },
  {
    "id": "Art.55(2)", "gate": "gpai_systemic",
    "checks": [
      {"source": "attestation", "severity": "MEDIUM", "message": "Codes of practice followed.", "remediation": "Satisfy the control: attest gpai.codes_of_practice", "path": ["gpai", "codes_of_practice"]},
    ],
  },
  {
    "id": "Art.72", "gate": "ai_system_active",
    "checks": [
      {"source": "either", "severity": "HIGH", "message": "Serious incident notification to market surveillance.", "remediation": "Use tkeir-audit incident --kind serious.", "key": "incident_runbook_present", "path": ["serious_incident_report_within_15_days"]},
    ],
  },
  {
    "id": "Art.73", "gate": "ai_system_active",
    "checks": [
      {"source": "either", "severity": "MEDIUM", "message": "Post-market monitoring plan in place.", "remediation": "Run `make audit-evidence` / `make audit-report`.", "key": "audit_evidence_dir_non_empty", "path": ["feedback_loop_controls"]},
    ],
  },
]

prohibited_article = {
  "subliminal_manipulation": "Art.5(1)(a)",
  "exploits_vulnerabilities": "Art.5(1)(b)",
  "social_scoring_public_authority": "Art.5(1)(c)",
  "real_time_biometric_public_space": "Art.5(1)(d)",
  "emotion_recognition_workplace_education": "Art.5(1)(e)",
  "biometric_categorisation_sensitive_attributes": "Art.5(1)(f)",
  "predictive_policing_individual": "Art.5(1)(g)",
}

prohibited_practice_remediation = {
  "subliminal_manipulation": "Cease subliminal/manipulative techniques that materially distort behaviour (Art.5(1)(a)).",
  "exploits_vulnerabilities": "Cease exploiting vulnerabilities of specific groups (Art.5(1)(b)).",
  "social_scoring_public_authority": "Cease public-authority social scoring (Art.5(1)(c)).",
  "real_time_biometric_public_space": "Cease real-time remote biometric identification in publicly accessible spaces outside narrow exceptions (Art.5(1)(d)).",
  "emotion_recognition_workplace_education": "Cease emotion recognition in workplace/education outside permitted exceptions (Art.5(1)(e)).",
  "biometric_categorisation_sensitive_attributes": "Cease biometric categorisation inferring sensitive attributes (Art.5(1)(f)).",
  "predictive_policing_individual": "Cease individual predictive-policing risk assessments based solely on profiling (Art.5(1)(g)).",
}

art5_ids = ["Art.5(1)(a)", "Art.5(1)(b)", "Art.5(1)(c)", "Art.5(1)(d)", "Art.5(1)(e)", "Art.5(1)(f)", "Art.5(1)(g)"]

violations[v] {
  some k
  prohibited_practices[k] == true
  v := common.violation(
    "AI_ACT", prohibited_article[k], "CRITICAL",
    sprintf("Prohibited AI practice in use: %s.", [k]),
    prohibited_practice_remediation[k],
  )
}

violations[v] {
  category == "UNACCEPTABLE"
  not any_prohibited_true
  v := common.violation(
    "AI_ACT", "Art.5(1)(a)", "CRITICAL",
    "System is classified UNACCEPTABLE but no specific prohibited practice flag is set; investigate classification.",
    "Re-run classification and identify which Art.5(1) prohibited practice applies; cease the practice.",
  )
}

passed[p] {
  category != "UNACCEPTABLE"
  some k
  prohibited_practices[k] == false
  p := common.pass("AI_ACT", prohibited_article[k], sprintf("No prohibited practice in use: %s.", [k]))
}


violations[v] {
  some i
  a := articles[i]
  gate_ok(a)
  some j
  c := a.checks[j]
  not check_passed(c)
  v := common.violation("AI_ACT", a.id, c.severity, c.message, c.remediation)
}

passed[p] {
  some i
  a := articles[i]
  gate_ok(a)
  some j
  c := a.checks[j]
  check_passed(c)
  p := common.pass("AI_ACT", a.id, c.message)
}

not_applicable[n] {
  some i
  a := articles[i]
  not gate_ok(a)
  n := common.not_mandatory("AI_ACT", a.id, gate_reason(a.gate))
}

all_article_ids[id] {
  some i
  id := art5_ids[i]
}

all_article_ids[id] {
  some i
  id := articles[i].id
}

articles_covered = sort([id | all_article_ids[id]])

summary = s {
  s := {
    "regulation": "AI_ACT",
    "category": category,
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
