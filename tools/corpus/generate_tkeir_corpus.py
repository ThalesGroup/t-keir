#!/usr/bin/env python3
"""Create a small, reproducible, offline-friendly T-KEIR demonstration corpus."""
from __future__ import annotations

import argparse
import csv
import datetime
import html
import io
import json
import logging
import os
import random
import shutil
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc  # type: ignore[attr-defined]

LOG = logging.getLogger("tkeir.corpus")
NOW = lambda: datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
OSINT_TOPIC_MAP = {
    "SITREP": "situational_awareness", "SALUTE": "situational_awareness",
    "AIS": "situational_awareness", "ADSB": "situational_awareness",
    "INTSUM": "intelligence", "ENTITY": "intelligence",
    "OPORD": "operations", "AAR": "operations", "LOGSIT": "operations",
    "NATOPUB": "publications",
}
ENTERPRISE_TOPIC_MAP = {
    "meeting_minutes": "projects",
    "project_report": "projects",
    "jira_ticket": "projects",
    "confluence_page": "projects",
    "technical_spec": "engineering",
    "api_doc": "engineering",
    "kb_article": "engineering",
    "procedure": "quality",
    "audit_report": "quality",
    "hr_policy": "hr",
    "email_thread": "hr",
    "invoice_summary": "finance",
    "crm_record": "finance",
    "transcript": "projects",
}
FIRST_NAMES = [
    "Alice", "Bob", "Caroline", "David", "Emma", "François", "Gabriel", "Hélène",
    "Ibrahim", "Julie", "Kevin", "Laura", "Marc", "Nadia", "Olivier", "Pierre",
    "Quentin", "Rachel", "Sophie", "Thomas", "Ursula", "Victor", "Wendy", "Xavier",
]
LAST_NAMES = [
    "Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand",
    "Leroy", "Moreau", "Simon", "Laurent", "Lefebvre", "Michel", "Garcia", "David",
    "Bertrand", "Roux", "Vincent", "Fournier", "Morel", "Girard", "André", "Lefèvre",
]
DEPARTMENTS = [
    "Engineering", "Product", "Sales", "HR", "Finance", "Legal",
    "Marketing", "DevOps", "Security", "Customer Success",
]
PROJECTS = [
    "Project ATLAS", "Project HERMES", "Project ORION", "Project ZENITH",
    "Platform v3.0", "API Gateway Refactor", "Cloud Migration",
    "SOC2 Audit 2024", "GDPR Compliance Sprint",
]
OSINT_TYPES = list(OSINT_TOPIC_MAP)
ENTERPRISE_TYPES = [
    "meeting_minutes", "technical_spec", "procedure", "hr_policy",
    "project_report", "email_thread", "invoice_summary", "kb_article",
]
ENTERPRISE_SOURCE_TOPIC = {
    "confluence": "projects", "gdoc": "projects", "jira": "projects",
    "email": "hr", "slack": "hr", "crm": "finance", "transcript": "projects",
}
OSINT_FORMATS = [("txt", 28), ("md", 20), ("html", 14), ("json", 12), ("pdf", 10), ("docx", 9), ("csv", 7)]
ENTERPRISE_FORMATS = [("pdf", 25), ("docx", 24), ("html", 20), ("md", 12), ("txt", 8), ("json", 7), ("csv", 4)]
FORMAT_DIRS = {"txt": "raw", "md": "markdown", "html": "html", "json": "json", "pdf": "pdf", "docx": "docx", "csv": "csv"}

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
NS = {
    "rdf": RDF, "rdfs": RDFS, "owl": OWL,
    "c2sim": "http://www.sisostds.org/ontologies/C2SIM#",
    "lox": "http://www.sisostds.org/ontologies/lox#",
    "smx": "http://www.sisostds.org/ontologies/smx#",
    "cwix": "http://www.sisostds.org/ontologies/C2SIM/cwix2023#",
    "c4isr": "http://www.nato.int/ontologies/c4isr#",
}
for _prefix, _uri in NS.items():
    ET.register_namespace(_prefix, _uri)


def choose_weighted(rng: random.Random, values: list[tuple[str, int]]) -> str:
    return rng.choices([v for v, _ in values], weights=[w for _, w in values], k=1)[0]


