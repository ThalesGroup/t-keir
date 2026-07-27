#!/usr/bin/env python3
"""Title: Fetch EU legal article texts (EUR-Lex / Publications Office Cellar).

Downloads official English XHTML for each regulation, splits articles /
paragraphs / points, and writes YAML keyed by the same IDs used in OPA
catalogues (``Art.5(1)``, ``AnnexI.PartI.1(a)``, …).

Usage (from repo root)::

    python3 compliance/opa/scripts/fetch_legal_texts.py
    python3 compliance/opa/scripts/fetch_legal_texts.py --regulation dora

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import html as html_lib
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML is required.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = Path(__file__).resolve().parent
LEGAL_DIR = ROOT / "compliance" / "opa" / "legal"
POL = ROOT / "compliance" / "opa" / "policies"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from catalogue_parse import parse_rego_articles  # noqa: E402

USER_AGENT = "T-KEIR-compliance-legal-fetch/1.0 (+https://github.com/ThalesGroup/t-keir)"

# Official CELEX identifiers (English expression via Cellar).
REGULATIONS: dict[str, dict[str, str]] = {
    "ai_act": {
        "label": "AI Act",
        "celex": "32024R1689",
        "eurlex": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689",
        "rego": "ai_act/ai_act.rego",
    },
    "cra": {
        "label": "CRA",
        "celex": "32024R2847",
        "eurlex": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R2847",
        "rego": "cra/cra.rego",
    },
    "gdpr": {
        "label": "GDPR",
        "celex": "32016R0679",
        "eurlex": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679",
        "rego": "gdpr/gdpr.rego",
    },
    "nis2": {
        "label": "NIS2",
        "celex": "32022L2555",
        "eurlex": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2555",
        "rego": "nis2/nis2.rego",
    },
    "dora": {
        "label": "DORA",
        "celex": "32022R2554",
        "eurlex": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2554",
        "rego": "dora/dora.rego",
    },
    "pld": {
        "label": "PLD",
        "celex": "32024L2853",
        "eurlex": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024L2853",
        "rego": "pld/pld.rego",
    },
}

# AI Act Title II rows are hardcoded in gen_doc_tables (not in articles[]).
AI_ACT_ART5_IDS = [
    "Art.5(1)(a)",
    "Art.5(1)(b)",
    "Art.5(1)(c)",
    "Art.5(1)(d)",
    "Art.5(1)(e)",
    "Art.5(1)(f)",
    "Art.5(1)(g)",
]


def _http_get(url: str, *, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", fragment)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = text.replace("\xa0", " ").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _rdf_get(url: str) -> str:
    return _http_get(url, accept="application/rdf+xml,*/*").decode(
        "utf-8", errors="replace"
    )


def _first_doc1(rdf: str) -> str | None:
    m = re.search(
        r"http://publications\.europa\.eu/resource/cellar/[0-9a-f.-]+/DOC_1",
        rdf,
    )
    return m.group(0) if m else None


def resolve_xhtml_doc_url(celex: str) -> str:
    """Return the Cellar DOC_1 URL for the English XHTML manifestation."""
    # Fast path (works for DORA / NIS2 style CELEX expressions).
    try:
        rdf = _rdf_get(
            f"http://publications.europa.eu/resource/celex/{celex}.ENG.xhtml"
        )
        doc = _first_doc1(rdf)
        if doc:
            return doc
    except urllib.error.HTTPError as exc:
        if exc.code not in {404, 406}:
            raise

    # Work → ENG expression → xhtml manifestation → DOC_1
    work = _rdf_get(f"http://publications.europa.eu/resource/celex/{celex}")
    expr_urls = sorted(
        set(
            re.findall(
                r"http://publications\.europa\.eu/resource/(?:celex|oj)/[^\"\s>]+ENG",
                work,
            )
        )
    )
    # Prefer OJ L_…ENG expression resources when present.
    expr_urls = sorted(
        expr_urls,
        key=lambda u: (0 if "/oj/" in u else 1, len(u)),
    )
    for expr in expr_urls:
        if expr.endswith(".xhtml") or expr.endswith(".pdfa2a") or expr.endswith(".fmx4"):
            continue
        try:
            expr_rdf = _rdf_get(expr)
        except urllib.error.HTTPError:
            continue
        xhtml_urls = sorted(
            set(
                re.findall(
                    r"http://publications\.europa\.eu/resource/(?:celex|oj)/[^\"\s>]+\.xhtml",
                    expr_rdf,
                )
            )
        )
        for xhtml in xhtml_urls:
            try:
                x_rdf = _rdf_get(xhtml)
            except urllib.error.HTTPError:
                continue
            doc = _first_doc1(x_rdf)
            if doc:
                return doc

    raise RuntimeError(f"no English XHTML DOC_1 for CELEX {celex}")


def fetch_regulation_xhtml(celex: str) -> str:
    doc_url = resolve_xhtml_doc_url(celex)
    data = _http_get(doc_url, accept="application/xhtml+xml,text/html,*/*")
    return data.decode("utf-8", errors="replace")


_ART_SPLIT = re.compile(
    r'<p[^>]*class="[^"]*oj-ti-art[^"]*"[^>]*>\s*Article\s*([0-9]+[a-zA-Z]?)\s*</p>',
    re.I,
)
_ANNEX_SPLIT = re.compile(
    r'<p[^>]*class="[^"]*oj-ti-section[^"]*"[^>]*>\s*ANNEX\s*([IVXLC]+)\s*</p>'
    r'|<p[^>]*class="[^"]*oj-ti-art[^"]*"[^>]*>\s*ANNEX\s*([IVXLC]+)\s*</p>',
    re.I,
)


def _article_title(body_html: str) -> str:
    m = re.search(
        r'<p[^>]*class="[^"]*oj-sti-art[^"]*"[^>]*>(.*?)</p>',
        body_html,
        re.I | re.S,
    )
    return _strip_tags(m.group(1)) if m else ""


def parse_articles_from_xhtml(xhtml: str) -> dict[str, dict[str, str]]:
    """Return ``{"Art.N": {"title": …, "text": …}, …}`` for whole articles."""
    matches = list(_ART_SPLIT.finditer(xhtml))
    out: dict[str, dict[str, str]] = {}
    for i, match in enumerate(matches):
        num = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(xhtml)
        # Stop at annex if it appears before next article.
        annex_m = re.search(r'class="[^"]*oj-ti-section[^"]*"[^>]*>\s*ANNEX', xhtml[start:end], re.I)
        if annex_m:
            end = start + annex_m.start()
        body = xhtml[start:end]
        title = _article_title(body)
        text = _strip_tags(body)
        # Drop leading title echo if present.
        if title and text.startswith(title):
            text = text[len(title) :].lstrip(" \n.—-")
        out[f"Art.{num}"] = {"title": title, "text": text}
    return out


def _split_numbered_paragraphs(article_text: str) -> dict[str, str]:
    """Split ``1. … 2. …`` body into paragraph map ``{"1": text, …}``."""
    # Normalise spaced numbers like "1 ." → "1."
    text = re.sub(r"(?m)^(\d+)\s+\.", r"\1.", article_text)
    parts = re.split(r"(?m)(?=^\d+\.\s)|(?<=\s)(?=\d+\.\s)", text)
    paras: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\.\s*(.*)$", part, re.S)
        if not m:
            continue
        paras[m.group(1)] = m.group(2).strip()
    return paras


def _split_lettered_points(para_text: str) -> dict[str, str]:
    """Split ``(a) … (b) …`` points from a paragraph body."""
    parts = re.split(r"(?=\([a-z]\))", para_text)
    points: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        m = re.match(r"^\(([a-z])\)\s*(.*)$", part, re.S)
        if not m:
            continue
        points[m.group(1)] = m.group(2).strip()
    return points


def parse_annexes_from_xhtml(xhtml: str) -> dict[str, str]:
    """Return ``{"I": text, "II": text, …}`` for ANNEX blocks."""
    matches = list(
        re.finditer(
            r'<p[^>]*class="[^"]*oj-doc-ti[^"]*"[^>]*>\s*ANNEX\s*([IVXLC]+)\s*</p>',
            xhtml,
            re.I,
        )
    )
    out: dict[str, str] = {}
    for i, match in enumerate(matches):
        roman = match.group(1).upper()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(xhtml)
        out[roman] = _strip_tags(xhtml[start:end])
    return out


def _split_annex_parts(annex_text: str) -> dict[str, str]:
    """Split ``Part I … Part II …`` inside an annex."""
    parts = re.split(r"(?i)(?=Part\s+[IVXLC0-9]+)\b", annex_text)
    out: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        m = re.match(r"(?i)^Part\s+([IVXLC0-9]+)\b[^\n]*\n?(.*)$", part, re.S)
        if not m:
            continue
        key = m.group(1).upper()
        # Normalise arabic → roman-ish labels used in Rego (I / II).
        if key == "1":
            key = "I"
        elif key == "2":
            key = "II"
        out[key] = m.group(2).strip()
    return out


def resolve_citation(
    citation: str,
    articles: dict[str, dict[str, str]],
    annexes: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Map an OPA catalogue id to exact legal text when possible."""
    annexes = annexes or {}

    # CRA-style: AnnexI.PartI.1(a) / AnnexI.PartII.3
    am = re.match(
        r"^Annex([IVXLC]+)\.Part([IVXLC0-9]+)\.(\d+)(?:\(([a-z])\))?$",
        citation,
    )
    if am:
        annex_r, part_r, num, point = (
            am.group(1).upper(),
            am.group(2).upper(),
            am.group(3),
            am.group(4),
        )
        if part_r == "1":
            part_r = "I"
        elif part_r == "2":
            part_r = "II"
        annex_text = annexes.get(annex_r, "")
        if not annex_text:
            return {
                "title": f"Annex {annex_r}",
                "text": "",
                "note": f"Annex {annex_r} not found in EUR-Lex XHTML.",
                "status": "missing_annex",
            }
        parts = _split_annex_parts(annex_text)
        part_text = parts.get(part_r, annex_text)
        if point:
            # Prefer lettered cyber-requirement points under Part I.
            points = _split_lettered_points(part_text)
            pt = points.get(point)
            if pt:
                return {
                    "title": f"Annex {annex_r} Part {part_r}",
                    "text": f"({point}) {pt}",
                    "status": "annex_point",
                }
            return {
                "title": f"Annex {annex_r} Part {part_r}",
                "text": part_text,
                "note": f"Point ({point}) not isolated; full Part {part_r} shown.",
                "status": "annex_part_fallback",
            }
        # Numbered items in Part II: "1. …" / "(1) …"
        paras = _split_numbered_paragraphs(part_text)
        if num in paras:
            return {
                "title": f"Annex {annex_r} Part {part_r}",
                "text": f"{num}. {paras[num]}",
                "status": "annex_paragraph",
            }
        # Also try parenthesised numbering "(1)" style.
        mpara = re.search(
            rf"\({re.escape(num)}\)\s*(.*?)(?=\(\d+\)|\Z)",
            part_text,
            re.S,
        )
        if mpara:
            return {
                "title": f"Annex {annex_r} Part {part_r}",
                "text": f"({num}) {mpara.group(1).strip()}",
                "status": "annex_paragraph",
            }
        return {
            "title": f"Annex {annex_r} Part {part_r}",
            "text": part_text,
            "note": f"Item {num} not isolated; full Part {part_r} shown.",
            "status": "annex_part_fallback",
        }

    m = re.match(
        r"^Art\.(\d+[a-zA-Z]?)(?:\((\d+)\))?(?:\(([a-z])\))?$",
        citation,
    )
    if not m:
        return None
    art_n, para_n, point = m.group(1), m.group(2), m.group(3)
    art_key = f"Art.{art_n}"
    art = articles.get(art_key)
    if not art:
        return None
    title = art.get("title", "")
    full = art["text"]
    if not para_n:
        return {"title": title, "text": full, "status": "article"}
    paras = _split_numbered_paragraphs(full)
    para = paras.get(para_n)
    if not para:
        return {
            "title": title,
            "text": full,
            "note": f"Paragraph {para_n} boundaries not detected; full Article {art_n} shown.",
            "status": "article_fallback",
        }
    if not point:
        return {"title": title, "text": f"{para_n}. {para}", "status": "paragraph"}
    points = _split_lettered_points(para)
    pt = points.get(point)
    if not pt:
        return {
            "title": title,
            "text": f"{para_n}. {para}",
            "note": f"Point ({point}) not isolated; full paragraph {para_n} shown.",
            "status": "paragraph_fallback",
        }
    return {
        "title": title,
        "text": f"({point}) {pt}",
        "status": "point",
    }


