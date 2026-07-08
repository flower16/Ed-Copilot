import streamlit as st
import pathlib

st.set_page_config(page_title="Ed-Copilot Deck (Editorial)", page_icon="🟧", layout="wide")

st.title("🟧 Ed-Copilot Overview Deck — Bold Editorial")
st.caption("Same 18-slide walkthrough, restyled with oversized type, strong color blocks, and a light background. Use the arrow buttons or ← / → keys to navigate. Use your browser's Print (Ctrl/Cmd+P) to save as PDF.")

html_path = pathlib.Path(__file__).parent.parent / "presentation-editorial.html"

if not html_path.exists():
    st.error("presentation-editorial.html not found. Expected at the project root.")
    st.stop()

html_content = html_path.read_text(encoding="utf-8")
st.components.v1.html(html_content, height=800, scrolling=False)
