# Android / Termux setup (experimental)

[Back to Blaze](../README.md)

Prefer an app with buttons? See the separate [Android APK preview](ANDROID-APK.md).

Use a current [Termux release from the official installation instructions](https://github.com/termux/termux-app#installation). Full package support requires Android 7 or newer.

Blaze runs inside Termux with its usual terminal dashboard. Python, FFmpeg and aria2 come from Termux packages; desktop Linux installers do not work on Android.

1. Download [the Termux installer ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Termux-Installer.zip).
2. In Termux, run `pkg install unzip`, then `termux-setup-storage` and allow storage access.
3. Run `unzip ~/storage/shared/Download/Blaze-Termux-Installer.zip -d ~/blaze-setup`.
4. Run `bash ~/blaze-setup/Blaze-Termux-Installer/Install-Blaze.sh`.
5. Start with `bash ~/Blaze/Start-Blaze.sh`.

Internet is required during setup. Setup installs Termux packages and private Python packages under `~/Blaze/.runtime/venv`; no root access is required.

Downloads normally stay in `~/Blaze/Audio` and `~/Blaze/Video`. To use Android's shared Downloads folder:

```sh
bash ~/Blaze/Start-Blaze.sh --output ~/storage/shared/Download/Blaze
```

Keep Termux in the foreground for long jobs. Android may stop background processes. Reduce simultaneous downloads on phones with limited memory. Use `--no-tui` for plain output if the dashboard is too crowded.

To upgrade, close Blaze and rerun the newer installer; your settings and downloads stay in place. If a Termux Python upgrade breaks the venv, rename `~/Blaze/.runtime/venv` to a backup location and rerun setup.

CI checks Android dependency selection, packaging, script syntax and rejection outside Termux. It does not run on an Android device. Physical-device installation, media conversion, resuming and storage permissions still need verification before this support is considered stable.
