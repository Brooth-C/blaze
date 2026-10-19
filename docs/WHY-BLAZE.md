# Why use Blaze? Save it, play it, understand it.

*A product vision and improvement roadmap. Features described as proposed are goals, not promises about the current release.*

Someone pasting a video link into a downloader usually wants more than a file. They want to watch it later, keep a useful recording, practise a song, or build a collection they can find again.

Blaze has the beginnings of a useful answer: bring downloading, a local library, playback and offline music analysis into the same app. Its strongest opportunity is to make that whole journey feel effortless.

The ambition should be bigger than collecting settings. A person should be able to say: **“I use Blaze because I can save a recording, play it, and work out how to play along—all in one place.”**

## What Blaze already brings together

Blaze documents audio and video downloading, quality and format choices, queues, supported partial-download resumption, audio conversion and separate audio/video merging. Its downloader uses yt-dlp, with optional aria2 support in the terminal engine.

The Windows and Mac apps include Downloads, Library and offline Music Studio. Android's preview includes local playback and Studio too. Studio provides chord analysis, beat/downbeat detection, piano and guitar diagrams, corrections, looping, timing adjustments and analysis exports. Transposition changes labels and diagrams; it does not change the recording's pitch.

That gives Blaze a practical story: download a recording you have permission to save, open it in Studio, inspect the suggested chords, correct uncertain passages, loop a section and practise.

There are limits to this story today. macOS and Android are previews. Android still needs physical-phone validation. Recognised chords may need correction, and documented checks do not establish accuracy across annotated real songs. Features and interfaces also vary by platform.

## How Blaze can earn the choice

Different tools already serve different needs well. Cobalt offers a simple browser experience. MeTube makes a server accessible through a web interface. Parabolic provides a focused desktop downloader. Seal and YTDLnis serve Android users. Pinchflat and Tube Archivist focus on collecting and managing YouTube media. yt-dlp supplies powerful downloading and automation.

Blaze should compete by making a complete personal workflow better, then prove each advantage. Calling it the best downloader before measuring it would weaken that case.

| User asks | Blaze's answer today | Improvement needed to strengthen it |
| --- | --- | --- |
| Why install this instead of using Cobalt? | Keep downloaded media, playback and music tools together locally. | Make the first download and the move into playback almost effortless. |
| Why use it instead of Parabolic? | Music Studio adds a way to study a recording after downloading it. | Validate analysis quality and make practice tools easy to discover. |
| Why use it instead of Seal or YTDLnis? | Android's preview combines downloads, playback and Studio. | Establish reliable behavior on real phones and graduate from preview. |
| Why use it instead of MeTube? | Blaze targets work on your own desktop or phone. | Make local organization, search and recovery dependable. |
| Why use it instead of yt-dlp directly? | Packaged interfaces and integrated media tools reduce manual steps. | Explain errors clearly while keeping useful advanced controls accessible. |
| Why use it instead of an archive manager? | Blaze is aimed at using and studying media interactively. | Add collection automation only when it serves that audience well. |

## 1. Make the first download feel obvious

**Proposed:** one clear starting point: paste a link, preview the title and duration, choose Video or Audio, and download. Remember the user's last sensible choices. Put codecs, connection settings and technical options behind an Advanced control.

Quality choices should describe the result: “Best available,” “Smaller file,” or “Audio for listening.” Always show the actual selected format and resolution before starting. Display estimated size only when the source provides enough information, and label estimates honestly.

For playlists, show the entries and let people choose which ones they want. After completion, offer useful next actions: Play, Open folder, or Open in Studio.

The benefit someone can repeat: **“Blaze makes downloading easy without making me learn downloader terminology.”**

## 2. Make reliability the foundation

**Proposed:** persist queue state across restarts; make supported resume behavior clear; prevent duplicate downloads; and provide safe, understandable retry controls. Track playlist outcomes per item so “completed” cannot hide missing tracks.

Failures should explain the next step. An unavailable video, a login requirement, a full disk and a site change need different messages. Preserve technical logs for troubleshooting, but lead with language a normal user can act on.

Keep the downloading engine current through a verifiable update process with recovery when an update fails. Test interrupted transfers, application restarts, storage exhaustion, Unicode filenames, overlapping playlists and expired authentication.

The benefit: **“I can leave Blaze working and understand exactly what finished.”**

## 3. Turn Music Studio into the strongest reason to stay

Blaze already has a substantial starting point here. The next step is evidence and polish.

**Proposed:** evaluate chord and timing results on a legally usable, annotated collection spanning different instruments, genres and recording quality. Publish the method, model versions, failures and results. A larger chord vocabulary alone does not demonstrate better accuracy.

