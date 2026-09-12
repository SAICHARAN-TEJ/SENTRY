"""Checksum-verified, resumable downloader for PRD Phase 0 source-lock artifacts.

Downloads the WorldStrat v1.1 initial set (and optionally the extra archives) into
``data/worldstrat/`` and verifies every file against the MD5 manifest recorded in
SOURCES.md. Any mismatch fails loudly with a non-zero exit so a corrupted download
can never silently enter the training/validation pipeline.

Usage:
    python scripts/fetch_sources.py                  # required files only
    python scripts/fetch_sources.py --with-optional  # include L1C + raw HR archives
    python scripts/fetch_sources.py --verify-only    # check hashes, download nothing
    python scripts/fetch_sources.py --dest DIR       # override destination
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

RECORD_URL = "https://zenodo.org/api/records/15382551/files/{key}/content"

# Manifest mirrored from SOURCES.md (verified against Zenodo 2026-09-12).
WORLDSTRAT_FILES: dict[str, dict] = {
    "LICENSE.txt": {"md5": "d97b8d86da83f7e51f2d3205509e4a7b", "optional": False},
    "metadata.csv": {"md5": "1a66ac42b9a688be18debd0d95633fa1", "optional": False},
    "stratified_train_val_test_split.csv": {
        "md5": "874612b59bbf7987f7de7edd48a30c70", "optional": False},
    "hr_dataset.zip": {
        "md5": "5ae09bb3557ce131242a133d9758d9e7", "optional": False},
    "lr_dataset_l2a.zip": {
        "md5": "7aa1878a37d22a6c7c4b84b022a14ad7", "optional": False},
    "lr_dataset_l1c.zip": {
        "md5": "e90ecfa4bf838ace0b51dea1031b5ed1", "optional": True},
    "hr_dataset_raw.zip": {
        "md5": "515f38e333bf06e79ac523fb2eab588d", "optional": True},
}

CHUNK = 1 << 20  # 1 MiB


def md5_file(path: Path) -> str:
    """Streamed MD5 so 38 GiB archives never sit in memory."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def download(key: str, dest: Path) -> None:
    """Stream one Zenodo file to dest, resuming from an existing ``.part`` file.

    Zenodo's content endpoint honors HTTP Range requests, so an interrupted
    multi-GiB download continues where it stopped instead of restarting. Any
    server that ignores Range answers 200; the partial file is then discarded
    and the download restarts cleanly rather than corrupting the target.
    """
    import requests

    tmp = dest.with_suffix(dest.suffix + ".part")
    url = RECORD_URL.format(key=key)
    headers: dict[str, str] = {}
    mode = "wb"
    if tmp.exists() and tmp.stat().st_size > 0:
        headers["Range"] = f"bytes={tmp.stat().st_size}-"
        mode = "ab"
    with requests.get(url, stream=True, timeout=60,
                      allow_redirects=True, headers=headers) as resp:
        if resp.status_code == 200 and mode == "ab":
            mode = "wb"  # server ignored Range: restart rather than append
        elif resp.status_code != 206:
            resp.raise_for_status()
        with open(tmp, mode) as fh:
            for chunk in resp.iter_content(chunk_size=CHUNK):
                if chunk:
                    fh.write(chunk)
    tmp.replace(dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch + verify WorldStrat v1.1")
    parser.add_argument("--dest", default=str(REPO / "data" / "worldstrat"),
                        help="download directory (default data/worldstrat)")
    parser.add_argument("--with-optional", action="store_true",
                        help="also fetch lr_dataset_l1c.zip and hr_dataset_raw.zip")
    parser.add_argument("--verify-only", action="store_true",
                        help="only verify MD5s of existing files; no downloads")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="skip files whose existing MD5 already matches (default)")
    args = parser.parse_args(argv)

    try:
        import requests  # noqa: F401
    except ImportError:
        print("ERROR: 'requests' is required for downloading "
              "(pip install requests)", file=sys.stderr)
        return 2

    dest_dir = Path(args.dest)
    failures: list[str] = []
    pending: list[str] = []

    for key, meta in WORLDSTRAT_FILES.items():
        if meta["optional"] and not args.with_optional:
            continue
        expected = meta["md5"]
        target = dest_dir / key

        if target.exists():
            actual = md5_file(target)
            if actual == expected:
                print(f"OK       {key} ({actual})")
                continue
            print(f"MISMATCH {key}: on-disk md5 {actual} != manifest {expected}",
                  file=sys.stderr)
            failures.append(key)
            if args.verify_only:
                continue
            print(f"         re-downloading {key} ...", file=sys.stderr)
        else:
            if args.verify_only:
                pending.append(key)
                print(f"MISSING  {key}")
                continue
            print(f"FETCH    {key} ...")

        if not args.verify_only:
            dest_dir.mkdir(parents=True, exist_ok=True)
            try:
                download(key, target)
            except Exception as exc:  # noqa: BLE001 - operator-facing report
                print(f"ERROR    {key}: {exc}", file=sys.stderr)
                failures.append(key)
                continue
            actual = md5_file(target)
            if actual == expected:
                print(f"OK       {key} ({actual})")
            else:
                print(f"MISMATCH {key}: downloaded md5 {actual} != manifest {expected}",
                      file=sys.stderr)
                print("         DELETE the corrupted file and re-run.", file=sys.stderr)
                failures.append(key)

    if pending:
        print(f"\n{len(pending)} file(s) missing; run without --verify-only to download.",
              file=sys.stderr)
    if failures:
        print(f"\nFAILED: {len(failures)} file(s) failed verification: "
              f"{', '.join(failures)}", file=sys.stderr)
        return 1
    print("\nAll fetched WorldStrat artifacts verified against the SOURCES.md manifest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
