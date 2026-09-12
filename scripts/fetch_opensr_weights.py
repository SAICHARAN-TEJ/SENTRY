"""Fetch the OpenSR LDSR-S2 checkpoint pinned by opensr-model v1.1.1.

Downloads ``opensr-ldsrs2_v1_0_0.ckpt`` (the ``ckpt_version`` referenced by the
pinned config) from the Hugging Face model hub into ``data/opensr/``, prints the
SHA-256 for the provenance record (SOURCES.md / ``model_versions.checksum``),
and skips the download when a file with the correct hash already exists.
A stale ``.part`` file resumes via HTTP Range instead of restarting.

Usage:
    python scripts/fetch_opensr_weights.py
    python scripts/fetch_opensr_weights.py --dest DIR
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

HF_BASE = "https://huggingface.co/simon-donike/RS-SR-LTDF/resolve/main"
CHECKPOINT = "opensr-ldsrs2_v1_0_0.ckpt"
USER_AGENT = "Sentry-SIH26142/0.1 (OpenSR LDSR-S2 checkpoint fetch)"
CHUNK = 1 << 20  # 1 MiB


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    """Stream the checkpoint to dest, resuming an existing ``.part`` file."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    headers = {"User-Agent": USER_AGENT}
    mode = "wb"
    if tmp.exists() and tmp.stat().st_size > 0:
        headers["Range"] = f"bytes={tmp.stat().st_size}-"
        mode = "ab"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status == 200 and mode == "ab":
            mode = "wb"  # server ignored Range: restart rather than append
        with open(tmp, mode) as fh:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
    tmp.replace(dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch pinned LDSR-S2 weights")
    parser.add_argument("--dest", default=str(REPO / "data" / "opensr"),
                        help="download directory (default data/opensr)")
    args = parser.parse_args(argv)

    dest_dir = Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / CHECKPOINT
    url = f"{HF_BASE}/{CHECKPOINT}"

    if target.exists():
        digest = sha256_file(target)
        print(f"EXISTS   {target} sha256={digest}")
        return 0

    print(f"FETCH    {url}")
    try:
        download(url, target)
    except Exception as exc:  # noqa: BLE001 - operator-facing report
        print(f"ERROR    {exc}", file=sys.stderr)
        print("         a partial .part file is kept and will resume on re-run",
              file=sys.stderr)
        return 1

    digest = sha256_file(target)
    size = target.stat().st_size
    print(f"OK       {CHECKPOINT} ({size:,} bytes)")
    print(f"SHA256   {digest}")
    print("Record this hash in SOURCES.md and model_versions.checksum.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
