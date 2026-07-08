#!/usr/bin/env bash
# Replit boot script: install deps, build the vector DBs on first run, then serve.
# Referenced by .replit ("Start application" workflow + deployment run).
# NOTE: no `set -e` around ingestion — a data hiccup must never stop the UI serving.

REQS_HASH_FILE=".pythonlibs/.requirements.sha256"
CURRENT_HASH="$(sha256sum requirements.txt | awk '{print $1}')"

if [ -f "$REQS_HASH_FILE" ] && [ "$(cat "$REQS_HASH_FILE")" = "$CURRENT_HASH" ]; then
  echo "[replit] python dependencies unchanged — skipping pip install."
else
  echo "[replit] installing python dependencies..."
  pip install -q -r requirements.txt
  mkdir -p .pythonlibs
  echo "$CURRENT_HASH" > "$REQS_HASH_FILE"
fi

# chroma_db/ is gitignored (regenerable + large), so it won't exist on a fresh
# Replit import. Build all three district collections once, on first boot.
if [ ! -d "chroma_db" ]; then
  echo "[replit] first run — building vector DBs (this takes a few minutes)..."
  python src/ingestion.py                  || echo "[replit] NC Math ingest failed; continuing"
  python src/ingestion/frisco_ingestion.py || echo "[replit] Frisco ingest failed; continuing"
  python src/ingestion/plano_ingestion.py  || echo "[replit] Plano ingest failed; continuing"
else
  echo "[replit] chroma_db/ already present — skipping ingestion."
fi

echo "[replit] starting Streamlit on 0.0.0.0:5000..."
exec streamlit run app.py --server.port 5000 --server.address 0.0.0.0 --server.headless true
