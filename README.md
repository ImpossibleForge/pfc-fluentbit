# pfc-fluentbit — PFC-JSONL Output for Fluent Bit

You're already using Fluent Bit to collect logs. But when you want to query them later, you hit the wall: decompress everything first, or pay for Athena/BigQuery to do it for you.

**pfc-fluentbit** routes Fluent Bit output into compressed `.pfc` archives that DuckDB can query directly — skipping only the blocks outside your time window, leaving everything else untouched on disk.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ImpossibleForge/pfc-fluentbit/blob/main/LICENSE)
[![Fluent Bit](https://img.shields.io/badge/Fluent%20Bit-3.x-green.svg)](https://fluentbit.io)
[![Version](https://img.shields.io/badge/Version-1.0.1-orange.svg)]()
[![DuckDB](https://img.shields.io/badge/DuckDB-Community%20Extension-orange.svg)](https://github.com/ImpossibleForge/pfc-duckdb)

> **Free for personal and open-source use** — no account, no signup, no daily limits.
> Commercial use requires a license: [info@impossibleforge.com](mailto:info@impossibleforge.com)

---

## Why switch from gzip?

| | gzip / zstd | **PFC-JSONL** |
|---|---|---|
| Compression | ~12–14% | **~9%** (25–37% smaller) |
| Query one hour from a 30-day archive | Decompress everything | **Decompress 1 block, skip 719** |
| Query in DuckDB | ❌ Not possible | ✅ `read_pfc_jsonl()` |
| Works with Fluent Bit | ✅ | ✅ (this repo) |

A 30-day log archive compressed with gzip means downloading and decompressing the entire thing just to look at one hour of errors. PFC-JSONL stores a block index alongside every archive — DuckDB reads the index, skips irrelevant blocks, and decompresses only what you asked for.

**The pipeline:**

---

## How It Works

```
Your Services
     |
     v
Fluent Bit (collect, filter, enrich)
     |
     | TCP json_lines  (port 5170)
     v
pfc_forwarder.py  <-- this repo
     |  buffers records in memory
     |  compresses when threshold reached
     v
/var/log/pfc/logs_20260404_1400.pfc       <- compressed archive
/var/log/pfc/logs_20260404_1400.pfc.bidx  <- block index for DuckDB
```

The forwarder is a **lightweight Python daemon** (standard library only, no pip installs).
It receives JSON log records over TCP, buffers them, and calls the `pfc_jsonl` binary to compress.

---

## Quick Start

### Step 1 — Install pfc_jsonl binary

```bash
# Linux x64:
curl -L https://github.com/ImpossibleForge/pfc-jsonl/releases/latest/download/pfc_jsonl-linux-x64 \
     -o /usr/local/bin/pfc_jsonl && chmod +x /usr/local/bin/pfc_jsonl

# macOS (Apple Silicon M1–M4):
curl -L https://github.com/ImpossibleForge/pfc-jsonl/releases/latest/download/pfc_jsonl-macos-arm64 \
     -o /usr/local/bin/pfc_jsonl && chmod +x /usr/local/bin/pfc_jsonl
```

> **macOS Intel (x64):** Binary coming soon.
> **Windows:** No native binary. Use WSL2 or a Linux machine.

### Step 2 — Start the forwarder

```bash
# Download
curl -L https://raw.githubusercontent.com/ImpossibleForge/pfc-fluentbit/main/pfc_forwarder.py \
     -o /opt/pfc_forwarder.py

# Run (will create /var/log/pfc/ automatically)
python3 /opt/pfc_forwarder.py
```

Default: listens on port `5170`, rotates every **32 MB** or **1 hour**.

### Step 3 — Point Fluent Bit at it

Add to your Fluent Bit config:

```ini
[OUTPUT]
    Name    tcp
    Match   *
    Host    127.0.0.1
    Port    5170
    Format  json_lines
```

That's it. Archives appear in `/var/log/pfc/` automatically.

---

## Configuration

```bash
python3 pfc_forwarder.py \
  --port        5170                     # TCP port (default: 5170)
  --output-dir  /var/log/pfc             # Where to write .pfc archives
  --buffer-mb   32                       # Rotate after N MB (default: 32)
  --rotate-secs 3600                     # Rotate after N seconds (default: 3600 = 1h)
  --pfc-binary  /usr/local/bin/pfc_jsonl # Path to pfc_jsonl binary
```

---

---

## Querying Archives with DuckDB

The `.pfc.bidx` index enables fast time-range queries without reading entire files:

```sql
INSTALL pfc FROM community;
LOAD pfc;
LOAD json;

-- Query one hour of logs
SELECT
    line->>'$.level'   AS level,
    line->>'$.service' AS service,
    line->>'$.message' AS message
FROM read_pfc_jsonl(
    '/var/log/pfc/logs_20260404_1400.pfc',
    ts_from = epoch(TIMESTAMPTZ '2026-04-04 14:00:00+00'),
    ts_to   = epoch(TIMESTAMPTZ '2026-04-04 15:00:00+00')
);
```

Only the relevant blocks are decompressed — the rest is never read.

See [pfc-duckdb](https://github.com/ImpossibleForge/pfc-duckdb) for the full DuckDB extension.

---

## Docker Compose

See [`examples/docker-compose.yml`](examples/docker-compose.yml) for a complete setup with Fluent Bit collecting container logs.

---

## Troubleshooting

**`ERROR: pfc_jsonl binary not found`**
Run the Step 1 install command above.

**`Address already in use: port 5170`**
Another process is on that port. Use `--port 5171` or kill the old process.

**Archives are bigger than input**
Buffer size is too small — data compresses poorly at < 1 MB. Use the default `--buffer-mb 32` in production.

---

## Migrate Existing Archives

Already have years of logs compressed with gzip, zstd, or bzip2 — on disk, on S3, on Azure, or on GCS?

**[pfc-migrate](https://github.com/ImpossibleForge/pfc-migrate)** converts them in one command, in-region (no egress charges):

```bash
pip install pfc-migrate[all]

# Local directory
pfc-migrate convert --dir /var/log/old-archive/ --output-dir /var/log/pfc/ -v

# S3 bucket (converts in-region)
pfc-migrate s3 --bucket my-logs --prefix 2025/ --out-bucket my-logs-pfc --out-prefix pfc/
```

After conversion, DuckDB can query them directly via the [`pfc` extension](https://github.com/ImpossibleForge/pfc-duckdb) — no decompression needed.

---

## Python Integration

Use the [pfc Python package](https://github.com/ImpossibleForge/pfc-py) to read or query `.pfc` archives from Python scripts:

```bash
pip install pfc-jsonl
```

```python
import pfc

# Query the archives written by pfc_forwarder
pfc.query("/var/log/pfc/logs_20260404_1400.pfc",
          from_ts="2026-04-04T14:30:00",
          to_ts="2026-04-04T14:45:00",
          output_path="/tmp/15min.jsonl")
```

---


## Related repos

- [pfc-jsonl](https://github.com/ImpossibleForge/pfc-jsonl) — core binary (compress/decompress/query)
- [pfc-gateway](https://github.com/ImpossibleForge/pfc-gateway) — HTTP REST gateway — ingest + query, no DuckDB
- [pfc-vector](https://github.com/ImpossibleForge/pfc-vector) — high-performance Rust ingest daemon for Vector.dev and Telegraf
- [pfc-migrate](https://github.com/ImpossibleForge/pfc-migrate) — one-shot export and archive conversion
- [pfc-py](https://github.com/ImpossibleForge/pfc-py) — Python client library for PFC
- [pfc-duckdb](https://github.com/ImpossibleForge/pfc-duckdb) — DuckDB extension for SQL queries on PFC files

---

## License

**pfc-fluentbit** (this repository) is released under the **MIT License** — see [LICENSE](https://github.com/ImpossibleForge/pfc-fluentbit/blob/main/LICENSE).

The **PFC-JSONL binary** (`pfc_jsonl`) is proprietary software — free for personal and open-source use.
Commercial use requires a license: [info@impossibleforge.com](mailto:info@impossibleforge.com)

---

*Built by [ImpossibleForge](https://github.com/ImpossibleForge)*
