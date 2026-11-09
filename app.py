"""TrendForge: collect and package public data from multiple APIs."""

from __future__ import annotations

import html
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from trendforge import SOURCES, collect_dataset, enrich_with_ai, prepare_kaggle_package


load_dotenv()
st.set_page_config(page_title="TrendForge · Dataset Studio", page_icon="📈", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&display=swap');
:root { --ink:#19251f; --muted:#778078; --paper:#f6f6ef; --green:#d6f36a; --line:#dfe2d6; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:var(--paper); color:var(--ink); }
.block-container { max-width:1180px; padding-top:2rem; }
.eyebrow { font:500 11px 'DM Mono',monospace; letter-spacing:.16em; text-transform:uppercase; color:#61705f; }
.hero { font-size:clamp(42px,7vw,78px); line-height:.98; letter-spacing:-.065em; font-weight:600; margin:.55rem 0 1rem; }
.hero em { font-family:Georgia,serif; font-weight:400; }
.intro { color:#69736c; font-size:17px; max-width:650px; }
.metric { background:#fff; border:1px solid var(--line); border-radius:14px; padding:18px 20px; }
.metric-label { color:var(--muted); text-transform:uppercase; font:11px 'DM Mono',monospace; letter-spacing:.08em; }
.metric-value { font-size:27px; font-weight:600; margin-top:5px; }
div[data-testid="stButton"] button[kind="primary"] { background:#19251f; color:#fff; border:0; border-radius:8px; }
div[data-testid="stButton"] button { border-radius:8px; }
hr { border-color:var(--line); }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="eyebrow">OPEN DATA PIPELINE · PYTHON + AI</div>', unsafe_allow_html=True)
st.markdown('<div class="hero">Signal in<br><em>the stream.</em></div>', unsafe_allow_html=True)
st.markdown('<div class="intro">Collect snapshots from Hacker News, GitHub, Stack Overflow, arXiv, or Open Library. Add optional AI labels, inspect the results, and prepare a tidy dataset for Kaggle.</div>', unsafe_allow_html=True)
st.write("")

with st.sidebar:
    st.markdown("### Build a dataset")
    source = st.selectbox("Data source", list(SOURCES))
    feed = "top"
    query = "stars:>100"
    tag = ""
    sort = "votes"
    if source == "Hacker News":
        feed = st.selectbox("Hacker News feed", ["top", "new", "best", "ask", "show", "jobs"])
        st.caption("Uses the official Hacker News Firebase API.")
    elif source == "GitHub repositories":
        query = st.text_input("Repository search", value="stars:>100", help="Use GitHub search qualifiers, for example: python stars:>1000")
        st.caption("Uses GitHub's public repository search API. Anonymous requests have a low rate limit.")
    elif source == "Stack Overflow questions":
        tag = st.text_input("Stack Overflow tags (optional)", placeholder="python; pandas", help="Separate multiple tags with semicolons. All entered tags must match.")
        sort = st.selectbox("Question ranking", ["votes", "activity", "creation", "hot", "week", "month"])
        st.caption("Uses the public Stack Exchange API for Stack Overflow questions.")
    elif source == "arXiv papers":
        query = st.text_input("Paper search", value="machine learning", help="Searches paper titles, abstracts, and metadata.")
        st.caption("Uses arXiv's public Atom API. Search for research papers by keyword.")
    else:
        query = st.text_input("Book search", value="science", help="Search book titles, authors, and catalog metadata.")
        st.caption("Uses Open Library's public Search API.")
    count = st.slider("Number of records", min_value=10, max_value=100, value=30, step=10)
    st.caption("Requests are limited to the selected record count (maximum 100).")
    st.markdown("---")
    st.markdown("### AI enrichment")
    default_key = os.getenv("OPENAI_API_KEY", "")
    api_key = st.text_input("OpenAI API key (optional)", value=default_key, type="password", help="Used only during this run. Without a key, the app still creates a complete dataset.")
    model = st.text_input("Model", value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    st.caption("AI adds a concise topic label and one-line summary. API usage may incur provider charges.")
    run = st.button("Collect dataset", type="primary", use_container_width=True)

if run:
    st.session_state.dataset = None
    with st.spinner("Collecting records and preparing your dataset…"):
        try:
            rows, source_label = collect_dataset(source, count, feed=feed, query=query, tag=tag, sort=sort)
            if api_key.strip() and rows:
                rows = enrich_with_ai(rows, api_key=api_key.strip(), model=model.strip())
            st.session_state.dataset = rows
            st.session_state.source = source
            st.session_state.source_label = source_label
            st.session_state.feed = feed
            st.session_state.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            st.session_state.package_dir = None
        except Exception as exc:
            st.error(f"Could not build the dataset: {exc}")

data = st.session_state.get("dataset")
if data is None:
    st.write("")
    st.info("Choose a source and press **Collect dataset** to build your first snapshot.")
    st.markdown("#### What this project demonstrates")
    st.write("Multi-source API ingestion · data cleaning · optional AI enrichment · CSV export · Kaggle dataset packaging")
else:
    frame = pd.DataFrame(data)
    source_label = st.session_state.source_label
    st.markdown(f'<div class="eyebrow">{html.escape(source_label.upper())} · BUILT {st.session_state.generated_at}</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="metric"><div class="metric-label">Records collected</div><div class="metric-value">{len(frame)}</div></div>', unsafe_allow_html=True)
    topics = frame["ai_topic"].replace("", pd.NA).nunique() if "ai_topic" in frame else 0
    c2.markdown(f'<div class="metric"><div class="metric-label">Distinct topics</div><div class="metric-value">{topics}</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric"><div class="metric-label">AI enriched</div><div class="metric-value">{"Yes" if frame.get("ai_summary", pd.Series(dtype=str)).fillna("").ne("").any() else "No"}</div></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown("### Dataset preview")
    st.dataframe(frame, use_container_width=True, hide_index=True)
    source_file = SOURCES[st.session_state.source]
    st.download_button("Download CSV", data=frame.to_csv(index=False).encode("utf-8-sig"), file_name=f"{source_file}_snapshot.csv", mime="text/csv")

    st.markdown("---")
    st.markdown("### Prepare for Kaggle")
    username = st.text_input("Your Kaggle username", placeholder="your-kaggle-username")
    suggested_slug = f"{source_file}-{st.session_state.get('feed', 'snapshot')}-snapshot" if source_file == "hacker_news" else f"{source_file}-snapshot"
    slug = st.text_input("Dataset slug", value=suggested_slug)
    if st.button("Prepare Kaggle package"):
        if not username.strip() or not slug.strip():
            st.warning("Enter your Kaggle username and a dataset slug first.")
        else:
            package = prepare_kaggle_package(data, username.strip(), slug.strip(), source_label)
            st.session_state.package_dir = str(package)
            st.success(f"Package prepared locally at `{package}`. Nothing has been uploaded.")
    if st.session_state.get("package_dir"):
        st.code(f'kaggle datasets create -p "{st.session_state.package_dir}"', language="powershell")
        st.caption("The Kaggle CLI creates the dataset as private by default. Review the files and source attribution before uploading. Add --public only if you deliberately want public distribution.")

