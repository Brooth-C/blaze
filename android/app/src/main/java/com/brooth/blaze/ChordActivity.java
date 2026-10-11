package com.brooth.blaze;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.*;
import java.util.Locale;
import java.util.concurrent.*;

/** Chords follow the embedded audio/video player's actual position, including seeks. */
public class ChordActivity extends VlcPlayerActivity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler updates = new Handler(Looper.getMainLooper());
    private ChordAnalyzer analyzer;
    private Future<?> task;
    private int generation, transpose, page;
    private boolean automatic = true;
    private long playbackTime;
    private TextView state, current, next, summary, shift;
    private LinearLayout rows;
    private Button analyze, cancel, previous, following;
    private ChordDiagramView diagram;
    private boolean guitar;
    ChordAnalyzer.Result result;
    private static final int PAGE_SIZE = 30;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        if (root == null || isFinishing()) return;
        if (saved != null) { transpose = Math.max(-12, Math.min(12, saved.getInt("transpose"))); page = saved.getInt("chordPage"); automatic = saved.getBoolean("chordAutomatic", true); guitar = saved.getBoolean("guitar"); }
        LinearLayout panel = new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(12), dp(6), dp(12), dp(6));
        // Keep the chord panel near the player. A bounded scroll area fits small screens.
        ScrollView scroll = new ScrollView(this); scroll.setId(R.id.chord_panel); scroll.addView(panel);
        root.addView(scroll, 2, new LinearLayout.LayoutParams(-1, panelHeight()));
        state = text(panel, "Offline chord finder", 14); state.setId(R.id.chord_status);
        current = text(panel, "Now: —", 24); current.setId(R.id.chord_current);
        next = text(panel, "Next: —", 16);
        LinearLayout instruments = new LinearLayout(this); panel.addView(instruments);
        button(instruments, "Piano", () -> { guitar = false; onPlaybackTime(playbackTime); });
        button(instruments, "Guitar", () -> { guitar = true; onPlaybackTime(playbackTime); });
        diagram = new ChordDiagramView(this); panel.addView(diagram, new LinearLayout.LayoutParams(-1, dp(150)));
        summary = text(panel, "Estimated major/minor chords. N means no reliable chord. Check uncertain passages by ear.", 12);
        LinearLayout actions = new LinearLayout(this); panel.addView(actions);
        analyze = button(actions, "Analyse", () -> { automatic = true; startAnalysis(); }); analyze.setId(R.id.chord_analyze);
        cancel = button(actions, "Cancel", () -> { automatic = false; stopAnalysis(); state.setText("Analysis cancelled. Tap Analyse to retry."); }); cancel.setId(R.id.chord_cancel); cancel.setEnabled(false);
        LinearLayout transposition = new LinearLayout(this); panel.addView(transposition);
        button(transposition, "−", () -> transpose(-1)); shift = text(transposition, "Transpose: " + transpose, 12);
        button(transposition, "+", () -> transpose(1)); button(transposition, "Reset", () -> { transpose = 0; render(); });
        text(panel, "Transposition changes chord labels; playback keeps its original pitch.", 12);
        rows = new LinearLayout(this); rows.setOrientation(LinearLayout.VERTICAL); panel.addView(rows);
        LinearLayout paging = new LinearLayout(this); panel.addView(paging);
        previous = button(paging, "Earlier", () -> { page = Math.max(0, page - 1); render(); });
        following = button(paging, "Later", () -> { page++; render(); });
        previous.setEnabled(false); following.setEnabled(false);
    }
    private void startAnalysis() {
        if (task != null && !task.isDone() || root == null || isFinishing()) return;
        final int request = ++generation;
        analyzer = new ChordAnalyzer(); final ChordAnalyzer operation = analyzer;
        analyze.setEnabled(false); cancel.setEnabled(true); state.setText("Reading media locally…");
        // Application context and local source only; no Activity is passed to the decoder.
        android.content.Context app = getApplicationContext();
        java.io.File file = source == null ? null : source.file;
        android.net.Uri uri = document;
        task = worker.submit(() -> {
            try {
                ChordAnalyzer.Result ready = operation.analyze(app, file, uri, message -> updates.post(() -> { if (request == generation) state.setText(message); }));
                updates.post(() -> {
                    if (request != generation || isFinishing() || isDestroyed()) return;
                    result = ready; automatic = false; task = null; analyze.setEnabled(true); cancel.setEnabled(false);
                    state.setText(ready.cached ? "Saved offline analysis" : "Analysis saved offline"); render();
                });
            } catch (CancellationException ignored) {
                // stopAnalysis invalidates all callbacks before cancelling the decoder.
            } catch (Exception error) {
                updates.post(() -> {
                    if (request != generation || isFinishing() || isDestroyed()) return;
                    task = null; automatic = false; analyze.setEnabled(true); cancel.setEnabled(false);
                    state.setText(error instanceof java.io.IOException ? error.getMessage() : "Could not analyse this file. Try again.");
                });
            }
        });
    }
    private void stopAnalysis() {
        generation++;
        if (analyzer != null) analyzer.cancel();
        if (task != null) task.cancel(true);
        task = null; analyzer = null;
        if (analyze != null) { analyze.setEnabled(true); cancel.setEnabled(false); }
    }
    private void transpose(int delta) { transpose = Math.max(-12, Math.min(12, transpose + delta)); render(); }
    private void render() {
        shift.setText("Transpose: " + (transpose > 0 ? "+" : "") + transpose);
        rows.removeAllViews();
        if (result == null) return;
        summary.setText("Estimated original key: " + result.key + " · " + result.events.size() + " segments · major/minor baseline\nN = no reliable chord. Check results by ear.");
        page = Math.max(0, Math.min(page, (result.events.size() - 1) / PAGE_SIZE));
        previous.setEnabled(page > 0); following.setEnabled((page + 1) * PAGE_SIZE < result.events.size());
        for (int i = page * PAGE_SIZE; i < Math.min(result.events.size(), (page + 1) * PAGE_SIZE); i++) {
            ChordEngine.Event event = result.events.get(i);
            Button row = new Button(this); row.setAllCaps(false); row.setTextColor(0xffff8c42);
            row.setText(time(event.startMs) + " – " + time(event.endMs) + "   " + event.label(transpose));
            row.setContentDescription("Seek to " + time(event.startMs) + ", chord " + event.label(transpose));
            row.setOnClickListener(v -> { if (player != null) { player.setTime(event.startMs); onPlaybackTime(event.startMs); } });
            rows.addView(row, new LinearLayout.LayoutParams(-1, -2));
        }
        onPlaybackTime(playbackTime);
    }
    @Override protected void onPlaybackTime(long millis) {
        playbackTime = millis;
        if (result == null || current == null) return;
        int low = 0, high = result.events.size() - 1, index = -1;
        while (low <= high) { int mid = (low + high) >>> 1; ChordEngine.Event event = result.events.get(mid); if (millis < event.startMs) high = mid - 1; else if (millis >= event.endMs) low = mid + 1; else { index = mid; break; } }
        current.setText(index < 0 ? "Now: —" : "Now: " + result.events.get(index).label(transpose));
        next.setText(index >= 0 && index + 1 < result.events.size() ? "Next: " + result.events.get(index + 1).label(transpose) : "Next: —");
        int chord = index < 0 ? -1 : result.events.get(index).chord;
        diagram.show(chord < 0 ? -1 : chord / 12 * 12 + Math.floorMod(chord % 12 + transpose, 12), guitar);
    }
    @Override protected void onResume() { super.onResume(); if (state != null && result == null && automatic) startAnalysis(); }
    @Override protected void onStop() { stopAnalysis(); if (state != null && result == null) state.setText("Analysis paused while Blaze is closed. Tap Analyse to retry."); automatic = false; super.onStop(); }
    @Override protected void onDestroy() { stopAnalysis(); worker.shutdownNow(); updates.removeCallbacksAndMessages(null); super.onDestroy(); }
    @Override protected void onSaveInstanceState(Bundle saved) { saved.putInt("transpose", transpose); saved.putInt("chordPage", page); saved.putBoolean("chordAutomatic", automatic || result != null); saved.putBoolean("guitar", guitar); super.onSaveInstanceState(saved); }
    @Override public void onConfigurationChanged(android.content.res.Configuration config) { super.onConfigurationChanged(config); View panel = findViewById(R.id.chord_panel); if (panel != null) { android.view.ViewGroup.LayoutParams layout = panel.getLayoutParams(); layout.height = panelHeight(); panel.setLayoutParams(layout); } }
    private int panelHeight() { return dp(Math.max(100, Math.min(240, getResources().getConfiguration().screenHeightDp / 3))); }
    private TextView text(LinearLayout parent, String value, int size) { TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(0xffeeeeee); parent.addView(v); return v; }
    private Button button(LinearLayout parent, String label, Runnable action) { Button b = new Button(this); b.setText(label); b.setAllCaps(false); b.setTextSize(12); b.setMinWidth(0); b.setMinimumWidth(0); b.setTextColor(0xffff8c42); b.setOnClickListener(v -> action.run()); parent.addView(b, new LinearLayout.LayoutParams(0, -2, 1)); return b; }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static String time(long value) { return String.format(Locale.ROOT, "%d:%02d.%01d", value / 60000, value / 1000 % 60, value / 100 % 10); }
}
