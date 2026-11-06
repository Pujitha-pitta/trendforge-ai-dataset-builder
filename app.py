"""TrendForge: turn Hacker News stories into an enriched, Kaggle-ready dataset."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from trendforge import build_dataset, prepare_kaggle_package


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
st.markdown('<div class="intro">Collect a snapshot of Hacker News stories, enrich them with AI topic labels, and prepare a tidy dataset you can inspect, download, or publish to Kaggle.</div>', unsafe_allow_html=True)
st.write("")

with st.sidebar:
    st.markdown("### Build a dataset")
    feed = st.selectbox("Story feed", ["top", "new", "best", "ask", "show", "jobs"])
    count = st.slider("Number of stories", min_value=10, max_value=100, value=30, step=10)
    st.caption("Uses the official Hacker News Firebase API. Requests are limited to the selected story count.")
    st.markdown("---")
    st.markdown("### AI enrichment")
    default_key = os.getenv("OPENAI_API_KEY", "")
    api_key = st.text_input("OpenAI API key (optional)", value=default_key, type="password", help="Used only during this run. Without a key, the app still creates a complete dataset.")
    model = st.text_input("Model", value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    st.caption("AI adds a concise topic label and one-line summary. API usage may incur provider charges.")
    run = st.button("Collect stories", type="primary", use_container_width=True)

if run:
    with st.spinner("Collecting stories and preparing your dataset…"):
        try:
            st.session_state.dataset = build_dataset(feed=feed, count=count, api_key=api_key.strip() or None, model=model.strip())
            st.session_state.feed = feed
            st.session_state.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            st.session_state.package_dir = None
        except Exception as exc:
            st.error(f"Could not build the dataset: {exc}")

data = st.session_state.get("dataset")
if data is None:
    st.write("")
    st.info("Choose a feed and press **Collect stories** to build your first snapshot.")
    st.markdown("#### What this project demonstrates")
    st.write("API ingestion · data cleaning · optional LLM enrichment · CSV export · Kaggle dataset packaging")
else:
    frame = pd.DataFrame(data)
    st.markdown(f'<div class="eyebrow">{st.session_state.feed.upper()} FEED · BUILT {st.session_state.generated_at}</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="metric"><div class="metric-label">Stories collected</div><div class="metric-value">{len(frame)}</div></div>', unsafe_allow_html=True)
    topics = frame["ai_topic"].replace("", pd.NA).nunique() if "ai_topic" in frame else 0
    c2.markdown(f'<div class="metric"><div class="metric-label">Distinct topics</div><div class="metric-value">{topics}</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric"><div class="metric-label">AI enriched</div><div class="metric-value">{"Yes" if frame.get("ai_summary", pd.Series(dtype=str)).fillna("").ne("").any() else "No"}</div></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown("### Dataset preview")
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button("Download CSV", data=frame.to_csv(index=False).encode("utf-8"), file_name=f"hacker_news_{st.session_state.feed}.csv", mime="text/csv")

    st.markdown("---")
    st.markdown("### Prepare for Kaggle")
    username = st.text_input("Your Kaggle username", placeholder="your-kaggle-username")
    slug = st.text_input("Dataset slug", value=f"hacker-news-{st.session_state.feed}-snapshot")
    if st.button("Prepare Kaggle package"):
        if not username.strip() or not slug.strip():
            st.warning("Enter your Kaggle username and a dataset slug first.")
        else:
            package = prepare_kaggle_package(data, username.strip(), slug.strip(), st.session_state.feed)
            st.session_state.package_dir = str(package)
            st.success(f"Package prepared locally at `{package}`. Nothing has been uploaded.")
    if st.session_state.get("package_dir"):
        st.code(f'kaggle datasets create -p "{st.session_state.package_dir}"', language="powershell")
        st.caption("The Kaggle CLI creates the dataset as private by default. Review the files and source attribution before uploading. Add --public only if you deliberately want public distribution.")

