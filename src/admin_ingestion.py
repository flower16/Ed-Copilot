"""Record ingestion runs to data/ingestion_log.json for the Knowledge Freshness widget.

Usage:
  python src/admin_ingestion.py             # run all district ingestion pipelines, then log the run
  python src/admin_ingestion.py --log-only  # skip ingestion; count existing Chroma collections and log

The log format matches what app.py's sidebar expects:
[
  {
    "run_at": "<ISO timestamp>",
    "total_chunks_indexed": <int>,
    "districts": {
      "<district_id>": {"name": "<display name>", "chunks_indexed": <int>},
      ...
    }
  },
  ...
]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import chromadb
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
ADMIN_CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db_admin")
LOG_PATH = os.path.join(BASE_DIR, "data", "ingestion_log.json")
TENANTS_GLOB = os.path.join(BASE_DIR, "config", "tenants", "*.yaml")

INGEST_SCRIPTS = [
    "src/ingestion.py",
    "src/ingestion/frisco_ingestion.py",
    "src/ingestion/plano_ingestion.py",
]


def district_names() -> dict:
    """district_id -> display name, read from tenant configs."""
    names = {}
    for path in sorted(glob.glob(TENANTS_GLOB)):
        try:
            with open(path, "r") as f:
                cfg = yaml.safe_load(f) or {}
            did = cfg.get("district_id")
            if did:
                names[did] = cfg.get("name", did)
        except Exception as exc:
            print(f"[admin_ingestion] could not read {path}: {exc}")
    return names


def count_chunks_by_district() -> dict:
    """district_id -> total chunk count across its Chroma collections."""
    counts: dict = {}

    def add(district_id: str, n: int):
        counts[district_id] = counts.get(district_id, 0) + n

    if os.path.isdir(CHROMA_DIR):
        try:
            client = chromadb.PersistentClient(path=CHROMA_DIR)
            for col in client.list_collections():
                n = col.count()
                if col.name == "nc_math_standards":
                    add("wake_county_nc", n)
                elif "__" in col.name:
                    add(col.name.split("__")[0], n)
                else:
                    print(f"[admin_ingestion] skipping unrecognized collection: {col.name}")
        except Exception as exc:
            print(f"[admin_ingestion] could not read {CHROMA_DIR}: {exc}")

    if os.path.isdir(ADMIN_CHROMA_DIR):
        try:
            client = chromadb.PersistentClient(path=ADMIN_CHROMA_DIR)
            for col in client.list_collections():
                if col.name == "admin_docs":
                    add("wake_county_nc", col.count())
        except Exception as exc:
            print(f"[admin_ingestion] could not read {ADMIN_CHROMA_DIR}: {exc}")

    return counts


def record_run() -> dict:
    """Append a run entry to the ingestion log based on current Chroma contents."""
    names = district_names()
    counts = count_chunks_by_district()

    districts = {}
    for did, n in sorted(counts.items()):
        districts[did] = {"name": names.get(did, did), "chunks_indexed": n}

    entry = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_chunks_indexed": sum(counts.values()),
        "districts": districts,
    }

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    log = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r") as f:
                log = json.load(f)
            if not isinstance(log, list):
                log = []
        except Exception:
            log = []
    log.append(entry)
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)

    print(f"[admin_ingestion] logged run: {entry['total_chunks_indexed']} total chunks "
          f"across {len(districts)} district(s) -> {LOG_PATH}")
    return entry


def run_ingestion_scripts():
    for script in INGEST_SCRIPTS:
        path = os.path.join(BASE_DIR, script)
        if not os.path.exists(path):
            print(f"[admin_ingestion] script not found, skipping: {script}")
            continue
        print(f"[admin_ingestion] running {script} ...")
        result = subprocess.run([sys.executable, path], cwd=BASE_DIR)
        if result.returncode != 0:
            print(f"[admin_ingestion] {script} failed (exit {result.returncode}); continuing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-only", action="store_true",
                        help="Skip ingestion; just count existing collections and record a log entry.")
    args = parser.parse_args()

    if not args.log_only:
        run_ingestion_scripts()

    record_run()


if __name__ == "__main__":
    main()
