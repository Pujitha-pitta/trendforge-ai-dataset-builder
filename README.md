# TrendForge — AI Dataset Studio

TrendForge collects a small, timestamped snapshot of Hacker News stories, normalizes it into a tidy table, optionally adds AI-generated topic labels and summaries, and packages the result for Kaggle.

## What it does

- Collects a bounded selection from the official Hacker News Firebase API feeds: top, new, best, Ask HN, Show HN, or jobs.
- Normalizes each story into consistent fields such as title, domain, score, comment count, and UTC submission time.
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

In the sidebar, choose a feed and a maximum of 100 stories, then click **Collect stories**. The official API returns story IDs first and each story as an item record; this app limits each run to the selected number and uses a small worker pool.

### Optional AI enrichment

Enter an OpenAI API key in the sidebar for one run, or copy `.env.example` to `.env` and set `OPENAI_API_KEY` and `OPENAI_MODEL`. The key is not written to the project files or dataset. Provider API usage may have a cost. Without a key, all collection, cleaning, CSV download, and Kaggle packaging features remain available.

## Prepare and upload to Kaggle

The app's **Prepare Kaggle package** button writes a CSV, metadata, and source notes under `output/<dataset-slug>/`. It does not upload anything.

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

## Dataset schema

`id`, `type`, `title`, `url`, `domain`, `author`, `score`, `comments`, `created_at`, `text`, `ai_topic`, `ai_summary`, `source`.

AI annotations can be imperfect. They are separate from source fields and should be checked before being used for analysis. Each run is a point-in-time snapshot; scores and comments change over time.

## Project structure

```text
trendforge/
├── app.py                 # Streamlit interface
├── trendforge.py          # API ingestion, normalization, AI enrichment, packaging
├── kaggle_upload.py       # Explicit, private-by-default Kaggle uploader
├── requirements.txt
├── .env.example
└── output/                # Generated data (git-ignored)
```

## Data source

Hacker News official API documentation: <https://github.com/HackerNews/API>. This project reads public story metadata from that API. It does not scrape article pages or collect comments or user profiles.

