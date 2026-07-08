import streamlit as st
from src.orchestrator import build_graph, EdCopilotState
from src.district_registry import DistrictRegistry
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

if os.environ.get("LANGCHAIN_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "Ed-Copilot")

st.set_page_config(page_title="Ed-Copilot", page_icon="🎓", layout="centered")

st.title("🎓 Ed-Copilot")
st.caption("Your AI school assistant for NC Math, district policy, and course planning.")

st.warning(
    "⚠️ Created for learning purposes. Please refer to your county's official website "
    "for authoritative information.",
    icon="📋",
)

@st.cache_resource(show_spinner="Loading district agents...")
def init_registry():
    return DistrictRegistry()


@st.cache_resource(show_spinner="Initializing Ed-Copilot...")
def init_graph(_registry):
    api_key = os.environ.get("NEBIUS_API_KEY", "")
    if not api_key or api_key == "your-key-here":
        st.error("Please add your NEBIUS_API_KEY to the .env file.")
        st.stop()
    return build_graph(_registry)


registry = init_registry()
graph = init_graph(registry)

with st.sidebar:
    st.header("⚙️ Settings")

    persona = st.selectbox(
        "Who are you?",
        options=["student", "parent", "teacher"],
        format_func=lambda x: {"student": "🧑‍🎓 Student", "parent": "👨‍👩‍👧 Parent", "teacher": "👩‍🏫 Teacher"}[x],
        key="persona",
    )

    _district_names = registry.display_names()
    district = st.selectbox(
        "District",
        options=list(_district_names.keys()),
        format_func=lambda x: _district_names.get(x, x),
        key="district",
    )

    st.divider()

    INGESTION_LOG_PATH = os.path.join(os.path.dirname(__file__), "data", "ingestion_log.json")
    st.subheader("📅 Knowledge Freshness")
    try:
        if os.path.exists(INGESTION_LOG_PATH):
            with open(INGESTION_LOG_PATH, "r") as _f:
                _log = json.load(_f)
            if _log:
                _last = _log[-1]
                _run_at_raw = _last.get("run_at", "")
                try:
                    _run_dt = datetime.fromisoformat(_run_at_raw)
                    _run_at_fmt = _run_dt.strftime("%b %d, %Y %H:%M UTC")
                except Exception:
                    _run_at_fmt = _run_at_raw
                st.success(f"Last refreshed: **{_run_at_fmt}**")
                _total = _last.get("total_chunks_indexed", 0)
                st.caption(f"{_total} chunks indexed in last run")
                _districts_info = _last.get("districts", {})
                if _districts_info:
                    with st.expander("Per-district details"):
                        for _dk, _dv in _districts_info.items():
                            _dname = _dv.get("name", _dk)
                            _dchunks = _dv.get("chunks_indexed", 0)
                            st.write(f"**{_dname}** — {_dchunks} chunks")
            else:
                st.info("No ingestion runs recorded yet.")
        else:
            st.info("No ingestion log found. Run `python src/admin_ingestion.py` to populate.")
    except Exception as _e:
        st.warning(f"Could not load ingestion log: {_e}")

    st.divider()
    st.page_link("pages/architecture.py", label="🏗️ System Architecture", icon=None)

    st.divider()
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and message.get("badge"):
            st.caption(message["badge"])
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("View Retrieved Sources"):
                for src in message["sources"]:
                    if "source_url" in src:
                        st.write(f"**{src['label']}** — [{src['source_url']}]({src['source_url']})")
                        st.caption(f"Fetched: {src.get('fetched_date', '—')}")
                        st.caption(src["snippet"])
                    else:
                        st.write(f"**{src['standard_id']}** (Course: {src['course_id']}) — Rerank Score: {src['rerank_score']:.2f}")
                        st.caption(src["snippet"])

if prompt := st.chat_input("Ask about NC Math, school policy, or course planning..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                state = EdCopilotState(
                    messages=st.session_state.messages,
                    persona=st.session_state.get("persona", "student"),
                    district=st.session_state.get("district", "wake_county_nc"),
                    intent="",
                    context_docs=[],
                    response="",
                    intent_badge="",
                )
                result = graph.invoke(state)
                response = result["response"]
                badge = result["intent_badge"]
                docs = result.get("context_docs", [])

                st.caption(badge)
                st.markdown(response)

                sources = []
                intent = result.get("intent", "")
                if docs:
                    with st.expander("View Retrieved Sources"):
                        if intent == "admin_policy":
                            for doc in docs:
                                label = doc.metadata.get("label", "—")
                                source_url = doc.metadata.get("source_url", "—")
                                fetched = doc.metadata.get("fetched_date", "—")
                                snippet = doc.page_content[:300] + "..."
                                st.write(f"**{label}** — [{source_url}]({source_url})")
                                st.caption(f"Fetched: {fetched}")
                                st.caption(snippet)
                                sources.append({
                                    "label": label,
                                    "source_url": source_url,
                                    "fetched_date": fetched,
                                    "snippet": snippet,
                                })
                        else:
                            for doc in docs:
                                sid = doc.metadata.get("standard_id", "—")
                                cid = doc.metadata.get("course_id", "—")
                                score = doc.metadata.get("rerank_score", 0.0)
                                snippet = doc.page_content[:300] + "..."
                                st.write(f"**{sid}** (Course: {cid}) — Rerank Score: {score:.2f}")
                                st.caption(snippet)
                                sources.append({
                                    "standard_id": sid,
                                    "course_id": cid,
                                    "rerank_score": score,
                                    "snippet": snippet,
                                })

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "badge": badge,
                    "sources": sources,
                })

            except Exception as e:
                st.error(f"Error: {str(e)}")
