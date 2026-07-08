"""Frisco ISD district agent — Phase 2 implementation.

Retrieves from ChromaDB collection frisco_isd_tx__course_catalog,
with groundedness scoring on every response.

Run ingestion first:
    python src/ingestion/frisco_ingestion.py
"""
from __future__ import annotations

import os
from typing import List, Optional

import chromadb
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI

from src.agents.base_agent import DistrictAgent
from src.guardrails.groundedness import score as groundedness_score, input_is_safe

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")

GROUNDEDNESS_THRESHOLD = 0.25

PERSONA_INSTRUCTIONS = {
    "student": "Explain simply. Use examples. Be encouraging. Mention prerequisites clearly.",
    "parent":  "Give practical context — what course sequence should my child follow?",
    "teacher": "Be precise. Include course numbers, prerequisites, and credit hours.",
}

_DISCLAIMER = (
    "_This information was sourced from Frisco ISD public resources. "
    "Always verify current offerings at friscoisd.org._"
)


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=os.environ.get("NEBIUS_API_KEY", ""),
        model="meta-llama/Llama-3.3-70B-Instruct",
    )


class FriscoIsdAgent(DistrictAgent):
    """Frisco ISD course catalog + admin policy agent."""

    def __init__(self):
        self._embeddings: Optional[HuggingFaceEmbeddings] = None
        self._chroma_client: Optional[chromadb.PersistentClient] = None

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def district_id(self) -> str:
        return "frisco_isd_tx"

    @property
    def supported_intents(self) -> List[str]:
        return ["course_catalog", "admin_policy"]

    # ------------------------------------------------------------------
    # Lazy initialisation
    # ------------------------------------------------------------------

    def _get_embeddings(self) -> HuggingFaceEmbeddings:
        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        return self._embeddings

    def _get_client(self) -> chromadb.PersistentClient:
        if self._chroma_client is None:
            self._chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
        return self._chroma_client

    def _query_collection(self, collection_name: str, query: str, k: int = 8) -> List[Document]:
        """Query a named ChromaDB collection directly (no LangChain wrapper)."""
        try:
            client = self._get_client()
            col = client.get_collection(name=collection_name)
            if col.count() == 0:
                return []

            embeddings = self._get_embeddings()
            query_vec = embeddings.embed_query(query)

            results = col.query(
                query_embeddings=[query_vec],
                n_results=min(k, col.count()),
                where={"district": self.district_id},
            )

            docs = []
            texts     = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas",  [[]])[0]
            for text, meta in zip(texts, metadatas):
                docs.append(Document(page_content=text, metadata=meta))
            return docs

        except Exception as exc:
            print(f"[frisco_agent] ChromaDB query failed ({collection_name}): {exc}")
            return []

    # ------------------------------------------------------------------
    # Plugin hooks
    # ------------------------------------------------------------------

    def retrieve(self, query: str, intent: str, persona: str) -> List[Document]:
        collection_map = {
            "course_catalog": f"{self.district_id}__course_catalog",
            "admin_policy":   f"{self.district_id}__admin_policy",
        }
        collection = collection_map.get(intent)
        if not collection:
            return []
        return self._query_collection(collection, query, k=8)

    def synthesize(
        self,
        query: str,
        docs: List[Document],
        intent: str,
        persona: str,
    ) -> str:
        if not docs:
            return (
                "I don't have Frisco ISD course catalog data available yet. "
                "Ingestion is pending — please run `python src/ingestion/frisco_ingestion.py`.\n\n"
                + _DISCLAIMER
            )

        context = "\n\n".join(
            f"[{d.metadata.get('course', d.metadata.get('doc_title', 'document'))} "
            f"| {d.metadata.get('source_url', '')}]\n{d.page_content}"
            for d in docs
        )

        llm = _get_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are a school assistant for Frisco ISD families in Texas.\n"
                "{persona_instruction}\n"
                "Answer using ONLY the provided Frisco ISD course catalog content below.\n"
                "Include course names, numbers, prerequisites, and credit hours when available.\n"
                "If the context does not contain the answer, say clearly: "
                "'I don't have that specific Frisco ISD information — please check friscoisd.org.'\n"
                "Always end your response with this line:\n"
                + _DISCLAIMER + "\n\n"
                "Context:\n{context}"
            )),
            ("human", "{question}"),
        ])

        response = (prompt | llm | StrOutputParser()).invoke({
            "persona_instruction": PERSONA_INSTRUCTIONS.get(persona, PERSONA_INSTRUCTIONS["parent"]),
            "context": context,
            "question": query,
        })

        # Groundedness check — warn if answer drifts from retrieved context
        g_score = groundedness_score(response, context)
        if g_score < GROUNDEDNESS_THRESHOLD and len(docs) > 0:
            print(f"[frisco_agent] low groundedness ({g_score:.2f}) — response may be hallucinated")

        if _DISCLAIMER not in response:
            response = response.rstrip() + "\n\n" + _DISCLAIMER
        return response

    # ------------------------------------------------------------------
    # Override handle() to add safety pre-check
    # ------------------------------------------------------------------

    def handle(self, state: dict) -> dict:
        query = state["messages"][-1]["content"]

        # Safety pre-check
        safe, refusal = input_is_safe(query)
        if not safe:
            return {**state, "context_docs": [], "response": refusal}

        intent  = state.get("intent", "")
        persona = state.get("persona", "student").lower()
        docs    = self.retrieve(query, intent, persona)
        response = self.synthesize(query, docs, intent, persona)
        return {**state, "context_docs": docs, "response": response}


agent = FriscoIsdAgent()