def catalogue_ids(reg_key: str) -> list[str]:
    meta = REGULATIONS[reg_key]
    path = POL / meta["rego"]
    ids = [a["id"] for a in parse_rego_articles(path)]
    if reg_key == "ai_act":
        ids = AI_ACT_ART5_IDS + ids
    # Preserve order, unique.
    seen: set[str] = set()
    out: list[str] = []
    for aid in ids:
        if aid not in seen:
            seen.add(aid)
            out.append(aid)
    return out


def build_legal_yaml(reg_key: str, *, xhtml: str | None = None) -> dict[str, Any]:
    meta = REGULATIONS[reg_key]
    if xhtml is None:
        print(f"[{reg_key}] fetching CELEX {meta['celex']} …", flush=True)
        xhtml = fetch_regulation_xhtml(meta["celex"])
    articles = parse_articles_from_xhtml(xhtml)
    annexes = parse_annexes_from_xhtml(xhtml)
    print(
        f"[{reg_key}] parsed {len(articles)} articles, {len(annexes)} annexes from XHTML",
        flush=True,
    )

    entries: dict[str, Any] = {}
    missing: list[str] = []
    for aid in catalogue_ids(reg_key):
        resolved = resolve_citation(aid, articles, annexes)
        if resolved is None or not (resolved.get("text") or "").strip():
            missing.append(aid)
            entries[aid] = {
                "title": (resolved or {}).get("title", ""),
                "text": "",
                "note": (resolved or {}).get(
                    "note",
                    "No matching text found in EUR-Lex XHTML for this citation.",
                ),
                "status": "missing",
            }
            continue
        entries[aid] = {
            "title": resolved.get("title", ""),
            "text": resolved.get("text", ""),
            "status": resolved.get("status", "ok"),
        }
        if resolved.get("note"):
            entries[aid]["note"] = resolved["note"]

    return {
        "regulation": meta["label"],
        "key": reg_key,
        "celex": meta["celex"],
        "source_url": meta["eurlex"],
        "language": "en",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclaimer": (
            "Official EU legal text sourced via Publications Office Cellar "
            "(English). Not legal advice. Attribution: © European Union, "
            "https://eur-lex.europa.eu/"
        ),
        "articles": entries,
        "stats": {
            "catalogue_ids": len(entries),
            "with_text": sum(1 for v in entries.values() if v.get("text")),
            "missing": missing,
        },
    }


