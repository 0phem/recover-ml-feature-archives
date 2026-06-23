Wire up the final enforcement step in `/app/recover.py`. It should evaluate the Rego policy at `/app/policy/recover.rego` against `/app/facts/opa_input.json` using the `opa eval` CLI and write the raw result to `/app/output/decision.json`.

After that, print the recoverable shard paths to stdout (one per line, lexicographically sorted) and print any denial messages to stderr prefixed with `DENY:`. Exit with code 2 if there are any denials, 0 otherwise.

The script must be callable as:

```
python /app/recover.py --archive /app/archive --facts-dir /app/facts --policy /app/policy/recover.rego --output-dir /app/output
```

All four args must accept custom paths and create output directories if missing.
