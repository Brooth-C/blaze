# Mac Studio workspace

Selecting **Music Studio** opens the graphite arrangement and waveform workspace.
The native Browse sidebar collapses on entry; its toggle remains available.
Leaving Studio restores the previous browsing sidebar and appearance. Command-F
returns to Explore search.

Import a recording from the transport or File menu. Its real waveform appears in
the arrangement and the lower stereo editor. **Split stems** creates the saved
instrument tracks; selecting a track opens it in the existing Studio player.
Each saved stem has a **Save WAV** action in the inspector. Waveform peak heights
are normalized for display; playback and exported audio are unchanged.

The transport provides play/pause, stop, ten-second navigation and repeat. The
inspector controls playback volume, mute and speed. The lower editor supports
click/drag seeking, keyboard seeking, zoom and Shift-drag range selection. Range
selection is a visual reference; exports save the complete original stem.

Library categories filter the current audio tracks. Empty sessions offer Import;
Blaze does not populate a production session with demonstration recordings.
Actual timing from chord analysis supplies tempo, key and resolved bar/beat
information. Unresolved information stays blank. The timeline ruler uses elapsed
time, so an unanalysed recording does not acquire an invented tempo or meter.

**Chords** opens the existing chord-practice drawer, retaining recognition,
notation, instrument diagrams, rhythm corrections and analysis exports.
The persistent media element is shared with Explore, Library and Now Playing.

The approved production-session concept supplies the layout and visual style.
This change implements an audio/stem workspace. MIDI sequencing, recording,
virtual-instrument patches, plug-ins and destructive audio editing need separate
engine work and are not presented as working controls.

Waveform previews are generated locally through the packaged decoder and the
authenticated loopback API. They use at most 1,024 stereo peak pairs per channel,
a small bounded cache and at most two concurrent decodes. Changing the source
invalidates stale requests and old stem ownership. No audio leaves the Mac.
