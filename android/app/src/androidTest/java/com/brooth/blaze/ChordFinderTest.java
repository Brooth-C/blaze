package com.brooth.blaze;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import androidx.core.content.FileProvider;
import androidx.lifecycle.Lifecycle;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.util.UUID;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class ChordFinderTest {
    private final Context app = InstrumentationRegistry.getInstrumentation().getTargetContext();
    @Test public void offlineAudioVideoCacheAndSyncedPlayback() throws Exception {
        File folder = new File(DownloadService.folder(app), "chord-test-" + UUID.randomUUID()); assertTrue(folder.mkdirs());
        File audio = new File(folder, "triads.wav"), video = new File(folder, "triads.mkv"), silentVideo = new File(folder, "silent.mp4");
        String id = null;
        try {
            writeChords(audio);
            ChordAnalyzer.Result detected = new ChordAnalyzer().analyze(app, audio, null, message -> { });
            assertFalse(detected.cached); assertEquals(9000, detected.durationMs);
            assertEquals(0, at(detected, 1500)); assertEquals(21, at(detected, 4500)); assertEquals(7, at(detected, 7500));
            assertTrue(new ChordAnalyzer().analyze(app, audio, null, message -> { }).cached);
            Uri selected = FileProvider.getUriForFile(app, app.getPackageName() + ".files", audio);
            assertTrue(new ChordAnalyzer().analyze(app, null, selected, message -> { }).cached);
            ChordAnalyzer cancelled = new ChordAnalyzer(); cancelled.cancel();
            try { cancelled.analyze(app, audio, null, message -> { }); fail("Cancelled work cannot return a cached result"); } catch (CancellationException expected) { }
            try (InputStream in = InstrumentationRegistry.getInstrumentation().getContext().getAssets().open("fixture-video.mp4"); OutputStream out = new FileOutputStream(silentVideo)) { byte[] b = new byte[8192]; int n; while ((n = in.read(b)) != -1) out.write(b, 0, n); }
            File ffmpeg = new File(app.getApplicationInfo().nativeLibraryDir, "libblaze_ffmpeg.so");
            Process mux = new ProcessBuilder(ffmpeg.getAbsolutePath(), "-nostdin", "-loglevel", "error", "-i", silentVideo.getAbsolutePath(), "-i", audio.getAbsolutePath(), "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", video.getAbsolutePath()).redirectErrorStream(true).start();
            try (InputStream in = mux.getInputStream()) { while (in.read() != -1) { } } assertEquals(0, mux.waitFor());
            ChordAnalyzer.Result videoResult = new ChordAnalyzer().analyze(app, video, null, message -> { });
            assertEquals(detected.durationMs, videoResult.durationMs); assertEquals(0, at(videoResult, 1500)); assertEquals(21, at(videoResult, 4500)); assertEquals(7, at(videoResult, 7500));
            try { new ChordAnalyzer().analyze(app, silentVideo, null, message -> { }); fail("Video without audio must fail clearly"); } catch (IOException expected) { }
            try (JobStore store = new JobStore(app)) {
                assertFalse(store.hasQueued()); id = store.enqueue("https://example.test/chords/" + UUID.randomUUID(), "video", "{}", "Offline chord test"); assertEquals(id, store.claimNext().id);
                store.finish(id, "complete", "Offline chord test", video.getAbsolutePath(), "");
            }
            try (ActivityScenario<ChordActivity> screen = ActivityScenario.launch(new Intent(app, ChordActivity.class).putExtra("job", id))) {
                ready(screen);
                screen.onActivity(a -> { assertTrue(a.result.cached); a.onPlaybackTime(1500); assertEquals("Now: C", ((android.widget.TextView) a.findViewById(R.id.chord_current)).getText().toString()); a.onPlaybackTime(4500); assertEquals("Now: Am", ((android.widget.TextView) a.findViewById(R.id.chord_current)).getText().toString()); a.toggle.performClick(); });
                screen.recreate(); ready(screen);
                screen.moveToState(Lifecycle.State.CREATED); screen.onActivity(a -> assertNull(a.player));
            }
            try (ActivityScenario<ChordActivity> screen = ActivityScenario.launch(new Intent(app, ChordActivity.class).setData(selected))) { ready(screen); screen.onActivity(a -> assertTrue(a.result.cached)); }
            // Changing the same file's contents invalidates the saved analysis.
            try (RandomAccessFile changed = new RandomAccessFile(audio, "rw")) { changed.seek(44); changed.writeShort(123); }
            assertFalse(new ChordAnalyzer().analyze(app, audio, null, message -> { }).cached);
        } finally {
            if (id != null) { try (JobStore store = new JobStore(app)) { store.getWritableDatabase().delete("jobs", "id=?", new String[]{id}); } app.getSharedPreferences("playback", Context.MODE_PRIVATE).edit().remove(id).apply(); }
            audio.delete(); video.delete(); silentVideo.delete(); folder.delete();
        }
    }
    private void ready(ActivityScenario<ChordActivity> screen) throws Exception {
        long until = System.currentTimeMillis() + 20000; AtomicBoolean ready = new AtomicBoolean();
        while (!ready.get() && System.currentTimeMillis() < until) { screen.onActivity(a -> ready.set(a.result != null && a.player != null && a.player.getLength() > 0)); Thread.sleep(50); }
        assertTrue("Local chord screen did not become ready", ready.get());
    }
    private static int at(ChordAnalyzer.Result result, long ms) { return result.events.stream().filter(e -> e.startMs <= ms && ms < e.endMs).findFirst().orElseThrow(() -> new AssertionError("Missing chord segment")).chord; }
    private static void writeChords(File file) throws IOException {
        int rate = 44100, samples = rate * 9; java.util.Random unique = new java.util.Random(); double phase = unique.nextDouble();
        try (DataOutputStream out = new DataOutputStream(new BufferedOutputStream(new FileOutputStream(file)))) {
            out.writeBytes("RIFF"); le32(out, 36 + samples * 2); out.writeBytes("WAVEfmt "); le32(out, 16); le16(out, 1); le16(out, 1); le32(out, rate); le32(out, rate * 2); le16(out, 2); le16(out, 16); out.writeBytes("data"); le32(out, samples * 2);
            int[] roots = {0, 9, 7};
            for (int i = 0; i < samples; i++) {
                int section = i / (rate * 3); double value = 0;
                for (int interval : new int[]{0, section == 1 ? 3 : 4, 7}) { double frequency = 440 * Math.pow(2, (48 + roots[section] + interval - 69) / 12.0); for (int harmonic = 1; harmonic <= 4; harmonic++) value += .12 / (harmonic * harmonic) * Math.sin(phase + 2 * Math.PI * frequency * harmonic * i / rate); }
                le16(out, (int) (value * 32767));
            }
        }
    }
    private static void le16(DataOutputStream out, int n) throws IOException { out.writeByte(n); out.writeByte(n >> 8); }
    private static void le32(DataOutputStream out, int n) throws IOException { le16(out, n); le16(out, n >> 16); }
}
