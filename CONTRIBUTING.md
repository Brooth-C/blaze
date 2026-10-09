# Contributing to Blaze

Start with a focused issue or pull request explaining the problem and the intended result.

## Local setup

Use Python 3.10 or newer in an isolated development environment:

```sh
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS/Linux, or
`.venv\Scripts\Activate.ps1` in Windows PowerShell. Then:

```sh
python -m pip install rich
python -m py_compile blaze.py build.py Blaze-Regression-Tests.py
python Blaze-Regression-Tests.py
```

The regression suite uses mocks and a locally generated wheel; it does not
require downloading media. The POSIX terminal tests are skipped on Windows.
The suite creates a temporary Python environment, so Python's venv/ensurepip
support must be available.

## Project conventions

- Keep managed dependencies, configuration, and runtime state inside the Blaze installation folder.
- Preserve terminal behavior on Windows, macOS, and Linux.
- Avoid adding system package-manager installations, permanent PATH changes, or administrator requirements.
- Keep Spotify/spotDL support removed.
- Add regression coverage for meaningful behavior changes.
- Explain which checks passed and which platforms were actually tested.
- Never commit credentials, cookies, personal media, or unredacted downloader logs.

## Installer changes

The application also exists in both installer source folders. When changing
`blaze.py`, synchronize those copies and rebuild the downloadable ZIP packages.
Verify archive contents and script syntax. Do not claim end-to-end Windows or
macOS validation unless the installer was actually run on that platform.

## Pull requests

Describe the concrete problem, resulting behavior, and validation.
Keep unrelated changes separate. Discuss new dependencies before introducing them.

## License

This repository currently has no project license. Contributions do not establish
a new license; licensing decisions belong to the repository owner.
