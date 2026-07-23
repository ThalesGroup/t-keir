#!/usr/bin/env python3
"""Title: Generate ``docs/quality/index.md`` from ``reports/quality/`` artefacts.

Called by ``make quality-docs``. Paths are relative to the repository root.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "quality"
COVERAGE_REPORTS_DIR = REPO_ROOT / "coverage-reports"
DOCS_OUT = REPO_ROOT / "docs" / "quality" / "index.md"
DEFAULT_COVERAGE_THRESHOLD = 90.0


def _load_radon_summary(path: pathlib.Path) -> dict:
    """Parse the radon cc --total-average summary text file."""
    result: dict = {"average": None, "grade": "?", "grade_d_plus": 0}
    if not path.exists():
        return result
    text = path.read_text(encoding="utf-8")
    match = re.search(r"Average complexity:\s+([A-F])\s+\(([\d.]+)\)", text)
    if match:
        result["grade"] = match.group(1)
        result["average"] = float(match.group(2))
    result["grade_d_plus"] = len(re.findall(r"-\s+[DEF]\s+\(\d+", text))
    return result


def _count_grade_d_plus_from_json(path: pathlib.Path) -> int | None:
    """Count functions/methods with CC > 20 from radon JSON if available."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    count = 0
    for items in data.values():
        for item in items:
            if item.get("type") in ("function", "method", "class") and int(
                item.get("complexity", 0)
            ) > 20:
                count += 1
    return count


def _load_mi_lowest(path: pathlib.Path) -> str:
    """Return the lowest-MI module line from a radon mi text report."""
    if not path.exists():
        return "n/a"
    lowest = None
    lowest_score = 101.0
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.search(r"^(\S+)\s+-\s+[A-F]\s+\(([\d.]+)\)", line)
        if not match:
            continue
        score = float(match.group(2))
        if score < lowest_score:
            lowest_score = score
            lowest = f"{match.group(1)} ({score:.2f})"
    return lowest or "n/a"


