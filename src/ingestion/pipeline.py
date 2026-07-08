"""Shared ingestion pipeline for TX district course catalogs.

Adapted from flower16/copilot-for-families/backend/app/ingestion/pipeline.py

Flow: load seed docs → (optional) live crawl → normalize → chunk → tag → upsert into ChromaDB.

Collection naming convention: {district_id}__{doc_type}
e.g.  frisco_isd_tx__course_catalog,  plano_isd_tx__admin_policy
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

import chromadb
from langchain_huggingface import HuggingFaceEmbeddings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")

ROLE_VISIBILITY = {
    "course_catalog": ["parent", "student", "teacher", "admin"],
    "admin_policy":   ["parent", "student", "teacher", "admin"],
    "calendar":       ["parent", "student", "teacher", "admin"],
}

_embeddings: Optional[HuggingFaceEmbeddings] = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        print("[pipeline] loading HuggingFace embeddings (BAAI/bge-small-en-v1.5)...")
        _embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    return _embeddings


def _collection_name(district_id: str, doc_type: str) -> str:
    return f"{district_id}__{doc_type}"


def _chunk_id(district_id: str, doc: dict, idx: int) -> str:
    raw = f"{district_id}|{doc.get('source_url')}|{doc.get('field')}|{idx}|{doc['text']}"
    return hashlib.sha1(raw.encode()).hexdigest()[:24]


def normalize_district_id(raw: str) -> str:
    """Map team repo district IDs → Ed-Copilot district IDs.
    Team repo uses 'frisco_isd' / 'plano_isd'; we use 'frisco_isd_tx' / 'plano_isd_tx'.
    """
    mapping = {
        "frisco_isd": "frisco_isd_tx",
        "plano_isd":  "plano_isd_tx",
    }
    return mapping.get(raw, raw)


def to_chunks(docs: list[dict]) -> list[dict]:
    """Convert raw doc dicts into ChromaDB-ready chunks with metadata."""
    chunks = []
    for i, d in enumerate(docs):
        text = (d.get("text") or "").strip()
        if not text:
            continue

        district_id = normalize_district_id(d.get("district", ""))
        doc_type    = d.get("doc_type", "course_catalog")
        visible     = ROLE_VISIBILITY.get(doc_type, ["parent", "student", "teacher", "admin"])

        meta = {
            "district":      district_id,
            "doc_type":      doc_type,
            "subject":       d.get("subject", ""),
            "school_level":  d.get("school_level", ""),
            "course":        d.get("course") or "",
            "course_number": d.get("course_number", ""),
            "grade":         ",".join(str(g) for g in d.get("grade", [])),
            "field":         d.get("field", ""),
            "source_url":    d.get("source_url", ""),
            "doc_title":     d.get("doc_title", ""),
        }
        # Encode role visibility as per-role booleans for Chroma metadata filtering.
        for role in ("parent", "student", "teacher", "admin"):
            meta[f"vis_{role}"] = role in visible

        chunks.append({
            "id":       _chunk_id(district_id, d, i),
            "text":     text,
            "metadata": meta,
        })
    return chunks


def upsert_to_chroma(district_id: str, doc_type: str, chunks: list[dict]) -> int:
    """Upsert chunks into the ChromaDB collection for this district + doc_type."""
    if not chunks:
        return 0

    collection_name = _collection_name(district_id, doc_type)
    embeddings = _get_embeddings()

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    col = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    # Embed texts
    texts = [c["text"] for c in chunks]
    vectors = embeddings.embed_documents(texts)

    col.upsert(
        ids=[c["id"] for c in chunks],
        embeddings=vectors,
        documents=texts,
        metadatas=[c["metadata"] for c in chunks],
    )
    print(f"[pipeline] upserted {len(chunks)} chunks → collection '{collection_name}'")
    return len(chunks)


def ingest_docs(docs: list[dict]) -> dict[str, int]:
    """Full pipeline: docs → normalize → chunk → upsert, grouped by district + doc_type.

    Returns a dict of {collection_name: chunk_count}.
    """
    chunks = to_chunks(docs)

    # Group by district + doc_type
    groups: dict[tuple[str, str], list[dict]] = {}
    for c in chunks:
        key = (c["metadata"]["district"], c["metadata"]["doc_type"])
        groups.setdefault(key, []).append(c)

    results = {}
    for (district_id, doc_type), group in groups.items():
        n = upsert_to_chroma(district_id, doc_type, group)
        results[_collection_name(district_id, doc_type)] = n
    return results