def person(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def nato_text(rtype: str, rng: random.Random, lang: str, index: int) -> tuple[str, str]:
    place = rng.choice(["Baltic Sea", "North Atlantic", "Sector Bravo", "Eastern corridor", "Training Area 7"])
    unit = rng.choice(["Task Group 47", "Joint Force Command", "Maritime Component", "NATO Response Cell"])
    timestamp = f"2026-07-{rng.randint(1, 28):02d}T{rng.randint(0,23):02d}:{rng.randint(0,59):02d}Z"
    title = f"{rtype} {index:05d} — {place}"
    en = {
        "SITREP": f"SITUATION REPORT\nDTG: {timestamp}\nUnit: {unit}\nArea: {place}\nObjective: Objective ALPHA\n\nSITREP Objective ALPHA — operational picture remains stable. ISR collection confirms routine maritime traffic. Commander assesses no immediate escalation indicators.",
        "SALUTE": f"SALUTE REPORT\nSize: {rng.randint(2,12)} personnel\nActivity: convoy staging\nLocation: {place}\nUnit/Uniform: unidentified support element\nTime: {timestamp}\nEquipment: tactical radios and light vehicles.",
        "AIS": f"AIS MARITIME TRACK\nTrack: NATO-{rng.randint(1000,9999)}\nPosition: {rng.randint(45,65)}N {rng.randint(5,30)}E\nCourse: {rng.randint(1,359)} degrees\nAssessment: commercial vessel; correlation pending.",
        "ADSB": f"ADS-B AIR TRACK\nCallsign: NAF{rng.randint(100,999)}\nAltitude: {rng.randint(12000,36000)} ft\nArea: {place}\nTime: {timestamp}\nC2ISR correlation: friendly flight plan matched.",
        "INTSUM": f"INTELLIGENCE SUMMARY\nReporting period: {timestamp}\nAssessment: activity near {place} is consistent with scheduled logistics. Confidence: moderate.\nCollection priorities: force posture, maritime approaches, communications indicators.",
        "ENTITY": f"ENTITY PROFILE\nDesignation: {unit}\nCategory: military organization\nArea of interest: {place}\nKnown capability: command and control coordination\nSource reliability: B2.",
        "OPORD": f"OPERATION ORDER\n1. Situation: maintain awareness in {place}.\n2. Mission: {unit} monitors assigned area.\n3. Execution: synchronize ISR and maritime reporting.\n4. Sustainment: report logistics constraints.\n5. Command and Signal: use approved NATO C2 channels.",
        "AAR": f"AFTER ACTION REVIEW\nExercise location: {place}\nObservation: common operational picture updates were timely.\nLesson: verify data provenance before dissemination.\nAction: improve liaison reporting cadence.",
        "LOGSIT": f"LOGISTICS SITUATION REPORT\nArea: {place}\nFuel status: {rng.randint(60,95)} percent\nMedical supplies: adequate\nTransport availability: mission capable\nRequest: confirm resupply route security.",
        "NATOPUB": f"NATO PUBLICATION EXTRACT\nSubject: interoperability and C4ISR information exchange\nThis reference outlines common terminology, message handling, and operational reporting responsibilities for multinational forces.",
    }[rtype]
    if lang == "fr":
        return title, en + "\n\nNote linguistique: diffusion de travail en français; situation opérationnelle stable."
    return title, en


def gen_meeting_minutes(rng: random.Random) -> tuple[str, str]:
    project, owner = rng.choice(PROJECTS), person(rng)
    return (
        f"AcmeSystems {project} Steering Meeting",
        f"Meeting minutes\nCompany: AcmeSystems\nChair: {owner}\nProject: {project}\n\n"
        f"Decisions: approve the next integration milestone for AcmeSystems {project}. "
        f"Actions: Engineering validates interfaces; Operations prepares rollout. "
        f"Risks: supplier lead time. Next review is Friday.",
    )


def gen_technical_spec(rng: random.Random) -> tuple[str, str]:
    project = rng.choice(PROJECTS)
    return (
        f"AcmeSystems {project} Technical Specification",
        f"Technical specification — AcmeSystems {project}\n\nPurpose: define a secure service interface. "
        f"Requirements: TLS transport, audit events, role-based authorization, and 99.9% availability. "
        f"Acceptance: integration tests pass in staging.",
    )


def gen_procedure(rng: random.Random) -> tuple[str, str]:
    return (
        "AcmeSystems ISO 27001 Change Procedure",
        "Procedure (ISO 27001 / SOC2)\n1. Record the change request.\n2. Obtain Security and Operations approval.\n"
        "3. Deploy in the approved maintenance window.\n4. Validate monitoring and document rollback.\n"
        "Company: AcmeSystems (Paris / Berlin / Montreal).",
    )


def gen_hr_policy(rng: random.Random) -> tuple[str, str]:
    return (
        "AcmeSystems Remote Work Policy",
        "HR policy — AcmeSystems\nEmployees may work remotely subject to manager approval. "
        "Protect company information, use managed devices, and report any suspected security incident promptly.",
    )


def gen_project_report(rng: random.Random) -> tuple[str, str]:
    project = rng.choice(PROJECTS)
    return (
        f"AcmeSystems {project} Status",
        f"Project report — AcmeSystems {project}\nStatus: amber\nCompleted: architecture review and prototype.\n"
        f"Next: user acceptance testing.\nBudget variance: {rng.randint(0, 8)} percent. Owner: {person(rng)}.",
    )


def gen_email_thread(rng: random.Random) -> tuple[str, str]:
    sender, recipient = person(rng), person(rng)
    return (
        "Email: AcmeSystems Integration Decision",
        f"From: {sender}@acmesystems.example\nTo: {recipient}@acmesystems.example\n"
        f"Subject: AcmeSystems integration decision\n\nPlease confirm the API version before Thursday.\n\n"
        f"Reply: Version 2 is approved; Security will review the deployment plan.",
    )


def gen_invoice_summary(rng: random.Random) -> tuple[str, str]:
    return (
        "AcmeSystems Invoice Summary",
        f"Invoice summary\nVendor: AcmeSystems supplier\nReference: INV-{rng.randint(10000, 99999)}\n"
        f"Amount: EUR {rng.randint(1200, 18000)}\nStatus: pending approval\nCost center: {rng.choice(DEPARTMENTS)}.",
    )


def gen_kb_article(rng: random.Random) -> tuple[str, str]:
    return (
        "AcmeSystems KB: Reset Service Credential",
        "Knowledge base article — AcmeSystems\nUse the identity portal to rotate a service credential. "
        "Update the vault entry, redeploy the dependent workload, and verify audit logs. Never send credentials through email.",
    )


ENTERPRISE_GENERATORS = {
    "meeting_minutes": gen_meeting_minutes,
    "technical_spec": gen_technical_spec,
    "procedure": gen_procedure,
    "hr_policy": gen_hr_policy,
    "project_report": gen_project_report,
    "email_thread": gen_email_thread,
    "invoice_summary": gen_invoice_summary,
    "kb_article": gen_kb_article,
}


def write_pdf(path: Path, title: str, text: str) -> None:
    safe = (title + "\n" + text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = safe.splitlines()[:40]
    stream = "BT /F1 10 Tf 50 760 Td " + " ".join(f"({line[:100]}) Tj 0 -14 Td" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", f"<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data)); data.extend(f"{i} 0 obj\n{obj}\nendobj\n".encode())
    xref = len(data); data.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    data.extend(b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets[1:]))
    data.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(data)


