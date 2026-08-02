#!/usr/bin/env python3
"""
download_rag_datasets.py
========================
Télécharge 4 corpus RAG benchmark pour l'évaluation de la génération :

  1. RAGBench – sous-ensembles Medical (covidqa, pubmedqa) + Finance (finqa, tatqa)
     Source : HuggingFace  rungalileo/ragbench
     Splits  : train / validation / test

  2. MultiHop-RAG – 2 556 QA multi-hop (2-4 docs) + corpus de 609 articles
     Source : HuggingFace  yixuantt/MultiHopRAG

  3. RGB – 4 testbeds (noise_robustness, negative_rejection, info_integration,
             counterfactual_robustness) EN + ZH
     Source : GitHub  IAAR-Shanghai/RGB  (pas de dépôt HF officiel)

  4. RAGTruth – ~18 000 réponses annotées au niveau mot pour la détection
                d'hallucinations (QA, data2txt, summarization)
     Source : GitHub  ParticleMedia/RAGTruth  +  HuggingFace  wandb/RAGTruth-processed

Usage
-----
  pip install datasets huggingface_hub requests tqdm
  python download_rag_datasets.py [--output_dir ./rag_benchmarks] [--hf_token HF_TOKEN]

Arborescence de sortie
----------------------
  rag_benchmarks/
  ├── ragbench/
  │   ├── medical/
  │   │   ├── covidqa/  {train,validation,test}.{parquet,json}
  │   │   └── pubmedqa/ {train,validation,test}.{parquet,json}
  │   └── finance/
  │       ├── finqa/    {train,validation,test}.{parquet,json}
  │       └── tatqa/    {train,validation,test}.{parquet,json}
  ├── multihop_rag/
  │   ├── MultiHopRAG.json   (2 556 QA pairs)
  │   └── corpus.json        (609 articles source)
  ├── rgb/
  │   ├── en/  {noise_robustness,negative_rejection,
  │   │         information_integration,counterfactual_robustness}.json
  │   └── zh/  (idem)
  └── ragtruth/
      ├── source.json        (contextes de référence)
      ├── response.json      (réponses LLM brutes)
      └── processed/         (version HF wandb/RAGTruth-processed)
          └── {train,test}.{parquet,json}

Published baselines live next to the data:
  leaderboard.yaml / LEADERBOARD.md
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports optionnels – vérifiés à l'exécution
# ---------------------------------------------------------------------------
MISSING = []
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    MISSING.append("requests")

try:
    from tqdm import tqdm
except ImportError:
    MISSING.append("tqdm")

try:
    from datasets import load_dataset
    from huggingface_hub import hf_hub_download, snapshot_download
except ImportError:
    MISSING.append("datasets")
    MISSING.append("huggingface_hub")

if MISSING:
    print(
        f"[ERROR] Dépendances manquantes : {', '.join(MISSING)}\n"
        "Installe-les avec :\n"
        f"  pip install {' '.join(MISSING)}"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session(retries: int = 5, backoff: float = 1.5) -> requests.Session:
    """Session HTTP avec retry exponentielle."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def download_file(url: str, dest: Path, session: requests.Session, desc: str = "") -> bool:
    """Télécharge un fichier avec barre de progression. Retourne True si succès."""
    try:
        resp = session.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f, tqdm(
            desc=desc or dest.name,
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            leave=False,
        ) as bar:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
        return True
    except Exception as exc:
        print(f"  [WARN] Échec téléchargement {url} → {exc}")
        return False


def parquet_to_json(parquet_path: Path, json_path: Path | None = None) -> Path:
    """Convertit un fichier parquet en JSON (tableau de records, indenté)."""
    dest = json_path or parquet_path.with_suffix(".json")
    if dest.exists():
        return dest
    try:
        import pandas as pd

        df = pd.read_parquet(parquet_path)
        rows = json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))
    except ImportError:
        import pyarrow.parquet as pq

        rows = pq.read_table(parquet_path).to_pylist()
    dest.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def ensure_json_siblings(directory: Path, name: str) -> None:
    """Pour chaque .parquet du dossier, écrit le .json frère s'il manque."""
    for parquet_path in sorted(directory.glob("*.parquet")):
        json_path = parquet_path.with_suffix(".json")
        if json_path.exists():
            continue
        parquet_to_json(parquet_path, json_path)
        size_mb = json_path.stat().st_size / 1e6
        print(f"    ✓ {name}/{json_path.name}  (depuis parquet, {size_mb:.1f} MB)")


