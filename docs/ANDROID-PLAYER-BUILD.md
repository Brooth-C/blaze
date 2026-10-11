# Embedded player sources and replacement

Blaze uses LibVLC 3.7.7 Java bindings, with native libraries built independently
using VideoLAN's LGPL 2.1 + advertising-clause build profile (`--license a`).
The upstream Maven AAR's native libraries are removed before packaging.

`Blaze-Android-Native-Sources.tar.gz` includes the pinned JNI source, patched VLC
source, downloaded dependency sources, Java bindings source and exact build
script under `libvlc/`. Licenses and credits are also included in the APK.

To rebuild on Linux, install the dependencies listed in
`.github/workflows/android-libvlc.yml`, set ANDROID_HOME and ANDROID_NDK, and run
`bash tools/build_android_libvlc.sh arm64-v8a` (or `x86_64`). The workflow documents
how to copy native libraries into the app and create the Java-only AAR. Build the
APK using `android/gradlew`; sign replacement builds with your own key.

The corresponding source archives may be unpacked into the build directory to
rebuild modified third-party libraries. Their licenses grant their own rights.
Blaze's reserved rights do not restrict replacement of LGPL components or reverse
engineering needed to debug those modifications, as required by the LGPL. This
does not grant general permission to distribute modified Blaze code.

Android requires matching signatures for updates. Export files before replacing
an installed APK signed by a different key.
