# Third-Party Notices

`pfc-fluentbit` (the Fluent Bit forwarder daemon) uses **only Python standard library** modules
and bundles no third-party code.

The following external components are required at runtime but are **not bundled**
in this repository — they are installed separately by the user:

## Fluent Bit
- **License:** Apache License 2.0
- **Source:** https://github.com/fluent/fluent-bit
- **Usage:** Log collection and forwarding. This project adds a TCP output target for Fluent Bit.

## PFC-JSONL Binary (`pfc_jsonl`)
- **License:** Proprietary — ImpossibleForge
- **Source:** https://github.com/ImpossibleForge/pfc-jsonl (binary releases)
- **Usage:** Compression engine called via subprocess. Not bundled, not modified.

## Python Standard Library
- **License:** Python Software Foundation License (PSF-2.0)
- **Usage:** `json`, `os`, `subprocess`, `threading`, `socketserver`, `argparse`, `time`, `tempfile`
