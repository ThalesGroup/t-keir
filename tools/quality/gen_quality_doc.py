#!/usr/bin/env python3
"""Generate ``tkeir/docs/quality/index.md`` from ``reports/quality/`` artefacts.

Called by ``make quality-docs``. Paths are relative to the repository root.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports" / "quality"
DOCS_OUT = REPO_ROOT / "tkeir" / "docs" / "quality" / "index.md"


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


def _status(value: float | None, threshold: float) -> str:
    if value is None:
        return "n/a"
    return "PASS" if value <= threshold else "FAIL"


def main() -> None:
    DOCS_OUT.parent.mkdir(parents=True, exist_ok=True)

    radon = _load_radon_summary(REPORTS_DIR / "radon_cc_summary.txt")
    d_from_json = _count_grade_d_plus_from_json(REPORTS_DIR / "radon_cc.json")
    if d_from_json is not None:
        radon["grade_d_plus"] = d_from_json
    licenses = _load_licenses(REPORTS_DIR / "licenses.json")
    lowest_mi = _load_mi_lowest(REPORTS_DIR / "radon_mi.txt")

    avg = radon["average"]
    grade = radon["grade"]
    d_plus = radon["grade_d_plus"]
    avg_s = f"{avg:.2f}" if avg is not None else "n/a"
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
        footer = [line for line in lines if "Average complexity:" in line or "blocks" in line]
        if footer:
            cc_body = "\n".join(footer[-5:])
        else:
            cc_body = "\n".join(lines[-8:])
        cc_body += (
            "\n\nFull per-function JSON: reports/quality/radon_cc.json"
        )

    page = f"""# Code quality

Generated automatically by `make quality-docs` — last updated **{ts}**.

Baseline before the B-grade refactoring pass (``thot/`` only): average was
already within band after hotspots were reduced; gate target remains
**average ≤ 7.0 (grade B)** with **zero functions at grade D or worse**.

---

## Cyclomatic complexity (Radon / McCabe)

**Target:** average ≤ 7.0 (grade B), zero functions at grade D or worse (CC > 20).

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Average CC | {avg_s} | ≤ 7.0 | {_status(avg, 7.0)} |
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

**CC average > 7.0:** run `make complexity-report`; open
`reports/quality/radon_cc.json`; refactor functions at grade C or worse.

**New copyleft licence:** check against
[`compliance/licenses-allowlist.txt`](../../../compliance/licenses-allowlist.txt);
copyleft licences (GPL, AGPL, EUPL) require legal review before merge.
Runtime licence policy remains enforced by `make liccheck`
([`tkeir/liccheck.ini`](../../liccheck.ini)).

**CI gate:** `make ci` runs `make complexity` (average ≤ 7.0 on `thot/`, no
grade-D functions) plus `make complexity-report` and `make pip-licenses`.

Regenerate:

```bash
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


if __name__ == "__main__":
    main()
