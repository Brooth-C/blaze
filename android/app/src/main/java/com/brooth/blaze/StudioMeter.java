package com.brooth.blaze;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Conservative pulse grouping from measured downbeats; notation is not guessed. */
final class StudioMeter {
    static final class Bar {
        final long start, end;
        final long[] beats;
        final int beatsPerBar;
        Bar(long start, long end, long[] beats) {
            this.start = start; this.end = end; this.beats = beats; this.beatsPerBar = beats.length;
        }
    }
    static final class Estimate {
        int beatsPerBar;
        String label = "Unknown";
        double confidence = Double.NaN;
        final List<Bar> bars = new ArrayList<>();
        boolean usable() { return !bars.isEmpty() && Double.isFinite(confidence) && confidence >= .5; }
    }
    private static final class Candidate {
        final Bar bar;
        final double pulse;
        Candidate(Bar bar, double pulse) { this.bar = bar; this.pulse = pulse; }
    }
    private static long[] timestamps(long[] values, long duration) {
        if (values == null) return null;
        long[] result = new long[values.length]; int count = 0;
        for (long value : values) {
            if (value < 0 || value > duration) continue;
            if (count > 0 && value < result[count - 1]) return null;
            if (count == 0 || value > result[count - 1]) result[count++] = value;
        }
        return Arrays.copyOf(result, count);
    }
    private static double median(long[] values) {
        long[] sorted = values.clone(); Arrays.sort(sorted);
        return sorted.length % 2 == 1 ? sorted[sorted.length / 2]
                : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2.0;
    }
    private static double ratio(double a, double b) { return Math.max(a, b) / Math.min(a, b); }
    private static void accept(List<Candidate> run, Estimate result) {
        if (run.size() >= 3) for (Candidate item : run) result.bars.add(item.bar);
        run.clear();
    }
    static Estimate estimate(long[] rawBeats, long[] rawDownbeats, long duration) {
        Estimate result = new Estimate();
        if (duration <= 0) return result;
        long[] beats = timestamps(rawBeats, duration), downbeats = timestamps(rawDownbeats, duration);
        if (beats == null || downbeats == null || beats.length < 3 || downbeats.length < 4) return result;
        List<Integer> indexes = new ArrayList<>(); List<Long> boundaries = new ArrayList<>();
        for (long time : downbeats) {
            int index = Arrays.binarySearch(beats, time);
            if (index < 0) index = -1;
            if (!indexes.isEmpty() && index >= 0 && index == indexes.get(indexes.size() - 1)) continue;
            indexes.add(index); boundaries.add(time);
        }
        if (indexes.size() < 4) return result;
        List<Candidate> run = new ArrayList<>();
        for (int i = 0; i + 1 < indexes.size(); i++) {
            int first = indexes.get(i), last = indexes.get(i + 1);
            Candidate candidate = null;
            if (first >= 0 && last >= 0 && last - first >= 2 && last - first <= 12) {
                long[] pulses = new long[last - first];
                for (int j = first; j < last; j++) pulses[j - first] = beats[j + 1] - beats[j];
                double typical = median(pulses); boolean valid = true;
                for (int j = 0; j < pulses.length; j++) {
                    valid &= pulses[j] >= 180 && pulses[j] <= 3000;
                    valid &= ratio(pulses[j], typical) <= 1.6;
                    if (j > 0) valid &= ratio(pulses[j], pulses[j - 1]) <= 1.6;
                }
                if (valid) candidate = new Candidate(new Bar(boundaries.get(i), boundaries.get(i + 1), Arrays.copyOfRange(beats, first, last)), typical);
            }
            if (candidate == null) { accept(run, result); continue; }
            if (!run.isEmpty()) {
                Candidate previous = run.get(run.size() - 1);
                if (candidate.bar.beatsPerBar != previous.bar.beatsPerBar || ratio(candidate.pulse, previous.pulse) > 1.6) accept(run, result);
            }
            run.add(candidate);
        }
        accept(run, result);
        if (result.bars.isEmpty()) return result;
        int count = result.bars.get(0).beatsPerBar;
        for (Bar bar : result.bars) if (bar.beatsPerBar != count) { count = 0; break; }
        result.beatsPerBar = count;
        result.label = count > 0 ? count + " beats/bar" : "Variable meter";
        result.confidence = Math.round(result.bars.size() * 1000000.0 / (indexes.size() - 1)) / 1000000.0;
        return result;
    }
}
