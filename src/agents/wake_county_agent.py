"""Wake County NC district agent.

Wraps the existing NC Math 1/2/3 retriever and WCPSS admin ChromaDB
into the DistrictAgent plugin interface.

Module-level variable ``agent`` is loaded by DistrictRegistry automatically.
"""
from __future__ import annotations

import os
from typing import List

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI

from src.agents.base_agent import DistrictAgent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
MATH_DB_DIR = os.path.join(BASE_DIR, "chroma_db")
ADMIN_DB_DIR = os.path.join(BASE_DIR, "chroma_db_admin")

STANDARD_DOMAIN_NAMES = {
    "N-RN": "The Real Number System",
    "N-Q": "Quantities",
    "N-CN": "The Complex Number System",
    "A-SSE": "Seeing Structure in Expressions",
    "A-APR": "Arithmetic with Polynomials and Rational Expressions",
    "A-CED": "Creating Equations",
    "A-REI": "Reasoning with Equations and Inequalities",
    "F-IF": "Interpreting Functions",
    "F-BF": "Building Functions",
    "F-LE": "Linear, Quadratic, and Exponential Models",
    "F-TF": "Trigonometric Functions",
    "G-CO": "Congruence",
    "G-SRT": "Similarity, Right Triangles, and Trigonometry",
    "G-C": "Circles",
    "G-GPE": "Expressing Geometric Properties with Equations",
    "G-GMD": "Geometric Measurement and Dimension",
    "G-MG": "Modeling with Geometry",
    "S-ID": "Interpreting Categorical and Quantitative Data",
    "S-CP": "Conditional Probability and the Rules of Probability",
    "S-IC": "Making Inferences and Justifying Conclusions",
    "S-MD": "Using Probability to Make Decisions",
}

PERSONA_INSTRUCTIONS = {
    "student": "Explain simply. Use examples. Be encouraging.",
    "parent": "Give practical context. What should my child focus on?",
    "teacher": "Be precise. Reference the specific standard ID. Give full detail.",
}

ADMIN_PERSONA_INSTRUCTIONS = {
    "student": "Give a brief, direct answer. Keep it simple and friendly.",
    "parent": "Summarize the key points and list any action items for the family.",
    "teacher": "Provide the full policy text and include the source link.",
}

_DISCLAIMER = (
    "_This information was scraped from public district websites. "
    "Verify at your district's official website._"
)


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=os.environ.get("NEBIUS_API_KEY", ""),
        model="meta-llama/Llama-3.3-70B-Instruct",
    )


def _describe_standard(standard_id: str) -> str:
    parts = standard_id.split(".")
    domain = parts[2] if len(parts) >= 3 else None
    name = STANDARD_DOMAIN_NAMES.get(domain)
    return f"{name} ({standard_id})" if name else standard_id


class WakeCountyAgent(DistrictAgent):
    """NC Math 1/2/3 + WCPSS admin policy agent."""

    def __init__(self):
        self._embeddings = None
        self._math_retriever = None
        self._admin_vs = None

    @property
    def district_id(self) -> str:
        return "wake_county_nc"

    @property
    def supported_intents(self) -> List[str]:
        return ["math_curriculum", "admin_policy", "college_guidance"]

    # ------------------------------------------------------------------
    # Lazy resource initialisation
    # ------------------------------------------------------------------

    def _get_embeddings(self):
        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
        return self._embeddings

    def _get_math_retriever(self):
        if self._math_retriever is None:
            vs = Chroma(
                collection_name="nc_math_standards",
                persist_directory=MATH_DB_DIR,
                embedding_function=self._get_embeddings(),
            )
            self._math_retriever = vs.as_retriever(search_kwargs={"k": 8})
        return self._math_retriever

    def _get_admin_vs(self):
        if self._admin_vs is None:
            self._admin_vs = Chroma(
                collection_name="admin_docs",
                persist_directory=ADMIN_DB_DIR,
                embedding_function=self._get_embeddings(),
            )
        return self._admin_vs

    # ------------------------------------------------------------------
    # Plugin hooks
    # ------------------------------------------------------------------

    def retrieve(self, query: str, intent: str, persona: str) -> List[Document]:
        if intent == "math_curriculum":
            return self._get_math_retriever().invoke(query)

        if intent == "admin_policy":
            if not os.path.exists(ADMIN_DB_DIR):
                return []
            try:
                return self._get_admin_vs().similarity_search(
                    query, k=5, filter={"district": self.district_id}
                )
            except Exception:
                return []

        return []

    def synthesize(
        self,
        query: str,
        docs: List[Document],
        intent: str,
        persona: str,
    ) -> str:
        llm = _get_llm()

        if intent == "math_curriculum":
            if not docs:
                return "I cannot find this in our syllabus, please ask your teacher."
            context = "\n\n".join(
                f"[{_describe_standard(d.metadata.get('standard_id', ''))}] {d.page_content}"
                for d in docs
            )
            prompt = ChatPromptTemplate.from_messages([
                ("system", (
                    "You are a Math Curriculum Expert for NC schools.\n"
                    "{persona_instruction}\n"
                    "Answer using ONLY the provided educational standards context.\n"
                    "If the context does not contain the answer, say "
                    "'I cannot find this in our syllabus, please ask your teacher.'\n\n"
                    "Whenever you reference a standard code, always use the human-friendly "
                    "domain name already given in brackets: 'Domain Name (standard code)'.\n\n"
                    "Context:\n{context}"
                )),
                ("human", "{question}"),
            ])
            return (prompt | llm | StrOutputParser()).invoke({
                "persona_instruction": PERSONA_INSTRUCTIONS.get(persona, PERSONA_INSTRUCTIONS["student"]),
                "context": context,
                "question": query,
            })

        if intent == "admin_policy":
            if not docs:
                return (
                    "I don't have specific information about that for Wake County. "
                    "Please check the WCPSS official website for the most current details.\n\n"
                    + _DISCLAIMER
                )
            context = "\n\n".join(
                f"[{d.metadata.get('label', 'document')} | {d.metadata.get('source_url', '')}]\n{d.page_content}"
                for d in docs
            )
            prompt = ChatPromptTemplate.from_messages([
                ("system", (
                    "You are a District Policy Expert for WCPSS.\n"
                    "{persona_instruction}\n"
                    "Answer using ONLY the provided district content.\n"
                    "Always end with: " + _DISCLAIMER + "\n\nContext:\n{context}"
                )),
                ("human", "{question}"),
            ])
            response = (prompt | llm | StrOutputParser()).invoke({
                "persona_instruction": ADMIN_PERSONA_INSTRUCTIONS.get(persona, ADMIN_PERSONA_INSTRUCTIONS["parent"]),
                "context": context,
                "question": query,
            })
            if _DISCLAIMER not in response:
                response = response.rstrip() + "\n\n" + _DISCLAIMER
            return response

        if intent == "college_guidance":
            return "College guidance planning is on the roadmap for Phase 2."

        return "I can help with NC school curriculum and district policies."


agent = WakeCountyAgent()