def write_docx(path: Path, title: str, text: str) -> None:
    paras = "".join(f"<w:p><w:r><w:t>{html.escape(line)}</w:t></w:r></w:p>" for line in (title + "\n" + text).splitlines())
    document = f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{paras}</w:body></w:document>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", document)


def write_document(path: Path, fmt: str, title: str, body: str, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "pdf": write_pdf(path, title, body)
    elif fmt == "docx": write_docx(path, title, body)
    elif fmt == "json": path.write_text(json.dumps({"title": title, "content": body, "metadata": record["metadata"]}, indent=2), encoding="utf-8")
    elif fmt == "csv":
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["title", "content", "topic"], [title, body.replace("\n", " "), record["topic_id"]]])
    elif fmt == "html": path.write_text(f"<!doctype html><html lang=\"{record['lang']}\"><head><title>{html.escape(title)}</title></head><body><h1>{html.escape(title)}</h1><pre>{html.escape(body)}</pre></body></html>", encoding="utf-8")
    elif fmt == "md": path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    else: path.write_text(f"{title}\n{'=' * len(title)}\n\n{body}\n", encoding="utf-8")


def generate_documents(root: Path, corpus: str, count: int, rng: random.Random) -> list[dict[str, Any]]:
    is_osint = corpus == "osint"
    types, formats = (OSINT_TYPES, OSINT_FORMATS) if is_osint else (ENTERPRISE_TYPES, ENTERPRISE_FORMATS)
    base = root / ("corpus_nato" if is_osint else "corpus_enterprise")
    entries = []
    for i in range(1, count + 1):
        dtype, fmt = rng.choice(types), choose_weighted(rng, formats)
        ident = f"{dtype}_{i:05d}_{rng.getrandbits(32):08x}"
        lang = "en" if rng.random() < 0.60 else "fr"
        if is_osint:
            title, body = nato_text(dtype, rng, lang, i)
            topic = OSINT_TOPIC_MAP[dtype]
            space = "demo-user"
        else:
            title, body = ENTERPRISE_GENERATORS[dtype](rng)
            if lang == "fr":
                body = body + "\n\nNote: document interne AcmeSystems (version française de travail)."
            topic = ENTERPRISE_TOPIC_MAP[dtype]
            space = "demo-admin"
        rel = Path(FORMAT_DIRS[fmt]) / f"{ident}.{fmt}"
        entry = {"id": ident, "doc_type": dtype, "format": fmt, "title": title, "lang": lang, "path": str(rel), "user_space": space, "topic_id": topic, "corpus": corpus, "origin": "generated", "metadata": {"company": None if is_osint else "AcmeSystems", "created_at": NOW(), "generator": "tkeir-corpus"}}
        write_document(base / rel, fmt, title, body, entry)
        entries.append(entry)
    return entries


