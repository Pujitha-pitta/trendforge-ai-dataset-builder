"""Explicitly upload an existing TrendForge package using the Kaggle CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a prepared dataset package to Kaggle.")
    parser.add_argument("package", type=Path, help="Folder containing dataset-metadata.json and CSV")
    parser.add_argument("--public", action="store_true", help="Publish the Kaggle dataset publicly")
    parser.add_argument("--confirm-upload", action="store_true", help="Confirm that you want to transmit this package to Kaggle")
    args = parser.parse_args()

    package = args.package.resolve()
    metadata_path = package / "dataset-metadata.json"
    csv_files = list(package.glob("*.csv"))
    if not metadata_path.is_file() or not csv_files:
        parser.error("Package must contain dataset-metadata.json and at least one CSV file.")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Could not read dataset metadata: {exc}")
    print(f"Dataset ID: {metadata.get('id', '(missing)')}")
    print(f"CSV files: {', '.join(path.name for path in csv_files)}")
    print(f"Visibility: {'PUBLIC' if args.public else 'PRIVATE'}")
    if not args.confirm_upload:
        parser.error("Review the package, then rerun with --confirm-upload to transmit it to Kaggle.")
    if args.public:
        print("Public datasets can be viewed and downloaded by anyone.")
        confirm = input("Type PUBLIC to confirm public publication: ")
        if confirm != "PUBLIC":
            print("Cancelled; nothing was uploaded.")
            return 2
    kaggle = shutil.which("kaggle")
    if not kaggle:
        print("Kaggle CLI is not installed. Install it with: pip install kaggle", file=sys.stderr)
        return 1
    command = [kaggle, "datasets", "create", "-p", str(package)]
    if args.public:
        command.append("--public")
    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

