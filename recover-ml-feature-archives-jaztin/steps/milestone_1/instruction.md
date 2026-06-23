The ChurnShield training pipeline broke after a feature export lost its manifest. `/app/archive` now has a mix of Parquet and CSV shards, YAML descriptors, and `.sha256` checksum files with no record of which shards are safe to use.

Write a script at `/app/recover.py` that uses Polars to scan every Parquet and CSV file in `/app/archive` and produces a catalog at `/app/facts/catalog.json`. Each entry should describe one shard: its absolute path, file type, row count, column names, file size in bytes, and whether its checksum is verified. A shard is checksum-verified only if a `.sha256` file exists for it and the hex digest on the first line matches the actual SHA-256 of the shard file.

Create `/app/facts/` if it doesn't exist. Corrupt or unreadable shards should be skipped with a warning to stderr.
