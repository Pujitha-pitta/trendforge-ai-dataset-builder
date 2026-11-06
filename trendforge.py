"""Hacker News collection, normalization, optional LLM enrichment, and export."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

API = "https://hacker-news.firebaseio.com/v0"
OUTPUT = Path(__file__).parent / "output"
FIELDS = ["id", "type", "title", "url", "domain", "author", "score", "comments", "created_at", "text", "ai_topic", "ai_summary", "source"]


def _get_json(url: str, timeout: int = 20) -> Any:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "TrendForge/1.0 (educational dataset builder)"})
    response.raise_for_status()
    return response.json()


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    link = item.get("url", "") or ""
    domain = re.sub(r"^www\.", "", requests.utils.urlparse(link).netloc.lower()) if link else "news.ycombinator.com"
    timestamp = item.get("time")
    created = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat() if timestamp else ""
    return {
        "id": item.get("id"),
        "type": item.get("type", "story"),
        "title": requests.utils.unquote(re.sub(r"<[^>]+>", "", item.get("title", "") or "")),
        "url": link or f"https://news.ycombinator.com/item?id={item.get('id', '')}",
        "domain": domain,
        "author": item.get("by", ""),
        "score": item.get("score", 0),
        "comments": item.get("descendants", 0),
        "created_at": created,
        "text": re.sub(r"<[^>]+>", " ", item.get("text", "") or "").strip(),
        "ai_topic": "",
        "ai_summary": "",
        "source": "Hacker News official Firebase API",
    }


def collect_stories(feed: str = "top", count: int = 30) -> list[dict[str, Any]]:
    """Fetch a bounded feed snapshot; detail calls are concurrency-limited."""
    allowed = {"top", "new", "best", "ask", "show", "jobs"}
    if feed not in allowed:
        raise ValueError(f"Unsupported feed: {feed}")
    if not 1 <= count <= 100:
        raise ValueError("Count must be between 1 and 100.")
    ids = _get_json(f"{API}/{feed}stories.json")
    ids = ids[:count]
    rows: list[dict[str, Any]] = []
    # Keep a modest worker count to avoid stressing the public service.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_get_json, f"{API}/item/{story_id}.json"): story_id for story_id in ids}
        for future in as_completed(futures):
            try:
                item = future.result()
                if item and not item.get("deleted") and not item.get("dead"):
                    rows.append(_normalize(item))
            except requests.RequestException:
                continue
    rows.sort(key=lambda row: row["score"], reverse=True)
    return rows


def enrich_with_ai(rows: list[dict[str, Any]], api_key: str, model: str) -> list[dict[str, Any]]:
    """Ask the configured OpenAI model for concise topic tags and summaries."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    # Batch inputs to keep prompts small and map the response to stable IDs.
    for start in range(0, len(rows), 20):
        batch = rows[start:start + 20]
        payload = [{"id": row["id"], "title": row["title"], "domain": row["domain"], "text": row["text"][:400]} for row in batch]
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": 'Classify each Hacker News item. Return JSON exactly as {"items":[{"id":123,"topic":"short category","summary":"one factual sentence"}]}. Do not infer facts beyond title, domain, and provided text. Keep topic under 4 words and summary under 25 words.'},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        annotations = json.loads(content).get("items", [])
        by_id = {str(item.get("id")): item for item in annotations}
        for row in batch:
            annotation = by_id.get(str(row["id"]), {})
            row["ai_topic"] = str(annotation.get("topic", ""))[:80]
            row["ai_summary"] = str(annotation.get("summary", ""))[:300]
    return rows


def build_dataset(feed: str, count: int, api_key: str | None = None, model: str = "gpt-4o-mini") -> list[dict[str, Any]]:
    rows = collect_stories(feed=feed, count=count)
    if api_key:
        rows = enrich_with_ai(rows, api_key=api_key, model=model)
    return rows


def prepare_kaggle_package(rows: list[dict[str, Any]], username: str, slug: str, feed: str) -> Path:
    """Write CSV and editable Kaggle metadata locally. Never uploads data."""
    safe_slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    if not safe_slug:
        raise ValueError("Please enter a valid dataset slug.")
    folder = OUTPUT / safe_slug
    folder.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=FIELDS)
    frame.to_csv(folder / "hacker_news_stories.csv", index=False)
    metadata = {
        "title": f"Hacker News {feed.title()} Stories Snapshot",
        "id": f"{username}/{safe_slug}",
        "licenses": [{"name": "other"}],
        "description": "A dated snapshot of public Hacker News story metadata collected through the official Firebase API. Review upstream terms and attribution before redistributing.",
    }
    (folder / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (folder / "README.txt").write_text(
        "Source: Hacker News official Firebase API (https://github.com/HackerNews/API)\n"
        f"Feed: {feed}\nRows: {len(frame)}\n"
        "AI topic and summary columns are generated annotations when enabled; verify before reuse.\n"
        "Review the source terms and attribution requirements before making this dataset public.\n",
        encoding="utf-8",
    )
    return folder