def save_hf_dataset(ds, out_dir: Path, name: str) -> None:
    """Sauvegarde un DatasetDict en parquet + JSON par split."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, data in ds.items():
        parquet_dest = out_dir / f"{split}.parquet"
        json_dest = out_dir / f"{split}.json"

        if not parquet_dest.exists():
            data.to_parquet(str(parquet_dest))
            size_mb = parquet_dest.stat().st_size / 1e6
            print(f"    ✓ {name}/{split}.parquet  ({len(data):,} rows, {size_mb:.1f} MB)")
        else:
            print(f"    [SKIP] {name}/{split}.parquet déjà présent")

        if not json_dest.exists():
            # Prefer in-memory export from the HF split when available;
            # otherwise convert the parquet sibling.
            try:
                rows = data.to_list()
                json_dest.write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except Exception:
                parquet_to_json(parquet_dest, json_dest)
            size_mb = json_dest.stat().st_size / 1e6
            print(f"    ✓ {name}/{split}.json  ({len(data):,} rows, {size_mb:.1f} MB)")
        else:
            print(f"    [SKIP] {name}/{split}.json déjà présent")


def banner(title: str) -> None:
    line = "─" * 60
    print(f"\n{line}\n  {title}\n{line}")


# ---------------------------------------------------------------------------
# 1. RAGBench (rungalileo/ragbench)
# ---------------------------------------------------------------------------

RAGBENCH_SUBSETS = {
    "medical": ["covidqa", "pubmedqa"],
    "finance": ["finqa", "tatqa"],
}


def download_ragbench(out_dir: Path, hf_token: str | None) -> None:
    banner("1/4  RAGBench – Medical & Finance")
    kwargs = {"token": hf_token} if hf_token else {}

    for domain, subsets in RAGBENCH_SUBSETS.items():
        for subset in subsets:
            print(f"\n  Sous-ensemble : {domain}/{subset}")
            dest = out_dir / "ragbench" / domain / subset
            if dest.exists() and any(dest.glob("*.parquet")):
                print(f"    [SKIP] déjà téléchargé dans {dest}")
                ensure_json_siblings(dest, f"{domain}/{subset}")
                continue
            try:
                ds = load_dataset("rungalileo/ragbench", subset, **kwargs)
                save_hf_dataset(ds, dest, f"{domain}/{subset}")
            except Exception as exc:
                print(f"    [ERROR] {subset} : {exc}")


# ---------------------------------------------------------------------------
# 2. MultiHop-RAG (yixuantt/MultiHopRAG)
# ---------------------------------------------------------------------------

MULTIHOP_FILES = {
    "MultiHopRAG.json": "https://huggingface.co/datasets/yixuantt/MultiHopRAG/resolve/main/MultiHopRAG.json",
    "corpus.json":      "https://huggingface.co/datasets/yixuantt/MultiHopRAG/resolve/main/corpus.json",
}


def download_multihop_rag(out_dir: Path, hf_token: str | None, session: requests.Session) -> None:
    banner("2/4  MultiHop-RAG")
    dest_dir = out_dir / "multihop_rag"
    dest_dir.mkdir(parents=True, exist_ok=True)

    headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}

    for fname, url in MULTIHOP_FILES.items():
        dest = dest_dir / fname
        if dest.exists():
            print(f"  [SKIP] {fname} déjà présent ({dest.stat().st_size/1e6:.1f} MB)")
            continue
        print(f"  Téléchargement : {fname}")
        ok = download_file(url, dest, session, desc=fname)
        if ok:
            size_mb = dest.stat().st_size / 1e6
            # Vérification rapide du contenu JSON
            with open(dest) as f:
                data = json.load(f)
            n = len(data) if isinstance(data, list) else len(data.get("queries", []))
            print(f"  ✓ {fname}  ({n:,} entrées, {size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# 3. RAGTruth (ParticleMedia/RAGTruth + wandb/RAGTruth-processed)
# ---------------------------------------------------------------------------

RAGTRUTH_GH_BASE = (
    "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset"
)

RAGTRUTH_FILES = {
    "source.json":   f"{RAGTRUTH_GH_BASE}/source.json",
    "response.json": f"{RAGTRUTH_GH_BASE}/response.json",
}


def download_ragtruth(out_dir: Path, hf_token: str | None, session: requests.Session) -> None:
    banner("4/4  RAGTruth – Hallucination Corpus (ACL 2024)")
    dest_dir = out_dir / "ragtruth"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # -- Fichiers bruts depuis GitHub (annotations span-level) --
    print("  Fichiers bruts (GitHub ParticleMedia/RAGTruth) :")
    for fname, url in RAGTRUTH_FILES.items():
        dest = dest_dir / fname
        if dest.exists():
            print(f"  [SKIP] {fname} déjà présent ({dest.stat().st_size/1e6:.1f} MB)")
            continue
        print(f"  Téléchargement : {fname}")
        ok = download_file(url, dest, session, desc=fname)
        if ok:
            with open(dest) as f:
                data = json.load(f)
            n = len(data) if isinstance(data, list) else "?"
            size_mb = dest.stat().st_size / 1e6
            print(f"  ✓ {fname}  ({n:,} entrées, {size_mb:.1f} MB)")

    # -- Version HuggingFace prétraitée (wandb/RAGTruth-processed) --
    print("\n  Version HuggingFace prétraitée (wandb/RAGTruth-processed) :")
    processed_dir = dest_dir / "processed"
    if processed_dir.exists() and any(processed_dir.glob("*.parquet")):
        print("  [SKIP] déjà téléchargé dans ragtruth/processed/")
        ensure_json_siblings(processed_dir, "ragtruth/processed")
    else:
        kwargs = {"token": hf_token} if hf_token else {}
        try:
            ds = load_dataset("wandb/RAGTruth-processed", **kwargs)
            save_hf_dataset(ds, processed_dir, "ragtruth/processed")
        except Exception as exc:
            print(f"  [ERROR] wandb/RAGTruth-processed : {exc}")
            print(
                "  Si le dataset est privé/gated, génère un token HF sur "
                "https://huggingface.co/settings/tokens et passe --hf_token TOKEN"
            )


# ---------------------------------------------------------------------------
# Rapport final
# ---------------------------------------------------------------------------

def print_summary(out_dir: Path) -> None:
    banner("Résumé des téléchargements")
    total_bytes = 0
    for p in sorted(out_dir.rglob("*")):
        if p.is_file():
            sz = p.stat().st_size
            total_bytes += sz
            rel = p.relative_to(out_dir)
            print(f"  {rel!s:<65}  {sz/1e6:6.1f} MB")
    print(f"\n  Total : {total_bytes/1e6:.1f} MB  ({total_bytes/1e9:.2f} GB)")
    print(f"  Répertoire : {out_dir.resolve()}")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Télécharge les corpus RAG benchmark pour évaluation de la génération.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output_dir",
        default="./rag_benchmarks",
        help="Répertoire de destination (défaut : ./rag_benchmarks)",
    )
    parser.add_argument(
        "--hf_token",
        default=os.environ.get("HF_TOKEN"),
        help="Token HuggingFace (ou variable d'env HF_TOKEN). "
             "Requis pour les datasets gated.",
    )
    parser.add_argument(
        "--skip_ragbench",    action="store_true", help="Ne pas télécharger RAGBench"
    )
    parser.add_argument(
        "--skip_multihop",    action="store_true", help="Ne pas télécharger MultiHop-RAG"
    )
    parser.add_argument(
        "--skip_ragtruth",    action="store_true", help="Ne pas télécharger RAGTruth"
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = make_session()

    t0 = time.time()

    if not args.skip_ragbench:
        download_ragbench(out_dir, args.hf_token)

    if not args.skip_multihop:
        download_multihop_rag(out_dir, args.hf_token, session)

    if not args.skip_ragtruth:
        download_ragtruth(out_dir, args.hf_token, session)

    elapsed = time.time() - t0
    print_summary(out_dir)
    print(f"\n  Durée totale : {elapsed:.0f}s")


if __name__ == "__main__":
    main()