def _load_licenses(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _load_coverage() -> dict:
    """Load scoped coverage metrics written by ``CoverageFast.sh``."""
    result: dict = {
        "percent": None,
        "threshold": DEFAULT_COVERAGE_THRESHOLD,
        "statements": None,
        "covered": None,
        "missing": None,
        "total_line": None,
        "report_excerpt": None,
        "xml_percent": None,
    }

    summary = REPORTS_DIR / "coverage_summary.txt"
    if summary.exists():
        for line in summary.read_text(encoding="utf-8").splitlines():
            if line.startswith("threshold_percent="):
                try:
                    result["threshold"] = float(line.split("=", 1)[1])
                except ValueError:
                    pass
            elif line.startswith("percent_covered="):
                raw = line.split("=", 1)[1].strip()
                if raw not in ("", "None"):
                    result["percent"] = float(raw)
            elif line.startswith("num_statements="):
                raw = line.split("=", 1)[1].strip()
                if raw not in ("", "None"):
                    result["statements"] = int(float(raw))
            elif line.startswith("covered_lines="):
                raw = line.split("=", 1)[1].strip()
                if raw not in ("", "None"):
                    result["covered"] = int(float(raw))
            elif line.startswith("missing_lines="):
                raw = line.split("=", 1)[1].strip()
                if raw not in ("", "None"):
                    result["missing"] = int(float(raw))
            elif line.startswith("TOTAL"):
                result["total_line"] = line.strip()

    json_path = REPORTS_DIR / "coverage.json"
    if result["percent"] is None and json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            totals = data.get("totals", {})
            if "percent_covered" in totals:
                result["percent"] = float(totals["percent_covered"])
            result["statements"] = totals.get("num_statements", result["statements"])
            result["covered"] = totals.get("covered_lines", result["covered"])
            result["missing"] = totals.get("missing_lines", result["missing"])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    report_path = REPORTS_DIR / "coverage_report.txt"
    if report_path.exists():
        lines = report_path.read_text(encoding="utf-8").splitlines()
        # Keep header + TOTAL (avoid dumping every file into MkDocs).
        header = lines[:2] if lines else []
        total = [line for line in lines if line.startswith("TOTAL")]
        result["report_excerpt"] = "\n".join(header + total) if total else "\n".join(lines[-5:])
        if result["total_line"] is None and total:
            result["total_line"] = total[-1].strip()

    for xml_candidate in (
        REPORTS_DIR / "coverage.xml",
        COVERAGE_REPORTS_DIR / "coverage.xml",
    ):
        if not xml_candidate.exists():
            continue
        try:
            root = ET.parse(xml_candidate).getroot()
            rate = root.attrib.get("line-rate")
            if rate is not None:
                result["xml_percent"] = float(rate) * 100.0
            break
        except (ET.ParseError, ValueError, OSError):
            continue

    return result


def _status_lower_better(value: float | None, threshold: float) -> str:
    if value is None:
        return "n/a"
    return "PASS" if value <= threshold else "FAIL"


def _status_higher_better(value: float | None, threshold: float) -> str:
    if value is None:
        return "n/a"
    return "PASS" if value >= threshold else "FAIL"


def main() -> None:
    DOCS_OUT.parent.mkdir(parents=True, exist_ok=True)

    radon = _load_radon_summary(REPORTS_DIR / "radon_cc_summary.txt")
    d_from_json = _count_grade_d_plus_from_json(REPORTS_DIR / "radon_cc.json")
    if d_from_json is not None:
        radon["grade_d_plus"] = d_from_json
    licenses = _load_licenses(REPORTS_DIR / "licenses.json")
    lowest_mi = _load_mi_lowest(REPORTS_DIR / "radon_mi.txt")
    coverage = _load_coverage()

    avg = radon["average"]
    grade = radon["grade"]
    d_plus = radon["grade_d_plus"]
    avg_s = f"{avg:.2f}" if avg is not None else "n/a"
    cov_pct = coverage["percent"]
    cov_thr = float(coverage["threshold"])
    cov_s = f"{cov_pct:.2f}%" if cov_pct is not None else "n/a"
    xml_s = (
        f"{coverage['xml_percent']:.2f}%"
        if coverage["xml_percent"] is not None
        else "n/a"
    )
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lic_rows = "\n".join(
        f"| {pkg.get('Name', '')} | {pkg.get('Version', '')} | "
        f"{pkg.get('License', '')} | {pkg.get('URL') or '—'} |"
        for pkg in sorted(licenses, key=lambda item: item.get("Name", "").lower())
    )

    cc_body = "(run `make complexity-report` to generate)"
    summary_path = REPORTS_DIR / "radon_cc_summary.txt"
    if summary_path.exists():
        lines = summary_path.read_text(encoding="utf-8").splitlines()
        footer = [
            line
            for line in lines
            if "Average complexity:" in line or re.search(r"^\d+ blocks", line)
        ]
        if footer:
            cc_body = "\n".join(footer[-5:])
        else:
            cc_body = "\n".join(lines[-8:])
        cc_body += "\n\nFull per-function JSON: reports/quality/radon_cc.json"

    cov_excerpt = coverage["report_excerpt"] or (
        coverage["total_line"]
        or "(run `make coverage` to generate reports/quality/coverage_*.*)"
    )
    cov_detail_rows = []
    if coverage["statements"] is not None:
        cov_detail_rows.append(
            f"| Statements (scoped) | {coverage['statements']} | — | — |"
        )
    if coverage["covered"] is not None:
        cov_detail_rows.append(
            f"| Covered lines | {coverage['covered']} | — | — |"
        )
    if coverage["missing"] is not None:
        cov_detail_rows.append(
            f"| Missing lines | {coverage['missing']} | — | — |"
        )
    cov_detail = "\n".join(cov_detail_rows)

    page = f"""# Code quality

Generated automatically by `make quality-docs` — last updated **{ts}**.

Baseline before the B-grade refactoring pass (``thot/`` only): average was
already within band after hotspots were reduced; gate target remains
**average ≤ 7.0 (grade B)** with **zero functions at grade D or worse**.

---

## Test coverage

Scoped line coverage from `make coverage` / `CoverageFast.sh` (same
`[tool.coverage.report]` include list and `COVERAGE_FAIL_UNDER` gate used in CI).

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Scoped line coverage | {cov_s} | ≥ {cov_thr:.0f}% | {_status_higher_better(cov_pct, cov_thr)} |
| Full ``thot/`` XML line-rate | {xml_s} | informational | — |
{cov_detail}

### Coverage report (TOTAL)

```
{cov_excerpt}
```

Artefacts: `reports/quality/coverage_summary.txt`, `coverage.json`,
`coverage_report.txt`, and `coverage-reports/coverage.xml`.

---

## Cyclomatic complexity (Radon / McCabe)

**Target:** average ≤ 7.0 (grade B), zero functions at grade D or worse (CC > 20).

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Average CC | {avg_s} | ≤ 7.0 | {_status_lower_better(avg, 7.0)} |
| Grade | {grade} | B or better | {'PASS' if grade in ('A', 'B') else 'FAIL'} |
| Functions at grade D+ | {d_plus} | 0 | {'PASS' if d_plus == 0 else 'FAIL'} |
| Lowest MI module | {lowest_mi} | ≥ 20 preferred | — |

### Risk reference table

| CC | Radon | SEI risk | T-KEIR policy |
|----|-------|----------|---------------|
| 1–5 | A | Minimal | Target for new code |
| 6–10 | B | Low | Acceptable |
| 11–20 | C | Moderate | Requires review on PR |
| 21–30 | D | High | Must refactor before merge |
| 31–40 | E | Very high | Blocked |
| 41+ | F | Untestable | Blocked |

### Full report (summary)

```
{cc_body}
```

---

## Dependency licences

All runtime and optional Python dependencies from the locked dependency set
(``tkeir`` / ``thot``). Generated by `make pip-licenses`.

| Package | Version | Licence | URL |
|---------|---------|---------|-----|
{lic_rows if lic_rows else "_(run `make pip-licenses` to generate)_"}

---

## Acting on this page

**Coverage < {cov_thr:.0f}%:** run `make coverage`; open
`reports/quality/coverage_report.txt` / `coverage.json`; add tests for
modules listed under the scoped include set in `tkeir/pyproject.toml`.

**CC average > 7.0:** run `make complexity-report`; open
`reports/quality/radon_cc.json`; refactor functions at grade C or worse.

**New copyleft licence:** check against
[`compliance/licenses-allowlist.txt`](../../compliance/licenses-allowlist.txt);
copyleft licences (GPL, AGPL, EUPL) require legal review before merge.
Runtime licence policy remains enforced by `make liccheck`
([`tkeir/liccheck.ini`](../../tkeir/liccheck.ini)).

**CI gate:** `make ci` runs `make coverage` (fail-under {cov_thr:.0f}%),
`make complexity` (average ≤ 7.0 on `thot/`, no grade-D functions), plus
`make complexity-report` and `make pip-licenses`.

Regenerate:

```bash
make coverage      # refreshes reports/quality/coverage_*.*
make quality-docs
make docs-build
```
"""
    DOCS_OUT.write_text(page, encoding="utf-8")
    print(f"Written: {DOCS_OUT}")

    if avg is not None and avg > 7.0:
        print(f"WARNING: CC average {avg_s} exceeds target 7.0", file=sys.stderr)
    if d_plus > 0:
        print(f"WARNING: {d_plus} functions at grade D or worse", file=sys.stderr)
    if cov_pct is not None and cov_pct < cov_thr:
        print(
            f"WARNING: coverage {cov_s} below target {cov_thr:.0f}%",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
