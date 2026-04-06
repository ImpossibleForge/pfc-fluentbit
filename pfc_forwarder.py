#!/usr/bin/env python3
"""
PFC Forwarder - Fluent Bit TCP Output -> PFC-JSONL compressed archives
MIT License - https://github.com/ImpossibleForge/pfc-fluentbit

Receives JSON log records from Fluent Bit over TCP, buffers them,
and compresses to .pfc format using the pfc_jsonl binary.

Fluent Bit config:
  [OUTPUT]
      Name    tcp
      Match   *
      Host    127.0.0.1
      Port    5170
      Format  json_lines

Requirements:
  - Python 3.8+ (standard library only, no pip installs)
  - pfc_jsonl binary >= v3.4  (https://github.com/ImpossibleForge/pfc-jsonl)

License:
  Free for personal and open-source use.
  Commercial use requires a license — https://github.com/ImpossibleForge/pfc-jsonl
"""
import argparse, json, os, signal, subprocess, threading, time
from datetime import datetime, timezone
from socketserver import TCPServer, StreamRequestHandler

__version__ = "1.0.1"


def parse_args():
    p = argparse.ArgumentParser(
        description="PFC Forwarder - Fluent Bit TCP output to PFC-JSONL archives"
    )
    p.add_argument("--port",        type=int, default=5170,
                   help="TCP port to listen on (default: 5170)")
    p.add_argument("--output-dir",  default="/var/log/pfc",
                   help="Directory for .pfc archive files (default: /var/log/pfc)")
    p.add_argument("--buffer-mb",   type=int, default=32,
                   help="Compress after N MB of buffered data (default: 32)")
    p.add_argument("--rotate-secs", type=int, default=3600,
                   help="Compress after N seconds even if buffer not full (default: 3600)")
    p.add_argument("--pfc-binary",  default="/usr/local/bin/pfc_jsonl",
                   help="Path to pfc_jsonl binary (default: /usr/local/bin/pfc_jsonl)")
    p.add_argument("--version",     action="version", version=f"pfc_forwarder {__version__}")
    return p.parse_args()


class PFCBuffer:
    """Thread-safe in-memory buffer. Compresses to .pfc when threshold reached."""

    def __init__(self, cfg):
        self.cfg         = cfg
        self._lock       = threading.Lock()
        self._lines      = []
        self._size       = 0
        self._started_at = time.time()
        self._cycles     = 0

    def add(self, line: bytes):
        with self._lock:
            self._lines.append(line)
            self._size += len(line)
            if self._size >= self.cfg.buffer_mb * 1024 * 1024:
                self._rotate_locked()

    def tick(self):
        """Called by background timer - rotate on age even if buffer not full."""
        with self._lock:
            if self._size >= 10 * 1024 and (time.time() - self._started_at) >= self.cfg.rotate_secs:
                self._rotate_locked()

    def flush(self):
        """Flush remaining buffer on shutdown."""
        with self._lock:
            if self._size > 1024:
                self._rotate_locked()

    def _rotate_locked(self):
        if not self._lines:
            return
        lines = self._lines
        self._lines      = []
        self._size       = 0
        self._started_at = time.time()
        threading.Thread(target=self._compress, args=(lines,), daemon=True).start()

    def _compress(self, lines):
        cfg     = self.cfg
        ts      = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        staging = os.path.join(cfg.output_dir, f"_staging_{ts}.jsonl")
        out_pfc = os.path.join(cfg.output_dir, f"logs_{ts}.pfc")

        with open(staging, "wb") as f:
            for line in lines:
                f.write(line if line.endswith(b"\n") else line + b"\n")

        src_mb = os.path.getsize(staging) / 1024 / 1024
        t0     = time.time()
        result = subprocess.run(
            [cfg.pfc_binary, "compress", staging, out_pfc],
            capture_output=True, text=True
        )
        elapsed = time.time() - t0

        if result.returncode == 0:
            out_mb = os.path.getsize(out_pfc) / 1024 / 1024
            ratio  = out_mb / src_mb * 100 if src_mb > 0 else 0
            bidx   = "yes" if os.path.exists(out_pfc + ".bidx") else "NO"
            self._cycles += 1
            log(f"[compress #{self._cycles}] {src_mb:.1f} MB -> {out_mb:.1f} MB "
                f"({ratio:.1f}%) in {elapsed:.1f}s  bidx={bidx}  -> {os.path.basename(out_pfc)}")
            os.remove(staging)
        else:
            log(f"[compress] FAILED: {result.stderr[:300]}")
            os.rename(staging, staging.replace("_staging_", "_failed_"))


_buffer = None


class FluentBitHandler(StreamRequestHandler):
    def handle(self):
        peer  = f"{self.client_address[0]}:{self.client_address[1]}"
        count = 0
        log(f"[tcp] Connected: {peer}")
        try:
            for raw in self.rfile:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    json.loads(raw)
                except json.JSONDecodeError:
                    continue
                _buffer.add(raw + b"\n")
                count += 1
        except Exception as e:
            log(f"[tcp] Error {peer}: {e}")
        finally:
            log(f"[tcp] Disconnected: {peer}  ({count:,} lines)")


def _timer_loop():
    while True:
        time.sleep(min(10, _buffer.cfg.rotate_secs))
        _buffer.tick()


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts}  {msg}", flush=True)


def main():
    global _buffer
    cfg = parse_args()
    os.makedirs(cfg.output_dir, exist_ok=True)

    if not os.path.isfile(cfg.pfc_binary):
        print(f"ERROR: pfc_jsonl binary not found at {cfg.pfc_binary}")
        print("Install: curl -L https://github.com/ImpossibleForge/pfc-jsonl"
              "/releases/latest/download/pfc_jsonl-linux-x64"
              " -o /usr/local/bin/pfc_jsonl && chmod +x /usr/local/bin/pfc_jsonl")
        raise SystemExit(1)

    _buffer = PFCBuffer(cfg)

    log(f"PFC Forwarder v{__version__} starting")
    log(f"  Listen      : 0.0.0.0:{cfg.port}")
    log(f"  Output dir  : {cfg.output_dir}")
    log(f"  Rotate at   : {cfg.buffer_mb} MB or {cfg.rotate_secs}s")
    log(f"  PFC binary  : {cfg.pfc_binary}")
    log(f"  License     : Free for personal/open-source use")

    def _shutdown(signum=None, frame=None):
        log("Shutting down - flushing buffer...")
        _buffer.flush()
        time.sleep(3)
        log("Goodbye.")
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    threading.Thread(target=_timer_loop, daemon=True).start()

    TCPServer.allow_reuse_address = True
    with TCPServer(("0.0.0.0", cfg.port), FluentBitHandler) as server:
        log(f"Ready. Waiting for Fluent Bit on port {cfg.port}...")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log("Shutting down - flushing buffer...")
            _buffer.flush()
            time.sleep(3)
            log("Goodbye.")


if __name__ == "__main__":
    main()
