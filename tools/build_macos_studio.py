"""Build an offline Cocoa Blaze.app on an Apple Silicon Mac.

Inputs are staged by the release workflow, never downloaded by this builder.
Both decoder programs must match their LGPL corresponding-source manifest.
PyInstaller performs ad-hoc signing; the final bundle is signed again after
adding notices, then archived with ditto to retain executable bits and symlinks.
"""

from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODEL_NOTICES = (
    "LICENSE-BTC.txt", "LICENSE-MusicXLab.txt", "LICENSE-Librosa.txt", "LICENSE-BeatThis.txt",
)
EXCLUDES = (
    "torch", "scipy", "librosa", "matplotlib", "pandas", "IPython", "pytest",
    "mutagen", "imageio_ffmpeg", "webview.platforms.qt", "webview.platforms.gtk",
    "webview.platforms.winforms", "webview.platforms.edgechromium",
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_file(path, metadata):
    """Validate bytes before any native tool can alter a code signature."""
    expected = metadata.get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Missing SHA256 for " + str(path))
    if not path.is_file() or digest(path) != expected:
        raise ValueError("Checksum mismatch: " + str(path))
    if "bytes" in metadata and path.stat().st_size != metadata["bytes"]:
        raise ValueError("Size mismatch: " + str(path))


def filename(name):
    if not isinstance(name, str) or Path(name).name != name or name in ("", ".", ".."):
        raise ValueError("Asset paths must be plain filenames.")
    return name


def stage_models(source, target):
    """Copy the same approved ensemble used by Windows and Android, no extras."""
    target.mkdir(parents=True)
    assets = {}
    for name in ("manifest.json", "structured_manifest.json", "rhythm_manifest.json"):
        metadata = json.loads((source / name).read_text(encoding="utf-8"))
        if metadata.get("license") != "MIT":
            raise ValueError("This release uses only the approved MIT model manifests.")
        if name == "manifest.json":
            models = metadata["models"]
            metadata["models"] = {key: models[key] for key in ("major_minor", "extended")}
        models = metadata.get("models")
        if isinstance(models, dict):
            entries = list(models.values())
        elif isinstance(models, list):
            if len(models) != 5:
                raise ValueError("Expected the approved five-model structured ensemble.")
            entries = models
        else:
            entries = [metadata["network"]]
        for entry in [metadata["frontend"], *entries]:
            name_in_bundle = filename(entry["file"])
            if name_in_bundle in assets and assets[name_in_bundle] != entry["sha256"]:
                raise ValueError("Conflicting model manifest: " + name_in_bundle)
            assets[name_in_bundle] = entry["sha256"]
            checked_file(source / name_in_bundle, entry)
        (target / name).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    for name in sorted(assets):
        shutil.copy2(source / name, target / name)
    for name in MODEL_NOTICES:
        shutil.copy2(source / name, target / name)
    return assets


def stage_stem_models(source, target):
    """Keep the separation model independent of the chord-analysis bundle."""
    try:
        from tools.stage_macos_studio import STEM_MODEL, STEM_LICENSES
    except ModuleNotFoundError:
        from stage_macos_studio import STEM_MODEL, STEM_LICENSES
    metadata = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    if (metadata.get('license') != 'MIT'
            or metadata.get('model') != {key: STEM_MODEL[key] for key in ('file', 'bytes', 'sha256')}
            or metadata.get('sample_rate') != 44100
            or metadata.get('segment_samples') != 343980
            or metadata.get('stems') != ['drums', 'bass', 'other', 'vocals']):
        raise ValueError('The Mac build requires the reviewed single SCNet model.')
    target.mkdir(parents=True)
    checked_file(source / STEM_MODEL['file'], STEM_MODEL)
    shutil.copy2(source / STEM_MODEL['file'], target / STEM_MODEL['file'])
    for name, license_metadata in STEM_LICENSES.items():
        checked_file(source / name, license_metadata)
        shutil.copy2(source / name, target / name)
    shutil.copy2(source / 'manifest.json', target / 'manifest.json')
    from music_studio.piano_assets import MODELS, LICENSES
    piano_source, piano_target = source / 'piano', target / 'piano'
    piano_target.mkdir()
    piano_metadata = json.loads((piano_source / 'manifest.json').read_text())
    if piano_metadata.get('models') != MODELS or piano_metadata.get('weight_license') != 'MIT':
        raise ValueError('The reviewed piano model manifest is missing or incompatible.')
    for name, meta in {**{m['file']: m for m in MODELS.values()}, **LICENSES}.items():
        checked_file(piano_source / name, meta)
        shutil.copy2(piano_source / name, piano_target / name)
    shutil.copy2(piano_source / 'manifest.json', piano_target / 'manifest.json')
    metadata['piano'] = piano_metadata
    return metadata


def run(*args):
    process = subprocess.run([str(arg) for arg in args], check=False, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if process.returncode:
        print(process.stdout, file=sys.stderr)
        process.check_returncode()
    return process.stdout


def decoder_entries(manifest):
    binaries = manifest.get("binaries")
    if isinstance(binaries, list):
        binaries = {entry["file"]: entry for entry in binaries}
    if not isinstance(binaries, dict):
        binaries = {"ffmpeg": manifest.get("binary"), "ffprobe": manifest.get("probe")}
    if any(not isinstance(binaries.get(name), dict) for name in ("ffmpeg", "ffprobe")):
        raise ValueError("The decoder manifest must identify both ffmpeg and ffprobe.")
    return binaries


def check_decoder(ffmpeg, ffprobe, materials, arch):
    manifest = json.loads((materials / "decoder-manifest.json").read_text(encoding="utf-8"))
    entries = decoder_entries(manifest)
    for name, path in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        checked_file(path, entries[name])
        run("/usr/bin/lipo", path, "-verify_arch", arch)
    archive = materials / "FFmpeg-LGPL-Corresponding-Sources.zip"
    if not archive.is_file() or not (materials / "licenses").is_dir():
        raise ValueError("Matching decoder source archive and license files are required.")
    if "source_archive" in manifest:
        checked_file(archive, manifest["source_archive"])
    with zipfile.ZipFile(archive) as source_zip:
        if source_zip.testzip() is not None:
            raise ValueError("Decoder corresponding-source archive is corrupt.")
    configuration = run(ffmpeg, "-buildconf")
    if any(flag in configuration for flag in ("--enable-gpl", "--enable-nonfree", "--enable-version3")):
        raise ValueError("The decoder must disable GPL, nonfree and version3 components.")
    license_text = run(ffmpeg, "-L")
    if "GNU Lesser General Public License" not in " ".join(license_text.split()):
        raise ValueError("This release requires an LGPL-only decoder.")
    return manifest


def make_icon(source, target):
    """Generate all macOS icon resolutions from the repository's Blaze artwork."""
    from PIL import Image, ImageOps
    iconset = target.with_suffix(".iconset")
    iconset.mkdir()
    with Image.open(source) as artwork:
        artwork = artwork.convert("RGBA")
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                pixels = size * scale
                icon = ImageOps.contain(artwork, (pixels, pixels), Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", (pixels, pixels))
                canvas.alpha_composite(icon, ((pixels - icon.width) // 2, (pixels - icon.height) // 2))
                suffix = "@2x" if scale == 2 else ""
                canvas.save(iconset / f"icon_{size}x{size}{suffix}.png")
    run("/usr/bin/iconutil", "-c", "icns", "-o", target, iconset)


def copy_python_notices(target, python_license=None, python_license_version=None):
    """Retain actual wheel license/NOTICE files, including vendored dependencies."""
    inventory = []
    required = {"numpy", "onnxruntime", "pywebview", "pyobjc-core", "pyinstaller"}
    found = set()
    for distribution in sorted(importlib.metadata.distributions(),
                               key=lambda dist: dist.metadata.get("Name", "").lower()):
        name = distribution.metadata.get("Name", "unknown")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        files = []
        for member in distribution.files or []:
            basename = member.name.lower()
            if not any(token in basename for token in ("license", "licence", "copying", "notice")):
                continue
            original = Path(distribution.locate_file(member))
            if not original.is_file():
                continue
            # Prefix the relative path to distinguish multiple vendored notices.
            relative = Path(*[part for part in member.parts if part not in (".", "..")])
            destination = target / "Python-packages" / safe_name / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
            files.append(destination.relative_to(target).as_posix())
        normalized_name = name.lower().replace("_", "-")
        if files:
            found.add(normalized_name)
        inventory.append({"name": name, "version": distribution.version,
                          "license": distribution.metadata.get("License-Expression") or
                          distribution.metadata.get("License", "See retained notices"),
                          "notices": files})
    if required - found:
        raise ValueError("License text missing for required packages: " + ", ".join(sorted(required - found)))
    if python_license is not None:
        actual_version = ".".join(str(number) for number in sys.version_info[:3])
        if python_license_version != actual_version:
            raise ValueError("Supplied Python license must match runtime " + actual_version)
        if not python_license.is_file():
            raise ValueError("The supplied Python license file is missing.")
    else:
        candidates = [Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "Resources/LICENSE.txt",
                      Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"]
        python_license = next((candidate for candidate in candidates if candidate.is_file()), None)
    if python_license is None:
        raise ValueError("The Python runtime's LICENSE.txt is required in its installation.")
    shutil.copy2(python_license, target / "Python-LICENSE.txt")
    (target / "Python-package-inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8")


def write_spec(path, entrypoint, source, models, stem_models, icon, binaries, arch, version):
    info = {
        "CFBundleDisplayName": "Blaze", "CFBundleName": "Blaze",
        "CFBundleVersion": version, "CFBundleShortVersionString": version,
        "LSMinimumSystemVersion": "13.0", "LSApplicationCategoryType": "public.app-category.music",
        "NSPrincipalClass": "NSApplication", "NSHighResolutionCapable": True,
        "NSAppleScriptEnabled": False,
        # Playback and the local UI use a loopback HTTP server; no arbitrary
        # Internet exceptions are needed for the native browser renderer.
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    }
    data = [(str(source), "music_studio/web"), (str(models), "music_studio/models"),
            (str(stem_models), "music_studio/stem_models")]
    script = f'''# Generated by tools/build_macos_studio.py
from PyInstaller.utils.hooks import collect_data_files
a = Analysis([{str(entrypoint)!r}], pathex=[{str(ROOT)!r}],
             binaries={binaries!r}, datas={data!r} + collect_data_files('webview', subdir='js'),
             hiddenimports=['webview.platforms.cocoa', 'onnxruntime'],
             hookspath=[], hooksconfig={{}}, runtime_hooks=[], excludes={list(EXCLUDES)!r},
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Blaze',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, argv_emulation=False, target_arch={arch!r},
          codesign_identity=None, entitlements_file=None)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Blaze')
app = BUNDLE(collection, name='Blaze.app', icon={str(icon)!r},
             bundle_identifier='com.broothc.blaze', version={version!r},
             info_plist={info!r})
'''
    path.write_text(script, encoding="utf-8")


def build(args):
    if sys.platform != "darwin" or platform.machine() != "arm64" or args.arch != "arm64":
        raise RuntimeError("New Mac builds require an Apple Silicon Mac (arm64).")
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise ValueError("--version must be a numeric three-part app version.")
    for path in (args.ffmpeg, args.ffprobe, args.ytdlp, args.node):
        if not path.is_file():
            raise ValueError("Missing local tool: " + str(path))
    if not args.external_notices.is_dir() or not any(args.external_notices.rglob("*")):
        raise ValueError("Supply retained Node and standalone yt-dlp license materials.")
    check_decoder(args.ffmpeg, args.ffprobe, args.decoder_materials, args.arch)
    for binary in (args.ytdlp, args.node):
        run("/usr/bin/lipo", binary, "-verify_arch", args.arch)
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="macos-stage-", dir=args.work) as temporary:
        stage = Path(temporary)
        assets = stage_models(args.models, stage / "models")
        stem_assets = stage_stem_models(args.stem_models, stage / "stem_models")
        shutil.copytree(ROOT / "music_studio/web", stage / "web")
        shutil.copy2(ROOT / "docs/assets/blaze-logo.png", stage / "web/blaze-logo.png")
        icon = stage / "Blaze.icns"
        make_icon(ROOT / "docs/assets/blaze-logo.png", icon)
        tools = stage / "bin"
        tools.mkdir()
        binaries = []
        for name, source in (("ffmpeg", args.ffmpeg), ("ffprobe", args.ffprobe),
                             ("node", args.node)):
            destination = tools / name
            shutil.copy2(source, destination)
            destination.chmod(0o755)
            binaries.append((str(destination), "bin"))
        spec = stage / "Blaze.spec"
        write_spec(spec, ROOT / "music_studio/mac_app.py", stage / "web", stage / "models", stage / "stem_models",
                   icon, binaries, args.arch, args.version)
        import PyInstaller.__main__
        PyInstaller.__main__.run(["--noconfirm", "--clean", "--distpath", str(args.output),
                                 "--workpath", str(args.work / "pyinstaller"), str(spec)])
        app = args.output / "Blaze.app"
        # The upstream downloader is itself a universal PyInstaller one-file
        # executable with an appended payload. Analysis would reclassify even
        # an explicit DATA input as BINARY, then lipo-thin it and lose that
        # payload. Copy the complete standalone program after collection.
        bundled_tools = app / "Contents/Resources/bin"
        bundled_tools.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.ytdlp, bundled_tools / "yt-dlp")
        (bundled_tools / "yt-dlp").chmod(0o755)
        if digest(bundled_tools / "yt-dlp") != digest(args.ytdlp):
            raise ValueError("The standalone downloader payload was not preserved.")
        licenses = app / "Contents/Resources/licenses"
        licenses.mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.decoder_materials / "licenses", licenses / "FFmpeg")
        for name in ("FFmpeg-LGPL-Corresponding-Sources.zip", "decoder-manifest.json"):
            shutil.copy2(args.decoder_materials / name, licenses / name)
        shutil.copytree(args.external_notices, licenses / "External-tools")
        for name in ("LICENSE.txt", "THIRD-PARTY-NOTICES.md"):
            shutil.copy2(ROOT / name, licenses / name)
        copy_python_notices(licenses, args.python_license, args.python_license_version)
        (licenses / "Blaze-Mac-Distribution.txt").write_text(
            "Blaze's license applies only to Blaze code. Each bundled dependency retains its own rights.\n"
            "FFmpeg/LAME remain separately replaceable LGPL programs. Exact source archives, licenses\n"
            "and rebuild instructions are retained here. Model licenses are in music_studio/models\n"
            "and music_studio/stem_models.\n"
            "PyInstaller's GPL license includes its bootloader exception; see the full copied license.\n"
            "This build is ad-hoc signed, without Apple notarization or a Developer ID certificate.\n",
            encoding="utf-8")
        # Sign nested code once; adding the resource manifest then signing the
        # outer bundle alone preserves the nested code hashes recorded below.
        run("/usr/bin/codesign", "--force", "--deep", "--sign", "-", app)
        manifest = {"version": args.version, "architecture": args.arch,
                    "minimum_macos": "13.0", "signing": "ad-hoc; not notarized",
                    "models": assets, "stem_model": stem_assets, "tools": {}}
        for name in ("ffmpeg", "ffprobe", "yt-dlp", "node"):
            binary = bundled_tools / name
            manifest["tools"][name] = {"sha256": digest(binary), "bytes": binary.stat().st_size}
        (licenses / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        run("/usr/bin/codesign", "--force", "--sign", "-", app)
        run("/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", app)
        archive = args.output / f"Blaze-Mac-{args.arch}.zip"
        run("/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, archive)
        print(json.dumps({"app": str(app), "archive": str(archive), "sha256": digest(archive),
                          "bytes": archive.stat().st_size}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--decoder-materials", type=Path, required=True)
    parser.add_argument("--ytdlp", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--external-notices", type=Path, required=True)
    parser.add_argument("--python-license", type=Path,
                        help="Upstream CPython LICENSE when the installed runtime omits it")
    parser.add_argument("--python-license-version",
                        help="Exact CPython x.y.z tag supplying --python-license; must match this interpreter")
    parser.add_argument("--models", type=Path, default=ROOT / "music_studio/models")
    parser.add_argument("--stem-models", type=Path, default=ROOT / "music_studio/stem_models")
    parser.add_argument("--arch", choices=("arm64",), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    if args.python_license:
        args.python_license = args.python_license.resolve()
        if not args.python_license_version:
            parser.error("--python-license requires --python-license-version")
    elif args.python_license_version:
        parser.error("--python-license-version requires --python-license")
    for name in ("ffmpeg", "ffprobe", "decoder_materials", "ytdlp", "node",
                 "external_notices", "models", "stem_models", "output", "work"):
        setattr(args, name, getattr(args, name).resolve())
    build(args)


if __name__ == "__main__":
    main()