def make_rdf_root() -> ET.Element:
    return ET.Element(f"{{{RDF}}}RDF")


def xml_ontology(path: Path, ns_key: str, title: str, triples: int = 60) -> None:
    uri = NS[ns_key]; root = make_rdf_root()
    onto = ET.SubElement(root, f"{{{OWL}}}Ontology", {f"{{{RDF}}}about": uri})
    label = ET.SubElement(onto, f"{{{RDFS}}}label", {XML_LANG: "en"}); label.text = title
    for i in range(triples):
        klass = ET.SubElement(root, f"{{{OWL}}}Class", {f"{{{RDF}}}about": f"{uri}Class{i}"})
        lab = ET.SubElement(klass, f"{{{RDFS}}}label", {XML_LANG: "en"}); lab.text = f"{title} Class {i}"
        if i:
            ET.SubElement(klass, f"{{{RDFS}}}subClassOf", {f"{{{RDF}}}resource": f"{uri}Class{i-1}"})
        prop = ET.SubElement(root, f"{{{OWL}}}ObjectProperty", {f"{{{RDF}}}about": f"{uri}relatesTo{i}"})
        ET.SubElement(prop, f"{{{RDFS}}}domain", {f"{{{RDF}}}resource": f"{uri}Class{i}"})
        ET.SubElement(prop, f"{{{RDFS}}}range", {f"{{{RDF}}}resource": f"{uri}Class{(i+1) % triples}"})
        individual = ET.SubElement(root, f"{{{OWL}}}NamedIndividual", {f"{{{RDF}}}about": f"{uri}Example{i}"})
        ET.SubElement(individual, f"{{{RDF}}}type", {f"{{{RDF}}}resource": f"{uri}Class{i}"})
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def ttl_ontology(path: Path, prefix: str, uri: str, title: str, combined: bool = False) -> None:
    lines = [
        f"@prefix {prefix}: <{uri}> .",
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix c2sim: <http://www.sisostds.org/ontologies/C2SIM#> .",
        "@prefix lox: <http://www.sisostds.org/ontologies/lox#> .",
        "@prefix cwix: <http://www.sisostds.org/ontologies/C2SIM/cwix2023#> .",
        "@prefix tkeir: <http://tkeir.local/ontology/> .",
        "@prefix tkeirdoc: <http://tkeir.local/doc/> .",
    ]
    if combined:
        lines.append("@prefix dc: <http://purl.org/dc/elements/1.1/> .")
    lines += [f'<{uri}> a owl:Ontology ; rdfs:label "{title}"@en .']
    for i in range(30):
        subclass = f" ; rdfs:subClassOf {prefix}:Class{i-1}" if i else ""
        lines.append(f'{prefix}:Class{i} a owl:Class ; rdfs:label "{title} Class {i}"@en{subclass} .')
        lines.append(f'{prefix}:asset{i} a {prefix}:Class{i} ; rdfs:label "Asset {i}"@en .')
    if combined:
        lines.extend(
            [
                'ex:CWIX2023_Scenario a cwix:ExerciseScenario ;',
                '  dc:description "CWIX 2023 coalition interoperability scenario."@en ;',
                '  rdfs:label "CWIX 2023"@en .',
                "c2sim:taskAssignedTo a owl:ObjectProperty .",
                "c2sim:taskName a owl:DatatypeProperty .",
                "c2sim:hasObjective a owl:ObjectProperty .",
                "lox:GroundUnit a owl:Class ; rdfs:label \"GroundUnit\"@en .",
                "c2sim:OperationalEntity a owl:Class ; rdfs:label \"OperationalEntity\"@en .",
                'c2sim:Unit_ALPHA a lox:GroundUnit , c2sim:OperationalEntity ; rdfs:label "Task Group ALPHA"@en .',
                'c2sim:Unit_BRAVO a lox:GroundUnit , c2sim:OperationalEntity ; rdfs:label "CWIX 2023 Force BRAVO"@en .',
                'c2sim:Obj_ALPHA a c2sim:Class0 ; rdfs:label "Objective ALPHA"@en .',
                'c2sim:Task_1 a c2sim:Class1 ;',
                '  c2sim:taskAssignedTo c2sim:Unit_ALPHA ;',
                '  c2sim:taskName "Secure Objective ALPHA"@en ;',
                '  c2sim:hasObjective c2sim:Obj_ALPHA ;',
                '  rdfs:label "Secure Objective ALPHA"@en .',
                'c2sim:Task_2 a c2sim:Class1 ;',
                '  c2sim:taskAssignedTo c2sim:Unit_BRAVO ;',
                '  c2sim:taskName "ISR collection CWIX 2023"@en ;',
                '  c2sim:hasObjective c2sim:Obj_ALPHA ;',
                '  rdfs:label "ISR collection CWIX 2023"@en .',
                "tkeirdoc:doc_nato a tkeir:Document ;",
                "  tkeir:hasChunk <http://tkeir.local/doc/doc_nato/Chunk/chunk_1> ;",
                "  tkeir:hasKeyword <http://tkeir.local/doc/doc_nato/Keyword/intsum> ;",
                "  tkeir:hasMention c2sim:Unit_ALPHA .",
                "<http://tkeir.local/doc/doc_nato/Keyword/intsum> a tkeir:Keyword ;",
                '  rdfs:label "INTSUM"@en .',
                "<http://tkeir.local/doc/doc_nato/Chunk/chunk_1> a tkeir:DocumentChunk ;",
                '  rdfs:label "sitrep.pdf#chunk-1-alpha" ;',
                "  tkeir:hasMention c2sim:Unit_ALPHA ;",
                "  tkeir:hasMention c2sim:Unit_BRAVO .",
            ]
        )
    # combined TTL references ex: — declare a harmless base prefix
    if combined:
        lines.insert(1, "@prefix ex: <http://example.org/cwix#> .")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_ontologies(root: Path) -> None:
    ontology_dir = root / "corpus_nato" / "ontologies"; ontology_dir.mkdir(parents=True, exist_ok=True)
    xml_ontology(ontology_dir / "c2sim_core.owl", "c2sim", "C2SIM Core", 65)
    xml_ontology(ontology_dir / "c2sim_lox.owl", "lox", "LOX", 55)
    xml_ontology(ontology_dir / "c2sim_smx.owl", "smx", "SMX", 55)
    xml_ontology(ontology_dir / "c2sim_cwix2023.owl", "cwix", "CWIX 2023", 55)
    ttl_ontology(ontology_dir / "c2sim_c4isr.ttl", "c4isr", NS["c4isr"], "NATO C4ISR")
    ttl_ontology(ontology_dir / "c2sim_combined.ttl", "cwix", NS["cwix"], "C2SIM Combined CWIX", True)
    (root / "corpus_nato" / "ONTOLOGY_INTEGRATION.md").write_text("# Ontology integration\n\nGenerated ontologies are suitable for local RDF ingestion. Official artifacts, when downloaded, are placed in `ontologies/official` so generated files remain unchanged.\n", encoding="utf-8")
    helper = root / "corpus_nato" / "ingest_all.sh"
    helper.write_text("#!/usr/bin/env sh\nset -eu\n# Example: replace this command with the local T-KEIR ingest invocation.\nfind \"$(dirname \"$0\")\"/ontologies -type f \\( -name '*.owl' -o -name '*.ttl' \\) -print\n", encoding="utf-8")
    helper.chmod(0o755)


