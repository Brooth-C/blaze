"""Publish already-tested Mac artifacts without rebuilding the native app."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import tempfile

try:
    from tools import release_page as release
except ModuleNotFoundError:
    import release_page as release


REPOSITORY = "Brooth-C/blaze"
MAC_TAG = "macos-v0.6.0-preview"
ORIGINS = {
    "Blaze-Windows.zip": "windows-v0.6.0",
    "Blaze-Android-Preview.apk": "android-v0.6.0-preview",
    "Blaze-Mac-arm64.zip": MAC_TAG,
    "Blaze-Mac-x86_64.zip": MAC_TAG,
    "Blaze-Linux-Installer.zip": "v4.1.29",
    "Blaze-Termux-Installer.zip": "v4.1.29",
}
INPUTS = (
    "blaze.py", "music_studio", "tools/build_macos_studio.py",
    "tools/build_macos_downloader.py", "tools/stage_macos_studio.py",
    "tools/macos_decoder", ".github/workflows/macos-app.yml", "docs/assets/blaze-logo.png",
)


def api(endpoint, optional=False):
    content = release.gh("api", f"repos/{REPOSITORY}/{endpoint}", optional=optional)
    return json.loads(content) if content is not None else None


def current_main():
    return api("git/ref/heads/main")["object"]["sha"]


def input_tree(commit):
    tree_sha = api(f"git/commits/{commit}")["tree"]["sha"]
    tree = api(f"git/trees/{tree_sha}?recursive=1")
    if tree.get("truncated"):
        raise ValueError("Application tree response was truncated")
    entries = {entry["path"]: (entry["type"], entry["sha"]) for entry in tree["tree"]}
    if any(path not in entries for path in INPUTS):
        raise ValueError("A required Mac application input is absent")
    return {path: entries[path] for path in INPUTS}


def validate(catalog, main_sha):
    if (catalog["repository"] != REPOSITORY or catalog["tag"] != "v4.2.1"
            or os.environ.get("GH_REPO", REPOSITORY) != REPOSITORY
            or os.environ.get("GITHUB_REPOSITORY", REPOSITORY) != REPOSITORY):
        raise ValueError("Promotion is restricted to the declared Blaze distribution")
    assets = catalog["assets"]
    if {asset["name"]: asset["source_tag"] for asset in assets} != ORIGINS:
        raise ValueError("Promotion requires exactly the six declared platform builds")
    proof = catalog.get("macos_validation", {})
    run_id, head = proof.get("run_id"), proof.get("head_sha", "")
    if type(run_id) is not int or run_id <= 0 or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("The catalog needs the successful native run ID and exact head SHA")
    run = api(f"actions/runs/{run_id}")
    if (run.get("name") != "Blaze macOS app" or run.get("status") != "completed"
            or run.get("conclusion") != "success" or run.get("head_sha") != head
            or run.get("repository", {}).get("full_name") != REPOSITORY
            or run.get("head_repository", {}).get("full_name") != REPOSITORY):
        raise ValueError("The declared native workflow run did not validate this source")
    jobs = api(f"actions/runs/{run_id}/jobs?per_page=100")["jobs"]
    for arch in ("arm64", "x86_64"):
        matches = [job for job in jobs if job["name"] == "Mac app / " + arch]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise ValueError("Both native architecture jobs must have passed")
    artifacts = api(f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    for arch in ("arm64", "x86_64"):
        matches = [artifact for artifact in artifacts if artifact["name"] == "Blaze-Mac-" + arch]
        if len(matches) != 1 or matches[0].get("expired"):
            raise ValueError("A validated Mac install artifact is missing or expired")
    if input_tree(main_sha) != input_tree(head):
        raise ValueError("Mac application inputs changed since the successful native run")
    return run_id, head


def fresh(main_sha):
    if current_main() != main_sha:
        raise ValueError("Main advanced during promotion; no newer source will be published unvalidated")


def publish(tag, title, expected, directory, notes, target, preview, main_sha):
    existing = api(f"releases/tags/{tag}", optional=True)
    if existing is None:
        fresh(main_sha)
        arguments = ["release", "create", tag, *(str(directory / asset["name"]) for asset in expected),
                     "--repo", REPOSITORY, "--target", target, "--title", title,
                     "--notes-file", str(notes), "--draft", "--latest=false"]
        if preview:
            arguments.append("--prerelease")
        release.gh(*arguments)
        existing = api(f"releases/tags/{tag}")
    release.verify_target(existing, {"assets": expected}, require_all=False)
    present = {asset['name'] for asset in existing['assets']}
    missing = [asset for asset in expected if asset['name'] not in present]
    if missing:
        if not existing.get('draft'):
            raise ValueError('An incomplete published release is preserved for review')
        fresh(main_sha)
        release.gh('release', 'upload', tag, *(str(directory / asset['name']) for asset in missing), '--repo', REPOSITORY)
        existing = api(f'releases/tags/{tag}')
    release.verify_target(existing, {"assets": expected}, require_all=True)
    if existing.get("prerelease") != preview:
        raise ValueError("Existing release has a different preview status; it is preserved")
    fresh(main_sha)
    release.gh("release", "edit", tag, "--repo", REPOSITORY, "--notes-file", str(notes),
               "--draft=false", "--latest=false" if preview else "--latest=true")
    final = api(f"releases/tags/{tag}")
    release.verify_target(final, {"assets": expected}, require_all=True)
    if final.get("draft") or final.get("prerelease") != preview:
        raise ValueError("Published release status does not match the catalog")


def promote(catalog):
    main_sha = current_main()
    if os.environ.get("GITHUB_SHA", main_sha) != main_sha:
        print("A newer main commit is awaiting validation; this run will not publish.")
        return
    run_id, head = validate(catalog, main_sha)
    mac_assets = [asset for asset in catalog["assets"] if asset["source_tag"] == MAC_TAG]
    with tempfile.TemporaryDirectory(prefix="blaze-promotion-") as temporary:
        directory = Path(temporary)
        for asset in catalog["assets"]:
            if asset["source_tag"] == MAC_TAG:
                artifact = asset["name"].removesuffix(".zip")
                destination = directory / artifact
                release.gh("run", "download", str(run_id), "--repo", REPOSITORY,
                           "--name", artifact, "--dir", str(destination))
                if {path.name for path in destination.iterdir()} != {asset["name"]}:
                    raise ValueError("Validated artifact contains unexpected files")
                shutil.move(str(destination / asset["name"]), directory / asset["name"])
            else:
                release.gh("release", "download", asset["source_tag"], "--repo", REPOSITORY,
                           "--pattern", asset["name"], "--dir", str(directory))
        release.verify_files(directory, catalog["assets"])
        sources = catalog["android_native_sources"]
        native_release = api(f"releases/tags/{sources['source_tag']}")
        release.verify_asset(next(asset for asset in native_release["assets"] if asset["name"] == sources["name"]), sources)
        notes = directory / "Mac-notes.md"
        notes.write_text(
            "# Blaze for macOS\n\nChoose one ZIP: arm64 for Apple Silicon, x86_64 for Intel. Requires macOS 13+. "
            "Extract it and move Blaze.app to Applications. Downloads, Music Studio and Library are inside Blaze; "
            "advanced chord and beat/meter analysis run offline.\n\n"
            "This preview is ad-hoc signed without Apple notarization. macOS may require Privacy & Security → Open Anyway "
            "on first launch. [Installation guide](https://github.com/Brooth-C/blaze/blob/main/docs/MACOS.md). "
            "Matching LGPL decoder sources and dependency notices are inside each app. Some video containers can be "
            "analysed but cannot play in the system web view.\n\n"
            f"Both native app/UI checks passed in [run {run_id}](https://github.com/{REPOSITORY}/actions/runs/{run_id}) "
            f"at source `{head}`. These are the unchanged tested artifacts.\n\n" +
            "\n".join(f"{asset['name']}: {asset['size']} bytes; SHA256 `{asset['sha256']}`" for asset in mac_assets),
            encoding="utf-8")
        publish(MAC_TAG, "Blaze for macOS", mac_assets, directory, notes, head, True, main_sha)
        notes = directory / "Unified-notes.md"
        notes.write_text(release.page(catalog), encoding="utf-8")
        publish(catalog["tag"], "Blaze " + catalog["tag"], catalog["assets"], directory, notes, main_sha, False, main_sha)
        if api("releases/latest")["tag_name"] != catalog["tag"]:
            raise ValueError("GitHub Latest did not select the completed unified release")
        print("Validated Mac preview and six-download main release published without rebuilding.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    promote(release.load_catalog(parser.parse_args().catalog))


if __name__ == "__main__":
    main()
