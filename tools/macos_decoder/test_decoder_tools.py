"""Run with python3 tools/macos_decoder/test_decoder_tools.py."""

from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from fetch_sources import extract, fetch
from package_sources import EVIDENCE_FILES, LICENSE_FILES, check_evidence, file_record, package


class DecoderToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_tar(self, name="codec-1/README", kind=tarfile.REGTYPE):
        archive = self.root / "codec.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.linkname = "../../outside"
            member.size = 3 if kind == tarfile.REGTYPE else 0
            bundle.addfile(member, io.BytesIO(b"abc") if member.size else None)
        asset = file_record(archive)
        asset.update(directory="codec-1", url="https://example.com/codec.tar.gz")
        return archive, asset

    def test_pristine_extraction_and_verified_cache(self):
        archive, asset = self.make_tar()
        path = extract(archive, self.root / "src", asset)
        self.assertEqual((path / "README").read_bytes(), b"abc")
        self.assertEqual(extract(archive, self.root / "src", asset), path)
        self.assertEqual(fetch(asset, self.root, offline=True), archive)

    def test_rejects_traversal_links_and_devices(self):
        for name, kind in (
            ("codec-1/../../outside", tarfile.REGTYPE),
            ("/codec-1/absolute", tarfile.REGTYPE),
            ("codec-1\\outside", tarfile.REGTYPE),
            ("other/README", tarfile.REGTYPE),
            ("codec-1/link", tarfile.SYMTYPE),
            ("codec-1/hardlink", tarfile.LNKTYPE),
            ("codec-1/device", tarfile.CHRTYPE),
        ):
            with self.subTest(name=name, kind=kind):
                archive, asset = self.make_tar(name, kind)
                with self.assertRaises(ValueError):
                    extract(archive, self.root / "src", asset)
                self.assertFalse((self.root / "src" / "codec-1").exists())

    def test_cache_corruption_and_unknown_source_tree_fail(self):
        archive, asset = self.make_tar()
        archive.write_bytes(b"corrupt")
        with self.assertRaises(RuntimeError):
            fetch(asset, self.root, offline=True)
        (self.root / "src" / "codec-1").mkdir(parents=True)
        with self.assertRaises(RuntimeError):
            extract(archive, self.root / "src", asset)

    def populate_build(self):
        output = self.root / "output"
        (output / "bin").mkdir(parents=True)
        (self.root / "logs").mkdir()
        for name in ("ffmpeg", "ffprobe"):
            (output / "bin" / name).write_bytes(b"synthetic-test-" + name.encode())
        for name in EVIDENCE_FILES:
            (output / name).write_text("build evidence\n", encoding="utf-8")
        (output / "buildconf.txt").write_text(
            "--disable-gpl --disable-nonfree --disable-version3\n", encoding="utf-8"
        )
        (output / "license.txt").write_text("GNU Lesser General Public License\n", encoding="utf-8")
        (output / "toolchain.txt").write_text("Native architecture: arm64\n", encoding="utf-8")
        for name in ("ffmpeg", "ffprobe"):
            (output / f"{name}-dependencies.txt").write_text(
                f"{name}:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n",
                encoding="utf-8",
            )
        downloads = self.root / "downloads"
        downloads.mkdir()
        source = downloads / "codec.tar.gz"
        source.write_bytes(b"synthetic source")
        manifest = {"assets": [file_record(source)]}
        (self.root / "sources-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        for relative, _ in LICENSE_FILES:
            path = self.root / "src" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("copyright and license test fixture", encoding="utf-8")
        for name in ("fetch_sources.py", "build.sh", "package_sources.py", "README.md"):
            (self.root / name).write_text("rebuild recipe fixture", encoding="utf-8")
        return output

    def test_exact_sources_package_identifies_both_binaries(self):
        output = self.populate_build()
        archive = package(self.root)
        outer = json.loads((output / "decoder-manifest.json").read_text())
        self.assertEqual(outer["source_archive"], file_record(archive))
        self.assertEqual(outer["architecture"], "arm64")
        self.assertEqual(outer["binary"], outer["binaries"]["ffmpeg"])
        self.assertEqual(outer["probe"], outer["binaries"]["ffprobe"])
        with zipfile.ZipFile(archive) as bundle:
            inner = json.loads(bundle.read("decoder-manifest.json"))
            self.assertEqual(inner["binaries"], outer["binaries"])
            self.assertNotIn("source_archive", inner)
            self.assertEqual(bundle.read("downloads/codec.tar.gz"), b"synthetic source")
            for _, name in LICENSE_FILES:
                self.assertIn("licenses/" + name, bundle.namelist())

    def test_gpl_build_and_external_codec_link_are_rejected(self):
        output = self.populate_build()
        buildconf = output / "buildconf.txt"
        original = buildconf.read_text()
        buildconf.write_text(original + "--enable-gpl\n")
        with self.assertRaises(RuntimeError):
            check_evidence(output)
        buildconf.write_text(original)
        (output / "ffprobe-dependencies.txt").write_text(
            "ffprobe:\n\t/opt/homebrew/lib/libogg.dylib (compatibility version 1.0.0)\n"
        )
        with self.assertRaises(RuntimeError):
            check_evidence(output)

    def test_pinned_sources_match_verified_windows_recipe(self):
        root = Path(__file__).resolve().parent
        mac = json.loads((root / "sources-manifest.json").read_text())
        windows = json.loads((root.parent / "windows_decoder" / "sources-manifest.json").read_text())
        expected = {a["file"]: a for a in windows["assets"] if not a["file"].endswith(".exe")}
        self.assertEqual(len(mac["assets"]), 5)
        for asset in mac["assets"]:
            for key in ("url", "sha256", "bytes", "license"):
                self.assertEqual(asset[key], expected[asset["file"]][key])
        self.assertEqual(mac["ffmpeg_commit"], windows["ffmpeg_commit"])


if __name__ == "__main__":
    unittest.main()