def _fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "tkeir-corpus-generator/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def download_official_artifacts(output_dir: Path | str, timeout: int = 30) -> dict[str, Any]:
    """Best-effort download. Never raises — always returns a summary dict."""
    result: dict[str, Any] = {
        "downloaded": False,
        "reason": "",
        "siso_ontologies": 0,
        "xsd_schemas": 0,
        "enterprise_docs": 0,
        "sources_tried": [],
        "sources_ok": [],
        "documents": [],
    }
    if os.environ.get("TKEIR_CORPUS_OFFLINE") == "1":
        result["reason"] = "offline mode"
        return result

    root = Path(output_dir)
    nato, enterprise = root / "corpus_nato", root / "corpus_enterprise"

    # SOURCE 1 — SISO C2SIM official ontologies (into official/, never overwrite generated)
    src = "OpenC2SIM/C2SIMArtifacts"
    result["sources_tried"].append(src)
    try:
        release = json.loads(
            _fetch("https://api.github.com/repos/OpenC2SIM/C2SIMArtifacts/releases/latest", timeout)
        )
        for asset in release.get("assets", []):
            if not str(asset.get("name", "")).lower().endswith(".zip"):
                continue
            blob = _fetch(asset["browser_download_url"], timeout)
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for name in archive.namelist():
                    if ".." in Path(name).parts:
                        continue
                    if not name.lower().endswith((".owl", ".ttl", ".xsd")):
                        continue
                    target = nato / "ontologies" / "official" / Path(name).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
                    result["siso_ontologies"] += 1
            result["sources_ok"].append(src)
            break
    except Exception as exc:
        LOG.warning("corpus-download skipping %s: %s", src, exc)

    # SOURCE 2 — C2SIM XSD schemas
    xsd_urls = [
        "https://raw.githubusercontent.com/OpenC2SIM/OpenC2SIM.github.io/master/C2SIM_SMX_LOX_V1.0.1.xsd",
        "https://raw.githubusercontent.com/OpenC2SIM/OpenC2SIM.github.io/master/C2SIM_SMX_LOX_CWIX2023v1.0.2.xsd",
    ]
    for url in xsd_urls:
        result["sources_tried"].append(url)
        try:
            data = _fetch(url, timeout)
            target = nato / "xml" / Path(url).name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            result["xsd_schemas"] += 1
            result["sources_ok"].append(url)
            break
        except Exception as exc:
            LOG.warning("corpus-download skipping %s: %s", url, exc)

    # SOURCE 3 — EnterpriseRAG-Bench slices
    enterprise_urls = [
        ("confluence", "https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench/resolve/main/confluence_slice_1.zip"),
        ("gdoc", "https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench/resolve/main/gdoc_slice_1.zip"),
        ("email", "https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench/resolve/main/email_slice_1.zip"),
        ("confluence", "https://github.com/onyx-dot-app/EnterpriseRAG-Bench/releases/latest/download/confluence_slice_1.zip"),
    ]
    max_docs = 500
    for source_type, url in enterprise_urls:
        if result["enterprise_docs"] >= max_docs:
            break
        result["sources_tried"].append(url)
        try:
            blob = _fetch(url, timeout)
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for name in archive.namelist():
                    if result["enterprise_docs"] >= max_docs:
                        break
                    if name.endswith("/") or ".." in Path(name).parts:
                        continue
                    suffix = Path(name).suffix.lower().lstrip(".")
                    if suffix not in {"txt", "html", "json", "md", "csv"}:
                        continue
                    fmt = "html" if suffix == "html" else ("json" if suffix == "json" else ("md" if suffix == "md" else ("csv" if suffix == "csv" else "txt")))
                    data = archive.read(name)
                    ident = f"{source_type}_{result['enterprise_docs']:05d}_{Path(name).stem[:40]}"
                    rel = Path(FORMAT_DIRS.get(fmt, "raw")) / f"{ident}.{fmt if fmt != 'txt' else 'txt'}"
                    if fmt == "txt":
                        rel = Path("raw") / f"{ident}.txt"
                    target = enterprise / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    topic = ENTERPRISE_SOURCE_TOPIC.get(source_type, "projects")
                    result["documents"].append(
                        {
                            "id": ident,
                            "doc_type": source_type,
                            "format": fmt,
                            "title": Path(name).name,
                            "lang": "en",
                            "path": str(rel),
                            "user_space": "demo-admin",
                            "topic_id": topic,
                            "corpus": "enterprise",
                            "origin": "downloaded",
                            "metadata": {"source_url": url, "source_type": source_type},
                        }
                    )
                    result["enterprise_docs"] += 1
            result["sources_ok"].append(url)
            break
        except Exception as exc:
            LOG.warning("corpus-download skipping %s: %s", url, exc)

    result["downloaded"] = bool(result["sources_ok"])
    result["reason"] = "completed" if result["downloaded"] else "no source available"
    return result


