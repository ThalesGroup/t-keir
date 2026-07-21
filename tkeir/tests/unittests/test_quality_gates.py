"""Quality gate tests: cyclomatic complexity and licence inventory.

Thresholds mirror the Makefile ``complexity`` / ``pip-licenses`` targets.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve()
for _parent in [REPO_ROOT, *REPO_ROOT.parents]:
    if (_parent / "Makefile").exists() and (_parent / "tkeir").is_dir():
        REPO_ROOT = _parent
        break

REPORTS_DIR = REPO_ROOT / "reports" / "quality"
SRC_ROOT = REPO_ROOT / "tkeir"
DOCS_QUALITY = SRC_ROOT / "docs" / "quality" / "index.md"

CC_AVERAGE_THRESHOLD = 7.0
COPYLEFT_LICENCES = {"GPL", "AGPL", "LGPL", "EUPL", "MPL", "OSL", "CDDL"}


def _run_radon_average() -> float | None:
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "radon",
                "cc",
                "thot",
                "-a",
                "--total-average",
            ],
            cwd=SRC_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        for line in result.stdout.splitlines():
            if "Average complexity:" in line:
                match = re.search(r"\(([\d.]+)\)", line)
                if match:
                    return float(match.group(1))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


def test_cc_average_within_target() -> None:
    """Radon average CC on ``thot/`` must be ≤ 7.0 (grade B)."""
    avg = _run_radon_average()
    if avg is None:
        pytest.skip("radon not available or source root not found")
    assert avg <= CC_AVERAGE_THRESHOLD, (
        f"CC average {avg:.2f} exceeds target {CC_AVERAGE_THRESHOLD} (grade B). "
        "Run `make complexity-report` and refactor grade-C/D functions."
    )


def test_no_functions_at_grade_d_or_worse() -> None:
    """No individual function in ``thot/`` should reach grade D (CC > 20)."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "radon",
                "cc",
                "thot",
                "-n",
                "D",
                "-s",
            ],
            cwd=SRC_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        violations = [
            line for line in result.stdout.splitlines() if line.strip()
        ]
    except (OSError, subprocess.SubprocessError):
        pytest.skip("radon not available")

    assert (
        not violations
    ), f"Found {len(violations)} line(s) at grade D or worse:\n" + "\n".join(
        violations[:20]
    )


def test_radon_report_exists_when_ci_ran() -> None:
    """If CI produced reports, radon_cc.json must be present and parseable."""
    report = REPORTS_DIR / "radon_cc.json"
    if not report.exists():
        pytest.skip(
            "radon_cc.json not found — run `make complexity-report` first"
        )
    data = json.loads(report.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "radon_cc.json must be a JSON object"
    assert len(data) > 0, "radon_cc.json must not be empty"


def test_license_report_exists_when_ci_ran() -> None:
    """If CI produced reports, licenses.json must be present."""
    lic = REPORTS_DIR / "licenses.json"
    if not lic.exists():
        pytest.skip("licenses.json not found — run `make pip-licenses` first")
    data = json.loads(lic.read_text(encoding="utf-8"))
    assert (
        isinstance(data, list) and len(data) > 0
    ), "licenses.json must be a non-empty list"


def test_no_unexpected_copyleft_licences() -> None:
    """No copyleft licence should appear without an allowlist entry."""
    lic_path = REPORTS_DIR / "licenses.json"
    if not lic_path.exists():
        pytest.skip("licenses.json not found — run `make pip-licenses` first")

    allowlist_path = REPO_ROOT / "compliance" / "licenses-allowlist.txt"
    allowlisted: set[str] = set()
    if allowlist_path.exists():
        allowlisted = {
            line.strip()
            for line in allowlist_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }

    data = json.loads(lic_path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for pkg in data:
        lic = pkg.get("License", "") or ""
        if any(keyword in lic.upper() for keyword in COPYLEFT_LICENCES):
            key = f"{pkg['Name']}=={pkg['Version']} ({lic})"
            if key not in allowlisted and pkg["Name"] not in allowlisted:
                violations.append(key)

    assert not violations, (
        "Copyleft licences found without allowlist entry:\n"
        + "\n".join(violations)
        + f"\nAdd them to {allowlist_path.relative_to(REPO_ROOT)} after legal review."
    )


def test_quality_dashboard_page_exists() -> None:
    """``tkeir/docs/quality/index.md`` must exist and cover CC + licences."""
    assert (
        DOCS_QUALITY.exists()
    ), "tkeir/docs/quality/index.md missing — run `make quality-docs`"
    content = DOCS_QUALITY.read_text(encoding="utf-8")
    assert (
        "Cyclomatic" in content or "radon" in content.lower()
    ), "Quality page must mention cyclomatic complexity"
    assert (
        "licen" in content.lower()
    ), "Quality page must mention dependency licences"


def test_docs_build_after_quality_page() -> None:
    """MkDocs build must succeed with the quality page present."""
    mkdocs = SRC_ROOT / "mkdocs.yml"
    if not mkdocs.exists():
        pytest.skip("mkdocs.yml not found")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "-f",
            str(mkdocs),
        ],
        cwd=str(SRC_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0 and "No module named mkdocs" in (
        result.stderr + result.stdout
    ):
        result = subprocess.run(
            [
                "uv",
                "run",
                "--python",
                "3.11",
                "--with",
                "mkdocs",
                "--with",
                "mkdocs-material",
                "--with",
                "mkdocs-render-swagger-plugin",
                "mkdocs",
                "build",
            ],
            cwd=str(SRC_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    errors = [
        line
        for line in (result.stderr or "").splitlines()
        if "ERROR" in line.upper()
    ]
    assert result.returncode == 0, "Docs build failed:\n" + "\n".join(
        errors[:15] or [(result.stderr or "")[-1500:]]
    )
