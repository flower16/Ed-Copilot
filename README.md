# NC Math 1, 2, & 3 Hybrid RAG Tutor

A Retrieval-Augmented Generation (RAG) system built over the Wake County North Carolina Math 1, 2, and 3 curriculum unpacking guides. It features incremental semantic ingestion, a high-accuracy hybrid search and reranking pipeline, a Streamlit interface acting as a "Patient Math Tutor," and a concurrent evaluation suite.

---

## 🏗️ System Architecture & RAG Pipeline Flow

```mermaid
graph TD
    subgraph Ingestion Phase
        A["data/*.pdf (Math 1, 2, 3 PDFs)"] -->|PyMuPDF Text Extraction| B["src/ingestion.py"]
        B -->|Regex Semantic Split by Standard ID| C[1,158 text chunks + metadata]
        C -->|BAAI/bge-small-en-v1.5 Embeddings| D[("Chroma Vector DB (chroma_db/)")]
    end

    subgraph Retrieval Phase
        E[User Question] -->|dense similarity search| D
        E -->|sparse keyword search| F["BM25 Retriever (src/retrieval.py)"]
        D -->|top 10 dense docs| G[Reciprocal Rank Fusion RRF]
        F -->|top 10 sparse docs| G
        G -->|top 10 fused candidates| H["Cross-Encoder Reranker (ms-marco-MiniLM-L-6-v2)"]
        H -->|top 4 reranked documents| I[Retrieved Context]
    end

    subgraph Generation Phase
        I --> J[Tutor Prompt Template]
        E --> J
        J -->|Format Prompt| K["Llama-3.3-70B LLM (via Nebius API)"]
        K -->|Stream Answer| L["app.py (Streamlit UI Chat)"]
    end

    subgraph Evaluation Phase
        M["tests/evaluation.py"] -->|Query 15 Gold Standard Questions| E
        K -->|Tutor Answer & Context| N["LLM-as-a-Judge (Llama-3.3-70B)"]
        N -->|Faithfulness & Relevance Scores| O["tests/evaluation_report.md"]
    end
```

---

## ⚙️ Functional Block Views

### 1. Ingestion Pipeline (Offline/Scheduled Refresh Activity)
This process runs periodically (or manually) when new curriculum guidelines are added to `data/`. It implements **incremental checks** to avoid duplicate indexing.

```mermaid
graph TD
    subgraph Trigger
        T[cron / Manual Run / New PDF added]
    end
    subgraph Step 1: Delta Check
        A["data/ folder"] --> B["src/ingestion.py"]
        C[("Chroma DB (chroma_db/)")] -->|Query unique 'source' metadata| B
        B -->|Identify new PDFs only| D[Filtered PDF list]
    end
    subgraph Step 2: Extraction & Semantic Chunking
        D -->|Read & Parse Text| E[PyMuPDF text extractor]
        E -->|Identify NC Math standard boundaries| F[Regex Semantic Chunker]
        F -->|Extract semantic sections| G[Clean chunks with standard metadata]
    end
    subgraph Step 3: Embed & Persist
        G -->|Convert to 384-dim vector| H["HuggingFace Embeddings (BAAI/bge-small-en-v1.5)"]
        H -->|Add/Append new records| C
    end
```

### 2. Retrieval & Query Pipeline (Real-time / User Triggered)
This runs in real-time on every query a student or parent submits:

```mermaid
graph TD
    subgraph Step 1: User Request
        U[User Query] -->|Input| UI["app.py (Streamlit Chat UI)"]
        UI -->|Send Query| R["src/retrieval.py"]
    end
    
    subgraph Step 2: Concurrent Dual Search
        R -->|Query| D[Chroma Dense Search]
        R -->|Query| S[BM25 Sparse Search]
        DB[("Chroma Vector DB (chroma_db/)")] <-->|Cosine distance similarity| D
        BM25_Index[BM25 Vocabulary Index] <-->|Exact keyword match| S
    end

    subgraph Step 3: Fusion & Reranking
        D -->|Top 10 Dense Chunks| F[Reciprocal Rank Fusion RRF]
        S -->|Top 10 Sparse Chunks| F
        F -->|Merged Top 10 Chunks| CE["Cross-Encoder Reranker (ms-marco-MiniLM-L-6-v2)"]
    end

    subgraph Step 4: Generation & UI Output
        CE -->|Top 4 High-Relevance Chunks| LLM["Llama-3.3-70B (via Nebius API)"]
        U -->|Query| LLM
        LLM -->|Streamed Tutor Answer| UI
    end
```

---

## 🛠️ Checklist of What Was Implemented & Tested

### Core RAG Implementation
- [x] **Raw Data Store:** Set up the `data/` folder and ingested official Math 1, 2, and 3 unpacking PDFs.
- [x] **Incremental Parser (`src/ingestion.py`):**
  - Parses PDFs using PyMuPDF (`fitz`).
  - Semantically chunks documents based on Regex boundaries identifying Math Standard IDs (e.g., `NC.M1.A-APR.1`).
  - Queries existing records in Chroma DB to **skip already indexed PDFs** and **prevent duplication**.
- [x] **Local Embedding & Vector Store (`chroma_db/`):**
  - Configured local Chroma DB to avoid external API overhead.
  - Implemented local embeddings with `BAAI/bge-small-en-v1.5`.
- [x] **Hybrid Retriever (`src/retrieval.py`):**
  - Combined Chroma dense similarity search with BM25 sparse keyword search.
  - Merged results using Reciprocal Rank Fusion (RRF).
  - Reranked candidates with a local Cross-Encoder model (`ms-marco-MiniLM-L-6-v2`).
