# Mac automatic updates

Blaze embeds the official Sparkle 2.10.1 framework. `tools/macos_sparkle.py` downloads the pinned upstream archive and verifies its SHA256. The builder preserves framework symlinks, vendor helper signatures and the upstream license, then signs the outer Blaze bundle.

The native updater is installed on Cocoa's main thread after the window loads. It provides **Blaze → Check for Updates…** and automatic checks every 24 hours. Sparkle owns downloading, signature validation, staging, app replacement and relaunch. Silent automatic installation and system profiling are disabled. The application must be installed in Applications rather than run directly from its download archive.

When the user chooses installation, the relaunch block is retained until playback is paused, chord/rhythm analysis and separation stop, exports/downloads finish, and practice saves finish. Playback state is read from the existing WKWebView; unavailable/error state prevents relaunch. The native timer requires two seconds of idle observations to allow pending practice autosaves to settle. Choosing a saved practice, transposing and analysis still use the original engines.

## Stable feed

- Feed: `https://github.com/Brooth-C/blaze/releases/latest/download/mac-appcast.xml`
- Archive: the versioned `macos-vX.Y.Z/Blaze-Mac-arm64.zip` asset.
- Verification key: `music_studio/mac_update_config.json`, also embedded in Info.plist.
- Private signing seed: **only** the repository Actions secret `BLAZE_UPDATE_PRIVATE_KEY` (base64-encoded 32-byte Ed25519 seed). Never commit it, expose it through artifacts, or print it in logs.

`tools/macos_update_feed.py` signs the exact archive after the app/package checks. It refuses missing or mismatched keys and non-stable/non-Mac inputs. The feed's publication time comes from the source commit (`SOURCE_DATE_EPOCH`) so reruns produce the same feed. Publication verifies the ZIP and feed are immutable when a release already exists. Publishing another platform as Latest without the Mac feed would break the feed URL; keep Latest assigned to the stable Mac release.

## One-time owner setup

The current GitHub integration returned HTTP 403 when attempting to set repository Actions secrets. A repository owner must set `BLAZE_UPDATE_PRIVATE_KEY` using the generated seed retained outside this checkout at `/workspace/blaze-update-signing/private-key`:

```sh
gh secret set BLAZE_UPDATE_PRIVATE_KEY --repo Brooth-C/blaze < /workspace/blaze-update-signing/private-key
```

Back up that key in an owner-controlled password manager before deleting the workspace copy. If it is lost before the first updater-enabled release, generate a new key and replace the public config before publishing. Once updater-enabled versions ship, do not casually rotate the key: existing clients trust their embedded verification key. Sparkle supports migration procedures documented upstream.

This updater is not included in older installed Blaze versions; the first updater-enabled build requires one manual installation. Sparkle signatures do not remove macOS Gatekeeper warnings. Developer ID signing and Apple notarization remain a separate distribution task.

## Verification

- `tests/Blaze-Mac-Updater-Tests.py`: exact-byte signatures, tamper/wrong-key rejection, reproducibility, stable-only feed, busy-job deferral and packaged public configuration.
- `tests/Blaze-Mac-Updater-Native.py`: macOS 26 only; real Sparkle protocol, Objective-C caller, PyObjC BOOL ABI and retained install-block lifetime.
- The existing macOS 26 package UI smoke loads the bundled Sparkle framework and constructs its controller/menu without starting network checks or changing updater preferences.
- `tests/Blaze-Mac-Publication-Tests.py`: immutable stable publication of ZIP and appcast together.

Native framework/package checks must pass before publication. A real upgrade from one installed version to a higher signed version still requires a Mac acceptance test; Linux tests do not establish that behavior.

References: https://sparkle-project.org/documentation/ and https://sparkle-project.org/documentation/programmatic-setup/
