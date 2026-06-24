#!/bin/bash
set -euo pipefail

# Milestone 3: Full recover.py with OPA eval, training manifest stdout, DENY stderr, exit codes

cat > /app/recover.py << 'PYEOF'
#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
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


def build_opa_input(catalog):
    import tempfile, os
    con = duckdb.connect()
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write(json.dumps(catalog))
    tmp.flush()
    tmp.close()
    con.execute(f"CREATE TABLE catalog AS SELECT * FROM read_json_auto(\'{tmp.name}\')")
    os.unlink(tmp.name)
    required = REQUIRED_COLUMNS
    rows = con.execute("SELECT path, file_type, row_count, checksum_verified, size_bytes, columns FROM catalog ORDER BY path").fetchall()
    shards = []
    for row in rows:
        path, file_type, row_count, checksum_verified, size_bytes, columns = row
        has_req = all(c in columns for c in required)
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


def run_opa_eval(policy_path: str, input_path: str, output_path: str) -> dict[str, Any]:
    query = "data.churnshield.recover"
    cmd = ["opa", "eval", "--v1-compatible", "--format", "json", "--input", input_path, "--data", policy_path, query]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in (0, 2):
        raise RuntimeError(f"opa eval failed (exit {result.returncode}):\n{result.stderr}")
    decision = json.loads(result.stdout)
    with open(output_path, "w") as f:
        json.dump(decision, f, indent=2)
    return decision


def extract_results(decision: dict[str, Any]) -> tuple[list[str], list[str]]:
    try:
        value = decision["result"][0]["expressions"][0]["value"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected OPA output structure: {exc}")
    raw_recoverable = value.get("recoverable", [])
    recoverable = sorted(raw_recoverable.keys() if isinstance(raw_recoverable, dict) else raw_recoverable)
    raw_deny = value.get("deny", [])
    deny_messages = sorted(raw_deny.keys() if isinstance(raw_deny, dict) else raw_deny)
    return recoverable, deny_messages


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

    decision_path = os.path.join(args.output_dir, "decision.json")
    decision = run_opa_eval(args.policy, opa_input_path, decision_path)

    recoverable, deny_messages = extract_results(decision)
    for path in recoverable:
        print(path)

    if deny_messages:
        for msg in deny_messages:
            print(f"DENY: {msg}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"RuntimeError: {exc}", file=sys.stderr)
        sys.exit(1)
PYEOF

python /app/recover.py \
    --archive /app/archive \
    --facts-dir /app/facts \
    --policy /app/policy/recover.rego \
    --output-dir /app/output
