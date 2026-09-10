"""Title: Install spaCy models

Download Explosion spaCy 3.6 wheels and extract them into
``tkeir/resources/modeling/spacy/<model>/`` so setup/install ships pipelines
next to BGE-M3 (not only as venv site-packages).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from thot.core.TkeirPaths import spacy_models_dir

SPACY_MODEL_VERSION = "3.6.0"

CORE_SPACY_MODELS = (
    "en_core_web_sm",
    "en_core_web_md",
    "fr_core_news_sm",
    "fr_core_news_md",
    "xx_ent_wiki_sm",
)

EXTRA_SPACY_MODELS = (
    "de_core_news_sm",
    "es_core_news_sm",
    "it_core_news_sm",
    "pt_core_news_sm",
    "nl_core_news_sm",
    "pl_core_news_sm",
    "da_core_news_sm",
    "sv_core_news_sm",
)


def spacy_wheel_url(model_name: str) -> str:
    """Return the Explosion GitHub wheel URL for a spaCy 3.6 model.

    Example:
        >>> from thot.tools.install_spacy_models import spacy_wheel_url
        >>> "en_core_web_sm-3.6.0" in spacy_wheel_url("en_core_web_sm")
        True
    """
    tag = model_name + "-" + SPACY_MODEL_VERSION
    return (
        "https://github.com/explosion/spacy-models/releases/download/"
        + tag
        + "/"
        + tag
        + "-py3-none-any.whl"
    )


def _model_ready(dest_root: Path, model_name: str) -> bool:
    """Return True when ``model_name`` is extracted under ``dest_root``.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.install_spacy_models import _model_ready
        >>> _model_ready(Path("/tmp"), "missing_model_xyz")
        False
    """
    from thot.core.SpacyModelLoader import resolve_spacy_load_name

    resolved = resolve_spacy_load_name(model_name, models_dir=str(dest_root))
    return resolved != model_name and Path(resolved).is_dir()


def extract_spacy_wheel(
    wheel_path: Path, dest_root: Path, model_name: str
) -> Path:
    """Unpack a spaCy model wheel under ``dest_root / model_name``.

    Example:
        >>> from thot.tools.install_spacy_models import extract_spacy_wheel
        >>> callable(extract_spacy_wheel)
        True
    """
    target = dest_root / model_name
    if target.exists():
        shutil.rmtree(target)
    dest_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel_path) as archive:
        archive.extractall(dest_root)
    for dist_info in dest_root.glob("*.dist-info"):
        shutil.rmtree(dist_info, ignore_errors=True)
    if not _model_ready(dest_root, model_name):
        raise OSError(
            "Extracted spaCy wheel is missing config.cfg for " + model_name
        )
    return target


def install_one_model(
    model_name: str,
    *,
    force: bool = False,
    dest_root: Path | None = None,
) -> Path:
    """Download one spaCy wheel into ``resources/modeling/spacy``.

    Args:
        model_name: Pipeline name such as ``en_core_web_sm``.
        force: Re-download even when the model directory already exists.
        dest_root: Override destination (defaults to ``spacy_models_dir()``).

    Returns:
        Directory containing the extracted package.

    Example:
        >>> from thot.tools.install_spacy_models import install_one_model
        >>> install_one_model("en_core_web_sm")  # doctest: +SKIP
    """
    root = Path(dest_root or spacy_models_dir())
    root.mkdir(parents=True, exist_ok=True)
    if not force and _model_ready(root, model_name):
        return root / model_name
    url = spacy_wheel_url(model_name)
    with tempfile.TemporaryDirectory(prefix="tkeir-spacy-") as tmp:
        wheel = Path(tmp) / (model_name + ".whl")
        print("Downloading", url, flush=True)
        urllib.request.urlretrieve(url, wheel)
        return extract_spacy_wheel(wheel, root, model_name)


def install_spacy_models(
    *,
    core: bool = True,
    extra: bool = True,
    force: bool = False,
    dest_root: Path | None = None,
) -> list[str]:
    """Install core (and optionally extra European) spaCy pipelines.

    Example:
        >>> from thot.tools.install_spacy_models import CORE_SPACY_MODELS
        >>> "en_core_web_md" in CORE_SPACY_MODELS
        True
    """
    names: list[str] = []
    if core:
        names.extend(CORE_SPACY_MODELS)
    if extra:
        names.extend(EXTRA_SPACY_MODELS)
    installed: list[str] = []
    failures: list[str] = []
    extra_set = set(EXTRA_SPACY_MODELS)
    for name in names:
        try:
            install_one_model(name, force=force, dest_root=dest_root)
            installed.append(name)
            print("Installed", name, "→", dest_root or spacy_models_dir())
        except Exception as error:
            if name in extra_set:
                print(
                    "WARN: extra spaCy model",
                    name,
                    "failed:",
                    error,
                    flush=True,
                )
                failures.append(name)
                continue
            raise
    if failures:
        print(
            "WARN: extra European spaCy models missing:",
            ",".join(failures),
            "(indexing falls back to xx_ent_wiki_sm)",
            flush=True,
        )
    return installed


def main(argv: list[str] | None = None) -> int:
    """CLI: extract spaCy wheels into ``resources/modeling/spacy``.

    Example:
        >>> from thot.tools.install_spacy_models import main
        >>> callable(main)
        True
    """
    parser = argparse.ArgumentParser(
        description=(
            "Download spaCy 3.6 models into tkeir/resources/modeling/spacy"
        )
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Install only en/fr/xx (skip extra European sm models)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when models are already present",
    )
    args = parser.parse_args(argv)
    force = args.force or os.environ.get("FORCE_SPACY_MODELS") == "1"
    dest = Path(spacy_models_dir())
    dest.mkdir(parents=True, exist_ok=True)
    print("spaCy models directory:", dest, flush=True)
    install_spacy_models(
        core=True,
        extra=not args.core_only,
        force=force,
        dest_root=dest,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
