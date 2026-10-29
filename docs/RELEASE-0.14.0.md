# Blaze for Mac 0.14.0

**Split stems → Nine stems** now exports **Vocals, Drums, Bass, Piano, Guitar,
Strings, Brass, Synths and Other** as nine independent WAVs.

The existing BS-RoFormer and piano stages create the main tracks. The new local
MVSep Mega instrument pass refines their Other track. Vocals, drums, bass and
piano are preserved; remaining unassigned instruments stay in Other. Related
guitar estimates compete for the same spectrum rather than being added twice.
At unity gain, the nine outputs reconstruct the original decoded recording.

**Five stems** remains available for a shorter workflow, and **Isolate piano**
still creates piano plus accompaniment. Nine-stem processing takes substantially
longer and increases the bundled model size. All processing stays on the Mac;
there is no account, audio upload or runtime model download.

The track list scrolls while its main actions remain visible. Each completed
track can be opened in the existing Studio player or exported individually.

These are instrument-family estimates, not recovered original studio tracks.
There can be bleed, missing notes and quiet estimates for absent instruments.
Other includes instruments such as woodwinds, organ, harp and remaining sounds.
The published open model differs from MVSep's newer hosted service model.

The creator explicitly permits commercial use, conversion and redistribution of
the new weights under MIT, without warranty or training-data indemnification.
Original notices and checksum-pinned provenance are bundled. See
[instrument model research and validation](MAC-INSTRUMENT-RESEARCH.md).

New Mac builds and native validation target **macOS 26 on Apple Silicon only**.
This release does not rebuild Windows, Linux or Android packages.
