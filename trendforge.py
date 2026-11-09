"""Multi-source collection, normalization, optional AI enrichment, and export."""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

HN_API = "https://hacker-news.firebaseio.com/v0"
GITHUB_API = "https://api.github.com"
STACK_API = "https://api.stackexchange.com/2.3"
OUTPUT = Path(__file__).parent / "output"
HN_FEEDS = {"top", "new", "best", "ask", "show", "jobs"}
SOURCES = {
    "Hacker News": "hacker_news",
    "GitHub repositories": "github",
    "Stack Overflow questions": "stackoverflow",
}


def _get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    request_headers = {"User-Agent": "TrendForge/2.0 (educational dataset builder)"}
    if headers:
        request_headers.update(headers)
    response = requests.get(url, params=params, timeout=timeout, headers=request_headers)
    response.raise_for_status()
    return response.json()


def _clean_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()


def _iso_utc(timestamp: int | float | None) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat() if timestamp else ""


def _normalize_hn(item: dict[str, Any]) -> dict[str, Any]:
    link = item.get("url", "") or ""
    domain = re.sub(r"^www\.", "", requests.utils.urlparse(link).netloc.lower()) if link else "news.ycombinator.com"
    return {
        "id": item.get("id", ""),
        "type": item.get("type", "story"),
        "title": _clean_html(item.get("title", "")),
        "url": link or f"https://news.ycombinator.com/item?id={item.get('id', '')}",
        "domain": domain,
        "author": item.get("by", ""),
        "score": item.get("score", 0),
        "comments": item.get("descendants", 0),
        "created_at": _iso_utc(item.get("time")),
        "text": _clean_html(item.get("text", "")),
        "source": "Hacker News official Firebase API",
        "ai_topic": "",
        "ai_summary": "",
    }


def collect_hacker_news(feed: str = "top", count: int = 30) -> list[dict[str, Any]]:
    if feed not in HN_FEEDS:
        raise ValueError(f"Unsupported Hacker News feed: {feed}")
    ids = _get_json(f"{HN_API}/{feed}stories.json")[:count]
    from concurrent.futures import ThreadPoolExecutor, as_completed

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_get_json, f"{HN_API}/item/{story_id}.json"): story_id for story_id in ids}
        for future in as_completed(futures):
            try:
                item = future.result()
                if item and not item.get("deleted") and not item.get("dead"):
                    rows.append(_normalize_hn(item))
            except requests.RequestException:
                continue
    rows.sort(key=lambda row: row["score"], reverse=True)
    return rows


def collect_github_repositories(count: int = 30, query: str = "stars:>100") -> list[dict[str, Any]]:
    query = (query or "stars:>100").strip()[:256]
    payload = _get_json(
        f"{GITHUB_API}/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc", "per_page": count},
        headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    rows = []
    for repo in payload.get("items", []):
        rows.append({
            "id": f"github:{repo.get('full_name', repo.get('id', ''))}",
            "type": "repository",
            "title": repo.get("full_name", ""),
            "url": repo.get("html_url", ""),
            "domain": "github.com",
            "author": (repo.get("owner") or {}).get("login", ""),
            "score": repo.get("stargazers_count", 0),
            "comments": "",
            "created_at": repo.get("created_at", ""),
            "text": repo.get("description") or "",
            "source": "GitHub REST API · repository search",
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
            "language": repo.get("language") or "",
            "license": (repo.get("license") or {}).get("spdx_id", ""),
            "ai_topic": "",
            "ai_summary": "",
        })
    return rows


