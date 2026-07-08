import streamlit as st
import pathlib

st.set_page_config(page_title="Ed-Copilot Deck (Data-Forward)", page_icon="📊", layout="wide")

st.title("📊 Ed-Copilot Overview Deck — Data-Forward")
st.caption("Same 18-slide walkthrough, restyled dark with a precise grid layout and chart/stat-heavy components. Use the arrow buttons or ← / → keys to navigate. Use your browser's Print (Ctrl/Cmd+P) to save as PDF.")

html_path = pathlib.Path(__file__).parent.parent / "presentation-dataforward.html"

if not html_path.exists():
    st.error("presentation-dataforward.html not found. Expected at the project root.")
    st.stop()

html_content = html_path.read_text(encoding="utf-8")
st.components.v1.html(html_content, height=800, scrolling=False)
