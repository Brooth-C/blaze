# Blaze for Mac 0.18.2

Studio keeps the original recording alongside separated stems, with a clear
Original label and the correct download filename and media type. Library track
selection now works, and Previous separations reopens earlier completed jobs
from the current app session. Starting, cancelling or failing a later split no
longer removes access to those completed files.

Chord analysis runs in the background while you open another recording or
switch stems. Its input remains available and results attach only to the
recording that was analysed. Returning to that recording restores its analysis.
Cancellation also works while its model is still opening.

Mixer gain, pan, mute and master volume changes support Undo and Redo, including
Command-Z and Shift-Command-Z. A drag is one undo action; changing the selected
track does not redirect an undo to another track. Reopening a separation restores
its playhead and original-track mixer settings.

Waveform previews recover from temporary decoder contention and stale responses.
Session validation avoids repeated filesystem lookups during waveform decoding.

The existing graphite appearance and GPU defaults are retained. Studio still
plays one selected recording or stem at a time; these changes do not add
simultaneous multitrack mixing or a full project-file system. Session history
is available until the app closes; saved audio remains in the Stems folder.
