Blaze for Linux (x86_64 / ARM64, glibc)

Extract the complete ZIP, then open a terminal in the extracted folder:
    bash Install-Blaze.sh
After setup:
    bash ~/Blaze/Start-Blaze.sh
Pass CLI arguments after the launcher, for example --help or --version.

Internet, Bash, curl, tar, sha256sum, awk, mktemp and glibc are required.
Alpine/musl and 32-bit Linux are not supported by this installer.
Python 3.13, dependencies, FFmpeg and aria2c install privately in ~/Blaze.
No sudo, system package installation, or shell profile changes are needed.
Close Blaze and rerun the installer to upgrade; settings and downloads remain.
The installer checks downloaded runtime hashes and validates the application
before replacing it. If setup fails, read the terminal error and retry.
