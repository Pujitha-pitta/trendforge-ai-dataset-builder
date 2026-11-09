"""Multi-source collection, normalization, optional AI enrichment, and export."""

from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

HN_API = "https://hacker-news.firebaseio.com/v0"
HN_SEARCH_API = "https://hn.algolia.com/api/v1/search"
GITHUB_API = "https://api.github.com"
STACK_API = "https://api.stackexchange.com/2.3"
ARXIV_API = "https://export.arxiv.org/api/query"
OPEN_LIBRARY_API = "https://openlibrary.org/search.json"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
CROSSREF_API = "https://api.crossref.org/works"
NCBI_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OPEN_METEO_GEOCODING_API = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_API = "https://api.open-meteo.com/v1/forecast"
OUTPUT = Path(__file__).parent / "output"
HN_FEEDS = {"top", "new", "best", "ask", "show", "jobs"}
SOURCES = {
    "Hacker News": "hacker_news",
    "GitHub repositories": "github",
    "Stack Overflow questions": "stackoverflow",
    "arXiv papers": "arxiv",
    "Open Library books": "open_library",
    "Project topic search": "project_topic",
    "Wikipedia articles": "wikipedia",
    "Crossref works": "crossref",
    "PubMed articles": "pubmed",
    "Open-Meteo weather": "open_meteo",
}
_ARXIV_REQUEST_LOCK = threading.Lock()
_ARXIV_LAST_REQUEST = 0.0


def _get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20) -> Any:
    request_headers = {"User-Agent": "TrendForge/2.3 (https://github.com/Pujitha-pitta/trendforge-ai-dataset-builder)"}
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


def collect_hacker_news_topic(query: str, count: int) -> list[dict[str, Any]]:
    """Search Hacker News stories by a project/topic phrase via the public Algolia HN index."""
    payload = _get_json(HN_SEARCH_API, params={"query": query, "tags": "story", "hitsPerPage": count})
    rows = []
    for hit in payload.get("hits", []):
        item_id = hit.get("objectID", "")
        link = hit.get("url") or (f"https://news.ycombinator.com/item?id={item_id}" if item_id else "")
        domain = requests.utils.urlparse(link).netloc.lower() if link else "news.ycombinator.com"
        rows.append({
            "id": f"hn:{item_id}",
            "type": "story",
            "title": hit.get("title", ""),
            "url": link,
            "domain": re.sub(r"^www\.", "", domain),
            "author": hit.get("author", ""),
            "score": hit.get("points", 0),
            "comments": hit.get("num_comments", 0),
            "created_at": hit.get("created_at", ""),
            "text": "",
            "source": "Hacker News Algolia Search API",
            "ai_topic": "",
            "ai_summary": "",
        })
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
    count: int = 30, tag: str = "", sort: str = "votes", site: str = "stackoverflow", keyword: str = ""
) -> list[dict[str, Any]]:
    allowed_sorts = {"votes", "activity", "creation", "hot", "week", "month"}
    if keyword:
        allowed_sorts.add("relevance")
    if sort not in allowed_sorts:
        raise ValueError("Choose a supported Stack Exchange question sort.")
    tags = ";".join(part.strip() for part in tag.split(";") if part.strip())[:200]
    if len([part for part in tags.split(";") if part]) > 5:
        raise ValueError("Stack Overflow accepts at most five tags in this search.")
    params: dict[str, Any] = {"site": site, "order": "desc", "sort": sort, "pagesize": count}
    if keyword:
        params["intitle"] = keyword[:100]
        endpoint = "search/advanced"
    else:
        if tags:
            params["tagged"] = tags
        endpoint = "questions"
    payload = _get_json(f"{STACK_API}/{endpoint}", params=params)
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