def collect_stackoverflow_questions(
    count: int = 30, tag: str = "", sort: str = "votes", site: str = "stackoverflow"
) -> list[dict[str, Any]]:
    if sort not in {"votes", "activity", "creation", "hot", "week", "month"}:
        raise ValueError("Choose a supported Stack Exchange question sort.")
    tags = ";".join(part.strip() for part in tag.split(";") if part.strip())[:200]
    params: dict[str, Any] = {"site": site, "order": "desc", "sort": sort, "pagesize": count}
    if tags:
        params["tagged"] = tags
    payload = _get_json(f"{STACK_API}/questions", params=params)
    rows = []
    for question in payload.get("items", []):
        owner = question.get("owner") or {}
        rows.append({
            "id": f"stackoverflow:{question.get('question_id', '')}",
            "type": "question",
            "title": _clean_html(question.get("title", "")),
            "url": question.get("link", ""),
            "domain": f"{site}.com",
            "author": owner.get("display_name", ""),
            "score": question.get("score", 0),
            "comments": "",
            "created_at": _iso_utc(question.get("creation_date")),
            "text": "",
            "source": f"Stack Exchange API · {site}",
            "answers": question.get("answer_count", 0),
            "views": question.get("view_count", 0),
            "tags": ";".join(question.get("tags", [])),
            "ai_topic": "",
            "ai_summary": "",
        })
    return rows


def collect_dataset(
    source: str, count: int, *, feed: str = "top", query: str = "stars:>100", tag: str = "", sort: str = "votes"
) -> tuple[list[dict[str, Any]], str]:
    """Collect from a selected service; return records and a label for this snapshot."""
    if not 1 <= count <= 100:
        raise ValueError("Count must be between 1 and 100.")
    if source == "Hacker News":
        return collect_hacker_news(feed, count), f"{source} · {feed}"
    if source == "GitHub repositories":
        return collect_github_repositories(count, query), f"{source} · {query or 'stars:>100'}"
    if source == "Stack Overflow questions":
        return collect_stackoverflow_questions(count, tag, sort), f"{source} · {tag or 'all tags'} · {sort}"
    raise ValueError(f"Unsupported source: {source}")


def enrich_with_ai(rows: list[dict[str, Any]], api_key: str, model: str) -> list[dict[str, Any]]:
    """Add optional concise topic labels and summaries, keyed to stable record IDs."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    for start in range(0, len(rows), 20):
        batch = rows[start:start + 20]
        payload = [{"id": row["id"], "title": row["title"], "domain": row["domain"], "text": str(row.get("text", ""))[:400]} for row in batch]
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": 'Classify each public dataset record using only its title, domain, and supplied text. Return JSON exactly as {"items":[{"id":"stable-id","topic":"short category","summary":"one factual sentence"}]}. Do not infer facts. Keep topic under 4 words and summary under 25 words.'},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        annotations = json.loads(response.choices[0].message.content or "{}").get("items", [])
        by_id = {str(item.get("id")): item for item in annotations}
        for row in batch:
            annotation = by_id.get(str(row["id"]), {})
            row["ai_topic"] = str(annotation.get("topic", ""))[:80]
            row["ai_summary"] = str(annotation.get("summary", ""))[:300]
    return rows


def prepare_kaggle_package(rows: list[dict[str, Any]], username: str, slug: str, source_label: str) -> Path:
    """Write CSV and editable Kaggle metadata locally. Never uploads data."""
    safe_slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    if not safe_slug:
        raise ValueError("Please enter a valid dataset slug.")
    folder = OUTPUT / safe_slug
    folder.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(folder / "dataset.csv", index=False, encoding="utf-8")
    source_name = source_label.split(" · ", 1)[0]
    metadata = {
        "title": f"{source_name} Snapshot",
        "id": f"{username}/{safe_slug}",
        "licenses": [{"name": "other"}],
        "description": f"A point-in-time snapshot collected through the public {source_name} API. Review source attribution and usage terms before redistribution.",
    }
    (folder / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (folder / "README.txt").write_text(
        f"Source: {source_name}\nSnapshot filter: {source_label}\nRows: {len(frame)}\n"
        "AI topic and summary columns are generated annotations when enabled; verify before reuse.\n"
        "Review the source terms and attribution requirements before making this dataset public.\n",
        encoding="utf-8",
    )
    return folder
