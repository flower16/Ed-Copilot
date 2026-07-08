"""Base class for all district agents.

To add a new district:
  1. Create  config/tenants/<district-id>.yaml   (point agent_module here)
  2. Create  src/agents/<district_id>_agent.py   (subclass DistrictAgent, expose `agent`)
  Done — the DistrictRegistry auto-discovers and the orchestrator routes to it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from langchain_core.documents import Document


class DistrictAgent(ABC):
    """Plugin interface every district agent must implement.

    Lifecycle
    ---------
    1. DistrictRegistry loads the agent module listed in the tenant YAML.
    2. It reads the module-level `agent` variable (an instance of DistrictAgent).
    3. The orchestrator registers `agent.handle` as a LangGraph node named
       ``agent_<district_id>``.
    4. When a user question is routed to this district, LangGraph calls
       ``handle(state)`` — which in turn calls ``retrieve`` then ``synthesize``.

    Subclasses only need to implement ``retrieve`` and ``synthesize``.
    ``handle`` is wired for you.
    """

    # ------------------------------------------------------------------
    # Identity — must be set by each subclass
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def district_id(self) -> str:
        """Unique key matching the district_id in the tenant YAML.
        Example: 'frisco_isd_tx'
        """

    @property
    @abstractmethod
    def supported_intents(self) -> List[str]:
        """Intents this agent can answer.
        Example: ['course_catalog', 'admin_policy']
        Orchestrator falls back to out_of_scope_handler for any other intent.
        """

    # ------------------------------------------------------------------
    # Plugin hooks — implement these in each district agent
    # ------------------------------------------------------------------

    @abstractmethod
    def retrieve(self, query: str, intent: str, persona: str) -> List[Document]:
        """Fetch relevant documents for the query.

        Args:
            query:   Raw user question.
            intent:  Classified intent (e.g. 'math_curriculum', 'course_catalog').
            persona: User role — 'student' | 'parent' | 'teacher'.

        Returns:
            List of LangChain Document objects with page_content + metadata.
        """

    @abstractmethod
    def synthesize(
        self,
        query: str,
        docs: List[Document],
        intent: str,
        persona: str,
    ) -> str:
        """Generate the final answer given retrieved docs.

        Args:
            query:   Raw user question.
            docs:    Documents returned by ``retrieve``.
            intent:  Classified intent.
            persona: User role.

        Returns:
            Answer string shown directly to the user.
        """

    # ------------------------------------------------------------------
    # LangGraph node — do NOT override unless you have a specific reason
    # ------------------------------------------------------------------

    def handle(self, state: dict) -> dict:
        """LangGraph node function.  Calls retrieve → synthesize and merges
        the results back into the shared state.

        Override only if you need custom state keys beyond context_docs /
        response (e.g. citations, confidence score).
        """
        query = state["messages"][-1]["content"]
        intent = state.get("intent", "")
        persona = state.get("persona", "student").lower()

        docs = self.retrieve(query, intent, persona)
        response = self.synthesize(query, docs, intent, persona)

        return {
            **state,
            "context_docs": docs,
            "response": response,
        }
