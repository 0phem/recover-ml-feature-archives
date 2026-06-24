"""
Generate the ChurnShield feature archive for the task environment.
Creates /app/archive with a realistic mix of:
  - valid Parquet shards (with all required columns)
  - valid CSV shards
  - a shard missing required columns
  - a shard with too few rows
  - correct .sha256 files for valid shards
  - a deliberately wrong .sha256 for one shard (tampered)
  - .yaml descriptor files for each shard
"""
import hashlib
import os
import random

import polars as pl
import yaml

ARCHIVE = "/app/archive"
os.makedirs(ARCHIVE, exist_ok=True)

REQUIRED_COLS = ["customer_id", "tenure", "monthly_charges", "label"]
MIN_ROWS = 500

random.seed(42)


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sha256(shard_path: str, corrupt: bool = False) -> None:
    digest = sha256_of_file(shard_path)
    if corrupt:
        digest = ("0" if digest[0] != "0" else "1") + digest[1:]
    filename = os.path.basename(shard_path)
    sha_path = shard_path + ".sha256"
    with open(sha_path, "w") as f:
        f.write(f"{digest}  {filename}\n")


def write_yaml(shard_path: str, note: str = "") -> None:
    name = os.path.splitext(os.path.basename(shard_path))[0]
    desc = {
        "shard_name": name,
        "source": "churnshield_export_v2",
        "note": note or "Auto-exported feature shard.",
        "pipeline": "churnshield-train",
    }
    yaml_path = os.path.join(ARCHIVE, name + ".yaml")
    with open(yaml_path, "w") as f:
        yaml.dump(desc, f)


def make_churn_rows(n: int, seed: int = 42) -> dict:
    rng = random.Random(seed)
    return {
        "customer_id": [f"CUST_{i:06d}" for i in range(n)],
        "tenure": [rng.randint(1, 72) for _ in range(n)],
        "monthly_charges": [round(rng.uniform(20.0, 120.0), 2) for _ in range(n)],
        "label": [rng.randint(0, 1) for _ in range(n)],
    }


# Shard A — valid Parquet, all required columns, 1200 rows, good checksum
shard_a = os.path.join(ARCHIVE, "shard_a.parquet")
df_a = pl.DataFrame(make_churn_rows(1200, seed=1))
df_a.write_parquet(shard_a)
write_sha256(shard_a)
write_yaml(shard_a, note="Main training shard, fully verified.")

# Shard B — valid CSV, all required columns, 800 rows, good checksum
shard_b = os.path.join(ARCHIVE, "shard_b.csv")
df_b = pl.DataFrame(make_churn_rows(800, seed=2))
df_b.write_csv(shard_b)
write_sha256(shard_b)
write_yaml(shard_b, note="CSV fallback shard from secondary export.")

# Shard C — valid Parquet, all required columns, 600 rows, BAD checksum
shard_c = os.path.join(ARCHIVE, "shard_c.parquet")
df_c = pl.DataFrame(make_churn_rows(600, seed=3))
df_c.write_parquet(shard_c)
write_sha256(shard_c, corrupt=True)
write_yaml(shard_c, note="Checksum mismatch — possible corruption.")

# Shard D — valid Parquet, MISSING 'label' column, 900 rows, good checksum
shard_d = os.path.join(ARCHIVE, "shard_d.parquet")
df_d = pl.DataFrame({
    "customer_id": [f"CUST_{i:06d}" for i in range(900)],
    "tenure": [random.randint(1, 72) for _ in range(900)],
    "monthly_charges": [round(random.uniform(20.0, 120.0), 2) for _ in range(900)],
})
df_d.write_parquet(shard_d)
write_sha256(shard_d)
write_yaml(shard_d, note="Label column missing — incomplete export.")

# Shard E — valid CSV, all required columns, 120 rows, good checksum
shard_e = os.path.join(ARCHIVE, "shard_e.csv")
df_e = pl.DataFrame(make_churn_rows(120, seed=5))
df_e.write_csv(shard_e)
write_sha256(shard_e)
write_yaml(shard_e, note="Undersized shard from partial export run.")

# Shard F — valid Parquet, all required columns, 750 rows, no .sha256
shard_f = os.path.join(ARCHIVE, "shard_f.parquet")
df_f = pl.DataFrame(make_churn_rows(750, seed=6))
df_f.write_parquet(shard_f)
write_yaml(shard_f, note="No checksum file present — provenance unknown.")

print("Archive setup complete.")
for fname in sorted(os.listdir(ARCHIVE)):
    print(f"  {fname}")
