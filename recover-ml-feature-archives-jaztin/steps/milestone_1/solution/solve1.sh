#!/bin/bash
set -euo pipefail

# Milestone 1: Write /app/recover.py with Polars catalog scan -> /app/facts/catalog.json

cat > /app/recover.py << 'PYEOF'
#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys
from typing import Any

import polars as pl

REQUIRED_COLUMNS = ["customer_id", "tenure", "monthly_charges", "label"]
MIN_ROWS = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default="/app/archive")
    parser.add_argument("--facts-dir", default="/app/facts")
    parser.add_argument("--policy", default="/app/policy/recover.rego")
    parser.add_argument("--output-dir", default="/app/output")
    return parser.parse_args()


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_shard_checksum(shard_path: str) -> bool:
    sha_path = shard_path + ".sha256"
    if not os.path.isfile(sha_path):
        return False
    try:
        with open(sha_path, "r") as f:
            first_line = f.readline().strip()
        expected_digest = first_line.split()[0]
        actual_digest = sha256_of_file(shard_path)
        return expected_digest == actual_digest
    except Exception:
        return False


def build_catalog(archive_dir: str) -> list[dict[str, Any]]:
    catalog = []
    for fname in sorted(os.listdir(archive_dir)):
        fpath = os.path.join(archive_dir, fname)
        if fname.endswith(".parquet"):
            file_type = "parquet"
            try:
                df = pl.read_parquet(fpath)
            except Exception as exc:
                print(f"Warning: could not read {fpath}: {exc}", file=sys.stderr)
                continue
        elif fname.endswith(".csv"):
            file_type = "csv"
            try:
                df = pl.read_csv(fpath)
            except Exception as exc:
                print(f"Warning: could not read {fpath}: {exc}", file=sys.stderr)
                continue
        else:
            continue
        catalog.append({
            "path": os.path.abspath(fpath),
            "file_type": file_type,
            "row_count": df.height,
            "columns": df.columns,
            "size_bytes": os.path.getsize(fpath),
            "checksum_verified": check_shard_checksum(fpath),
        })
    return catalog


def main() -> None:
    args = parse_args()
    os.makedirs(args.facts_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    catalog = build_catalog(args.archive)
    catalog_path = os.path.join(args.facts_dir, "catalog.json")
    with open(catalog_path, "w") as f:
        json.dump(catalog, f, indent=2)


if __name__ == "__main__":
    main()
PYEOF

python /app/recover.py \
    --archive /app/archive \
    --facts-dir /app/facts \
    --policy /app/policy/recover.rego \
    --output-dir /app/output
