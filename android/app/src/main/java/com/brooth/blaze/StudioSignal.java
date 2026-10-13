package com.brooth.blaze;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Exact Beat This! peak decoder; no spectral-flux beat guesses. */
final class StudioSignal {
    static long[] peakTimes(float[] logits) {
        List<Long> peaks = new ArrayList<>();
        double mean = Double.NaN;
        int count = 0;
        for (int i = 0; i < logits.length; i++) {
            if (!Float.isFinite(logits[i])) throw new IllegalArgumentException("Invalid rhythm prediction.");
            if (logits[i] <= 0) continue;
            float maximum = logits[i];
            for (int j = Math.max(0, i - 3); j <= Math.min(logits.length - 1, i + 3); j++) maximum = Math.max(maximum, logits[j]);
            if (logits[i] != maximum) continue;
            // Merge adjacent maxima against their running mean, matching upstream.
            if (Double.isFinite(mean) && i - mean <= 1) {
                count++; mean += (i - mean) / count;
            } else {
                if (Double.isFinite(mean)) peaks.add(Math.round(mean * 20));
                mean = i; count = 1;
            }
        }
        if (Double.isFinite(mean)) peaks.add(Math.round(mean * 20));
        long[] result = new long[peaks.size()];
        for (int i = 0; i < result.length; i++) result[i] = peaks.get(i);
        return result;
    }

    static double tempo(long[] beats) {
        if (beats.length < 4) return Double.NaN;
        long[] intervals = new long[beats.length - 1];
        for (int i = 0; i < intervals.length; i++) {
            intervals[i] = beats[i + 1] - beats[i];
            if (intervals[i] <= 0) return Double.NaN;
        }
        Arrays.sort(intervals);
        double typical = intervals.length % 2 == 1 ? intervals[intervals.length / 2]
                : (intervals[intervals.length / 2 - 1] + intervals[intervals.length / 2]) / 2.0;
        return Math.round(600000 / typical) / 10.0;
    }
}
