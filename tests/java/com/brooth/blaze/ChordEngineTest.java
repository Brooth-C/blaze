package com.brooth.blaze;

import java.util.List;

/** Executable JVM regression tests, also called from the Android build workflow. */
public final class ChordEngineTest {
    public static void main(String[] args) {
        for (int quality = 0; quality < 2; quality++) for (int root = 0; root < 12; root++) {
            ChordEngine engine = new ChordEngine(); tone(engine, root, quality == 1, 3, true);
            List<ChordEngine.Event> events = engine.finish();
            int expected = quality * 12 + root;
            long matched = events.stream().filter(e -> e.chord == expected).mapToLong(e -> e.endMs - e.startMs).sum();
            require(matched > 2400, "Triad " + ChordEngine.NOTES[root] + (quality == 1 ? "m" : "") + ": " + describe(events));
            require(engine.finish().size() == events.size(), "finish must be idempotent");
            coverage(events, 3000);
        }
        ChordEngine sequence = new ChordEngine();
        tone(sequence, 0, false, 3, true); tone(sequence, 9, true, 3, true); silence(sequence, 2); tone(sequence, 7, false, 3, true);
        List<ChordEngine.Event> events = sequence.finish(); coverage(events, 11000);
        require(at(events, 1500) == 0, "C at opening"); require(at(events, 4500) == 21, "Am after transition");
        require(at(events, 7000) == -1, "Silence must not fabricate chords"); require(at(events, 9500) == 7, "G after silence");
        require(events.stream().anyMatch(e -> e.chord == 21 && Math.abs(e.startMs - 3000) < 500), "Transition timing: " + describe(events));
        require(new ChordEngine.Event(0, 1, 21, 1).label(3).equals("Cm"), "Transpose preserves quality");
        require(new ChordEngine.Event(0, 1, 0, 1).label(-1).equals("B"), "Negative transpose wraps");
        require(new ChordEngine.Event(0, 1, -1, 0).label(3).equals("N"), "Unknown does not transpose");
        ChordEngine quiet = new ChordEngine(); silence(quiet, 2);
        require(quiet.finish().stream().allMatch(e -> e.chord == -1), "Silence labels"); require(quiet.estimatedKey().equals("Unknown"), "Silence has no key");
        ChordEngine single = new ChordEngine();
        for (int i = 0; i < ChordEngine.RATE * 2; i++) single.sample(.5 * Math.sin(2 * Math.PI * 440 * i / ChordEngine.RATE));
        require(single.finish().stream().allMatch(e -> e.chord == -1), "A single note cannot establish a triad");
        ChordEngine noise = new ChordEngine(); java.util.Random random = new java.util.Random(42);
        for (int i = 0; i < ChordEngine.RATE * 3; i++) noise.sample((random.nextDouble() - .5) * .2);
        require(noise.finish().stream().filter(e -> e.chord >= 0).mapToLong(e -> e.endMs - e.startMs).sum() < 500, "Noise should remain uncertain");
        ChordEngine shortClip = new ChordEngine(); for (int i = 0; i < 100; i++) shortClip.sample(0);
        coverage(shortClip.finish(), Math.round(100000.0 / ChordEngine.RATE));
        require(new ChordEngine().finish().isEmpty(), "Empty input");
        System.out.println("Chord engine checks passed: 24 triads, timing, silence, single notes, noise, transposition, and complete coverage.");
    }
    private static void tone(ChordEngine engine, int root, boolean minor, int seconds, boolean harmonics) {
        int[] intervals = {0, minor ? 3 : 4, 7};
        for (int i = 0; i < ChordEngine.RATE * seconds; i++) {
            double value = 0;
            for (int interval : intervals) {
                double frequency = 440 * Math.pow(2, (48 + root + interval - 69) / 12.0);
                for (int h = 1; h <= (harmonics ? 4 : 1); h++) value += .12 / (h * h) * Math.sin(2 * Math.PI * frequency * h * i / ChordEngine.RATE);
            }
            engine.sample(value);
        }
    }
    private static void silence(ChordEngine engine, int seconds) { for (int i = 0; i < ChordEngine.RATE * seconds; i++) engine.sample(0); }
    private static int at(List<ChordEngine.Event> events, long ms) { return events.stream().filter(e -> e.startMs <= ms && ms < e.endMs).findFirst().orElseThrow().chord; }
    private static void coverage(List<ChordEngine.Event> events, long duration) { long last = 0; for (ChordEngine.Event e : events) { require(e.startMs == last && e.endMs > e.startMs, "Continuous timeline"); last = e.endMs; } require(last == duration, "Final partial audio frame retained"); }
    private static String describe(List<ChordEngine.Event> events) { StringBuilder out = new StringBuilder(); for (ChordEngine.Event e : events) out.append(e.label(0)).append('@').append(e.startMs).append('-').append(e.endMs).append(' '); return out.toString(); }
    private static void require(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
}
