#!/bin/bash
set -euo pipefail

# Milestone 2: Extend /app/recover.py with DuckDB query -> /app/facts/opa_input.json

cat > /app/recover.py << 'PYEOF'
#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys
from typing import Any

import duckdb
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


def build_opa_input(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    con = duckdb.connect()
    con.execute("CREATE TABLE catalog AS SELECT * FROM read_json_auto(?)", [catalog])
    required_json = json.dumps(REQUIRED_COLUMNS)
    rows = con.execute(f"""
        SELECT
            path,
            file_type,
            row_count,
            checksum_verified,
            size_bytes,
            (
                SELECT COUNT(*)
                FROM (SELECT UNNEST(columns) AS col) t
                WHERE col IN (SELECT UNNEST(CAST({required_json!r} AS VARCHAR[])))
            ) = {len(REQUIRED_COLUMNS)} AS has_required_columns
        FROM catalog
        ORDER BY path
    """).fetchall()
    shards = []
    for row in rows:
        path, file_type, row_count, checksum_verified, size_bytes, has_req = row
        shards.append({
            "path": path,
            "file_type": file_type,
            "row_count": int(row_count),
            "has_required_columns": bool(has_req),
            "checksum_verified": bool(checksum_verified),
            "size_bytes": int(size_bytes),
        })
    con.close()
    return {"shards": shards, "required_columns": REQUIRED_COLUMNS, "min_rows": MIN_ROWS}


def main() -> None:
    args = parse_args()
    os.makedirs(args.facts_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    catalog = build_catalog(args.archive)
    catalog_path = os.path.join(args.facts_dir, "catalog.json")
    with open(catalog_path, "w") as f:
        json.dump(catalog, f, indent=2)

    opa_input = build_opa_input(catalog)
    opa_input_path = os.path.join(args.facts_dir, "opa_input.json")
    with open(opa_input_path, "w") as f:
        json.dump(opa_input, f, indent=2)


if __name__ == "__main__":
    main()
PYEOF

python /app/recover.py \
    --archive /app/archive \
    --facts-dir /app/facts \
    --policy /app/policy/recover.rego \
    --output-dir /app/output
