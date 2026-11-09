"""Create a reviewed, Kaggle-ready version of the Hacker News snapshot."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_USERNAME = "pujithapitta"
DATASET_SLUG = "hacker-news-top-snapshot"
DEFAULT_EXCLUDED_IDS = ["50378228"]
OUTPUT_DIR = Path(__file__).parent / "output" / f"{DATASET_SLUG}-v3"
OPTIONAL_AI_COLUMNS = ("ai_topic", "ai_summary")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean the downloaded Hacker News CSV and prepare Kaggle Version 3 files.")
    parser.add_argument("csv_file", type=Path, help="Path to hacker_news_stories.csv")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="Kaggle username (not the profile URL)")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="Output folder for the Kaggle version package")
    parser.add_argument("--exclude-id", action="append", default=None, help="Story ID to exclude; may be repeated")
    args = parser.parse_args()

    source = args.csv_file.expanduser().resolve()
    if not source.is_file():
        parser.error(f"CSV file not found: {source}")

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            parser.error("The CSV is empty or has no header row.")
        columns = list(reader.fieldnames)
        rows = list(reader)

    excluded = set(args.exclude_id if args.exclude_id is not None else DEFAULT_EXCLUDED_IDS)
    original_count = len(rows)
    rows = [
        row for row in rows
        if (row.get("type", "").strip().lower() == "story")
        and (row.get("id", "").strip() not in excluded)
    ]
    removed_count = original_count - len(rows)

    dropped_ai = []
    for field in OPTIONAL_AI_COLUMNS:
        if field in columns and all(not (row.get(field) or "").strip() for row in rows):
            columns.remove(field)
            dropped_ai.append(field)
            for row in rows:
                row.pop(field, None)

    required = ("id", "title", "url", "domain")
    for field in required:
        if field not in columns:
            parser.error(f"Required column is missing: {field}")
        blank_count = sum(not (row.get(field) or "").strip() for row in rows)
        if blank_count:
            parser.error(f"Found {blank_count} blank values in required column '{field}'. Review before publishing.")

    ids = [row["id"].strip() for row in rows]
    urls = [row["url"].strip() for row in rows]
    if len(ids) != len(set(ids)):
        parser.error("Duplicate IDs remain after cleaning.")
    if len(urls) != len(set(urls)):
        parser.error("Duplicate URLs remain after cleaning.")

    prepared_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if "prepared_at_utc" not in columns:
        columns.append("prepared_at_utc")
    for row in rows:
        row["prepared_at_utc"] = prepared_at

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "hacker_news_stories.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    metadata = {
        "title": "Hacker News Top Stories Snapshot",
        "id": f"{args.username.strip()}/{DATASET_SLUG}",
        "licenses": [{"name": "other"}],
        "description": (
            "Reviewed snapshot of Hacker News top-story metadata. Source: the official Hacker News Firebase API. "
            "prepared_at_utc records when this cleaned export was prepared; created_at is the original post time. "
            "AI annotation fields are omitted because AI enrichment was not run for this snapshot."
        ),
    }
    (output / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    readme = (
        "Hacker News Top Stories Snapshot — Version 3 preparation\n\n"
        f"Rows: {len(rows)} story records (source file had {original_count}; removed {removed_count} non-story or excluded record(s)).\n"
        f"Prepared at (UTC): {prepared_at}\n"
        "Source: Hacker News official Firebase API (https://github.com/HackerNews/API).\n"
        "created_at is the original Hacker News post time; prepared_at_utc is when this cleaned export was prepared.\n"
        "Empty AI annotation columns were removed because AI enrichment was not run.\n"
        "Review the upstream source terms and attribution requirements before redistributing.\n"
    )
    (output / "README.txt").write_text(readme, encoding="utf-8")

    print(f"Prepared {len(rows)} rows; removed {removed_count} record(s).")
    print(f"Removed empty AI columns: {', '.join(dropped_ai) if dropped_ai else 'none'}")
    print(f"Kaggle dataset ID: {metadata['id']}")
    print(f"Package folder: {output}")
    print("No upload was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

