---
name: Ed-Copilot cold-start cost
description: Why Ed-Copilot's boot takes ~20s and why that's expected, not a bug
---

The app's cold start (~20s) is dominated by importing `langchain_huggingface` / `sentence_transformers`, which eagerly pull in `torch` + `transformers` (torch import alone is ~5s, the full chain ~10s). These are used for local embeddings (BAAI/bge-small-en-v1.5) and cross-encoder reranking in `src/retrieval.py`, imported transitively by every district agent at module load.

**Why:** These are real ML libraries needed for hybrid retrieval; there's no lightweight substitute without switching to an API-based embedding provider (which would require re-ingesting the entire vector DB with new embeddings — a bigger architectural change, not attempted here).

**How to apply:** Since the deployment target is `vm` (Reserved VM, not autoscale — see `.replit` `[deployment] deploymentTarget = "vm"`), this cost is paid once per process boot/restart, not per user request. The process stays warm afterward. If a user reports "slow app," clarify whether they mean the one-time boot after a deploy/restart (expected) or ongoing per-request slowness (would indicate a different problem, e.g. autoscale cold starts if deployment target ever changes).

**Resolution (July 2026):** The UI-facing cost was eliminated by lazy-loading: `app.py` no longer imports the orchestrator/registry at module level. Sidebar district names come straight from `config/tenants/*.yaml`, and the heavy AI stack loads inside a `@st.cache_resource` function only on the first chat question (with a visible spinner). Page render is now instant; the ~10-20s cost moved to the first question per process. Keep this pattern — reintroducing a top-level import of anything that transitively touches `src/retrieval.py` or the agents will regress launch time.
