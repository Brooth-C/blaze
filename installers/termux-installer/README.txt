Blaze for Android / Termux (experimental)

Install a current Termux release from its official installation page:
https://github.com/termux/termux-app#installation
Requires Android 7+ and internet access. This is a terminal app, not a Blaze APK.

In Termux:
  pkg install unzip
  termux-setup-storage
Allow the storage permission if you want to access your Android Downloads folder.
Download and extract the entire Blaze-Termux-Installer.zip, then run:
  bash Install-Blaze.sh
After setup:
  bash ~/Blaze/Start-Blaze.sh

Python, FFmpeg and aria2 are installed through Termux's package manager.
Blaze and its private Python packages stay in ~/Blaze.
Default audio/video downloads are under ~/Blaze/Audio and ~/Blaze/Video.
To save into shared Android storage, pass:
  bash ~/Blaze/Start-Blaze.sh --output ~/storage/shared/Download/Blaze

Keep Termux in the foreground for long jobs; Android may stop background processes.
Close Blaze and rerun the installer to upgrade. Settings and downloads are preserved.
If Termux's Python changes major/minor version, recreate the private venv before setup.
Only the Termux installer is intended for Android; desktop Linux binaries are incompatible.
Desktop CI checks packaging and Android dependency selection. A real Android device
installation has not yet been verified; report issues with Android and Termux versions.

Copyright and usage terms: LICENSE.txt. Third-party licenses: THIRD-PARTY-NOTICES.md.
