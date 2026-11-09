# Blaze: learn and practise songs

Blaze helps musicians take a real song apart, understand its chords and practise
one passage at a time. The first focused experience is piano practice on Apple
Silicon Macs.

The primary flow is: open or find a song, listen to the original, prepare its
piano and backing tracks when needed, slow down and loop a passage, follow the
chord guide, and play along. Playback and practice stay available while local
analysis or isolation runs. The original, piano and backing share a timeline;
changing listening mode preserves the passage and playback position.

A saved practice session remembers the recording, listening mode, position,
speed and A–B loop after app restart. Prepared tracks and completed analysis
should be reused rather than recomputed. Missing or changed files get a clear
recovery message. Chord recognition is a guide, not note-for-note piano
transcription.

The existing graphite appearance, local inference engines and GPU defaults
remain the foundation. Advanced Studio remains accessible for existing users.
Full DAW production, MIDI recording and a full Rust rewrite are deferred while
the practice experience is completed.

Success for this milestone means a user can open a song, practise its piano part
or play against its backing, close Blaze, and resume the same passage without
preparing the song again.
