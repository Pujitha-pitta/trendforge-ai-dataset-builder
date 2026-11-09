# TrendForge — Multi-Source Dataset Studio

TrendForge collects point-in-time snapshots from Hacker News, GitHub, Stack Overflow, arXiv, and Open Library, normalizes them into inspectable tables, optionally adds AI-generated topic labels and summaries, and prepares packages for Kaggle. Project Topic Search combines keyword-matched records from all five providers into one project-focused dataset.

## What it does

- Collects up to 100 records from five public APIs: Hacker News feeds, GitHub repository search, Stack Overflow questions, arXiv papers, and Open Library books.
- Lets you choose source-specific filters: Hacker News feed, GitHub search qualifiers, Stack Overflow tags and ranking, arXiv search terms, or Open Library book search.
- Searches across all five providers with one project or topic phrase and combines the returned real records into a single dataset.
- Normalizes results into common fields such as title, URL, author, score, and UTC creation time while retaining source-specific fields such as GitHub stars or Stack Overflow tags.
- Optionally enriches titles with concise AI topic labels and summaries. AI enrichment is opt-in and requires your own OpenAI API key.
- Previews the dataset, lets you download a CSV, and prepares a Kaggle-ready folder with metadata and source notes.
- Keeps upload explicit: packages remain local until you run the uploader. Public upload requires a second explicit confirmation.

## Run locally

Use Python 3.10 or newer.

```powershell
cd trendforge
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

In the sidebar, choose a source and up to 100 records, then click **Collect dataset**. Hacker News supports top, new, best, Ask HN, Show HN, and jobs feeds. GitHub accepts repository search qualifiers such as `python stars:>1000`. Stack Overflow supports up to five semicolon-separated tags and ranking. arXiv and Open Library accept keyword searches. **Project topic search** distributes the requested record count across all five providers and adds the search phrase to each row.

All collectors use public APIs and do not require a source account or API key. GitHub's anonymous search has a low rate limit. Open Library describes its Search API as experimental. TrendForge waits three seconds between arXiv requests, as requested in arXiv's API manual. Project topic search uses the Hacker News Search API powered by Algolia. Check current provider terms before publishing collected data.

### Optional AI enrichment

Enter an OpenAI API key in the sidebar for one run, or copy `.env.example` to `.env` and set `OPENAI_API_KEY` and `OPENAI_MODEL`. The key is not written to the project files or dataset. Provider API usage may have a cost. Without a key, all collection, cleaning, CSV download, and Kaggle packaging features remain available.

## Prepare and upload to Kaggle

The app's **Prepare Kaggle package** button writes a CSV, metadata, and source notes under `output/<dataset-slug>/`. It does not upload anything. CSV columns vary by source; common fields are kept consistent, and available source-specific fields are included where relevant.

1. Review the generated CSV and metadata, and confirm the source's current terms and attribution requirements.
2. Install and configure the Kaggle CLI with your own account credentials. Never commit `kaggle.json` or API tokens.
3. Upload privately by default:

```powershell
python kaggle_upload.py output\hacker-news-top-snapshot --confirm-upload
```

For public distribution, add `--public`. The uploader then asks you to type `PUBLIC` before sending the dataset:

```powershell
python kaggle_upload.py output\hacker-news-top-snapshot --confirm-upload --public
```

Kaggle's CLI supports creating datasets from a folder containing `dataset-metadata.json` and data files. Public publication is optional; review the metadata and source terms before choosing it.

### Clean an existing snapshot for a new version

To prepare a reviewed Version 3 package from a downloaded CSV, run:

```powershell
py clean_dataset.py "C:\path\to\hacker_news_stories.csv" --username your-kaggle-username
```

The cleaner keeps story rows, excludes the reviewed sample row ID `50378228`, drops AI annotation columns when they are entirely blank, checks required fields and duplicate IDs/URLs, and adds `prepared_at_utc`. It writes a new folder under `output/hacker-news-top-snapshot-v3/` and does not upload anything. Review the output CSV before publishing it. If the Kaggle dataset already exists, publish the folder as a new version with `kaggle datasets version`, not `kaggle datasets create`.

## Dataset schema

Common fields include `id`, `type`, `title`, `url`, `domain`, `author`, `score`, `comments`, `created_at`, `text`, `ai_topic`, `ai_summary`, and `source`. Project topic search also adds `project_topic`. Extra fields depend on the source: GitHub adds `stars`, `forks`, `open_issues`, `language`, and `license`; Stack Overflow adds `answers`, `views`, and `tags`; arXiv adds `categories` and `updated_at`; Open Library adds `first_publish_year`, `edition_count`, `subjects`, and `isbn`. A field can be blank when that API does not provide an equivalent value.

AI annotations can be imperfect. They are separate from source fields and should be checked before being used for analysis. Each run is a point-in-time snapshot; scores and comments change over time.

## Project structure

```text
trendforge/
├── app.py                 # Streamlit interface
├── trendforge.py          # Multi-source API ingestion, normalization, AI enrichment, packaging
├── kaggle_upload.py       # Explicit, private-by-default Kaggle uploader
├── requirements.txt
├── .env.example
└── output/                # Generated data (git-ignored)
```

## Data source

This project uses public endpoints documented by [Hacker News](https://github.com/HackerNews/API), the [Hacker News Search API by Algolia](https://hn.algolia.com/api), [GitHub REST API](https://docs.github.com/en/rest/search/search), the [Stack Exchange API](https://api.stackexchange.com/docs), the [arXiv API](https://info.arxiv.org/help/api/user-manual.html), and [Open Library Search API](https://openlibrary.org/dev/docs/api/search). It does not scrape article pages or collect private account data.

