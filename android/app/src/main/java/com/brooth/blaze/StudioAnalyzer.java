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
final class StudioAnalyzer {
    static final int VERSION = 5;
    static final int MAX_RESULTS = 128;
    static final long MAX_CACHE_BYTES = 32L * 1024 * 1024;
    private static final Object CACHE_LOCK = new Object();
    static final long MAX_BYTES = 2L * 1024 * 1024 * 1024, MAX_SAMPLES = StudioModels.RATE * 7200L;
    interface Progress { void update(String message); }
    static final class Result {
        final List<ChordEngine.Event> events;
        final long durationMs;
        final String key;
        final boolean cached;
        final float[] waveform;
        String identity,sourceHash;
        double tempo=Double.NaN;long[] beats=new long[0],downbeats=new long[0];
        StudioMeter.Estimate meter=new StudioMeter.Estimate();
        String modelName="Blaze Advanced Ensemble",modelHash="",engineVersion="structured1",rhythmModelHash="";
        Result(List<ChordEngine.Event> events,long duration,String key,boolean cached,float[] waveform){this.events=events;durationMs=duration;this.key=key;this.cached=cached;this.waveform=waveform;}
        Result(List<ChordEngine.Event> events, long duration, String key, boolean cached) {
            this(events,duration,key,cached,new float[0]);
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
            String sourceHash=hex(digest.digest());digest.update(sourceHash.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            for(String name:new String[]{"manifest.json","structured_manifest.json","rhythm_manifest.json"})try(InputStream manifest=app.getAssets().open("musicstudio_models/"+name)){digest.update(StudioModels.read(manifest,1024*1024));}
            digest.update("powerful:structured1:overlap1:rhythm1:cache5".getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder hash = new StringBuilder(); for (byte value : digest.digest()) hash.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
            File folder = new File(app.getFilesDir(), "studio-chords");
            if (!folder.isDirectory() && !folder.mkdirs()) throw new IOException("Could not save chord results.");
            AtomicFile cache = new AtomicFile(new File(folder, "v" + VERSION + "-" + hash + ".json"));
            Result saved;
            synchronized (CACHE_LOCK) {
                saved = read(cache);
                if (saved != null) {
                    cache.getBaseFile().setLastModified(System.currentTimeMillis());
                    prune(folder, cache.getBaseFile());
                }
            }
            if (saved != null) { check(); saved.identity=hash.toString();saved.sourceHash=sourceHash; return saved; }
            progress.update("Finding chords offline…");
            File executable = new File(app.getApplicationInfo().nativeLibraryDir, "libblaze_ffmpeg.so");
            if (!executable.isFile()) throw new IOException("Local media tools are missing. Install the complete Blaze APK.");
            Process running;
            synchronized (this) {
                check();
                // Restrict demuxer protocols too: a selected playlist cannot fetch remote resources.
                process = new ProcessBuilder(executable.getAbsolutePath(), "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-protocol_whitelist", "file,pipe", "-threads", "2", "-i", file.getAbsolutePath(), "-map", "0:a:0",
                    "-vn", "-sn", "-dn", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", "22050",
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
            StudioModels models = new StudioModels(app,"powerful",this::check);
            try {
            try(StudioEngine engine = new StudioEngine(app,models,this::check,progress)){
            long samples = 0, reported = -1;
            try (InputStream pcm = new BufferedInputStream(running.getInputStream(), 32768)) {
                track(pcm); wavHeader(pcm,StudioModels.RATE);
                byte[] bytes = new byte[16384]; int pending = -1, n;
                while ((n = pcm.read(bytes)) != -1) {
                    check();
                    for (int i = 0; i < n; i++) {
                        int value = bytes[i] & 255;
                        if (pending < 0) pending = value;
                        else { if (++samples > MAX_SAMPLES) throw new IOException("Choose media shorter than two hours."); engine.sample((short) (pending | value << 8) / 32768.0); pending = -1; }
                    }
                    long seconds = samples / StudioModels.RATE;
                    if (seconds != reported) { reported = seconds; progress.update("Finding chords offline · " + seconds + " seconds analysed"); }
                }
                if (pending >= 0) throw new IOException("The audio stream is incomplete.");
            }
            check();
            if (running.waitFor() != 0 || samples == 0) throw new IOException("No readable audio track. Try another audio or video file.");
            engine.decoded();
            StudioBeatDetector.Result rhythm=StudioBeatDetector.analyze(app,engine.audioFile(),samples,this::check,progress);
            Result result = new Result(engine.finish(rhythm.beats), engine.durationMs(), engine.key, false,engine.waveform());
            result.identity=hash.toString();result.sourceHash=sourceHash;result.tempo=rhythm.bpm;result.beats=rhythm.beats;result.downbeats=rhythm.downbeats;result.meter=rhythm.meter;
            result.modelHash=models.modelHash;result.rhythmModelHash=rhythm.modelHash;
            check(); write(cache, result); return result;
            }
            } finally { models.close(); }
        } catch (IOException error) {
            check(); throw error;
        } finally {
            synchronized (this) { if (process != null) { process.destroy(); process = null; } input = null; }
            if (temporary != null) temporary.delete();
        }
    }
    private static String hex(byte[] bytes){StringBuilder text=new StringBuilder();for(byte value:bytes)text.append(String.format(java.util.Locale.ROOT,"%02x",value&255));return text.toString();}
    private void copyAndHash(InputStream in, OutputStream out, MessageDigest digest) throws IOException {
        byte[] bytes = new byte[65536]; long size = 0; int n;
        while ((n = in.read(bytes)) != -1) { check(); size += n; if (size > MAX_BYTES) throw new IOException("Choose a file smaller than 2 GB."); digest.update(bytes, 0, n); if (out != null) out.write(bytes, 0, n); }
        if (size == 0) throw new IOException("This file is empty.");
    }
    static void wavHeader(InputStream in) throws IOException {
        wavHeader(in, ChordEngine.RATE);
    }
    static void wavHeader(InputStream in, int expectedRate) throws IOException {
        DataInputStream data = new DataInputStream(in); byte[] header = new byte[12]; data.readFully(header);
        if (!ascii(header, 0, "RIFF") || !ascii(header, 8, "WAVE")) throw new IOException("Could not decode the audio.");
        boolean format = false; long skipped = 0;
        while (skipped < 1048576) {
            byte[] chunk = new byte[8]; data.readFully(chunk); long length = unsigned32(chunk, 4);
            if (ascii(chunk, 0, "data")) { if (!format) throw new IOException("Missing audio format."); return; }
            if (length > 1048576) throw new IOException("Invalid decoded audio header.");
            byte[] payload = new byte[(int) length]; data.readFully(payload);
            if (ascii(chunk, 0, "fmt ")) {
                if (length < 16 || unsigned16(payload, 0) != 1 || unsigned16(payload, 2) != 1 || unsigned32(payload, 4) != expectedRate || unsigned16(payload, 14) != 16) throw new IOException("Unsupported decoded audio format.");
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
        if (!file.getBaseFile().isFile() || file.getBaseFile().length() > 16 * 1024 * 1024) return null;
        try (InputStream in = file.openRead(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int n; while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
            JSONObject data = new JSONObject(out.toString("UTF-8"));
            if (data.getInt("version") != VERSION) return null;
            long duration = data.getLong("durationMs"), previous = 0;
            if (duration <= 0 || duration > 7200000) return null;
            List<ChordEngine.Event> events = new ArrayList<>(); JSONArray entries = data.getJSONArray("events");
            if (entries.length() == 0 || entries.length() > 100000) return null;
            for (int i = 0; i < entries.length(); i++) {
                JSONObject e = entries.getJSONObject(i); long start = e.getLong("startMs"), end = e.getLong("endMs"); int chord = e.getInt("chord"); double score = e.getDouble("confidence");
                if (start != previous || end <= start || end > duration || !StudioChord.valid(chord) || !Double.isFinite(score) || score < 0 || score > 1) return null;
                events.add(new ChordEngine.Event(start, end, chord, score)); previous = end;
            }
            if (previous != duration) return null;
            JSONArray peaks=data.optJSONArray("waveform");float[] wave=new float[peaks==null?0:Math.min(2048,peaks.length())];for(int i=0;i<wave.length;i++){wave[i]=(float)peaks.getDouble(i);if(!Float.isFinite(wave[i])||wave[i]<0||wave[i]>1)return null;}
            Result result=new Result(events, duration, data.getString("key"), true,wave);result.tempo=data.optDouble("tempo",Double.NaN);
            result.beats=times(data.getJSONArray("beats"),duration);result.downbeats=times(data.getJSONArray("downbeats"),duration);result.meter=StudioRhythm.meterRead(data.optJSONObject("meter"),duration);
            result.modelName=data.getString("modelName");result.modelHash=data.getString("modelHash");result.engineVersion=data.getString("engineVersion");result.rhythmModelHash=data.getString("rhythmModelHash");
            if(!"Blaze Advanced Ensemble".equals(result.modelName)||!"structured1".equals(result.engineVersion)||!result.modelHash.matches("[a-f0-9]{64}")||!result.rhythmModelHash.matches("[a-f0-9]{64}"))return null;
            return result;
        } catch (Exception error) { return null; }
    }
    private void write(AtomicFile file, Result result) throws Exception {
        JSONArray entries = new JSONArray();
        for (ChordEngine.Event e : result.events) entries.put(new JSONObject().put("startMs", e.startMs).put("endMs", e.endMs).put("chord", e.chord).put("confidence", e.confidence));
        JSONArray wave=new JSONArray();for(float value:result.waveform)wave.put(value);
        JSONArray beats=new JSONArray();for(long t:result.beats)beats.put(t);
        JSONArray downbeats=new JSONArray();for(long t:result.downbeats)downbeats.put(t);
        JSONObject data = new JSONObject().put("beats",beats).put("downbeats",downbeats).put("meter",StudioRhythm.meterWrite(result.meter)).put("modelName",result.modelName).put("modelHash",result.modelHash).put("engineVersion",result.engineVersion).put("rhythmModelHash",result.rhythmModelHash).put("tempo",Double.isFinite(result.tempo)?result.tempo:JSONObject.NULL).put("waveform",wave).put("version", VERSION).put("durationMs", result.durationMs).put("key", result.key).put("events", entries);
        FileOutputStream out = null;
        // Cancellation and publication are serialized: cancelled work cannot publish a partial result.
        synchronized (CACHE_LOCK) { synchronized (this) {
            check();
            try { out = file.startWrite(); out.write(data.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)); file.finishWrite(out); }
            catch (Exception error) { if (out != null) file.failWrite(out); throw error; }
        } prune(file.getBaseFile().getParentFile(), file.getBaseFile()); }
    }
    private static long[] times(JSONArray values,long duration)throws Exception{if(values.length()>360001)throw new IOException("Invalid rhythm timeline.");long[] result=new long[values.length()];long previous=-1;for(int i=0;i<result.length;i++){long value=values.getLong(i);if(value<=previous||value<0||value>=duration)throw new IOException("Invalid rhythm timestamp.");result[i]=value;previous=value;}return result;}
    /** Evict oldest saved analyses; never touch source media or unrelated files. */
    static void prune(File folder, File keep) {
        synchronized (CACHE_LOCK) {
            File[] files = folder.listFiles(f -> f.isFile() && f.getName().matches("v[0-9]+-[a-f0-9]{64}\\.json"));
            if (files == null) return;
            java.util.Arrays.sort(files, java.util.Comparator.comparingLong(File::lastModified).reversed());
            long bytes = keep.isFile() ? keep.length() : 0; int count = keep.isFile() ? 1 : 0;
            for (File candidate : files) {
                if (candidate.equals(keep)) continue;
                long size = candidate.length();
                if (count >= MAX_RESULTS || bytes + size > MAX_CACHE_BYTES) new AtomicFile(candidate).delete();
                else { bytes += size; count++; }
            }
        }
    }
}
