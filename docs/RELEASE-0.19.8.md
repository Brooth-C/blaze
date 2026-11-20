# Blaze for Mac 0.19.8

- Native automatic update checks with Sparkle 2, plus **Blaze → Check for Updates…**.
- Updates use a dedicated Ed25519 signature and the stable Mac release feed. Downloads remain on GitHub.
- Installation waits for playback, chord/rhythm analysis, stem separation, audio exports and practice saves to become idle. Silent automatic installation is disabled.
- Compact chord-analysis progress with Reduce Motion support.
- Save practice in the header; saved songs open in an on-demand menu without filling the song workspace.

This build introduces the updater. Older builds do not have it, so users must install this release manually once. Update signatures are separate from Apple Developer ID signing and notarization; the initial Gatekeeper approval is still required for this ad-hoc-signed build.
