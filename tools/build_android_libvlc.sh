#!/usr/bin/env bash
set -euo pipefail
abi="${1:?Pass arm64-v8a or x86_64}"
case "$abi" in arm64-v8a|x86_64) ;; *) exit 2 ;; esac
root="$PWD"
task_build="$root/build/libvlc-$abi"
mkdir -p "$task_build/output/jniLibs/$abi" "$task_build/source"
git clone --single-branch --branch libvlcjni-3.x https://code.videolan.org/videolan/libvlcjni.git "$task_build/jni"
cd "$task_build/jni"
git checkout --detach 0b8dc65efb203c86a0476bc337ddd99ecf1c0ef6
git config user.name 'Blaze source build'
git config user.email 'build@example.invalid'
./buildsystem/get-vlc.sh
# Never use GPL prebuilt contribs. Build LGPL 2.1 + advertising-clause dependencies.
./buildsystem/compile-libvlc.sh -a "$abi" --release --license a --static-cpp
cp libvlc/jni/libs/"$abi"/*.so "$task_build/output/jniLibs/$abi/"
git archive --format=tar HEAD > "$task_build/source/libvlcjni-source.tar"
git -C vlc archive --format=tar HEAD > "$task_build/source/vlc-patched-source.tar"
cp -a vlc/contrib/tarballs "$task_build/source/contrib-tarballs"
printf '%s\n' 'LibVLC 3.7.7; JNI 0b8dc65efb203c86a0476bc337ddd99ecf1c0ef6' 'Build: compile-libvlc.sh --release --license a --static-cpp' > "$task_build/source/BUILD.txt"
cp "$root/tools/build_android_libvlc.sh" "$task_build/source/"
mkdir -p "$task_build/output/licenses"
cp libvlc/COPYING.LIB "$task_build/output/licenses/LIBVLC-LICENSE.txt"
if [ "$abi" = arm64-v8a ]; then
  tar -czf "$task_build/output/Blaze-LibVLC-Sources.tar.gz" -C "$task_build/source" .
fi