def collect_arxiv_papers(count: int = 30, query: str = "machine learning") -> list[dict[str, Any]]:
    """Search arXiv's public Atom API and normalize paper metadata."""
    terms = re.findall(r"[\w.-]+", (query or "machine learning"), flags=re.UNICODE)
    if not terms:
        raise ValueError("Enter at least one search term for arXiv.")
    search_query = " AND ".join(f"all:{term}" for term in terms[:8])
    global _ARXIV_LAST_REQUEST
    with _ARXIV_REQUEST_LOCK:
        wait_seconds = 3 - (time.monotonic() - _ARXIV_LAST_REQUEST)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        response = requests.get(
            ARXIV_API,
            params={"search_query": search_query, "start": 0, "max_results": count, "sortBy": "relevance", "sortOrder": "descending"},
            timeout=30,
            headers={"User-Agent": "TrendForge/2.1 (educational metadata search)"},
        )
        _ARXIV_LAST_REQUEST = time.monotonic()
    response.raise_for_status()
    root = ET.fromstring(response.content)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    rows = []
    for entry in root.findall("atom:entry", ns):
        identifier = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        authors = [node.text.strip() for node in entry.findall("atom:author/atom:name", ns) if node.text]
        categories = [node.get("term", "") for node in entry.findall("atom:category", ns)]
        rows.append({
            "id": f"arxiv:{identifier.rsplit('/', 1)[-1]}",
            "type": "paper",
            "title": " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split()),
            "url": identifier.replace("http://", "https://", 1),
            "domain": "arxiv.org",
            "author": "; ".join(authors),
            "score": "",
            "comments": "",
            "created_at": entry.findtext("atom:published", default="", namespaces=ns),
            "text": " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split()),
            "source": "arXiv public Atom API",
            "categories": ";".join(categories),
            "updated_at": entry.findtext("atom:updated", default="", namespaces=ns),
            "ai_topic": "",
            "ai_summary": "",
        })
    return rows


def collect_open_library_books(count: int = 30, query: str = "science") -> list[dict[str, Any]]:
    """Search Open Library's public works search API."""
    query = (query or "science").strip()[:200]
    if not query:
        raise ValueError("Enter a book search term.")
    payload = _get_json(
        OPEN_LIBRARY_API,
        params={
            "q": query,
            "limit": count,
            "fields": "key,title,author_name,first_publish_year,edition_count,subject,isbn",
        },
        headers={"User-Agent": "TrendForge/2.1 (educational metadata search)"},
    )
    rows = []
    for book in payload.get("docs", []):
        key = book.get("key", "")
        rows.append({
            "id": f"openlibrary:{key.rsplit('/', 1)[-1]}",
            "type": "book",
            "title": book.get("title", ""),
            "url": f"https://openlibrary.org{key}" if key else "",
            "domain": "openlibrary.org",
            "author": "; ".join(book.get("author_name", [])),
            "score": book.get("edition_count", ""),
            "comments": "",
            "created_at": "",
            "text": "; ".join((book.get("subject") or [])[:12]),
            "source": "Open Library Search API",
            "first_publish_year": book.get("first_publish_year", ""),
            "edition_count": book.get("edition_count", ""),
            "subjects": ";".join((book.get("subject") or [])[:12]),
            "isbn": ";".join((book.get("isbn") or [])[:3]),
            "ai_topic": "",
            "ai_summary": "",
        })
    return rows


def collect_wikipedia_articles(count: int = 30, query: str = "science") -> list[dict[str, Any]]:
    """Search English Wikipedia pages with the MediaWiki Action API."""
    query = (query or "").strip()[:200]
    if not query:
        raise ValueError("Enter a Wikipedia search term.")
    payload = _get_json(
        WIKIPEDIA_API,
        params={"action": "query", "list": "search", "srsearch": query, "srlimit": count, "srprop": "snippet|timestamp", "format": "json", "formatversion": 2},
    )
    rows = []
    for page in payload.get("query", {}).get("search", []):
        page_id = page.get("pageid", "")
        rows.append({
            "id": f"wikipedia:{page_id}",
            "type": "article",
            "title": page.get("title", ""),
            "url": f"https://en.wikipedia.org/?curid={page_id}" if page_id else "",
            "domain": "en.wikipedia.org",
            "author": "",
            "score": page.get("wordcount", ""),
            "comments": "",
            "created_at": page.get("timestamp", ""),
            "text": _clean_html(page.get("snippet", "")),
            "source": "Wikipedia MediaWiki Search API",
            "page_id": page_id,
            "word_count": page.get("wordcount", ""),
            "ai_topic": "",
            "ai_summary": "",
        })
    return rows


