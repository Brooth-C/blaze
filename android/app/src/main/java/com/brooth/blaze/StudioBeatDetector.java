package com.brooth.blaze;

import android.content.Context;
import ai.onnxruntime.*;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.security.MessageDigest;
import java.util.*;

/** Verified offline Beat This! model, using the same frontend and decoder as Windows. */
final class StudioBeatDetector {
    static final class Result {
        final double bpm;
        final long[] beats, downbeats;
        final StudioMeter.Estimate meter;
        final String modelHash;
        Result(long[] beats, long[] downbeats, long duration, String hash) {
            this.beats = beats; this.downbeats = downbeats;
            bpm = StudioSignal.tempo(beats); meter = StudioMeter.estimate(beats, downbeats, duration); modelHash = hash;
        }
    }
    static Result analyze(Context context, File pcm, long samples, Runnable check, StudioAnalyzer.Progress progress) throws Exception {
        Context app = context.getApplicationContext(); check.run();
        JSONObject manifest;
        try (InputStream input = app.getAssets().open("musicstudio_models/rhythm_manifest.json")) {
            manifest = new JSONObject(new String(StudioModels.read(input, 65536), java.nio.charset.StandardCharsets.UTF_8));
        }
        String[] fields = {"schema_version", "sample_rate", "hop_length", "n_fft", "fps", "chunk_frames", "border_frames"};
        int[] expected = {1, 22050, 441, 1024, 50, 1500, 6};
        for (int i = 0; i < fields.length; i++) if (manifest.getInt(fields[i]) != expected[i]) throw new IOException("Incompatible offline rhythm model.");
        JSONObject networkMetadata = manifest.getJSONObject("network");
        String hash = networkMetadata.getString("sha256");
        byte[] frontend = smallAsset(app, manifest.getJSONObject("frontend"));
        long duration = Math.round(samples * 1000.0 / 22050);
        File features = File.createTempFile("blaze-rhythm-", ".f32", app.getCacheDir());
        try {
            PythonRuntime.get(app);
            PyObject bridge = Python.getInstance().getModule("blaze_rhythm");
            progress.update("Finding beats and meter offline…");
            JSONObject prepared = new JSONObject(bridge.callAttr("prepare_rhythm", pcm.getAbsolutePath(), frontend, features.getAbsolutePath(), samples, check).toString());
            int frames = prepared.getInt("frames"); check.run();
            if (frames < 200 || !prepared.getBoolean("audible")) return new Result(new long[0], new long[0], duration, hash);
            if (frames > 360001 || features.length() != frames * 128L * 4) throw new IOException("Invalid rhythm features.");
            File network = networkAsset(app, networkMetadata, check);
            OrtEnvironment environment = OrtEnvironment.getEnvironment("BlazeMusicStudio"); environment.setTelemetry(false);
            float[][] predictions = new float[2][frames]; boolean[] filled = new boolean[frames];
            for (float[] channel : predictions) Arrays.fill(channel, -1000);
            int chunks = (frames + 1487) / 1488;
            try (OrtSession.SessionOptions options = new OrtSession.SessionOptions()) {
                options.setIntraOpNumThreads(2); options.setInterOpNumThreads(1);
                options.setExecutionMode(OrtSession.SessionOptions.ExecutionMode.SEQUENTIAL);
                try (OrtSession session = environment.createSession(network.getAbsolutePath(), options)) {
                    for (int number = 0; number < chunks; number++) {
                        check.run(); progress.update("Finding beats and meter offline · " + (number + 1) + " / " + chunks);
                        int start = -6 + number * 1488;
                        if (frames > 1488 && number == chunks - 1) start = frames - 1494;
                        byte[] raw = bridge.callAttr("rhythm_chunk", features.getAbsolutePath(), frames, start).toJava(byte[].class);
                        if (raw.length % (128 * 4) != 0) throw new IOException("Invalid rhythm chunk.");
                        int length = raw.length / (128 * 4);
                        ByteBuffer buffer = ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN);
                        try (OnnxTensor input = OnnxTensor.createTensor(environment, buffer.asFloatBuffer(), new long[]{1, length, 128});
                             OrtSession.Result outputs = session.run(Collections.singletonMap("spect", input))) {
                            if (outputs.size() != 2) throw new IOException("Invalid rhythm network output.");
                            for (int channel = 0; channel < 2; channel++) {
                                float[][] found = (float[][]) outputs.get(channel).getValue();
                                if (found.length != 1 || found[0].length != length) throw new IOException("Invalid rhythm network output.");
                                for (int i = 6; i < length - 6; i++) {
                                    int destination = start + i;
                                    if (destination < 0 || destination >= frames) throw new IOException("Invalid rhythm overlap.");
                                    if (!filled[destination]) predictions[channel][destination] = found[0][i];
                                }
                            }
                            for (int i = 6; i < length - 6; i++) filled[start + i] = true;
                        }
                    }
                }
            }
            for (boolean valid : filled) if (!valid) throw new IOException("Incomplete rhythm prediction.");
            check.run();
            long[] beats = beforeEnd(StudioSignal.peakTimes(predictions[0]), duration);
            long[] rawDownbeats = beforeEnd(StudioSignal.peakTimes(predictions[1]), duration);
            TreeSet<Long> aligned = new TreeSet<>();
            for (long downbeat : rawDownbeats) {
                if (beats.length == 0) break;
                int index = Arrays.binarySearch(beats, downbeat);
                if (index < 0) {
                    int right = -index - 1;
                    if (right == 0) index = 0;
                    else if (right == beats.length) index = beats.length - 1;
                    else index = downbeat - beats[right - 1] <= beats[right] - downbeat ? right - 1 : right;
                }
                aligned.add(beats[index]);
            }
            long[] downbeats = new long[aligned.size()]; int i = 0; for (long beat : aligned) downbeats[i++] = beat;
            return new Result(beats, downbeats, duration, hash);
        } catch (Exception error) {
            // Chaquopy wraps exceptions raised by the Java cancellation hook.
            // Recheck here so cancellation remains a CancellationException.
            check.run(); throw error;
        } finally { features.delete(); }
    }
    private static long[] beforeEnd(long[] times, long duration) {
        int count = 0; while (count < times.length && times[count] < duration) count++;
        return Arrays.copyOf(times, count);
    }
    private static String name(JSONObject metadata) throws Exception {
        String name = metadata.getString("file");
        if (!name.matches("[a-zA-Z0-9_.-]+") || name.contains("..") || !metadata.getString("sha256").matches("[a-f0-9]{64}")) throw new IOException("Invalid rhythm asset path.");
        return name;
    }
    private static byte[] smallAsset(Context app, JSONObject metadata) throws Exception {
        byte[] data;
        try (InputStream input = app.getAssets().open("musicstudio_models/" + name(metadata))) { data = StudioModels.read(input, 4 * 1024 * 1024); }
        if (!StudioModels.hash(data).equals(metadata.getString("sha256"))) throw new IOException("Rhythm asset verification failed.");
        return data;
    }
    private static File networkAsset(Context app, JSONObject metadata, Runnable check) throws Exception {
        String asset = name(metadata), hash = metadata.getString("sha256");
        File target = new File(app.getCacheDir(), "blaze-beat-" + hash + ".onnx");
        if (target.isFile() && hashFile(target, check).equals(hash)) return target;
        File temporary = File.createTempFile("blaze-beat-", ".tmp", app.getCacheDir());
        try {
            try (InputStream input = app.getAssets().open("musicstudio_models/" + asset); OutputStream output = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[65536]; long total = 0; int n;
                while ((n = input.read(buffer)) != -1) {
                    check.run(); total += n;
                    if (total > 200L * 1024 * 1024) throw new IOException("Rhythm model is too large.");
                    output.write(buffer, 0, n);
                }
            }
            if (!hashFile(temporary, check).equals(hash)) throw new IOException("Rhythm asset verification failed.");
            if (!temporary.renameTo(target)) throw new IOException("Could not load the offline rhythm model.");
            return target;
        } finally { temporary.delete(); }
    }
    private static String hashFile(File file, Runnable check) throws Exception {
        if (file.length() > 200L * 1024 * 1024) return "";
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[65536]; int n;
            while ((n = input.read(buffer)) != -1) { check.run(); digest.update(buffer, 0, n); }
        }
        StringBuilder text = new StringBuilder(); for (byte value : digest.digest()) text.append(String.format(Locale.ROOT, "%02x", value & 255));
        return text.toString();
    }
}
