# Getting help with Blaze

Start with the platform setup instructions in [README.md](README.md).
For desktop/Termux, run your installed launcher with `--help` for available
options and `--version` to identify the application version. For the Android
APK, open **About Blaze** and follow the [APK guide](docs/ANDROID-APK.md).

## Android APK preview

Paste a complete HTTPS link to a single item. If a service needs conversion,
separate video/audio merging, playlists, login or JavaScript, try the Termux
version instead. Check the error shown in the app. Use **Save a copy…** to keep
completed files outside Blaze before uninstalling. Different debug-build keys
can prevent an in-place update; export your files before removing an old build.

Include your Android version, device architecture, APK version, affected
service, and the steps you tapped when reporting a bug. The preview is not yet
validated on physical phones.

## Desktop and Termux

If setup fails, keep the terminal open and read the first error. Extract the
whole installer ZIP, check your internet connection, and rerun setup after
closing Blaze. Linux installer requirements are listed in its README.

For a download issue, retry with `--no-tui` to see plain output. If it only
occurs with aria2c, compare with `--no-aria2c`. Website extractors can change
independently of Blaze; include the affected service and sanitized error.

Use the [bug report form](https://github.com/Brooth-C/blaze/issues/new?template=bug_report.yml)
with your version, operating system, architecture, installation method,
reproduction steps, and expected/actual result. Use the feature request form
for suggestions. Response times are not guaranteed.

Remove cookies, tokens, private URLs, personal paths and account details from
logs or screenshots before posting. Do not post credentials in an issue.
