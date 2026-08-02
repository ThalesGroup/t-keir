#!/usr/bin/env python3
"""Title: Generate bom

Generate a unified CycloneDX BOM (SBOM + AIBOM) for T-Keir.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from cyclonedx.model import (
    ExternalReference,
    ExternalReferenceType,
    HashAlgorithm,
    HashType,
    Property,
    XsUri,
)
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model.contact import OrganizationalContact
from cyclonedx.output import OutputFormat, make_outputter
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator
from packageurl import PackageURL


class BomConfigError(ValueError):
    """Raised when scripts/bom/config.yaml is invalid."""


class BomValidationError(RuntimeError):
    """Raised when generated BOM fails CycloneDX schema validation."""


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BomConfigError(f"config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise BomConfigError("config must be a mapping")
    return data


def _normalise_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _model_component(entry: dict[str, Any]) -> Component:
    name = str(entry["name"])
    version = str(entry.get("version", ""))
    supplier = str(entry.get("supplier", "unknown"))
    use_case = str(entry.get("use_case", "nlp"))
    purl = PackageURL(type="pypi", name=name, version=version or None)
    component = Component(
        type=ComponentType.MACHINE_LEARNING_MODEL,
        name=name,
        version=version or None,
        purl=purl,
        supplier=OrganizationalContact(name=supplier),
    )
    component.properties.add(Property(name="ai:use_case", value=use_case))
    component.properties.add(
        Property(name="ai:component_role", value="nlp-model")
    )
    return component


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _guess_dataset_supplier(name: str, download_url: str | None) -> str:
    lowered = name.lower()
    if "geoname" in lowered or (download_url and "geonames.org" in download_url):
        return "GeoNames"
    if "fortune" in lowered:
        return "Fortune"
    return "tkeir"


def _dataset_component(
    *,
    name: str,
    path: Path,
    language: str,
    role: str,
    use_case: str,
    repo_root: Path,
    label: str | None = None,
    data_type: str | None = None,
    pos: str | None = None,
    download_url: str | None = None,
    description: str | None = None,
) -> Component:
    supplier = _guess_dataset_supplier(name, download_url)
    try:
        relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        relative = path.as_posix()
    qualifiers = {"download_url": download_url} if download_url else None
    purl = PackageURL(
        type="generic",
        namespace="tkeir",
        name=name,
        qualifiers=qualifiers,
        subpath=relative if path.is_file() else None,
    )
    component = Component(
        type=ComponentType.DATA,
        name=name,
        description=description,
        purl=purl,
        supplier=OrganizationalContact(name=supplier),
    )
    component.properties.add(Property(name="ai:component_role", value=role))
    component.properties.add(Property(name="ai:use_case", value=use_case))
    component.properties.add(Property(name="tokenizer:language", value=language))
    component.properties.add(Property(name="tokenizer:path", value=relative))
    if label:
        component.properties.add(Property(name="tokenizer:label", value=label))
    if data_type:
        component.properties.add(Property(name="tokenizer:type", value=data_type))
    if pos:
        component.properties.add(Property(name="tokenizer:pos", value=pos))
    if download_url:
        component.external_references.add(
            ExternalReference(
                type=ExternalReferenceType.DISTRIBUTION,
                url=XsUri(download_url),
            )
        )
    digest = _sha256_file(path)
    if digest:
        component.hashes.add(
            HashType(alg=HashAlgorithm.SHA_256, content=digest)
        )
    return component


def _iter_annotation_lists(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for block in catalog.get("data") or []:
        if not isinstance(block, dict):
            continue
        for item in block.get("lists") or []:
            if isinstance(item, dict) and item.get("name"):
                entries.append(item)
    return entries


def load_dataset_components(
    config: dict[str, Any],
    *,
    repo_root: Path,
) -> list[Component]:
    """Expand annotation-resources catalogs into CycloneDX DATA components."""
    components: list[Component] = []
    seen: set[str] = set()

    for entry in config.get("datasets") or []:
        if not isinstance(entry, dict):
            continue
        catalog_rel = entry.get("catalog")
        if not catalog_rel:
            continue
        catalog_path = Path(str(catalog_rel))
        if not catalog_path.is_absolute():
            catalog_path = repo_root / catalog_path
        if not catalog_path.is_file():
            raise BomConfigError(f"dataset catalog not found: {catalog_path}")

        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        language = str(entry.get("language") or catalog_path.parent.name)
        role = str(entry.get("role") or "inference-gazetteer")
        use_case = str(entry.get("use_case") or "tokenizer-ner-mwe")
        base = catalog_path.parent

        for item in _iter_annotation_lists(catalog):
            name = str(item["name"])
            if name in seen:
                continue
            seen.add(name)
            rel_path = str(item.get("path") or "")
            file_path = base / rel_path if rel_path else base
            download = item.get("download") or {}
            download_url = None
            if isinstance(download, dict):
                download_url = download.get("url")
            components.append(
                _dataset_component(
                    name=name,
                    path=file_path,
                    language=language,
                    role=role,
                    use_case=use_case,
                    repo_root=repo_root,
                    label=str(item["label"]) if item.get("label") else None,
                    data_type=str(item["type"]) if item.get("type") else None,
                    pos=str(item["pos"]) if item.get("pos") else None,
                    download_url=str(download_url) if download_url else None,
                    description=(
                        f"Tokenizer {language} gazetteer/lexicon "
                        f"from {catalog_path.name}"
                    ),
                )
            )

        if entry.get("include_compiled_mwe", True):
            mwe_path = base / "tkeir_mwe.pkl"
            mwe_name = f"tkeir-mwe-{language}"
            if mwe_name not in seen and mwe_path.is_file():
                seen.add(mwe_name)
                components.append(
                    _dataset_component(
                        name=mwe_name,
                        path=mwe_path,
                        language=language,
                        role="compiled-mwe",
                        use_case=use_case,
                        repo_root=repo_root,
                        description=(
                            f"Compiled MWE trie for tokenizer language={language}"
                        ),
                    )
                )

    return components


def build_ai_bom(config: dict[str, Any], *, repo_root: Path | None = None) -> Bom:
    bom = Bom()
    root = Component(
        type=ComponentType.APPLICATION,
        name=str(config.get("project_name", "tkeir")),
        version=str(config.get("project_version", "0.0.0")),
        description=str(config.get("description", "")).strip() or None,
    )
    author = config.get("author")
    if author:
        bom.metadata.authors = [OrganizationalContact(name=str(author))]
    bom.metadata.component = root
    bom.metadata.timestamp = datetime.now(tz=UTC)

    model_components = [
        _model_component(entry)
        for entry in config.get("models") or []
        if isinstance(entry, dict) and entry.get("name")
    ]
    dataset_components = (
        load_dataset_components(config, repo_root=repo_root)
        if repo_root is not None
        else []
    )
    for component in model_components + dataset_components:
        bom.components.add(component)
    bom.register_dependency(
        root, depends_on=model_components + dataset_components
    )
    return bom


def _tag_ml_libraries(component: Component, ml_libraries: set[str]) -> None:
    name = _normalise_package_name(component.name or "")
    if name in ml_libraries:
        component.properties.add(Property(name="ml:role", value="framework"))
        component.properties.add(
            Property(name="ai:component_role", value="ml-library")
        )


def merge_dependency_bom(
    bom: Bom,
    dependency_json: dict[str, Any],
    ml_libraries: set[str],
) -> int:
    added = 0
    existing = {
        _normalise_package_name(component.name or "")
        for component in bom.components
        if component.name
    }
    for comp_dict in dependency_json.get("components", []):
        name = _normalise_package_name(str(comp_dict.get("name", "")))
        if not name or name in existing:
            continue
        component = Component.from_json(comp_dict)
        _tag_ml_libraries(component, ml_libraries)
        bom.components.add(component)
        existing.add(name)
        added += 1
    return added


def export_requirements_files(tkeir_dir: Path, req_dir: Path) -> tuple[Path, Path]:
    req_dir.mkdir(parents=True, exist_ok=True)
    runtime_path = req_dir / "requirements-runtime.txt"
    ci_path = req_dir / "requirements-ci.txt"
    subprocess.run(
        [
            "uv",
            "export",
            "--format",
            "requirements-txt",
            "--no-hashes",
            "--no-emit-project",
            "-o",
            str(runtime_path),
        ],
        check=True,
        cwd=tkeir_dir,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "uv",
            "export",
            "--group",
            "dev",
            "--format",
            "requirements-txt",
            "--no-hashes",
            "--no-emit-project",
            "-o",
            str(ci_path),
        ],
        check=True,
        cwd=tkeir_dir,
        stdout=subprocess.DEVNULL,
    )
    return runtime_path, ci_path


def export_requirements_bom(
    *,
    tkeir_dir: Path,
    requirements_path: Path,
    spec_version: str,
    python_executable: str | None = None,
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(suffix=".cdx.json", delete=False) as handle:
        output_path = Path(handle.name)

    cmd = ["uv", "run", "cyclonedx-py"]
    if python_executable:
        cmd.extend(
            [
                "environment",
                "--pyproject",
                str(tkeir_dir / "pyproject.toml"),
                "--mc-type",
                "application",
                "--sv",
                spec_version,
                "--output-format",
                "JSON",
                "--output-file",
                str(output_path),
                python_executable,
            ]
        )
    else:
        cmd.extend(
            [
                "requirements",
                "--pyproject",
                str(tkeir_dir / "pyproject.toml"),
                "--mc-type",
                "application",
                "--sv",
                spec_version,
                "--output-format",
                "JSON",
                "--output-file",
                str(output_path),
                str(requirements_path),
            ]
        )

    subprocess.run(
        cmd,
        check=True,
        cwd=tkeir_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    data = json.loads(output_path.read_text(encoding="utf-8"))
    output_path.unlink(missing_ok=True)
    return data


def validate_json_output(json_text: str) -> None:
    validator = JsonStrictValidator(SchemaVersion.V1_6)
    error = validator.validate_str(json_text)
    if error:
        raise BomValidationError(
            f"BOM JSON failed CycloneDX 1.6 validation:\n{error}"
        )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2)
    validate_json_output(text)
    path.write_text(text, encoding="utf-8")


def build_unified_bom(
    config: dict[str, Any],
    *,
    repo_root: Path,
    tkeir_dir: Path,
    spec_version: str = "1.6",
    python_executable: Path | None = None,
) -> tuple[Bom, dict[str, dict[str, Any]]]:
    bom = build_ai_bom(config, repo_root=repo_root)
    ml_libraries = {
        _normalise_package_name(str(name))
        for name in config.get("ml_libraries") or []
    }
    views: dict[str, dict[str, Any]] = {}

    req_dir = repo_root / "reports" / "security"
    runtime_req, ci_req = export_requirements_files(tkeir_dir, req_dir)

    views["dependencies-runtime"] = export_requirements_bom(
        tkeir_dir=tkeir_dir,
        requirements_path=runtime_req,
        spec_version=spec_version,
    )
    views["dependencies-ci"] = export_requirements_bom(
        tkeir_dir=tkeir_dir,
        requirements_path=ci_req,
        spec_version=spec_version,
    )

    if python_executable and python_executable.is_file():
        views["dependencies-environment"] = export_requirements_bom(
            tkeir_dir=tkeir_dir,
            requirements_path=runtime_req,
            spec_version=spec_version,
            python_executable=str(python_executable),
        )

    merge_dependency_bom(bom, views["dependencies-runtime"], ml_libraries)
    return bom, views


def write_bom_outputs(
    bom: Bom,
    output_dir: Path,
    project_name: str,
    views: dict[str, dict[str, Any]],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    views_dir = output_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{project_name}.cdx.json"
    xml_path = output_dir / f"{project_name}.cdx.xml"

    json_outputter = make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_6)
    json_text = json_outputter.output_as_string(indent=2)
    validate_json_output(json_text)
    json_path.write_text(json_text, encoding="utf-8")

    xml_outputter = make_outputter(bom, OutputFormat.XML, SchemaVersion.V1_6)
    xml_path.write_text(xml_outputter.output_as_string(), encoding="utf-8")

    written: dict[str, Path] = {"json": json_path, "xml": xml_path}
    for view_name, view_data in views.items():
        view_path = views_dir / f"{view_name}.cdx.json"
        _write_json(view_path, view_data)
        written[view_name] = view_path
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate unified CycloneDX BOM for T-Keir"
    )
    repo_root = Path(__file__).resolve().parents[2]
    tkeir_dir = repo_root / "tkeir"
    parser.add_argument(
        "--config",
        type=Path,
        default=repo_root / "scripts" / "bom" / "config.yaml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "reports" / "bom",
    )
    parser.add_argument("--spec-version", default="1.6")
    parser.add_argument(
        "--python",
        type=Path,
        default=tkeir_dir / ".venv" / "bin" / "python",
    )
    parser.add_argument(
        "--tkeir-dir",
        type=Path,
        default=tkeir_dir,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    try:
        config = load_config(args.config)
        bom, views = build_unified_bom(
            config,
            repo_root=repo_root,
            tkeir_dir=args.tkeir_dir,
            spec_version=args.spec_version,
            python_executable=args.python,
        )
        project_name = str(config.get("project_name", "tkeir"))
        written = write_bom_outputs(
            bom, args.output_dir, project_name, views
        )
    except (
        BomConfigError,
        BomValidationError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    summary = {
        "components": len(bom.components),
        "outputs": {key: str(path) for key, path in written.items()},
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
