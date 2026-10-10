# Blaze 4.1.25

- Add an experimental Android / Termux installer with a private Blaze venv and Termux-native Python, FFmpeg and aria2.
- Prevent Android dependency fallback from downloading desktop Linux executables.
- Add Android setup and shared-storage instructions. Android device validation remains outstanding.

# Blaze 4.1.24

- Add a private Linux installer and terminal launcher for glibc x86_64 and ARM64.
- Package a Linux installer ZIP alongside the Windows and macOS installers.
- Gate release publication on Ubuntu x86_64 and ARM64 installer, upgrade,
  invalid-source rejection, HTTPS, and local-media download tests.
- Preserve the existing Windows/macOS installation and runtime behavior.
- Add troubleshooting guidance, Linux bug-report options, and stable download links.
- Include the Blaze Free-Use License and third-party notices in each installer ZIP.
