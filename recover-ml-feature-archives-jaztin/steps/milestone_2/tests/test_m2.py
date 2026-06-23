"""
Milestone 2 tests: DuckDB query on catalog.json produces /app/facts/opa_input.json
with correct structure, has_required_columns logic, and OPA-compatible shape.
"""

import json
import os
import subprocess
import sys

import pytest

ARCHIVE = "/app/archive"
FACTS_DIR = "/app/facts"
CATALOG_JSON = os.path.join(FACTS_DIR, "catalog.json")
OPA_INPUT_JSON = os.path.join(FACTS_DIR, "opa_input.json")
REQUIRED_COLUMNS = ["customer_id", "tenure", "monthly_charges", "label"]
MIN_ROWS = 500
CLI = [sys.executable, "/app/recover.py"]


class TestMilestone2:

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

    def _load_opa(self):
        with open(OPA_INPUT_JSON) as f:
            return json.load(f)

    def _load_catalog(self):
        with open(CATALOG_JSON) as f:
            return json.load(f)

    def test_opa_input_json_exists(self):
        """opa_input.json must be created at /app/facts/opa_input.json."""
        assert os.path.exists(OPA_INPUT_JSON), f"Missing: {OPA_INPUT_JSON}"

    def test_opa_input_top_level_fields(self):
        """opa_input.json must contain shards, required_columns, and min_rows."""
        data = self._load_opa()
        assert "shards" in data
        assert "required_columns" in data
        assert "min_rows" in data
        assert data["required_columns"] == REQUIRED_COLUMNS
        assert data["min_rows"] == MIN_ROWS

    def test_opa_input_shard_fields(self):
        """Every shard entry must have the six OPA-required fields with correct types."""
        shards = self._load_opa()["shards"]
        assert len(shards) > 0
        required = {"path", "file_type", "row_count", "has_required_columns", "checksum_verified", "size_bytes"}
        for shard in shards:
            missing = required - shard.keys()
            assert not missing, f"Shard missing fields {missing}: {shard}"
            assert isinstance(shard["has_required_columns"], bool)
            assert isinstance(shard["checksum_verified"], bool)
            assert isinstance(shard["row_count"], int)

    def test_has_required_columns_logic(self):
        """has_required_columns must be True iff every required column is present in the shard."""
        catalog = {e["path"]: e for e in self._load_catalog()}
        for shard in self._load_opa()["shards"]:
            path = shard["path"]
            assert path in catalog, f"OPA shard {path} not in catalog"
            shard_cols = set(catalog[path]["columns"])
            expected = all(c in shard_cols for c in REQUIRED_COLUMNS)
            assert shard["has_required_columns"] == expected, (
                f"{path}: has_required_columns={shard['has_required_columns']} expected={expected}"
            )

    def test_shard_d_missing_label_column(self):
        """shard_d is missing the label column — has_required_columns must be False."""
        shards = {s["path"]: s for s in self._load_opa()["shards"]}
        shard_d = next((v for k, v in shards.items() if "shard_d" in k), None)
        assert shard_d is not None, "shard_d not found in opa_input shards"
        assert shard_d["has_required_columns"] is False, (
            "shard_d is missing 'label', has_required_columns must be False"
        )

    def test_shards_count_matches_catalog(self):
        """opa_input shards count must equal catalog entries count."""
        catalog = self._load_catalog()
        shards = self._load_opa()["shards"]
        assert len(shards) == len(catalog), (
            f"opa_input has {len(shards)} shards but catalog has {len(catalog)}"
        )
