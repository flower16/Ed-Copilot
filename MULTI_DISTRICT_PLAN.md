# Ed-Copilot Multi-District Architecture Plan

> **Status:** Phase 1 complete — plugin hook system live  
> **Canonical repo:** `satsraja12-eng/Ed-Copilot`  
> **Team repo:** `flower16/copilot-for-families` (Frisco/Plano ISD ingestion + retrieval already built)  
> **Goal:** Multi-district K-12 family assistant where each school district is a self-contained plugin agent, and the master orchestrator routes conversations automatically.

---

## Table of Contents

1. [Current State](#1-current-state)
2. [Plugin Hook Architecture](#2-plugin-hook-architecture)
3. [How to Add a New District (Step-by-Step)](#3-how-to-add-a-new-district-step-by-step)
4. [Building Blocks](#4-building-blocks)
5. [Repo Merge Strategy](#5-repo-merge-strategy)
6. [Phased Delivery](#6-phased-delivery)
7. [File Structure](#7-file-structure)
8. [Key Decisions](#8-key-decisions)
9. [Open Questions for Team](#9-open-questions-for-team)
10. [User Manual](#10-user-manual)
11. [References](#11-references)

---

## 1. Current State

### Ed-Copilot (this repo)

| Component | Status |
|---|---|
| **Plugin hook system** | ✅ Live — `DistrictAgent` base class + `DistrictRegistry` auto-discovery |
| **Orchestrator** | ✅ Registry-driven — district nodes registered automatically from YAML |
| **Wake County NC agent** | ✅ NC Math 1/2/3 hybrid retriever + WCPSS admin policy |
| **Frisco ISD agent** | ✅ **Live** — real ChromaDB retrieval, groundedness scoring, safety guard (7 chunks ingested) |
| **Plano ISD agent** | ✅ **Live** — real ChromaDB retrieval, groundedness scoring, safety guard (5 chunks ingested) |
| **Tenant YAML configs** | ✅ All 3 districts configured under `config/tenants/` |
| **LangSmith tracing** | ✅ Full trace on every conversation (`Ed-Copilot` project) |
| **Evaluation suite** | ✅ 15 gold-standard Q&A pairs, LLM-as-judge (Faithfulness + Relevance) |
| **District guardrail** | ✅ NC Math content blocked for TX districts |
| **Ingestion pipeline** | ✅ `src/ingestion/pipeline.py` — normalize → chunk → tag → upsert into ChromaDB |
| **TX crawlers** | ✅ `src/ingestion/crawlers.py` — Playwright + httpx, best-effort fallback to seed |
| **Groundedness guardrail** | ✅ `src/guardrails/groundedness.py` — lexical overlap scorer + PII safety pre-check |
| **Seed course data** | ✅ `data/seed/collin_county.json` — 12 Frisco + Plano HS math courses |

### Team Repo (`flower16/copilot-for-families`)

| Component | Status |
|---|---|
| **Frisco ISD course catalog ingestion** | ✅ Playwright + Apptegy API crawler |
| **Plano ISD course catalog ingestion** | ✅ httpx + PISD web scraper |
| **Ingestion pipeline** | ✅ Chunk, tag, role-visibility metadata, upsert |
| **Metadata-first retriever** | ✅ district + doc_type + role filter |
| **ChromaDB vectorstore** | ✅ Tenant-scoped collections |
| **Tenant YAML configs** | ✅ `configs/tenants/collin-county-tx.yaml` |

### Gap Analysis (remaining work)

| Capability | Status | Phase |
|---|---|---|
| Frisco + Plano ingestion (port from team repo) | ✅ Complete | Phase 2 |
| Groundedness verifier + retry loop | ✅ Complete | Phase 2 |
| User district registration (SQLite) | ⬜ Pending | Phase 3 |
| Auto-routing from registered profile | ⬜ Pending | Phase 3 |
| Live crawl refresh (scheduled nightly/weekly) | ⬜ Pending | Phase 3 |
| Citations in responses | ⬜ Pending | Phase 5 |
| Frisco/Plano LangSmith eval questions | ⬜ Pending | Phase 4 |

---

## 2. Plugin Hook Architecture

### Design Principle

Adding a new district requires **exactly 2 files**. Zero changes to the orchestrator, app, or any other core code.

```
config/tenants/<district-id>.yaml     ← declare the district
src/agents/<district_id>_agent.py     ← implement the agent
```

`DistrictRegistry` scans `config/tenants/` on startup, imports each agent module, and registers the agent with the master orchestrator automatically.

---

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Streamlit Frontend (app.py)                   │
│                                                                       │
│  Sidebar: Persona (Student / Parent / Teacher)                        │
│           District  (registry-driven dropdown — auto-updates)         │
│                              │                                        │
│                    user_context {district, persona}                   │
└──────────────────────────────┼────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              DistrictRegistry  (src/district_registry.py)            │
│                                                                       │
│  On startup: scans config/tenants/*.yaml                              │
│              imports agent_module from each YAML                      │
│              reads module-level `agent` variable                      │
│              registers {district_id: DistrictAgent instance}          │
│                                                                       │
│  Registered: frisco_isd_tx, plano_isd_tx, wake_county_nc             │
└─────────────────────────────┬───────────────────────────────────────┘
                               │  builds graph
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Master Orchestrator  (src/orchestrator.py)              │
│                                                                       │
│   [classify_intent]                                                   │
│         │                                                             │
│         ├─ intent + district → agent_wake_county_nc ──┐              │
│         ├─ intent + district → agent_frisco_isd_tx  ──┤→ response    │
│         ├─ intent + district → agent_plano_isd_tx   ──┘              │
│         └─ out_of_scope     → out_of_scope_handler                   │
│                                                                       │
│   ← Graph nodes registered per district automatically by registry    │
└─────────────────────────────────────────────────────────────────────┘
                    │                │                │
       ┌────────────▼───┐  ┌─────────▼──┐  ┌────────▼──────┐
       │ WakeCountyAgent│  │FriscoAgent │  │ PlanoAgent    │
       │                │  │            │  │               │
       │ retrieve()     │  │ retrieve() │  │ retrieve()    │
       │ synthesize()   │  │ synthesize │  │ synthesize()  │
       │ handle() ✓     │  │ handle() ✓ │  │ handle() ✓    │
       │                │  │            │  │               │
       │ NC Math 1/2/3  │  │ Frisco     │  │ Plano ISD     │
       │ WCPSS admin    │  │ course     │  │ course        │
       │                │  │ catalog    │  │ catalog       │
       └────────────────┘  └────────────┘  └───────────────┘
```

---

### Class Contract (`src/agents/base_agent.py`)

```python
class DistrictAgent(ABC):

    @property
    @abstractmethod
    def district_id(self) -> str:
        """Unique key matching YAML district_id. e.g. 'frisco_isd_tx'"""

    @property
    @abstractmethod
    def supported_intents(self) -> List[str]:
        """Intents this agent handles. e.g. ['course_catalog', 'admin_policy']
        Orchestrator routes to out_of_scope for any other intent."""

    @abstractmethod
    def retrieve(self, query: str, intent: str, persona: str) -> List[Document]:
        """Fetch relevant documents from ChromaDB (or any source)."""

    @abstractmethod
    def synthesize(self, query: str, docs: List[Document],
                   intent: str, persona: str) -> str:
        """Generate the answer grounded in retrieved docs."""

    def handle(self, state: dict) -> dict:
        """LangGraph node — wired for you. Do not override unless you
        need custom state keys (e.g. citations, confidence score)."""
        docs = self.retrieve(state["messages"][-1]["content"],
                             state.get("intent"), state.get("persona"))
        response = self.synthesize(...)
        return {**state, "context_docs": docs, "response": response}
```

---

### Auto-Discovery Flow (`src/district_registry.py`)

```
Startup
  │
  ├── glob("config/tenants/*.yaml")
  │     ├── wake-county-nc.yaml   → agent_module: src.agents.wake_county_agent
  │     ├── frisco-isd-tx.yaml    → agent_module: src.agents.frisco_isd_tx_agent
  │     └── plano-isd-tx.yaml     → agent_module: src.agents.plano_isd_tx_agent
  │
  ├── importlib.import_module(agent_module)
  │     └── reads module-level variable:  agent = <DistrictAgent subclass>()
  │
  └── registry._agents = {
        "wake_county_nc": WakeCountyAgent(),
        "frisco_isd_tx":  FriscoIsdAgent(),
        "plano_isd_tx":   PlanoIsdAgent(),
      }

Graph build (orchestrator)
  │
  ├── for district_id in registry.all_district_ids():
  │     graph.add_node(f"agent_{district_id}", agent.handle)
  │
  └── conditional_edges route to correct f"agent_{district_id}" by state.district
```

---

### Orchestrator Routing (zero hardcoding)

```python
def route_after_classify(state) -> str:
    intent   = state.get("intent", "out_of_scope")
    district = state.get("district", "")

    if intent == "out_of_scope":
        return "out_of_scope_handler"

    agent = registry.get(district)
    if agent and intent in agent.supported_intents:
        return f"agent_{district}"       # e.g. "agent_frisco_isd_tx"

    return "out_of_scope_handler"
```

When a new district is registered, its node `agent_<district_id>` appears in the routing map automatically — no `if/elif` chain to maintain.

---

## 3. How to Add a New District (Step-by-Step)

Example: adding **Allen ISD, TX**.

### Step 1 — Create the tenant YAML

**`config/tenants/allen-isd-tx.yaml`**

```yaml
district_id: allen_isd_tx
name: Allen ISD
state: TX
county: Collin
agent_module: src.agents.allen_isd_tx_agent   # ← points to your Python file
intents:
  - course_catalog
  - admin_policy
retrieval:
  k: 8
  rerank_n: 4
  min_score: 0.35
sources:
  course_catalog:
    type: web
    url: "https://www.allenisd.org/academics/course-catalog"
    crawler: httpx
  admin_policy:
    type: pdf
    path: data/allen/
chroma:
  collection_prefix: allen_isd_tx
```

---

### Step 2 — Create the agent module

**`src/agents/allen_isd_tx_agent.py`**

```python
from src.agents.base_agent import DistrictAgent
from langchain_core.documents import Document
from typing import List

class AllenIsdAgent(DistrictAgent):

    @property
    def district_id(self) -> str:
        return "allen_isd_tx"

    @property
    def supported_intents(self) -> List[str]:
        return ["course_catalog", "admin_policy"]

    def retrieve(self, query: str, intent: str, persona: str) -> List[Document]:
        # Connect to ChromaDB collection allen_isd_tx__course_catalog
        # (run ingestion first)
        vs = self._get_vectorstore(intent)
        return vs.similarity_search(query, k=8,
               filter={"district": "allen_isd_tx", "doc_type": intent})

    def synthesize(self, query: str, docs: List[Document],
                   intent: str, persona: str) -> str:
        # Build context, call LLM, return answer string
        ...

# Module-level variable — DistrictRegistry reads this automatically
agent = AllenIsdAgent()
```

---

### Step 3 — Ingest district content

```bash
# Run the ingestion script for Allen ISD
python src/ingestion/allen_ingestion.py
# Creates ChromaDB collection: allen_isd_tx__course_catalog
```

---

### Step 4 — Start the app

```bash
streamlit run app.py --server.port 5000
```

**That's it.** On startup you will see:

```
[registry] Loaded agent for district: allen_isd_tx  (Allen ISD)
```

The district automatically appears in the sidebar dropdown. The orchestrator routes to it. No other changes needed.

---

### What NOT to Change

| File | Change needed? |
|---|---|
| `src/orchestrator.py` | ❌ No |
| `app.py` | ❌ No |
| `src/district_registry.py` | ❌ No |
| `src/agents/base_agent.py` | ❌ No |
| Any existing agent file | ❌ No |

---

## 4. Building Blocks

### 4.1 Tenant Config (YAML per district)

Three district configs are live under `config/tenants/`:

**`config/tenants/wake-county-nc.yaml`**
```yaml
district_id: wake_county_nc
name: Wake County NC (WCPSS)
state: NC
county: Wake
agent_module: src.agents.wake_county_agent
intents:
  - math_curriculum
  - admin_policy
  - college_guidance
retrieval:
  k: 8
  rerank_n: 4
  min_score: 0.35
chroma:
  math_db_dir: chroma_db
  admin_db_dir: chroma_db_admin
```

**`config/tenants/frisco-isd-tx.yaml`**
```yaml
district_id: frisco_isd_tx
name: Frisco ISD
state: TX
county: Collin
agent_module: src.agents.frisco_isd_tx_agent
intents:
  - course_catalog
  - admin_policy
retrieval:
  k: 8
  rerank_n: 4
  min_score: 0.35
sources:
  course_catalog:
    type: apptegy_api
    url: "https://www.friscoisd.org/academics/course-catalog"
    crawler: playwright
chroma:
  collection_prefix: frisco_isd_tx
```

**`config/tenants/plano-isd-tx.yaml`**
```yaml
district_id: plano_isd_tx
name: Plano ISD
state: TX
county: Collin
agent_module: src.agents.plano_isd_tx_agent
intents:
  - course_catalog
  - admin_policy
retrieval:
  k: 8
  rerank_n: 4
  min_score: 0.35
sources:
  course_catalog:
    type: web
    url: "https://www.pisd.edu/students-families-a6/eschool/catalog/mathematics"
    crawler: httpx
chroma:
  collection_prefix: plano_isd_tx
```

---

### 4.2 ChromaDB Collection Strategy

Named collections per district + doc_type. Collection naming: `{district_id}__{doc_type}`

```
chroma_db/                          (single persist directory)
  nc_math_standards                 ← existing NC Math 1/2/3 chunks (1,760 chunks)
  admin_docs                        ← WCPSS calendars, attendance, AIG (filtered by district metadata)
  frisco_isd_tx__course_catalog     ← Frisco course catalog (pending Phase 2 ingestion)
  frisco_isd_tx__admin_policy       ← Frisco handbook PDFs (pending Phase 2 ingestion)
  plano_isd_tx__course_catalog      ← Plano course catalog (pending Phase 2 ingestion)
  plano_isd_tx__admin_policy        ← Plano handbook PDFs (pending Phase 2 ingestion)
```

Benefits:
- **Zero cross-district leakage** — each district's data is in a separate collection
- **Independent re-ingestion** — refresh one district without touching others
- **Easy to extend** — new doc_type = new collection, no schema migration

---

### 4.3 Agent Communication Mechanism

All agents use **LangGraph shared state** — the recommended mechanism for single-deployment multi-district setups.

```
EdCopilotState (TypedDict)
  messages, persona, district, intent, intent_badge, context_docs, response
       │
       ▼
 classify_intent()     reads → messages, district
                       writes → intent, intent_badge
       │
       ▼
 agent_<district_id>() reads → messages, intent, persona
  (DistrictAgent.handle)       calls retrieve() + synthesize()
                       writes → context_docs, response
```

**A2A (Agent-to-Agent) Protocol** is available for future production scale-out when each district needs physical isolation (separate deployments). Each agent would become a standalone service exposing `/.well-known/agent.json` and a `/run` endpoint. Migration path: extract each `DistrictAgent` subclass → separate Replit app → wire master orchestrator via HTTP POST.

| Mechanism | When to use |
|---|---|
| LangGraph shared state (current) | Single-app POC/pilot — full LangSmith tracing, zero network overhead |
| A2A single-app multi-route | Pilot with real users — clean boundaries, still one deployment |
| A2A separate apps | Production — true district isolation, independent release cycles |

---

### 4.4 District Registration (Phase 3)

**First-visit flow (planned):**
```
Page loads
  │
  ▼
session_state["user_profile"] exists? ──No──► registration form (district + role)
  │ Yes                                              │
  ▼                                                  ▼
Load from SQLite ◄──────────────────── Save to SQLite
  │
  ▼
Normal chat (district shown in sidebar, editable anytime)
```

**SQLite schema (no external DB needed):**
```sql
CREATE TABLE user_profiles (
    session_id    TEXT PRIMARY KEY,
    district      TEXT NOT NULL,   -- wake_county_nc | frisco_isd_tx | plano_isd_tx
    role          TEXT NOT NULL,   -- student | parent | teacher
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP
);
```

---

## 5. Repo Merge Strategy

### What to adopt from `flower16/copilot-for-families`

| Component | Source | Destination | Status |
|---|---|---|---|
| Tenant YAML configs | `configs/tenants/` | `config/tenants/` | ✅ Done (extended with NC) |
| Frisco ingestion | `backend/app/ingestion/` | `src/ingestion/frisco_ingestion.py` | ⬜ Phase 2 |
| Plano ingestion | `backend/app/ingestion/` | `src/ingestion/plano_ingestion.py` | ⬜ Phase 2 |
| Metadata-first retriever | `backend/app/rag/retriever.py` | `src/rag/retriever.py` | ⬜ Phase 2 |
| Groundedness verifier | `backend/app/guardrails/groundedness.py` | `src/guardrails/groundedness.py` | ⬜ Phase 2 |
| Citation builder | `backend/app/rag/citations.py` | `src/rag/citations.py` | ⬜ Phase 5 |
| Personas | `backend/app/graph/personas.py` | Merge with `PERSONA_INSTRUCTIONS` | ⬜ Phase 5 |

### What we keep from Ed-Copilot

| Component | Reason |
|---|---|
| Hybrid retriever (BM25 + CrossEncoder reranking) | Better quality for NC Math standards |
| LangSmith evaluation suite | Already working — extend with TX districts |
| NC Math standard domain-name mapping | Unique feature — keep and extend |
| `chroma_db/` NC Math chunks (1,760 chunks) | Already ingested |
| Plugin hook architecture | New — district agents as first-class plugins |

### What we skip (for now)

| Component | Reason |
|---|---|
| `auth/security.py` (JWT) | Too much infra for POC — SQLite is sufficient |
| Docker / `docker-compose.yml` | Replit handles deployment |
| `backend/app/main.py` (FastAPI) | Staying with Streamlit |

---

## 6. Phased Delivery

### Phase 1 — Plugin Hook System + Tenant Config ✅ Complete

- [x] Create `config/tenants/` with 3 district YAML files
- [x] Create `src/agents/base_agent.py` — `DistrictAgent` abstract base class
- [x] Create `src/district_registry.py` — auto-discovery from YAML
- [x] Refactor `src/orchestrator.py` — registry-driven node registration, zero hardcoding
- [x] Create `src/agents/wake_county_agent.py` — wraps existing NC Math + WCPSS admin
- [x] Create `src/agents/frisco_isd_tx_agent.py` — stub with hooks wired
- [x] Create `src/agents/plano_isd_tx_agent.py` — stub with hooks wired
- [x] Update `app.py` — uses `DistrictRegistry`, district dropdown is registry-driven
- [x] Update `tests/langsmith_eval.py` — uses `DistrictRegistry`
- [x] Smoke test: all 3 districts load, graph nodes registered, Wake County still answers correctly

### Phase 2 — Frisco & Plano Agents: Integrate from Team Repo ✅ Complete

> ✅ **Already built in `flower16/copilot-for-families`** — integration only.

| Already done in team repo | Where |
|---|---|
| Frisco ISD course catalog crawler (Playwright + Apptegy API) | `backend/app/ingestion/crawlers.py` |
| Plano ISD course catalog crawler (httpx + PISD web) | `backend/app/ingestion/crawlers.py` |
| Ingestion pipeline (chunk, tag, role-visibility, upsert) | `backend/app/ingestion/pipeline.py` |
| Metadata-first retriever (district + doc_type + role filter) | `backend/app/rag/retriever.py` |
| ChromaDB vectorstore (tenant-scoped collections) | `backend/app/rag/vectorstore.py` |

**Integration tasks:**
- [x] Port `crawlers.py` from team repo → `src/ingestion/crawlers.py` (Playwright + httpx, best-effort)
- [x] Port ingestion pipeline → `src/ingestion/pipeline.py` (chunk, tag, role-visibility, upsert)
- [x] Port groundedness verifier → `src/guardrails/groundedness.py` (lexical overlap scorer + safety guard)
- [x] Adapt to Ed-Copilot collection naming convention (`{district}__{doc_type}`)
- [x] Create `src/ingestion/frisco_ingestion.py` — seed + optional live crawl
- [x] Create `src/ingestion/plano_ingestion.py` — seed + optional live crawl
- [x] Run Frisco ingestion → `frisco_isd_tx__course_catalog`: **7 chunks** ✅
- [x] Run Plano ingestion → `plano_isd_tx__course_catalog`: **5 chunks** ✅
- [x] Update `FriscoIsdAgent` with real ChromaDB retrieval + groundedness scoring
- [x] Update `PlanoIsdAgent` with real ChromaDB retrieval + groundedness scoring
- [x] Smoke test: Frisco retrieves 7 docs for AP Calculus query ✅, Plano retrieves 5 docs ✅

**ChromaDB state after Phase 2:**
```
chroma_db/
  langchain                       ← NC Math 1/2/3 (1,158 chunks)     ✅ Wake County
  frisco_isd_tx__course_catalog   ← Frisco course catalog (7 chunks)  ✅ Frisco ISD
  plano_isd_tx__course_catalog    ← Plano course catalog (5 chunks)   ✅ Plano ISD
  frisco_isd_tx__admin_policy     ← (0 chunks — admin PDFs pending)
  plano_isd_tx__admin_policy      ← (0 chunks — admin PDFs pending)
chroma_db_admin/
  admin_docs                      ← WCPSS admin policy (1,760 chunks) ✅ Wake County
```

### Phase 3 — Registration + Profile Auto-Routing (1–2 days)

- [ ] Build `src/user_registry.py` with SQLite backend (session_id → district + role)
- [ ] Add registration screen to `app.py` (shown on first visit only)
- [ ] Auto-route from registered profile — remove manual district dropdown
- [ ] Allow users to update district from sidebar
- [ ] End-to-end test across all 3 districts with registered profiles

### Phase 4 — Evaluation Extension (1 day)

- [ ] Add Frisco + Plano questions to LangSmith dataset (`tests/langsmith_eval.py`)
- [ ] Add `retrieval_hit` evaluator for course catalog questions
- [ ] Run baseline experiment for all 3 district agents and compare scores

### Phase 5 — Polish (1 day)

- [ ] Add citation display in Streamlit (port team repo's `rag/citations.py`)
- [ ] Update architecture diagram (`pages/architecture.py`)
- [ ] Update README with new setup + ingestion steps

---

## 7. File Structure

```
ed-copilot/
├── app.py                              ← Updated: uses DistrictRegistry, registry-driven dropdown
├── config/
│   └── tenants/
│       ├── wake-county-nc.yaml         ← ✅ Live
│       ├── frisco-isd-tx.yaml          ← ✅ Live
│       └── plano-isd-tx.yaml           ← ✅ Live
│       └── <new-district>.yaml         ← DROP HERE to add a district
├── src/
│   ├── orchestrator.py                 ← ✅ Registry-driven, zero per-district hardcoding
│   ├── district_registry.py            ← ✅ Auto-discovers agents from config/tenants/
│   ├── agents/
│   │   ├── base_agent.py               ← ✅ DistrictAgent ABC — the plugin contract
│   │   ├── wake_county_agent.py        ← ✅ NC Math + WCPSS admin, fully functional
│   │   ├── frisco_isd_tx_agent.py      ← ✅ Hooks wired, awaiting ingestion (Phase 2)
│   │   ├── plano_isd_tx_agent.py       ← ✅ Hooks wired, awaiting ingestion (Phase 2)
│   │   └── <new>_agent.py              ← DROP HERE to implement a new agent
│   ├── retrieval.py                    ← NC Math hybrid retriever (BM25 + CrossEncoder)
│   ├── ingestion.py                    ← NC Math ingestion
│   ├── admin_ingestion.py              ← WCPSS admin ingestion
│   ├── ingestion/
│   │   ├── frisco_ingestion.py         ← Phase 2: port from team repo
│   │   └── plano_ingestion.py          ← Phase 2: port from team repo
│   ├── guardrails/
│   │   └── groundedness.py             ← Phase 2: port from team repo
│   └── rag/
│       └── citations.py                ← Phase 5: port from team repo
├── chroma_db/                          ← NC Math 1/2/3 (1,760 chunks)
├── chroma_db_admin/                    ← WCPSS admin policy
├── pages/
│   └── architecture.py                 ← System architecture diagram (Streamlit page)
├── tests/
│   ├── langsmith_eval.py               ← ✅ Updated: uses DistrictRegistry
│   ├── evaluation.py                   ← Offline evaluation
│   └── test_admin_specialist.py        ← Unit tests for admin isolation + disclaimer
├── data/
│   ├── math/                           ← NC Math PDFs
│   ├── frisco/                         ← Frisco admin PDFs (Phase 2)
│   └── plano/                          ← Plano admin PDFs (Phase 2)
└── MULTI_DISTRICT_PLAN.md              ← This file
```

---

## 8. Key Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | **Agent communication** | LangGraph shared state | Single-app POC — full LangSmith tracing, zero network overhead |
| 2 | **District extensibility** | Plugin hook (YAML + Python file) | Zero orchestrator changes to add a district |
| 3 | **Registration persistence** | SQLite (Phase 3) | Survives page refresh, no external DB needed |
| 4 | **Single vs. multi-deployment** | Single Replit app | Simple ops; A2A migration path available when needed |
| 5 | **ChromaDB layout** | Named collections `{district}__{doc_type}` | Clean isolation, independent re-ingestion |
| 6 | **Auth** | Skip JWT for now | SQLite session profiles sufficient for POC |
| 7 | **Groundedness threshold** | 0.6 | Team repo default — proven on Frisco/Plano |

---

## 9. Open Questions for Team

1. **Frisco/Plano ingestion credentials**: Is the Apptegy API URL in the team repo still live? Does it require auth?
2. **Admin PDF location**: Where are the most current Frisco/Plano handbook PDFs?
3. **Canonical merged repo**: `satsraja12-eng/Ed-Copilot` or a new shared repo?
4. **LangSmith project**: One shared `Ed-Copilot` project or separate projects per district?
5. **Gold-standard answers**: Who on the team can write/validate Frisco/Plano Q&A pairs for the eval dataset?
6. **Deployment target**: Replit (current) stays or Docker + cloud after team merge?

---

## 10. User Manual

### Overview

Ed-Copilot is a school assistant for K-12 families. It answers questions about math curriculum, district policies, and course planning — grounded strictly in official district content.

---

### Getting Started

**Step 1 — Open the app**

Navigate to the Ed-Copilot URL in your browser. The app loads in seconds.

**Step 2 — Choose who you are (Sidebar → "Who are you?")**

| Option | Best for |
|---|---|
| 🧑‍🎓 Student | Simple explanations, examples, encouragement |
| 👨‍👩‍👧 Parent | Practical summaries, action items, key dates |
| 👩‍🏫 Teacher | Full policy text, standard codes, source links |

**Step 3 — Choose your district (Sidebar → "District")**

| District | What it covers |
|---|---|
| Wake County NC | NC Math 1/2/3 curriculum standards + WCPSS admin policies |
| Frisco ISD | Frisco ISD course catalog + admin policies *(ingestion Phase 2)* |
| Plano ISD | Plano ISD course catalog + admin policies *(ingestion Phase 2)* |

**Step 4 — Ask your question**

Type in the chat box at the bottom. Press Enter or click Send.

---

### What You Can Ask

#### Wake County NC

**Math Curriculum (NC Math 1, 2, 3)**
```
What topics are covered in NC Math 1?
Explain how to solve a multi-step linear equation step by step.
What does standard NC.M2.G-SRT.6 mean in plain English?
How do I prepare for NC Math 3? Give me a week-by-week study plan.
What is the difference between NC Math 2 and NC Math 3?
```

**District Policy (WCPSS)**
```
When is spring break for Wake County schools?
What is the WCPSS attendance policy?
How does the AIG (Advanced Academics) program work?
What are the grading policies for middle school?
When is the last day of school?
```

**College & Course Planning**
```
What math courses should I take to prepare for engineering?
What are the prerequisites for AP Calculus?
How does taking NC Math 1 in 7th grade affect my high school plan?
```

#### Frisco ISD / Plano ISD *(available after Phase 2 ingestion)*

```
What math courses does Frisco ISD offer for 9th graders?
What are the prerequisites for AP Statistics at Frisco ISD?
What is Plano ISD's course sequence from Algebra 1 to Calculus?
Does Plano ISD offer IB math courses?
```

---

### Understanding the Response

Every response shows:

| Element | Meaning |
|---|---|
| **Intent badge** (top of response) | 📐 Math Curriculum / 🏫 District Policy / 📚 Course Catalog |
| **Answer text** | Grounded strictly in official district content |
| **"View Retrieved Sources"** (expandable) | Exact chunks retrieved from ChromaDB with source URLs |
| **Disclaimer** (admin responses) | Reminder to verify at the official district website |

---

### Tips for Best Results

| Tip | Example |
|---|---|
| Be specific about the course | "NC Math 2" not just "math" |
| Include the grade or level | "8th grade" or "high school" |
| Ask one question at a time | Clearer answers, better source retrieval |
| For study plans, say so explicitly | "Give me a week-by-week plan for NC Math 1" |
| For policy, name the topic | "attendance policy" not "school rules" |

---

### What Ed-Copilot Will Not Answer

Ed-Copilot stays within school-related topics. It will politely decline:

- Personal advice unrelated to school
- Questions about other states' curricula when a TX district is selected
- Opinions, predictions, or anything not in the official district content

If the answer isn't in the district's content, it will say so clearly — and point you to the official website — rather than guessing.

---

### Troubleshooting

| Issue | What to do |
|---|---|
| "I cannot find this in our syllabus" | Try rephrasing — use the standard code or topic name |
| No sources shown | The question may have matched the LLM knowledge directly, not ChromaDB |
| Wrong district answering | Check the District dropdown in the sidebar |
| Frisco/Plano shows "not yet ingested" | Phase 2 ingestion is pending — Wake County NC is fully functional |
| Slow response | The LLM inference on first load takes ~5 seconds; subsequent turns are faster |

---

### For Developers — Adding a District in 4 Steps

See [Section 3 — How to Add a New District](#3-how-to-add-a-new-district-step-by-step) for the full walkthrough.

**Quick summary:**
1. `config/tenants/<district>.yaml` — declare district + point to agent module
2. `src/agents/<district>_agent.py` — implement `retrieve()` + `synthesize()`, export `agent = YourAgent()`
3. Run ingestion to populate ChromaDB
4. Start the app — district appears automatically

No changes to `orchestrator.py`, `app.py`, or `district_registry.py`.

---

## 11. References

- **Ed-Copilot repo**: https://github.com/satsraja12-eng/Ed-Copilot
- **Team repo**: https://github.com/flower16/copilot-for-families
- **LangSmith project**: https://smith.langchain.com (project: `Ed-Copilot`)
- **LangGraph docs**: https://langchain-ai.github.io/langgraph/
- **Google A2A Protocol**: https://google.github.io/A2A/
- **Deployed app**: Published via Replit
