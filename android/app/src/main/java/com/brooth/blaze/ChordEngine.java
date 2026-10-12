package com.brooth.blaze;

import java.util.ArrayList;
import java.util.List;

/** Streaming offline harmonic baseline. No Android, network, or model dependency. */
final class ChordEngine {
    static final int RATE = 11025, WINDOW = 8192, HOP = 2048;
    static final String[] NOTES = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
    // Start with triads: richer labels require evaluation against real annotated recordings.
    static final String[] QUALITIES = {"", "m"};
    private static final int[][] INTERVALS = {{0, 4, 7}, {0, 3, 7}};
    static final class Event {
        final long startMs, endMs;
        final int chord;
        final double confidence;
        Event(long start, long end, int chord, double confidence) {
            this.startMs = start; this.endMs = end; this.chord = chord; this.confidence = confidence;
        }
        String label(int transpose) { return chord == -2 ? "X" : chord < 0 ? "N" : NOTES[Math.floorMod(chord % 12 + transpose, 12)] + QUALITIES[chord / 12]; }
    }
    private final double[] samples = new double[WINDOW], real = new double[WINDOW], imaginary = new double[WINDOW];
    private final double[] window = new double[WINDOW], keyChroma = new double[12];
    private final List<Event> events = new ArrayList<>();
    private int filled;
    private long count, classifiedUntil;
    private boolean finished;
    private final List<Integer> labels = new ArrayList<>();
    private final List<Double> confidence = new ArrayList<>();

