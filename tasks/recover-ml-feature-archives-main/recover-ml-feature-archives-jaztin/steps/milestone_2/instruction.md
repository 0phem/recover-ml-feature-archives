Now that `/app/facts/catalog.json` exists, extend `/app/recover.py` to query it using DuckDB and produce a second facts file at `/app/facts/opa_input.json` in the shape the OPA policy at `/app/policy/recover.rego` expects.

The output must include a `shards` array (one entry per shard from the catalog), a `required_columns` list, and a `min_rows` value. Each shard entry needs a `has_required_columns` field — true only if all of `["customer_id", "tenure", "monthly_charges", "label"]` are present in that shard's columns. Use `500` as the minimum row threshold. The DuckDB query must drive the `has_required_columns` computation, not Python-side logic.

The archive of shards is located at `/app/archive`. The Rego policy used in later milestones is at `/app/policy/recover.rego`.

Output files produced by this milestone:
- `/app/facts/catalog.json` — shard catalog array (carried over from milestone 1)
- `/app/facts/opa_input.json` — OPA-compatible input document
