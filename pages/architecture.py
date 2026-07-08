import streamlit as st
import pathlib

st.set_page_config(page_title="Ed-Copilot Architecture", page_icon="🏗️", layout="wide")

st.title("🏗️ System Architecture")
st.caption("End-to-end design of the Ed-Copilot pipeline — from user interface to knowledge retrieval.")

html_path = pathlib.Path(__file__).parent.parent / "architecture.html"

if not html_path.exists():
    st.error("architecture.html not found. Expected at the project root.")
    st.stop()

html_content = html_path.read_text(encoding="utf-8")
st.components.v1.html(html_content, height=2600, scrolling=True)
