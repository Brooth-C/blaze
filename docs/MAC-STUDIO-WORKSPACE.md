# Mac Studio workspace

Selecting **Music Studio** opens the Logic-style arrangement and waveform workspace.
The native Browse sidebar and toolbar step aside on entry, leaving the Mac
titlebar above Studio's own transport. Leaving Studio restores browsing chrome
and appearance. Command-F returns to Explore search; Back is available at the
bottom of the Library panel.

Import a recording from the transport or File menu. Its real waveform appears in
the arrangement and the lower stereo editor. **Split stems** creates the saved
instrument tracks; selecting a track opens it in the existing Studio player.
Each saved stem has a **Save WAV** action in the inspector's playback options
(the + button below Audio FX). Waveform peak heights
are normalized for display; playback and exported audio are unchanged.

The transport provides play/pause, stop, ten-second navigation and repeat. The
inspector controls playback volume, mute, pan and speed. Channel EQ and
Compressor slots apply real effects to the current audition through Web Audio;
the output meters follow the actual audio signal. Project tempo, meter and key
can be edited from the transport, and the metronome follows that project grid.
Undo/redo covers local volume, pan, mute and zoom settings. The lower editor supports
click/drag seeking, keyboard seeking, zoom and Shift-drag range selection. Range
selection is a visual reference; exports save the complete original stem.
Dragging the arrangement ruler sets a genuine A–B cycle using the existing
playback loop. The lower range selection remains independent of that cycle.

The optional Library opens a list of actual session tracks. Categories and
Search tracks filter that list without removing arrangement tracks. Empty sessions offer Import; Blaze
does not populate a production session with demonstration recordings.
The transport starts with editable project defaults of 120 BPM, 4/4 and C major.
Those are project settings, not claims of detected musical properties. Actual
analysis can supply timing and key unless the project grid was manually changed.
The numbered rulers follow the current project grid.

The chord button beside Import/Split stems opens the existing chord-practice
drawer, retaining recognition,
notation, instrument diagrams, rhythm corrections and analysis exports.
The persistent media element is shared with Explore, Library and Now Playing.

Apple's public Logic Pro user-guide figures supply the workstation layout and
visual patterns; see the [design sources](MAC-STUDIO-DESIGN.md).
This change implements an audio/stem workspace. The MIDI tab and piano/synth
guide lanes display notes derived from chord analysis; they are explicitly guides,
not recovered original MIDI. MIDI sequencing, recording, virtual-instrument
patches, third-party plug-ins and destructive/fade editing need separate engine
work. Their reference controls retain an unavailable state. EQ, compression,
pan and volume are audition effects; WAV export keeps the saved stem unchanged.

The Library starts closed; the wide layout uses a 210 px Inspector and 310 px
track headers. The stereo amplitude gutter stays fixed while zoomed waveforms
scroll. Window/control chrome follows the user's appearance above dark editing
surfaces. Original Blaze instrument artwork is used. Smaller windows collapse
the panels and preserve the transport, arrangement and waveform viewport.

Waveform previews are generated locally through the packaged decoder and the
authenticated loopback API. They use at most 8,192 stereo peak pairs per channel,
a small bounded cache and at most two concurrent decodes. Changing the source
invalidates stale requests and old stem ownership. No audio leaves the Mac.
