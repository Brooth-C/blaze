"""Package exact decoder sources, licence texts and native rebuild evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from fetch_sources import verify


ROOT = Path(__file__).resolve().parent
LICENSE_FILES = (
    ("ffmpeg-7.1.3/COPYING.LGPLv2.1", "FFmpeg-LGPL-2.1.txt"),
    ("ffmpeg-7.1.3/LICENSE.md", "FFmpeg-LICENSE.md"),
    ("lame-3.100/COPYING", "LAME-LGPL.txt"),
    ("ogg-1.3.5/COPYING", "Ogg-BSD.txt"),
    ("vorbis-1.3.7/COPYING", "Vorbis-BSD.txt"),
    ("opus-1.5.2/COPYING", "Opus-BSD.txt"),
)
EVIDENCE_FILES = (
    "version.txt", "probe-version.txt", "buildconf.txt", "license.txt",
    "config.mak", "config.log", "toolchain.txt",
    "ffmpeg-dependencies.txt", "ffprobe-dependencies.txt",
)


def file_record(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"file": path.name, "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def check_evidence(output: Path) -> None:
    buildconf = (output / "buildconf.txt").read_text(encoding="utf-8")
    license_text = (output / "license.txt").read_text(encoding="utf-8")
    if "GNU Lesser General Public License" not in license_text:
        raise RuntimeError("Decoder does not report an LGPL license")
    for flag in ("gpl", "nonfree", "version3"):
        if f"--enable-{flag}" in buildconf or f"--disable-{flag}" not in buildconf:
            raise RuntimeError(f"Forbidden or unspecified FFmpeg {flag} configuration")
    for program in ("ffmpeg", "ffprobe"):
        binary = output / "bin" / program
        if not binary.is_file() or binary.stat().st_size == 0:
            raise RuntimeError(f"Missing decoder executable: {program}")
        # Executables link only Apple system frameworks/runtimes. All codec
        # libraries built here are linked into this separate executable.
        lines = (output / f"{program}-dependencies.txt").read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            dependency = line.strip().split(" (", 1)[0]
            if dependency and not dependency.startswith(("/usr/lib/", "/System/Library/")):
                raise RuntimeError(f"Non-system decoder dependency: {dependency}")


def package(root: Path) -> Path:
    output = root / "output"
    licenses = output / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / "sources-manifest.json").read_text(encoding="utf-8"))
    for asset in manifest["assets"]:
        verify(root / "downloads" / asset["file"], asset)
    check_evidence(output)
    for relative, name in LICENSE_FILES:
        shutil.copy2(root / "src" / relative, licenses / name)
    for name in EVIDENCE_FILES:
        if not (output / name).is_file():
            raise FileNotFoundError(f"Missing decoder build evidence: {name}")
    shutil.copy2(root / "README.md", output / "SOURCE-README.md")
    manifest["platform"] = "macOS"
    manifest["minimum_macos"] = "13.0"
    native = (output / "toolchain.txt").read_text(encoding="utf-8").splitlines()[0]
    if native not in ("Native architecture: arm64", "Native architecture: x86_64"):
        raise RuntimeError("Decoder architecture was not recorded")
    manifest["architecture"] = native.split(": ", 1)[1]
    manifest["binaries"] = {
        name: file_record(output / "bin" / name) for name in ("ffmpeg", "ffprobe")
    }
    manifest["binary"] = manifest["binaries"]["ffmpeg"]
    manifest["probe"] = manifest["binaries"]["ffprobe"]
    manifest["configuration"] = "buildconf.txt"
    manifest["toolchain"] = "toolchain.txt"
    manifest["linkage"] = "Separate executables; static codec libraries; Apple system libraries only"
    inner_manifest = json.dumps(manifest, indent=2) + "\n"
    archive = output / "FFmpeg-LGPL-Corresponding-Sources.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as bundle:
        for asset in manifest["assets"]:
            path = root / "downloads" / asset["file"]
            bundle.write(path, "downloads/" + path.name)
        for name in ("fetch_sources.py", "build.sh", "sources-manifest.json", "package_sources.py", "README.md"):
            bundle.write(root / name, name)
        for name in EVIDENCE_FILES:
            bundle.write(output / name, "output/" + name)
        bundle.write(output / "SOURCE-README.md", "SOURCE-README.md")
        bundle.writestr("decoder-manifest.json", inner_manifest)
        for path in sorted(licenses.iterdir()):
            if path.is_file():
                bundle.write(path, "licenses/" + path.name)
        for path in sorted((root / "logs").glob("*.log")):
            bundle.write(path, "logs/" + path.name)
    # The archive's own digest belongs in the outer manifest to avoid a circular
    # digest. Its internal manifest already identifies both matching binaries.
    manifest["source_archive"] = file_record(archive)
    (output / "decoder-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Matching decoder sources: {archive} ({archive.stat().st_size} bytes)")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    package(args.root.resolve())


if __name__ == "__main__":
    main()
