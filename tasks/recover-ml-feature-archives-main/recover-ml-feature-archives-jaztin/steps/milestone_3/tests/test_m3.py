"""
Milestone 3 tests: OPA eval produces decision.json, stdout lists recoverable shards
in lexicographic order, stderr carries DENY messages, and exit code is 2 when denials exist.
"""

import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile

import polars as pl
import pytest

ARCHIVE = "/app/archive"
FACTS_DIR = "/app/facts"
POLICY = "/app/policy/recover.rego"
OUTPUT_DIR = "/app/output"
DECISION_JSON = os.path.join(OUTPUT_DIR, "decision.json")
CLI = [sys.executable, "/app/recover.py"]


def run_cli(archive=ARCHIVE, facts_dir=FACTS_DIR, policy=POLICY, output_dir=OUTPUT_DIR):
    return subprocess.run(
        CLI + ["--archive", archive, "--facts-dir", facts_dir,
               "--policy", policy, "--output-dir", output_dir],
        capture_output=True, text=True,
    )


class TestMilestone3:

    @pytest.fixture(autouse=True)
    def run_default(self):
        result = run_cli()
        assert result.returncode in (0, 2), (
            f"CLI failed (exit {result.returncode}):\n{result.stderr}"
        )

    def test_decision_json_exists(self):
        """decision.json must be written to /app/output/decision.json."""
        assert os.path.exists(DECISION_JSON), f"Missing: {DECISION_JSON}"

    def test_decision_json_has_opa_structure(self):
        """decision.json must contain a valid OPA eval result with recoverable and deny sets."""
        with open(DECISION_JSON) as f:
            decision = json.load(f)
        assert "result" in decision
        assert isinstance(decision["result"], list) and len(decision["result"]) > 0
        value = decision["result"][0]["expressions"][0]["value"]
        assert "recoverable" in value
        assert "deny" in value

    def test_only_shard_a_and_b_are_recoverable(self):
        """Only shard_a.parquet and shard_b.csv pass all three policy gates."""
        with open(DECISION_JSON) as f:
            decision = json.load(f)
        value = decision["result"][0]["expressions"][0]["value"]
        raw = value.get("recoverable", [])
        recoverable = set(raw.keys() if isinstance(raw, dict) else raw)
        expected = {
            os.path.join(ARCHIVE, "shard_a.parquet"),
            os.path.join(ARCHIVE, "shard_b.csv"),
        }
        assert recoverable == expected, f"Expected {expected}, got {recoverable}"

    def test_stdout_lists_recoverable_paths_sorted(self):
        """stdout must list recoverable paths one per line in lexicographic order."""
        result = run_cli()
        paths = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        assert len(paths) >= 1
        assert paths == sorted(paths), f"Paths not sorted: {paths}"
        for p in paths:
            assert os.path.exists(p), f"stdout path does not exist: {p}"

    def test_exit_code_2_with_denials(self):
        """CLI must exit with code 2 when the policy emits denial messages."""
        result = run_cli()
        assert result.returncode == 2, (
            f"Expected exit code 2 (denials present), got {result.returncode}"
        )

    def test_stderr_has_deny_prefix(self):
        """Each denial message on stderr must be prefixed with DENY:"""
        result = run_cli()
        deny_lines = [line for line in result.stderr.splitlines() if line.startswith("DENY:")]
        assert len(deny_lines) >= 1, f"No DENY: lines on stderr. stderr={result.stderr}"
        assert "shard_c.parquet" in result.stderr or "shard_f.parquet" in result.stderr

    def test_custom_paths_respected(self):
        """All outputs must land in custom --facts-dir and --output-dir, not defaults."""
        with tempfile.TemporaryDirectory() as tmp:
            facts = os.path.join(tmp, "facts")
            output = os.path.join(tmp, "output")
            result = run_cli(facts_dir=facts, output_dir=output)
            assert result.returncode in (0, 2)
            assert os.path.exists(os.path.join(facts, "catalog.json"))
            assert os.path.exists(os.path.join(facts, "opa_input.json"))
            assert os.path.exists(os.path.join(output, "decision.json"))

    def test_all_bad_archive_triggers_no_recoverable_denial(self):
        """An archive with no valid shards must produce 'No recoverable shards' denial and exit 2."""
        with tempfile.TemporaryDirectory() as tmp:
            bad_archive = os.path.join(tmp, "archive")
            facts = os.path.join(tmp, "facts")
            output = os.path.join(tmp, "output")
            os.makedirs(bad_archive)
            df = pl.DataFrame({
                "customer_id": [f"C{i}" for i in range(10)],
                "tenure": list(range(10)),
                "monthly_charges": [float(i) for i in range(10)],
                "label": [0] * 10,
            })
            df.write_parquet(os.path.join(bad_archive, "tiny.parquet"))
            result = run_cli(archive=bad_archive, facts_dir=facts, output_dir=output)
            assert result.returncode == 2
            deny_lines = [line for line in result.stderr.splitlines() if line.startswith("DENY:")]
            assert any("No recoverable shards" in line for line in deny_lines)

    def test_all_valid_archive_exits_zero(self):
        """An archive with only valid shards must exit 0 with no DENY messages."""
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "archive")
            facts = os.path.join(tmp, "facts")
            output = os.path.join(tmp, "output")
            os.makedirs(good)
            rng = random.Random(99)
            n = 600
            df = pl.DataFrame({
                "customer_id": [f"CUST_{i:06d}" for i in range(n)],
                "tenure": [rng.randint(1, 72) for _ in range(n)],
                "monthly_charges": [round(rng.uniform(20.0, 120.0), 2) for _ in range(n)],
                "label": [rng.randint(0, 1) for _ in range(n)],
            })
            shard = os.path.join(good, "good.parquet")
            df.write_parquet(shard)
            h = hashlib.sha256()
            with open(shard, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            with open(shard + ".sha256", "w") as fh:
                fh.write(f"{h.hexdigest()}  good.parquet\n")
            result = run_cli(archive=good, facts_dir=facts, output_dir=output)
            assert result.returncode == 0, f"stderr: {result.stderr}"
            assert not any(line.startswith("DENY:") for line in result.stderr.splitlines())
            assert shard in [line.strip() for line in result.stdout.strip().splitlines()]