    ChordEngine() { for (int i = 0; i < WINDOW; i++) window[i] = .5 - .5 * Math.cos(2 * Math.PI * i / (WINDOW - 1)); }
    void sample(double value) {
        if (finished) throw new IllegalStateException("Analysis is complete");
        samples[filled++] = Double.isFinite(value) ? value : 0;
        count++;
        if (filled == WINDOW) {
            classify();
            System.arraycopy(samples, HOP, samples, 0, WINDOW - HOP);
            filled -= HOP;
        }
    }
    List<Event> finish() {
        if (finished) return new ArrayList<>(events);
        finished = true;
        if (count == 0) return new ArrayList<>();
        // A partial final window is zero padded, never dropped.
        if (classifiedUntil < count) {
            for (int i = filled; i < WINDOW; i++) samples[i] = 0;
            classify();
        }
        // Median voting removes isolated frame flips without assuming a song's key.
        int length = labels.size();
        int[] smoothed = new int[length];
        for (int i = 0; i < length; i++) {
            smoothed[i] = labels.get(i);
            if (i > 0 && i + 1 < length && labels.get(i - 1).equals(labels.get(i + 1))) smoothed[i] = labels.get(i - 1);
        }
        long duration = durationMs();
        int begin = 0;
        while (begin < length) {
            int end = begin + 1;
            double score = confidence.get(begin);
            while (end < length && smoothed[end] == smoothed[begin]) score += confidence.get(end++);
            long startMs = boundary(begin), endMs = end == length ? duration : boundary(end);
            if (endMs > startMs) events.add(new Event(startMs, endMs, smoothed[begin], score / (end - begin)));
            begin = end;
        }
        return new ArrayList<>(events);
    }
    private long boundary(int frame) {
        // Each frame represents its centre; label zero also covers the opening edge.
        return frame == 0 ? 0 : Math.min(durationMs(), Math.round((WINDOW / 2.0 + (frame - .5) * HOP) * 1000 / RATE));
    }
    long durationMs() { return Math.round(count * 1000.0 / RATE); }
    private void classify() {
        double energy = 0;
        for (int i = 0; i < WINDOW; i++) { energy += samples[i] * samples[i]; real[i] = samples[i] * window[i]; imaginary[i] = 0; }
        fft(real, imaginary);
        double[] chroma = new double[12];
        // Local peaks avoid spreading a single note into neighbouring pitch classes.
        for (int bin = 2; bin < WINDOW / 2 - 1; bin++) {
            double frequency = bin * (double) RATE / WINDOW;
            if (frequency < 65 || frequency > 2100) continue;
            double power = real[bin] * real[bin] + imaginary[bin] * imaginary[bin];
            double left = real[bin - 1] * real[bin - 1] + imaginary[bin - 1] * imaginary[bin - 1];
            double right = real[bin + 1] * real[bin + 1] + imaginary[bin + 1] * imaginary[bin + 1];
            if (power <= left || power < right || power < 1e-8) continue;
            double denominator = Math.log(Math.max(left, 1e-20)) - 2 * Math.log(power) + Math.log(Math.max(right, 1e-20));
            double offset = denominator == 0 ? 0 : .5 * (Math.log(Math.max(left, 1e-20)) - Math.log(Math.max(right, 1e-20))) / denominator;
            offset = Math.max(-.5, Math.min(.5, offset));
            double midi = 69 + 12 * Math.log((bin + offset) * RATE / WINDOW / 440.0) / Math.log(2);
            if (Math.abs(midi - Math.rint(midi)) > .4) continue;
            int pitch = Math.floorMod((int) Math.round(midi), 12);
            chroma[pitch] += Math.sqrt(power) / Math.sqrt(frequency);
        }
        double sum = 0;
        for (double value : chroma) sum += value;
        int best = -1;
        double first = -1, second = -1;
        double maximum = 0;
        if (sum > 0) {
            for (int i = 0; i < 12; i++) { chroma[i] /= sum; maximum = Math.max(maximum, chroma[i]); }
            for (int quality = 0; quality < INTERVALS.length; quality++) for (int root = 0; root < 12; root++) {
                double inside = 0, weakest = 1;
                for (int interval : INTERVALS[quality]) { double note = chroma[(root + interval) % 12]; inside += note; weakest = Math.min(weakest, note); }
                double score = inside + .4 * weakest;
                if (score > first) { second = first; first = score; best = quality * 12 + root; } else second = Math.max(second, score);
            }
        }
        double margin = Math.max(0, first - second);
        // Silence, single notes, and ambiguous noise are explicitly "no reliable chord".
        if (energy / WINDOW < 1e-7 || first < .60 || margin < .045 || maximum > .82) best = -1;
        if (best >= 0) for (int i = 0; i < 12; i++) keyChroma[i] += chroma[i];
        labels.add(best);
        confidence.add(best < 0 ? 0 : Math.min(1, margin / .3)); // heuristic, not calibrated probability
        classifiedUntil = count;
    }
    String estimatedKey() {
        double[] major = {6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88};
        double[] minor = {6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17};
        double total = 0; for (double value : keyChroma) total += value;
        if (total == 0) return "Unknown";
        double best = -2, second = -2; String key = "Unknown";
        for (int mode = 0; mode < 2; mode++) for (int root = 0; root < 12; root++) {
            double score = correlation(keyChroma, mode == 0 ? major : minor, root);
            if (score > best) { second = best; best = score; key = NOTES[root] + (mode == 0 ? " major" : " minor"); } else second = Math.max(second, score);
        }
        return best < .55 || best - second < .04 ? "Uncertain" : key;
    }
    private static double correlation(double[] values, double[] profile, int root) {
        double mean = 0, expected = 0; for (int i = 0; i < 12; i++) { mean += values[i]; expected += profile[i]; }
        mean /= 12; expected /= 12;
        double numerator = 0, a = 0, b = 0;
        for (int i = 0; i < 12; i++) { double x = values[(root + i) % 12] - mean, y = profile[i] - expected; numerator += x * y; a += x * x; b += y * y; }
        return a == 0 || b == 0 ? -1 : numerator / Math.sqrt(a * b);
    }
    private static void fft(double[] real, double[] imaginary) {
        int n = real.length;
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >> 1; for (; (j & bit) != 0; bit >>= 1) j ^= bit; j ^= bit;
            if (i < j) { double t = real[i]; real[i] = real[j]; real[j] = t; }
        }
        for (int size = 2; size <= n; size <<= 1) {
            double angle = -2 * Math.PI / size, wr = Math.cos(angle), wi = Math.sin(angle);
            for (int begin = 0; begin < n; begin += size) {
                double r = 1, im = 0;
                for (int i = 0; i < size / 2; i++) {
                    int a = begin + i, b = a + size / 2;
                    double tr = r * real[b] - im * imaginary[b], ti = r * imaginary[b] + im * real[b];
                    real[b] = real[a] - tr; imaginary[b] = imaginary[a] - ti; real[a] += tr; imaginary[a] += ti;
                    double next = r * wr - im * wi; im = r * wi + im * wr; r = next;
                }
            }
        }
    }
}
