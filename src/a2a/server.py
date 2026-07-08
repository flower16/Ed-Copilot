"""A2A HTTP server exposing Ed-Copilot's district agents.

Endpoints
---------
GET  /.well-known/agent.json   → the A2A agent card (skills = districts)
GET  /health                   → liveness + registered districts
POST /run                      → run one question through the orchestrator

Run it:
    # from the project root, using the project venv
    USE_TF=0 .venv/Scripts/python.exe -m src.a2a.server
    # or
    uvicorn src.a2a.server:app --port 8100

Environment:
    NEBIUS_API_KEY        required (the district agents call the LLM)
    A2A_PORT              default 8100
    A2A_PUBLIC_URL        override the `url` advertised in the agent card
                          (default: http://localhost:{A2A_PORT})
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

load_dotenv()

from src.a2a.agent_card import build_agent_card
from src.district_registry import DistrictRegistry
from src.orchestrator import EdCopilotState, build_graph

app = FastAPI(title="Ed-Copilot A2A", version="0.1.0")


# --- lazy singletons so import stays cheap and the model loads once ----------

@lru_cache(maxsize=1)
def _registry() -> DistrictRegistry:
    return DistrictRegistry()


@lru_cache(maxsize=1)
def _graph():
    return build_graph(_registry())


def _public_url(request: Request) -> str:
    env = os.environ.get("A2A_PUBLIC_URL")
    if env:
        return env
    # Fall back to the URL the request came in on (scheme + host[:port]).
    return str(request.base_url).rstrip("/")


# --- schemas -----------------------------------------------------------------

class RunRequest(BaseModel):
    message: str = Field(..., description="The user's question.")
    district: str = Field(..., description="District id, e.g. 'frisco_isd_tx'.")
    persona: str = Field("parent", description="student | parent | teacher")


class SourceDoc(BaseModel):
    snippet: str
    metadata: dict


class RunResponse(BaseModel):
    response: str
    intent: str
    intent_badge: str
    district: str
    sources: List[SourceDoc]


# --- routes ------------------------------------------------------------------

@app.get("/.well-known/agent.json")
def agent_card(request: Request) -> dict:
    return build_agent_card(_registry(), _public_url(request))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "districts": _registry().all_district_ids()}


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest) -> RunResponse:
    registry = _registry()
    if registry.get(req.district) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown district '{req.district}'. "
                   f"Known: {registry.all_district_ids()}",
        )

    state: EdCopilotState = {
        "messages": [{"role": "user", "content": req.message}],
        "persona": (req.persona or "parent").lower(),
        "district": req.district,
        "intent": "",
        "context_docs": [],
        "response": "",
        "intent_badge": "",
    }
    result = _graph().invoke(state)

    sources = [
        SourceDoc(snippet=(d.page_content or "")[:400], metadata=dict(d.metadata or {}))
        for d in result.get("context_docs", [])
    ]
    return RunResponse(
        response=result.get("response", ""),
        intent=result.get("intent", ""),
        intent_badge=result.get("intent_badge", ""),
        district=req.district,
        sources=sources,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("A2A_PORT", "8100"))
    print(f"[a2a] starting Ed-Copilot A2A server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
