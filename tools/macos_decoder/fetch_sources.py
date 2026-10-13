"""Download verified, pinned decoder sources and extract only contained paths."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import time
import urllib.request


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_asset(asset: dict) -> None:
    for key in ("file", "directory"):
        value = asset[key]
        if not isinstance(value, str) or not value or Path(value).name != value:
            raise ValueError(f"Unsafe source {key}: {value!r}")
        if value in (".", "..") or "\\" in value or ":" in value:
            raise ValueError(f"Unsafe source {key}: {value!r}")
    digest = asset["sha256"]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Source SHA256 must be a lowercase 64-digit hash")
    if not isinstance(asset["bytes"], int) or asset["bytes"] <= 0:
        raise ValueError("Source size must be positive")
    if not asset["url"].startswith("https://"):
        raise ValueError("Source URLs must use HTTPS")


def verify(path: Path, asset: dict) -> None:
    if path.stat().st_size != asset["bytes"] or sha256(path) != asset["sha256"]:
        raise RuntimeError(f"Source size/SHA256 mismatch: {asset['file']}")


def fetch(asset: dict, downloads: Path, offline: bool = False) -> Path:
    validate_asset(asset)
    downloads.mkdir(parents=True, exist_ok=True)
    destination = downloads / asset["file"]
    if destination.exists():
        verify(destination, asset)
        return destination
    if offline:
        raise FileNotFoundError(f"Missing offline source: {destination}")
    # A partial request never becomes a cache hit. Every retry uses a fresh file.
    for attempt in range(3):
        partial = destination.with_name(destination.name + ".part")
        try:
            request = urllib.request.Request(
                asset["url"], headers={"User-Agent": "Blaze-macOS-decoder-build/1.0"}
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                with partial.open("wb") as stream:
                    shutil.copyfileobj(response, stream, length=1024 * 1024)
            verify(partial, asset)
            partial.replace(destination)
            return destination
        except (OSError, RuntimeError):
            partial.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("Unreachable download retry state")


def extract(archive: Path, source_root: Path, asset: dict) -> Path:
    """Reject links/devices and traversal before safe data-filter extraction."""
    directory = asset["directory"]
    source_root.mkdir(parents=True, exist_ok=True)
    target = source_root / directory
    marker = target / ".blaze-source-sha256"
    if target.exists():
        if marker.is_file() and marker.read_text(encoding="ascii").strip() == asset["sha256"]:
            return target
        raise RuntimeError(f"Unverified extracted source exists: {target}")
    with tempfile.TemporaryDirectory(prefix=".extract-", dir=source_root) as scratch:
        with tarfile.open(archive, "r:*") as bundle:
            for member in bundle.getmembers():
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in member.name
                    or ":" in member.name
                    or not path.parts
                    or path.parts[0] != directory
                    or not (member.isfile() or member.isdir())
                ):
                    raise ValueError(f"Unsafe archive member: {member.name!r}")
            bundle.extractall(scratch, filter="data")
        extracted = Path(scratch) / directory
        if not extracted.is_dir():
            raise ValueError(f"Archive does not contain {directory}")
        (extracted / ".blaze-source-sha256").write_text(asset["sha256"] + "\n", encoding="ascii")
        extracted.rename(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use only included source archives")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "sources-manifest.json").read_text(encoding="utf-8"))
    assets = manifest["assets"]
    if len({asset["file"] for asset in assets}) != len(assets):
        raise ValueError("Duplicate source archives")
    with ThreadPoolExecutor(max_workers=3) as pool:
        paths = list(pool.map(lambda asset: fetch(asset, root / "downloads", args.offline), assets))
    for asset, archive in zip(assets, paths):
        if not args.download_only:
            extract(archive, root / "src", asset)
        print(f"Verified {asset['file']} {asset['sha256']}", flush=True)


if __name__ == "__main__":
    main()
