package com.brooth.blaze;

import java.io.*;
import java.util.List;

/** Exercises the production WAV header reader and engine with real FFmpeg output. */
public final class ChordWavTest {
    public static void main(String[] args) throws Exception {
        ChordEngine engine = new ChordEngine();
        try (InputStream in = new BufferedInputStream(new FileInputStream(args[0]))) {
            ChordAnalyzer.wavHeader(in);
            int low, high;
            while ((low = in.read()) != -1) { high = in.read(); if (high < 0) throw new AssertionError("Truncated PCM"); engine.sample((short) (low | high << 8) / 32768.0); }
        }
        List<ChordEngine.Event> events = engine.finish();
        long offset = args.length > 1 ? Long.parseLong(args[1]) : 0;
        if (Math.abs(engine.durationMs() - 9000 - offset) > 100) throw new AssertionError("Wrong decoded duration: " + engine.durationMs());
        require(at(events, offset + 1500) == 0, "C"); require(at(events, offset + 4500) == 21, "Am"); require(at(events, offset + 7500) == 7, "G");
        if (offset > 0) require(at(events, offset / 2) == -1, "Leading silence aligns with video");
        System.out.println("Real decoder checks passed: " + engine.durationMs() + " ms, C / Am / G, video offset " + offset + " ms.");
    }
    private static int at(List<ChordEngine.Event> events, long ms) { return events.stream().filter(e -> e.startMs <= ms && ms < e.endMs).findFirst().orElseThrow().chord; }
    private static void require(boolean value, String chord) { if (!value) throw new AssertionError("Missing expected " + chord); }
}
