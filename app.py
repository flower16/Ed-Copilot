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

FEEDBACK_LOG_PATH = os.path.join(os.path.dirname(__file__), "data", "feedback_log.json")


def save_feedback(question, response_text, persona, district, rating, districts=None):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "persona": persona,
        "district": district,
        "districts": districts if districts else [district],
        "question": question,
        "response": response_text,
        "rating": "up" if rating == 1 else "down",
    }
    try:
        os.makedirs(os.path.dirname(FEEDBACK_LOG_PATH), exist_ok=True)
        if os.path.exists(FEEDBACK_LOG_PATH):
            with open(FEEDBACK_LOG_PATH, "r") as _f:
                _existing = json.load(_f)
        else:
            _existing = []
        _existing.append(record)
        with open(FEEDBACK_LOG_PATH, "w") as _f:
            json.dump(_existing, _f, indent=2)
    except Exception as _e:
        st.toast(f"Could not save feedback: {_e}", icon="⚠️")


DISTRICT_NAMES = registry.display_names()

# Curated aliases only — avoid broad single-word matches (e.g. "wake") that
# could hijack routing on ordinary sentences.
DISTRICT_ALIASES = {
    "frisco_isd_tx": ["frisco isd", "frisco"],
    "plano_isd_tx": ["plano isd", "plano"],
    "wake_county_nc": ["wake county", "wcpss"],
}


def detect_mentioned_districts(text):
    """Return district ids explicitly mentioned in the question text."""
    import re
    t = text.lower()
    found = []
    for did, name in DISTRICT_NAMES.items():
        aliases = set(DISTRICT_ALIASES.get(did, [])) | {name.lower()}
        if any(re.search(rf"\b{re.escape(a)}\b", t) for a in aliases):
            found.append(did)
    return found


def build_sources(intent, docs):
    sources = []
    if intent == "admin_policy":
        for doc in docs:
            sources.append({
                "label": doc.metadata.get("label", "—"),
                "source_url": doc.metadata.get("source_url", "—"),
                "fetched_date": doc.metadata.get("fetched_date", "—"),
                "snippet": doc.page_content[:300] + "...",
            })
    else:
        for doc in docs:
            sources.append({
                "standard_id": doc.metadata.get("standard_id", "—"),
                "course_id": doc.metadata.get("course_id", "—"),
                "rerank_score": doc.metadata.get("rerank_score", 0.0),
                "snippet": doc.page_content[:300] + "...",
            })
    return sources


def render_source(src):
    if src.get("district"):
        st.caption(f"District: {src['district']}")
    if "source_url" in src:
        st.write(f"**{src['label']}** — [{src['source_url']}]({src['source_url']})")
        st.caption(f"Fetched: {src.get('fetched_date', '—')}")
        st.caption(src["snippet"])
    else:
        st.write(f"**{src['standard_id']}** (Course: {src['course_id']}) — Rerank Score: {src['rerank_score']:.2f}")
        st.caption(src["snippet"])


def render_feedback_widget(idx, question, response_text, districts=None):
    saved_key = f"feedback_saved_{idx}"
    rating = st.feedback("thumbs", key=f"feedback_{idx}")
    if rating is not None and st.session_state.get(saved_key) != rating:
        save_feedback(
            question,
            response_text,
            st.session_state.get("persona", "student"),
            st.session_state.get("district", "wake_county_nc"),
            rating,
            districts=districts,
        )
        st.session_state[saved_key] = rating
        st.toast("Thanks for the feedback!", icon="🙏")

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
    st.caption("Tip: mention districts by name in your question (e.g. \"Frisco and Plano\") to compare across districts.")

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
    st.page_link("pages/presentation.py", label="🎞️ Overview Deck", icon=None)
    st.page_link("pages/presentation_warm.py", label="📖 Overview Deck (Warm)", icon=None)
    st.page_link("pages/presentation_corporate.py", label="🗂️ Overview Deck (Corporate)", icon=None)
    st.page_link("pages/presentation_editorial.py", label="🟧 Overview Deck (Editorial)", icon=None)
    st.page_link("pages/presentation_dataforward.py", label="📊 Overview Deck (Data-Forward)", icon=None)
    st.page_link("pages/presentation_requirements.py", label="📑 Executive Summary & Requirements", icon=None)

    st.divider()
    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and message.get("badge"):
            st.caption(message["badge"])
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("View Retrieved Sources"):
                for src in message["sources"]:
                    render_source(src)
        if message["role"] == "assistant":
            _prev_question = st.session_state.messages[idx - 1]["content"] if idx > 0 else ""
            render_feedback_widget(idx, _prev_question, message["content"], districts=message.get("districts"))

if prompt := st.chat_input("Ask about NC Math, school policy, or course planning..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                mentioned = detect_mentioned_districts(prompt)
                targets = mentioned if mentioned else [st.session_state.get("district", "wake_county_nc")]

                results = []
                for _did in targets:
                    state = EdCopilotState(
                        messages=st.session_state.messages,
                        persona=st.session_state.get("persona", "student"),
                        district=_did,
                        intent="",
                        context_docs=[],
                        response="",
                        intent_badge="",
                    )
                    results.append((_did, graph.invoke(state)))

                if len(results) == 1:
                    _did, _res = results[0]
                    response = _res["response"]
                    badge = _res["intent_badge"]
                else:
                    response = "\n\n---\n\n".join(
                        f"### {DISTRICT_NAMES.get(d, d)}\n\n{r['response']}" for d, r in results
                    )
                    badge = " | ".join(
                        f"{DISTRICT_NAMES.get(d, d)}: {r['intent_badge']}" for d, r in results
                    )

                sources = []
                for _d, _r in results:
                    for _src in build_sources(_r.get("intent", ""), _r.get("context_docs", [])):
                        if len(results) > 1:
                            _src["district"] = DISTRICT_NAMES.get(_d, _d)
                        sources.append(_src)

                st.caption(badge)
                st.markdown(response)

                if sources:
                    with st.expander("View Retrieved Sources"):
                        for _src in sources:
                            render_source(_src)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "badge": badge,
                    "sources": sources,
                    "districts": targets,
                })

                render_feedback_widget(len(st.session_state.messages) - 1, prompt, response, districts=targets)

            except Exception as e:
                st.error(f"Error: {str(e)}")
