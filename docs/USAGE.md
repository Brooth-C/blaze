# Dashboard and command-line usage

[Back to Blaze](../README.md)

## Dashboard controls

| Key | Action |
| --- | --- |
| N / P | Next / previous queue page |
| F | Failed downloads only |
| A | All downloads |
| D | Active and waiting downloads |
| Q / Ctrl+C | Stop downloads and keep partial files |

Use `--no-tui` for plain terminal output and `--no-aria2c` for native downloading.
Output history is scoped to format/quality and destination. Different media
jobs writing to the same folder are serialized to prevent overlapping writes.
Playlist reports describe the URL job result, not a per-track completeness audit.

Spotify/spotDL support has been removed. Download only media you are permitted to download.