def write_manifest(root: Path, corpus: str, seed: int, entries: list[dict[str, Any]]) -> None:
    base = root / ("corpus_nato" if corpus == "osint" else "corpus_enterprise")
    base.mkdir(parents=True, exist_ok=True)
    (base / "manifest.json").write_text(json.dumps({"corpus": corpus, "count_generated": sum(e["origin"] == "generated" for e in entries), "seed": seed, "documents": entries}, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--output", default="./workspace", help="Corpus output directory (default: ./workspace)")
    p.add_argument("--count-osint", type=int, default=1500)
    p.add_argument("--count-enterprise", type=int, default=500)
    p.add_argument("-s", "--seed", type=int, default=42)
    p.add_argument("--download", action="store_true", help="Best-effort optional public artifacts download")
    p.add_argument("--only-ontologies", action="store_true", help="Generate ontologies but skip documents")
    p.add_argument("--corpus", choices=("osint", "enterprise", "all"), default="all")
    p.add_argument("-q", "--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.count_osint < 0 or args.count_enterprise < 0:
        raise SystemExit("counts must be non-negative")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    root = Path(args.output).expanduser().resolve(); root.mkdir(parents=True, exist_ok=True)
    if args.corpus in ("osint", "all"): generate_ontologies(root)
    entries: dict[str, list[dict[str, Any]]] = {"osint": [], "enterprise": []}
    rng = random.Random(args.seed)
    if not args.only_ontologies:
        if args.corpus in ("osint", "all"): entries["osint"] = generate_documents(root, "osint", args.count_osint, rng)
        if args.corpus in ("enterprise", "all"): entries["enterprise"] = generate_documents(root, "enterprise", args.count_enterprise, rng)
    downloaded: dict[str, Any] | None = None
    if args.download: downloaded = download_official_artifacts(root)
    if downloaded and args.corpus in ("enterprise", "all"): entries["enterprise"].extend(downloaded["documents"])
    if not args.only_ontologies:
        for corpus in ("osint", "enterprise"):
            if args.corpus in (corpus, "all"): write_manifest(root, corpus, args.seed, entries[corpus])
    if not args.quiet:
        print(f"Generated corpus in {root}")
        if downloaded:
            ok = len(downloaded.get("sources_ok") or [])
            tried = len(downloaded.get("sources_tried") or [])
            print(f"Download: {downloaded['reason']} ({ok}/{tried} sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