def write_yaml(reg_key: str, payload: dict[str, Any]) -> Path:
    LEGAL_DIR.mkdir(parents=True, exist_ok=True)
    path = LEGAL_DIR / f"{reg_key}.yaml"
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regulation",
        choices=sorted(REGULATIONS),
        action="append",
        help="Limit to one or more regulations (default: all)",
    )
    parser.add_argument(
        "--from-xhtml",
        type=Path,
        help="Use a local XHTML file instead of fetching (with --regulation)",
    )
    args = parser.parse_args(argv)
    regs = args.regulation or list(REGULATIONS)
    if args.from_xhtml and len(regs) != 1:
        print("--from-xhtml requires exactly one --regulation", file=sys.stderr)
        return 1

    for reg in regs:
        xhtml = None
        if args.from_xhtml:
            xhtml = args.from_xhtml.read_text(encoding="utf-8")
        try:
            payload = build_legal_yaml(reg, xhtml=xhtml)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            print(f"[{reg}] FAILED: {exc}", file=sys.stderr)
            return 1
        path = write_yaml(reg, payload)
        stats = payload["stats"]
        print(
            f"[{reg}] wrote {path} "
            f"({stats['with_text']}/{stats['catalogue_ids']} with text; "
            f"missing={len(stats['missing'])})",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
