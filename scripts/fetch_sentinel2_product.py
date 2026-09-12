"""Checksum-verified download of one Copernicus Sentinel-2 product.

Downloads a single L2A product via the authenticated CDSE path (same flow as
``backend.copernicus.download_product``), verifies it against the catalogue's
official MD5 **before** the file is accepted, and keeps a resumable ``.part``
file so an interrupted multi-hundred-MB transfer continues instead of restarting.
A corrupted download can never enter the staging pipeline (PRD Phase 0 rule).

Usage:
    python scripts/fetch_sentinel2_product.py \
        --product-id 0ad3fe38-5b2a-46c9-9c93-08e22084b52b \
        --md5 c87bd6943db17c619567bacf0f392f47
    # or, with the descriptor written by the search step:
    python scripts/fetch_sentinel2_product.py --from data/target_product.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import httpx  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.copernicus import _access_token, DOWNLOAD_URL, USER_AGENT  # noqa: E402

CHUNK = 1 << 20  # 1 MiB


def md5_file(path: Path) -> str:
    """Streamed MD5 so ~1 GB products never sit in memory."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_prefix(path: Path) -> "hashlib._Hash":
    """MD5 state seeded from an existing partial file (for Range resume)."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h


def download(product_id: str, dest: Path) -> Path:
    """Stream the product zip to ``dest`` (``.part`` while in flight)."""
    settings = get_settings()
    username, password = settings.copernicus_username, settings.copernicus_password
    if not username or not password:
        print("ERROR: set COPERNICUS_USERNAME/COPERNICUS_PASSWORD (see .env / SOURCES.md)",
              file=sys.stderr)
        sys.exit(2)

    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    token = _access_token(username, password)
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    digest = hashlib.md5()
    mode = "wb"

    if tmp.exists() and tmp.stat().st_size > 0:
        headers["Range"] = f"bytes={tmp.stat().st_size}-"
        digest = md5_prefix(tmp)
        mode = "ab"
        print(f"RESUME   from {tmp.stat().st_size:,} bytes")

    with httpx.stream("GET", DOWNLOAD_URL.format(product_id=product_id),
                      headers=headers, follow_redirects=True,
                      timeout=httpx.Timeout(3600.0, connect=30.0)) as resp:
        if resp.status_code == 200 and mode == "ab":
            mode = "wb"      # server ignored Range: restart cleanly
            digest = hashlib.md5()
        elif resp.status_code != 206:
            resp.raise_for_status()
        print(f"HTTP     {resp.status_code} | content-length: "
              f"{resp.headers.get('content-length', '?')}")
        with open(tmp, mode) as fh:
            for chunk in resp.iter_bytes(chunk_size=CHUNK):
                fh.write(chunk)
                digest.update(chunk)

    actual = digest.hexdigest()
    tmp.replace(dest)
    print(f"MD5      {actual}")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product-id", help="OData product GUID")
    parser.add_argument("--md5", help="official MD5 from the catalogue (expected)")
    parser.add_argument("--from", dest="descriptor",
                        default=str(REPO / "data" / "target_product.json"),
                        help="JSON with product_id/md5 (default data/target_product.json)")
    parser.add_argument("--dest-dir", default=str(REPO / "data" / "copernicus"))
    args = parser.parse_args(argv)

    if args.product_id and args.md5:
        product_id, expected_md5 = args.product_id, args.md5
    else:
        info = json.loads(Path(args.descriptor).read_text())
        product_id, expected_md5 = info["product_id"], info.get("md5")
        print(f"TARGET   {info.get('name', product_id)}")
    if not expected_md5:
        print("ERROR: no expected MD5 available; refusing to download unverified",
              file=sys.stderr)
        return 2

    dest = Path(args.dest_dir) / f"{product_id}.zip"
    if dest.exists():
        actual = md5_file(dest)
        if actual == expected_md5:
            print(f"OK       {dest} already verified ({actual})")
            return 0
        print(f"MISMATCH on existing file ({actual}); re-downloading", file=sys.stderr)
        dest.unlink()

    try:
        download(product_id, dest)
    except Exception as exc:  # noqa: BLE001 - operator-facing report
        print(f"ERROR    {exc}", file=sys.stderr)
        print("         partial .part kept; re-run to resume", file=sys.stderr)
        return 1

    actual = md5_file(dest)
    if actual != expected_md5.lower():
        print(f"FAILED   md5 {actual} != catalogue {expected_md5} — deleting corrupt file",
              file=sys.stderr)
        dest.unlink()
        return 1
    print(f"VERIFIED {dest} ({dest.stat().st_size:,} bytes) matches catalogue MD5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