def collect_crossref_works(count: int = 30, query: str = "science") -> list[dict[str, Any]]:
    """Search Crossref's public scholarly metadata."""
    query = (query or "").strip()[:200]
    if not query:
        raise ValueError("Enter a Crossref search term.")
    payload = _get_json(
        CROSSREF_API,
        params={
            "query.bibliographic": query,
            "rows": count,
            "select": "DOI,title,author,published,URL,type,container-title,is-referenced-by-count,subject,publisher",
        },
    )
    rows = []
    for work in payload.get("message", {}).get("items", []):
        title = (work.get("title") or [""])[0]
        authors = [" ".join(part for part in (author.get("given"), author.get("family")) if part) for author in work.get("author", [])]
        date_parts = (work.get("published") or {}).get("date-parts", [[]])[0]
        published = "-".join(f"{part:02d}" if index > 0 else str(part) for index, part in enumerate(date_parts))
        doi = work.get("DOI", "")
        rows.append({
            "id": f"crossref:{doi or work.get('URL', '')}",
            "type": work.get("type", "work"),
            "title": title,
            "url": work.get("URL", ""),
            "domain": "doi.org" if doi else "",
            "author": "; ".join(authors),
            "score": work.get("is-referenced-by-count", ""),
            "comments": "",
            "created_at": published,
            "text": "; ".join((work.get("subject") or [])[:10]),
            "source": "Crossref REST API",
            "doi": doi,
            "journal": "; ".join(work.get("container-title") or []),
            "publisher": work.get("publisher", ""),
            "citations": work.get("is-referenced-by-count", ""),
            "ai_topic": "",
            "ai_summary": "",
        })
    return rows