Make uncertainty easy to understand. Keep manual correction fast and preserve edits when reopening a recording. Connect each selected passage to looping and suggested piano or guitar voicings. Verify exports against what the player actually displays.

Playback speed control with pitch preservation, saved practice sections and actual audio pitch shifting could be valuable additions. These are proposed features; the current label-transposition feature should never be presented as audio pitch shifting.

The benefit: **“Blaze helps me practise the recording I just saved.”**

## 4. Build a library people can trust

**Proposed:** let users search titles, creators and source links; organize media into collections; find duplicates; and reconnect files moved outside the app. Keep source attribution with each recording when available.

Make storage understandable: where the original file lives, what analysis data uses, and what each delete action removes. Support straightforward export and backup so users can keep their recordings and corrections independently of the app.

The benefit: **“My downloads become a useful collection I can find and keep.”**

## 5. Earn confidence on every advertised platform

**Proposed:** prioritize Windows reliability, macOS distribution and real-device Android testing before widening the platform promise. Publish a feature matrix that distinguishes GUI, terminal and preview capabilities.

On Android, validate background downloads, process termination, permissions, low storage, battery behavior and upgrade continuity. On macOS, improve signing and notarization. Across graphical interfaces, check keyboard navigation, screen-reader labels, contrast and smaller windows.

The benefit: **“Blaze behaves like an app made for my device.”**

## 6. Make trust visible

Local music analysis is a meaningful feature. Explain which operations stay on the device and which contact media services, update servers or other endpoints. Publish a clear account of telemetry and crash reporting based on actual behavior.

Document handling of cookies and credentials, release checksums, dependency updates and supported versions. Show users how to remove stored authentication.

Blaze's current license allows free use but requires permission for modification and redistribution. Describe it as **free to use**. An open-source license would be a separate ownership decision if community modification and redistribution become priorities.

The benefit: **“I understand what Blaze does with my files and what rights I have.”**

## What to build first

| Priority | Deliverable | Evidence that it works |
| --- | --- | --- |
| 1 | Simple first-download flow and clear failure messages | New users complete representative tasks without help; failures have actionable explanations. |
| 2 | Persistent queue, recovery and per-item playlist reporting | Interrupted jobs recover appropriately and every playlist item has a truthful outcome. |
| 3 | Reliable download-to-player-to-Studio journey | Users open, analyse, correct, loop and export a recording without losing work. |
| 4 | Platform readiness and accessible controls | Real-device checks and a published platform matrix support release claims. |
| 5 | Searchable library and portable backups | Users can find recordings and restore media metadata and Studio edits. |
| 6 | Optional browser handoff, subscriptions or remote access | User research shows these solve frequent needs worth their maintenance cost. |

## Prove advantages before advertising them

Use the same permitted source URLs, quality settings, hardware and network conditions when comparing downloaders. Record application and engine versions. Separate downloading from conversion time. Repeat trials and report failures alongside successful results.

Measure completion rate, time to first successful download, playlist completeness, restart recovery, resource use and the number of steps needed to reach playback. Evaluate music recognition separately against annotated reference data. Share the protocol and representative results so others can assess the claims.

Shared yt-dlp foundations mean Blaze cannot assume it supports more sites than other yt-dlp applications. Likewise, optional parallel downloading does not establish a universal speed advantage. Better defaults, clearer recovery and a useful integrated workflow are advantages Blaze can build and measure.

## The answer to “Why should I use Blaze?”

**A defensible answer today:**

> Use Blaze if you want downloading, local playback and offline music tools together. You can save audio or video, keep it in your library, and use Music Studio to explore chords and rhythm with practice diagrams and correction tools. Platform support varies, and the Mac and Android releases are previews.

**The answer to earn through the roadmap:**

> Blaze takes you from a link to a recording you can keep, enjoy and practise. It makes downloads dependable, keeps your collection organized and puts useful music tools beside the player.

That is a stronger product promise than “better than every downloader.” It tells a specific person why Blaze belongs in their everyday workflow—and gives the project a concrete standard to meet.

## References

Blaze's current capabilities and limitations: [project README](../README.md), [terminal usage](USAGE.md), [Android guide](ANDROID-APK.md), [Music Studio documentation](../music_studio/README.md), and [license](../LICENSE.txt).

Alternative project documentation: [Cobalt](https://github.com/imputnet/cobalt), [MeTube](https://github.com/alexta69/metube), [Parabolic](https://github.com/NickvisionApps/Parabolic), [Seal](https://github.com/JunkFood02/Seal), [YTDLnis](https://github.com/deniscerri/ytdlnis), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [Pinchflat](https://github.com/kieraneglin/pinchflat), and [Tube Archivist](https://github.com/tubearchivist/tubearchivist). Comparisons describe documented product focus, not a head-to-head benchmark.
