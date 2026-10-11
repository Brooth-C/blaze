# Bundled native tools

Blaze builds FFmpeg 9.0.2 with LAME 3.100 and QuickJS-ng 0.17.0 from source for
ARM64 and x86_64. Android NDK 28.2 targets API 24 with 16 KB ELF alignment.
The executables are installed as extracted native APK files; they are not
downloaded or executed from writable application storage.

FFmpeg/LAME are standalone LGPL media programs. GPL, nonfree, and version3
features are disabled. QuickJS-ng is MIT-licensed. Their licenses are included
in APK assets. Blaze's reserved rights do not restrict modifying, replacing,
reverse engineering or redistributing these components under their own licenses.

The corresponding source archives and exact build script are attached to each
Android release as Blaze-Android-Native-Sources.tar.gz. Build with
`bash android/native/build.sh arm64-v8a` or `x86_64` on an isolated Linux runner
with the specified Android NDK. Rebuild/repackage the native components as
permitted by their licenses. This source offer applies to these LGPL programs,
not to Blaze's separately licensed UI/backend code.

FFmpeg release signatures are checked against its published signing-key
fingerprint. LAME's source archive is SHA-256 pinned. QuickJS-ng is pinned to
commit 6d46d07d04041b40f4f49eaa7fdebe44c314c699.