def collect_pubmed_articles(count: int = 30, query: str = "health") -> list[dict[str, Any]]:
    """Search PubMed using NCBI E-utilities without requiring an API key."""
    query = (query or "").strip()[:200]
    if not query:
        raise ValueError("Enter a PubMed search term.")
    search = _get_json(f"{NCBI_API}/esearch.fcgi", params={"db": "pubmed", "term": query, "retmax": count, "retmode": "json"})
    ids = search.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    summary = _get_json(f"{NCBI_API}/esummary.fcgi", params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    result = summary.get("result", {})
    rows = []
    for pmid in result.get("uids", ids):
        article = result.get(pmid, {})
        authors = [author.get("name", "") for author in article.get("authors", [])]
        article_ids = article.get("articleids", [])
        doi = next((item.get("value", "") for item in article_ids if item.get("idtype") == "doi"), "")
        rows.append({
            "id": f"pubmed:{pmid}",
            "type": "medical_article",
            "title": _clean_html(article.get("title", "")),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "domain": "pubmed.ncbi.nlm.nih.gov",
            "author": "; ".join(authors),
            "score": "",
            "comments": "",
            "created_at": article.get("pubdate", ""),
            "text": article.get("fulljournalname", ""),
            "source": "NCBI PubMed E-utilities",
            "pmid": pmid,
            "journal": article.get("fulljournalname", ""),
            "doi": doi,
            "publication_type": ";".join(article.get("pubtype") or []),
            "ai_topic": "",
            "ai_summary": "",
        })
    return rows


def collect_open_meteo_forecast(count: int = 7, location: str = "") -> list[dict[str, Any]]:
    """Geocode a location and collect up to 16 days of daily forecast data."""
    location = (location or "").strip()[:120]
    if not location:
        raise ValueError("Enter a city or location for the weather forecast.")
    geocode = _get_json(OPEN_METEO_GEOCODING_API, params={"name": location, "count": 1, "language": "en", "format": "json"})
    places = geocode.get("results", [])
    if not places:
        raise ValueError(f"No location matched '{location}'. Try adding a country name.")
    place = places[0]
    forecast_days = max(1, min(count, 16))
    forecast = _get_json(
        OPEN_METEO_FORECAST_API,
        params={
            "latitude": place["latitude"], "longitude": place["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
            "forecast_days": forecast_days, "timezone": "auto",
        },
    )
    daily = forecast.get("daily", {})
    descriptions = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers", 81: "Rain showers", 82: "Heavy rain showers", 95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail"}
    rows = []
    for index, forecast_date in enumerate(daily.get("time", [])):
        weather_code = (daily.get("weather_code") or [None] * len(daily["time"]))[index]
        tmax = (daily.get("temperature_2m_max") or [None] * len(daily["time"]))[index]
        tmin = (daily.get("temperature_2m_min") or [None] * len(daily["time"]))[index]
        precipitation = (daily.get("precipitation_sum") or [None] * len(daily["time"]))[index]
        wind = (daily.get("wind_speed_10m_max") or [None] * len(daily["time"]))[index]
        rows.append({
            "id": f"open-meteo:{place['latitude']},{place['longitude']}:{forecast_date}",
            "type": "weather_forecast",
            "title": f"Forecast for {place.get('name', location)} on {forecast_date}",
            "url": "https://open-meteo.com/",
            "domain": "open-meteo.com",
            "author": "",
            "score": "",
            "comments": "",
            "created_at": "",
            "text": descriptions.get(weather_code, "Weather forecast"),
            "source": "Open-Meteo Forecast API",
            "forecast_date": forecast_date,
            "location": place.get("name", location),
            "country": place.get("country", ""),
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
            "temperature_max_c": tmax,
            "temperature_min_c": tmin,
            "precipitation_mm": precipitation,
            "wind_speed_max_kmh": wind,
            "weather_code": weather_code,
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
    if source == "arXiv papers":
        return collect_arxiv_papers(count, query), f"{source} · {query or 'machine learning'}"
    if source == "Open Library books":
        return collect_open_library_books(count, query), f"{source} · {query or 'science'}"
    if source == "Wikipedia articles":
        return collect_wikipedia_articles(count, query), f"{source} · {query}"
    if source == "Crossref works":
        return collect_crossref_works(count, query), f"{source} · {query}"
    if source == "PubMed articles":
        return collect_pubmed_articles(count, query), f"{source} · {query}"
    if source == "Open-Meteo weather":
        days = max(1, min(count, 16))
        return collect_open_meteo_forecast(days, query), f"{source} · {query} · {days} days"
    if source == "Project topic search":
        topic = (query or "").strip()
        if not topic:
            raise ValueError("Enter a project name or topic to search.")
        providers = [
            ("Hacker News", lambda n: collect_hacker_news_topic(topic, n)),
            ("GitHub", lambda n: collect_github_repositories(n, topic)),
            ("Stack Overflow", lambda n: collect_stackoverflow_questions(n, sort="relevance", keyword=topic)),
            ("arXiv", lambda n: collect_arxiv_papers(n, topic)),
            ("Open Library", lambda n: collect_open_library_books(n, topic)),
            ("Wikipedia", lambda n: collect_wikipedia_articles(n, topic)),
            ("Crossref", lambda n: collect_crossref_works(n, topic)),
            ("PubMed", lambda n: collect_pubmed_articles(n, topic)),
        ]
        per_provider, extra = divmod(count, len(providers))
        combined: list[dict[str, Any]] = []
        for index, (provider, collector) in enumerate(providers):
            provider_count = per_provider + (1 if index < extra else 0)
            try:
                hits = collector(provider_count)
                for row in hits:
                    row["project_topic"] = topic
                combined.extend(hits)
            except requests.RequestException:
                continue
        if not combined:
            raise ValueError("No records were returned. Check the topic and try again.")
        return combined, f"Project topic search · {topic}"
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