- [x] **Tutor Interface (`app.py`):**
  - Designed Streamlit chat UI configured with `meta-llama/Llama-3.3-70B-Instruct` on Nebius.
  - Configured prompt grounding to enforce math tutor behavior and syllabus-only answering.
  - Added source tracing with expandable metadata card display.

### Testing & Validation
- [x] **Concurrent Evaluation Suite (`tests/evaluation.py`):**
  - Programmed a multithreaded test suite using `ThreadPoolExecutor` to concurrently evaluate a 15-question gold standard set.
  - Integrated an LLM-as-a-judge system using Llama-3.3-70B to evaluate both **Faithfulness** and **Relevance** on a 1-5 scale.
- [x] **Report Generation:** Generates a structured markdown log of all questions and score cards in [`tests/evaluation_report.md`](tests/evaluation_report.md).
- [x] **Retrieval Latency Verification:** Verified average retrieval latency is under **0.60 seconds**.
- [x] **Grounding Verification:** Validated tutor responses have a **4.73 / 5.00** faithfulness score, confirming robust grounding.
- [x] **Fallback Logic:** Confirmed that out-of-scope questions (e.g. comparing cell phone plans when context is absent) correctly trigger the fallback message: *"I cannot find this in our syllabus, please ask your teacher."*

---

## 🚀 How to Run the App

1. Ensure your Nebius API key is configured in `Wake-County-RAG/.env`:
   ```env
   NEBIUS_API_KEY="your-api-key"
   NEBIUS_BASE_URL="https://api.studio.nebius.ai/v1/"
   ```
2. Start the Streamlit application:
   ```bash
   uv run streamlit run Wake-County-RAG/app.py
   ```
3. Open your browser and navigate to the local URL (usually `http://localhost:8501`) to start chatting with your Patient Math Tutor!

---

## 🤝 Agent-to-Agent (A2A) Integration

Ed-Copilot exposes its district agents over the **Agent-to-Agent (A2A) protocol** so other
systems (e.g. `flower16/copilot-for-families`) can delegate district / curriculum questions
to it over HTTP — **without importing any Ed-Copilot code**. The two apps share only an HTTP +
JSON contract, so each stays independently deployable. See
[MULTI_DISTRICT_PLAN.md §4.3](MULTI_DISTRICT_PLAN.md).

### Architecture

```
┌──────────────────────────────┐      HTTP / JSON       ┌──────────────────────────────┐
│  Consumer                    │  ───────────────────▶   │  Ed-Copilot A2A server        │
│  copilot-for-families        │  GET /.well-known/       │  src/a2a/server.py            │
│  backend/app/a2a/client.py   │      agent.json          │  src/a2a/agent_card.py        │
│  EdCopilotA2AClient          │  ◀──── agent card ────    │                              │
│                              │  POST /run {district,msg}│  → orchestrator → ChromaDB    │
│  POST /a2a/ask (auth route)  │  ◀──── grounded answer ─  │  → Nebius LLM                 │
└──────────────────────────────┘                         └──────────────────────────────┘
```

### Server side (this repo) — `src/a2a/`

| File | Role |
|---|---|
| [`agent_card.py`](src/a2a/agent_card.py) | Builds the A2A **agent card** from the `DistrictRegistry` — one *skill* per district (id, name, intents, examples). Add a district → the card advertises it automatically. |
| [`server.py`](src/a2a/server.py) | FastAPI app exposing the endpoints below. Drives the **existing orchestrator** unchanged; registry + graph are lazily cached. |

**Endpoints**

| Endpoint | Purpose |
|---|---|
| `GET /.well-known/agent.json` | Serve the agent card (A2A discovery convention) |
| `GET /health` | Liveness + registered district ids |
| `POST /run` | Run one question: `{message, district, persona}` → `{response, intent, intent_badge, sources}` |

**Run it**

```bash
# from the project root, using the project venv; needs NEBIUS_API_KEY in .env
A2A_PORT=8100 python -m src.a2a.server
# health check
curl http://localhost:8100/health
# ask a district agent
curl -X POST http://localhost:8100/run -H "Content-Type: application/json" \
  -d '{"district":"frisco_isd_tx","persona":"parent","message":"What math courses does Frisco ISD offer?"}'
```

Env: `A2A_PORT` (default `8100`), `A2A_PUBLIC_URL` (overrides the `url` in the agent card).

### Consumer side (`flower16/copilot-for-families`) — `backend/app/a2a/`

- `client.py` — `EdCopilotA2AClient` (httpx-only): `get_agent_card()`, `supported_districts()`,
  `supports(district, intent)`, `run(district, message, persona)`.
- `config.py` — `ED_COPILOT_A2A_URL` setting (empty disables the feature).
- `main.py` — auth-protected `GET /a2a/districts` and `POST /a2a/ask` routes that map the
  logged-in user's role → persona and delegate to this server.

Point it at a running server via `ED_COPILOT_A2A_URL=http://localhost:8100` in that repo's `.env`.

### Request flow

```
parent logs into copilot-for-families            → JWT
POST /a2a/ask {district, message} (Bearer token)
  → EdCopilotA2AClient.run()
    → POST {A2A_URL}/run
      → registry check → orchestrator.invoke()
        → classify_intent → agent_<district> → retrieve() → synthesize() (Nebius)
      ← {response, intent, intent_badge, sources}
```

