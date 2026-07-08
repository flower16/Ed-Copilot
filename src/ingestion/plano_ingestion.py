"""Plano ISD course catalog ingestion.

Run:  python src/ingestion/plano_ingestion.py          # seed only (safe offline)
      python src/ingestion/plano_ingestion.py --crawl  # attempt live crawl first

Populates ChromaDB collection: plano_isd_tx__course_catalog
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, BASE_DIR)

from src.ingestion.crawlers import crawl_plano
from src.ingestion.pipeline import ingest_docs

SEED_PATH = os.path.join(BASE_DIR, "data", "seed", "collin_county.json")


def load_seed() -> list[dict]:
    with open(SEED_PATH, encoding="utf-8") as f:
        all_docs = json.load(f)["documents"]
    # Only Plano docs (team repo uses 'plano_isd'; pipeline normalizes to 'plano_isd_tx')
    return [d for d in all_docs if "plano" in d.get("district", "").lower()]


def run(crawl: bool = False) -> dict[str, int]:
    print("=== Plano ISD Ingestion ===")

    docs = load_seed()
    print(f"[ingest] Loaded {len(docs)} seed doc(s) for Plano ISD")

    if crawl:
        print("[ingest] Attempting live crawl of Plano ISD course catalog...")
        live_docs = crawl_plano(subject="math")
        if live_docs:
            docs = [d for d in docs if d.get("doc_type") != "course_catalog"]
            docs += live_docs
            print(f"[ingest] Live crawl succeeded: {len(live_docs)} doc(s) — replacing seed catalog.")
        else:
            print("[ingest] Live crawl returned no results — using seed data only.")

    print(f"[ingest] Total docs to ingest: {len(docs)}")
    results = ingest_docs(docs)

    print()
    print("=== Ingestion Complete ===")
    for collection, count in results.items():
        print(f"  {collection}: {count} chunks")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Plano ISD ingestion")
    ap.add_argument("--crawl", action="store_true",
                    help="Attempt live crawl before falling back to seed data")
    args = ap.parse_args()
    run(crawl=args.crawl)
