package com.brooth.blaze;

import android.content.Context;
import android.net.Uri;
import android.util.AtomicFile;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CancellationException;

/** Local-only decoder and content-addressed results. One instance per analysis task. */
final class ChordAnalyzer {
    static final int VERSION = 1;
    static final long MAX_BYTES = 2L * 1024 * 1024 * 1024, MAX_SAMPLES = ChordEngine.RATE * 7200L;
    interface Progress { void update(String message); }
    static final class Result {
        final List<ChordEngine.Event> events;
        final long durationMs;
        final String key;
        final boolean cached;
        Result(List<ChordEngine.Event> events, long duration, String key, boolean cached) {
            this.events = events; durationMs = duration; this.key = key; this.cached = cached;
        }
    }
    private volatile boolean cancelled;
    private Process process;
    private InputStream input;
    synchronized void cancel() {
        cancelled = true;
        if (process != null) process.destroy();
        if (input != null) try { input.close(); } catch (IOException ignored) { }
    }
    private void check() { if (cancelled || Thread.currentThread().isInterrupted()) throw new CancellationException(); }
    private synchronized void track(InputStream stream) throws IOException {
        if (cancelled) { stream.close(); throw new CancellationException(); }
        input = stream;
    }
    Result analyze(Context context, File file, Uri document, Progress progress) throws Exception {
        Context app = context.getApplicationContext();
        File temporary = null;
        try {
            progress.update("Reading media locally…");
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            if (document != null) {
                if (!"content".equals(document.getScheme())) throw new IOException("Choose a local audio or video file.");
                temporary = File.createTempFile("chord-input-", ".media", app.getCacheDir());
                try (InputStream in = app.getContentResolver().openInputStream(document); OutputStream out = new FileOutputStream(temporary)) {
                    if (in == null) throw new IOException("The selected file is unavailable.");
                    track(in); copyAndHash(in, out, digest);
                }
                file = temporary;
            } else {
                if (file == null || !file.isFile()) throw new IOException("The downloaded file is unavailable.");
                try (InputStream in = new FileInputStream(file)) { track(in); copyAndHash(in, null, digest); }
            }
            check();
            StringBuilder hash = new StringBuilder(); for (byte value : digest.digest()) hash.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
            File folder = new File(app.getFilesDir(), "chords");
            if (!folder.isDirectory() && !folder.mkdirs()) throw new IOException("Could not save chord results.");
            AtomicFile cache = new AtomicFile(new File(folder, "v" + VERSION + "-" + hash + ".json"));
            Result saved = read(cache);
            if (saved != null) { check(); return saved; }
            progress.update("Finding chords offline…");
            File executable = new File(app.getApplicationInfo().nativeLibraryDir, "libblaze_ffmpeg.so");
            if (!executable.isFile()) throw new IOException("Local media tools are missing. Install the complete Blaze APK.");
            Process running;
            synchronized (this) {
                check();
                // Restrict demuxer protocols too: a selected playlist cannot fetch remote resources.
                process = new ProcessBuilder(executable.getAbsolutePath(), "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-protocol_whitelist", "file,pipe", "-threads", "2", "-i", file.getAbsolutePath(), "-map", "0:a:0",
                    "-vn", "-sn", "-dn", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", "11025",
                    "-c:a", "pcm_s16le", "-f", "wav", "pipe:1").start();
                running = process;
            }
            // ProcessBuilder file redirection needs API 26; drain stderr on API 24 too.
            Thread errors = new Thread(() -> {
                try (InputStream stream = running.getErrorStream()) {
                    byte[] buffer = new byte[4096]; while (stream.read(buffer) != -1) { /* Discard decoder diagnostics, never media bytes or paths in UI. */ }
                } catch (IOException ignored) { /* Cancellation closes the process pipes. */ }
            }, "BlazeChordDecoderErrors");
            errors.setDaemon(true); errors.start();
            ChordEngine engine = new ChordEngine();
            long samples = 0, reported = -1;
            try (InputStream pcm = new BufferedInputStream(running.getInputStream(), 32768)) {
                track(pcm); wavHeader(pcm);
                byte[] bytes = new byte[16384]; int pending = -1, n;
                while ((n = pcm.read(bytes)) != -1) {
                    check();
                    for (int i = 0; i < n; i++) {
                        int value = bytes[i] & 255;
                        if (pending < 0) pending = value;
                        else { if (++samples > MAX_SAMPLES) throw new IOException("Choose media shorter than two hours."); engine.sample((short) (pending | value << 8) / 32768.0); pending = -1; }
                    }
                    long seconds = samples / ChordEngine.RATE;
                    if (seconds != reported) { reported = seconds; progress.update("Finding chords offline · " + seconds + " seconds analysed"); }
                }
                if (pending >= 0) throw new IOException("The audio stream is incomplete.");
            }
            check();
            if (running.waitFor() != 0 || samples == 0) throw new IOException("No readable audio track. Try another audio or video file.");
            Result result = new Result(engine.finish(), engine.durationMs(), engine.estimatedKey(), false);
            check(); write(cache, result); return result;
        } catch (IOException error) {
            check(); throw error;
        } finally {
            synchronized (this) { if (process != null) { process.destroy(); process = null; } input = null; }
            if (temporary != null) temporary.delete();
        }
    }
    private void copyAndHash(InputStream in, OutputStream out, MessageDigest digest) throws IOException {
        byte[] bytes = new byte[65536]; long size = 0; int n;
        while ((n = in.read(bytes)) != -1) { check(); size += n; if (size > MAX_BYTES) throw new IOException("Choose a file smaller than 2 GB."); digest.update(bytes, 0, n); if (out != null) out.write(bytes, 0, n); }
        if (size == 0) throw new IOException("This file is empty.");
    }
    static void wavHeader(InputStream in) throws IOException {
        DataInputStream data = new DataInputStream(in); byte[] header = new byte[12]; data.readFully(header);
        if (!ascii(header, 0, "RIFF") || !ascii(header, 8, "WAVE")) throw new IOException("Could not decode the audio.");
        boolean format = false; long skipped = 0;
        while (skipped < 1048576) {
            byte[] chunk = new byte[8]; data.readFully(chunk); long length = unsigned32(chunk, 4);
            if (ascii(chunk, 0, "data")) { if (!format) throw new IOException("Missing audio format."); return; }
            if (length > 1048576) throw new IOException("Invalid decoded audio header.");
            byte[] payload = new byte[(int) length]; data.readFully(payload);
            if (ascii(chunk, 0, "fmt ")) {
                if (length < 16 || unsigned16(payload, 0) != 1 || unsigned16(payload, 2) != 1 || unsigned32(payload, 4) != ChordEngine.RATE || unsigned16(payload, 14) != 16) throw new IOException("Unsupported decoded audio format.");
                format = true;
            }
            if ((length & 1) != 0) data.readByte(); skipped += length + 8;
        }
        throw new IOException("Invalid decoded audio header.");
    }
    private static boolean ascii(byte[] bytes, int start, String text) { for (int i = 0; i < text.length(); i++) if (bytes[start + i] != text.charAt(i)) return false; return true; }
    private static int unsigned16(byte[] bytes, int i) { return (bytes[i] & 255) | (bytes[i + 1] & 255) << 8; }
    private static long unsigned32(byte[] bytes, int i) { return unsigned16(bytes, i) | (long) unsigned16(bytes, i + 2) << 16; }
    private static Result read(AtomicFile file) {
        if (!file.getBaseFile().isFile() || file.getBaseFile().length() > 8 * 1024 * 1024) return null;
        try (InputStream in = file.openRead(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int n; while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
            JSONObject data = new JSONObject(out.toString("UTF-8"));
            if (data.getInt("version") != VERSION) return null;
            long duration = data.getLong("durationMs"), previous = 0;
            if (duration <= 0 || duration > 7200000) return null;
            List<ChordEngine.Event> events = new ArrayList<>(); JSONArray entries = data.getJSONArray("events");
            if (entries.length() == 0 || entries.length() > 40000) return null;
            for (int i = 0; i < entries.length(); i++) {
                JSONObject e = entries.getJSONObject(i); long start = e.getLong("startMs"), end = e.getLong("endMs"); int chord = e.getInt("chord"); double score = e.getDouble("confidence");
                if (start != previous || end <= start || end > duration || chord < -1 || chord >= 24 || !Double.isFinite(score) || score < 0 || score > 1) return null;
                events.add(new ChordEngine.Event(start, end, chord, score)); previous = end;
            }
            if (previous != duration) return null;
            return new Result(events, duration, data.getString("key"), true);
        } catch (Exception error) { return null; }
    }
    private void write(AtomicFile file, Result result) throws Exception {
        JSONArray entries = new JSONArray();
        for (ChordEngine.Event e : result.events) entries.put(new JSONObject().put("startMs", e.startMs).put("endMs", e.endMs).put("chord", e.chord).put("confidence", e.confidence));
        JSONObject data = new JSONObject().put("version", VERSION).put("durationMs", result.durationMs).put("key", result.key).put("events", entries);
        FileOutputStream out = null;
        // Cancellation and publication are serialized: cancelled work cannot publish a partial result.
        synchronized (this) {
            check();
            try { out = file.startWrite(); out.write(data.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)); file.finishWrite(out); }
            catch (Exception error) { if (out != null) file.failWrite(out); throw error; }
        }
    }
}
