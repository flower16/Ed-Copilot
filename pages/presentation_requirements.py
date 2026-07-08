import streamlit as st
import pathlib

st.set_page_config(page_title="Ed-Copilot Deck (Requirements)", page_icon="📑", layout="wide")

st.title("📑 Ed-Copilot — Executive Summary & Requirements")
st.caption("Executive summary, business requirements, technical requirements, and system workflow — 14 slides. Use the arrow buttons or ← / → keys to navigate. Use your browser's Print (Ctrl/Cmd+P) to save as PDF.")

html_path = pathlib.Path(__file__).parent.parent / "presentation-requirements.html"

if not html_path.exists():
    st.error("presentation-requirements.html not found. Expected at the project root.")
    st.stop()

html_content = html_path.read_text(encoding="utf-8")
st.components.v1.html(html_content, height=800, scrolling=False)
