"""
Milestone 1 tests: Polars archive scan produces /app/facts/catalog.json
with correct schema, row counts, column lists, and checksum verification.
"""

import hashlib
import json
import os
import subprocess
import sys

import polars as pl
import pytest

ARCHIVE = "/app/archive"
FACTS_DIR = "/app/facts"
CATALOG_JSON = os.path.join(FACTS_DIR, "catalog.json")
CLI = [sys.executable, "/app/recover.py"]


class TestMilestone1:

    @pytest.fixture(autouse=True)
    def run_cli(self):
        result = subprocess.run(
            CLI + ["--archive", ARCHIVE, "--facts-dir", FACTS_DIR,
                   "--policy", "/app/policy/recover.rego", "--output-dir", "/app/output"],
            capture_output=True, text=True,
        )
        assert result.returncode in (0, 2), (
            f"CLI failed (exit {result.returncode}):\n{result.stderr}"
        )

    def _load(self):
        with open(CATALOG_JSON) as f:
            return json.load(f)

    def test_catalog_json_exists(self):
        """catalog.json must be created at /app/facts/catalog.json."""
        assert os.path.exists(CATALOG_JSON), f"Missing: {CATALOG_JSON}"

    def test_catalog_is_nonempty_array(self):
        """catalog.json must be a non-empty JSON array."""
        catalog = self._load()
        assert isinstance(catalog, list) and len(catalog) > 0

    def test_catalog_entries_have_required_fields(self):
        """Every catalog entry must have all six required fields with correct types."""
        catalog = self._load()
        required = {"path", "file_type", "row_count", "columns", "size_bytes", "checksum_verified"}
        for entry in catalog:
            missing = required - entry.keys()
            assert not missing, f"Entry missing fields {missing}: {entry}"
            assert entry["file_type"] in ("parquet", "csv")
            assert isinstance(entry["row_count"], int) and entry["row_count"] >= 0
            assert isinstance(entry["columns"], list)
            assert isinstance(entry["size_bytes"], int) and entry["size_bytes"] > 0
            assert isinstance(entry["checksum_verified"], bool)

    def test_catalog_row_counts_match_polars(self):
        """Row counts in catalog.json must match what Polars reads from each file."""
        for entry in self._load():
            path = entry["path"]
            assert os.path.exists(path), f"Catalog references missing file: {path}"
            df = pl.read_parquet(path) if entry["file_type"] == "parquet" else pl.read_csv(path)
            assert entry["row_count"] == df.height, (
                f"{path}: catalog={entry['row_count']} polars={df.height}"
            )
            assert sorted(entry["columns"]) == sorted(df.columns), (
                f"{path}: columns mismatch"
            )

    def test_catalog_checksum_verified_accuracy(self):
        """checksum_verified must be True iff a matching .sha256 file exists."""
        for entry in self._load():
            path = entry["path"]
            sha_path = path + ".sha256"
            if not os.path.exists(sha_path):
                assert entry["checksum_verified"] is False, (
                    f"{path}: no .sha256 exists, checksum_verified must be False"
                )
            else:
                with open(sha_path) as f:
                    expected = f.readline().strip().split()[0]
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                actual = h.hexdigest()
                assert entry["checksum_verified"] == (expected == actual), (
                    f"{path}: checksum_verified mismatch"
                )

    def test_catalog_only_contains_data_files(self):
        """catalog.json must not include .yaml or .sha256 files."""
        for entry in self._load():
            assert not entry["path"].endswith(".yaml"), "YAML files must not appear in catalog"
            assert not entry["path"].endswith(".sha256"), ".sha256 files must not appear in catalog"
