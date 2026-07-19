# EU compliance shared helpers
package eu.common

violation(regulation, article, severity, message, remediation) = v {
  v := {
    "status": "VIOLATION",
    "regulation": regulation,
    "article": article,
    "severity": severity,
    "message": message,
    "remediation": remediation,
  }
}

pass(regulation, article, message) = p {
  p := {
    "status": "PASS",
    "regulation": regulation,
    "article": article,
    "message": message,
  }
}

not_mandatory(regulation, article, reason) = n {
  n := {
    "status": "NOT_MANDATORY",
    "regulation": regulation,
    "article": article,
    "reason": reason,
  }
}

# true only when explicitly true (null/false/missing → unmet)
truthy(x) {
  x == true
}

score(passed_n, viol_n) = s {
  total := passed_n + viol_n
  total > 0
  s := round((passed_n / total) * 100)
}

score(passed_n, viol_n) = 100 {
  passed_n + viol_n == 0
}
