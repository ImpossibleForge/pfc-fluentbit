# pfc-fluentbit — PFC-JSONL Output for Fluent Bit

Stream logs from Fluent Bit directly to compressed `.pfc` archives — **26–34% smaller than gzip/zstd**, with block-level random access for fast queries.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Fluent Bit](https://img.shields.io/badge/Fluent%20Bit-3.x-green.svg)](https://fluentbit.io)
[![Version](https://img.shields.io/badge/Version-1.0-orange.svg)]()

---

## Why?

| Tool | Compression | Random Access | Query in DuckDB |
|------|-------------|---------------|-----------------|
| **PFC-JSONL** | **~10%** | Block-level (`.bidx` index) | `read_pfc_jsonl()` |
| gzip | ~14.5% | Full file only | No |
| zstd | ~16% | Full file only | No |

**PFC-JSONL is 26–34% smaller than gzip on typical structured log data.**
Archives include a `.pfc.bidx` block index — query only the hours you need, not entire files.

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
curl -L https://github.com/ImpossibleForge/pfc-jsonl/releases/latest/download/pfc_jsonl-linux-x64 \
     -o /usr/local/bin/pfc_jsonl && chmod +x /usr/local/bin/pfc_jsonl
```

> **macOS:** coming soon — contact **impossibleforge@gmail.com** for early access.

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

## Community Mode

The `pfc_jsonl` binary includes a built-in free tier — **no account, no signup**:

| | Community | Licensed |
|-|-----------|----------|
| Daily limit | 5 GB/day | Unlimited |
| License key | not required | required |
| Phone home | never | never |

Usage is tracked locally in `~/.pfc/usage.json`. Nothing leaves your machine.
`compress` counts **input bytes**; `decompress`, `query`, `seek-blocks` count **decompressed output bytes**.

For production workloads > 5 GB/day: [impossibleforge@gmail.com](mailto:impossibleforge@gmail.com)

---

## Querying Archives with DuckDB

The `.pfc.bidx` index enables fast time-range queries without reading entire files:

> **Status:** DuckDB extension pending review ([PR #1679](https://github.com/duckdb/community-extensions/pull/1679)). Once merged:

```sql
-- Once available in DuckDB community extensions:
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

**`PFC Community Mode daily limit reached`**
5 GB/day exceeded. Wait until midnight UTC or [get a license](mailto:impossibleforge@gmail.com).

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

## License

**pfc-fluentbit** (this repository) is released under the **MIT License** — see [LICENSE](LICENSE).

The **PFC-JSONL binary** (`pfc_jsonl`) is **proprietary software** — Community Mode provides 5 GB/day free.
Commercial licenses: [impossibleforge@gmail.com](mailto:impossibleforge@gmail.com)

---

*Built by [ImpossibleForge](https://github.com/ImpossibleForge)*
