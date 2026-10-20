package com.brooth.blaze;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.*;
import java.util.Locale;
import java.util.concurrent.*;

/** Chords follow the embedded audio/video player's actual position, including seeks. */
public class MusicStudioActivity extends VlcPlayerActivity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler updates = new Handler(Looper.getMainLooper());
    private StudioAnalyzer analyzer;
    private Future<?> task;
    private int generation, transpose, page;
    private boolean automatic = false;
    private long playbackTime;
    private TextView state, current, next, summary, shift, trackName;
    private LinearLayout rows;
    private Button analyze, cancel, previous, following, pianoChoice, guitarChoice, videoChoice;
    private ChordDiagramView diagram, nextDiagram;
    private LinearLayout playbackOptions, studioPanel, instrumentRow, cardRow, actionRow;
    private boolean videoExpanded, videoPresented, scrollFallback;
    private ScrollView studioScroll;
    private FrameLayout videoHost;
    private TextView playerStatus;
    private final Runnable playerMessages = new Runnable() { public void run() {
        if (playerStatus != null) { String message = playerStatus.getText().toString(); boolean failure = message.startsWith("Could") || message.contains("unavailable") || message.contains("could not"); playerStatus.setVisibility(failure ? View.VISIBLE : View.GONE); }
        if (foreground) updates.postDelayed(this, 500);
    }};
    private boolean guitar;
    private StudioWaveformView waveform;
    private StudioFlowView flow;
    private StudioTimeline musical;
    private StudioTimeline.Rhythm rhythm=new StudioTimeline.Rhythm();
    private TextView rhythmStatus,countdown;
    private boolean foreground,framePending;
    private long lastFrame;
    private final android.view.Choreographer.FrameCallback frame=new android.view.Choreographer.FrameCallback(){public void doFrame(long nanos){framePending=false;if(!foreground||isFinishing()||!playbackMoving())return;if(nanos-lastFrame>=33333333L){lastFrame=nanos;onPlaybackTime(playbackPosition());}scheduleFrame();}};
    private void scheduleFrame(){if(foreground&&playbackMoving()&&!framePending){framePending=true;android.view.Choreographer.getInstance().postFrameCallback(frame);}}
    private void stopFrame(){android.view.Choreographer.getInstance().removeFrameCallback(frame);framePending=false;}

    private int selected=-1;
    private boolean csv;
    private byte[] exportBytes;
    StudioAnalyzer.Result result;
    private static final int PAGE_SIZE = 30;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        if (root == null || isFinishing()) return;
        if (saved != null) { transpose = Math.max(-12, Math.min(12, saved.getInt("transpose"))); page = saved.getInt("chordPage"); automatic = saved.getBoolean("chordAutomatic", false); guitar = saved.getBoolean("guitar"); }
        // The player exposes explicit containers so Studio never depends on child indexes.
        playbackOptions = playbackSettings;
        detach(playbackOptions);
        detach(playbackControls);
        playerStatus = playbackStatus;
        playerStatus.setTextSize(12); playerStatus.setMaxLines(2); playerStatus.setVisibility(View.GONE);
        videoHost = videoViewport;
        videoHost.setLayoutParams(new LinearLayout.LayoutParams(-1, 0)); videoHost.setVisibility(View.GONE);
        playbackTitle.setText("Music Studio"); playbackTitle.setContentDescription("Blaze Music Studio");
        playbackMenu.setOnClickListener(v -> optionsDialog()); playbackMenu.setContentDescription("Studio options");

        studioPanel = ui.column(); studioPanel.setId(R.id.chord_panel);
        studioPanel.setPadding(dp(20), dp(4), dp(20), dp(12));
        root.addView(studioPanel, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(playbackControls, new LinearLayout.LayoutParams(-1, -2));
        trackName = ui.heading(mediaName(), 16); trackName.setSingleLine(true);
        trackName.setEllipsize(android.text.TextUtils.TruncateAt.END);
        state = ui.label("Your music. Analysed on this device.", 12, ui.secondary);
        state.setId(R.id.chord_status); state.setMaxLines(2); state.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        flow = new StudioFlowView(this); flow.setTag("studio_timeline"); flow.seek = this::seekPlayback;
        waveform = new StudioWaveformView(this); waveform.seek = this::seekPlayback; waveform.setVisibility(View.GONE);
        rhythmStatus = ui.label("Chord changes and rhythm will appear here", 12, ui.secondary);
        rhythmStatus.setMaxLines(1); rhythmStatus.setEllipsize(android.text.TextUtils.TruncateAt.END);
        instrumentRow = new LinearLayout(this); instrumentRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        instrumentRow.setPadding(dp(4), dp(4), dp(4), dp(4)); instrumentRow.setBackground(ui.shape(ui.surface, 16));
        pianoChoice = button(instrumentRow, "Piano", () -> { guitar = false; updateInstrument(); onPlaybackTime(playbackTime); });
        guitarChoice = button(instrumentRow, "Guitar", () -> { guitar = true; updateInstrument(); onPlaybackTime(playbackTime); });
        videoChoice = button(instrumentRow, "Video", () -> { videoExpanded = !videoExpanded; updateInstrument(); onFullscreenChanged(playbackFullscreen()); });
        cardRow = new LinearLayout(this);
        LinearLayout nowCard = chordCard(cardRow, true);
        current = ui.heading("Now: —", 29); current.setId(R.id.chord_current);
        current.setTextColor(ui.accent); current.setMaxLines(1); current.setEllipsize(android.text.TextUtils.TruncateAt.END); nowCard.addView(current);
        diagram = new ChordDiagramView(this); diagram.setTag("studio_current_diagram");
        diagram.addOnLayoutChangeListener((view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) -> checkStudioSpace()); nowCard.addView(diagram, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout nextCard = chordCard(cardRow, false);
        next = ui.heading("Next: —", 22); next.setMaxLines(1); next.setEllipsize(android.text.TextUtils.TruncateAt.END); nextCard.addView(next);
        nextDiagram = new ChordDiagramView(this); nextDiagram.setTag("studio_next_diagram"); nextCard.addView(nextDiagram, new LinearLayout.LayoutParams(-1, 0, 1));
        countdown = ui.label("Discover the chords. Then play along.", 12, ui.secondary); countdown.setMaxLines(1);
        actionRow = new LinearLayout(this); actionRow.setGravity(android.view.Gravity.CENTER_VERTICAL);
        analyze = button(actionRow, "Analyse chords", () -> { automatic = true; startAnalysis(); }); analyze.setId(R.id.chord_analyze); ui.styleButton(analyze, true);
        cancel = button(actionRow, "Cancel", () -> { automatic = false; stopAnalysis(); state.setText("Analysis cancelled. Tap Analyse chords to retry."); }); cancel.setId(R.id.chord_cancel); cancel.setEnabled(false); cancel.setVisibility(View.GONE);
        Button options = button(actionRow, "Options", this::optionsDialog); options.setTag("studio_options"); options.setContentDescription("Studio options: instruments, chords, rhythm and export");
        summary = ui.label("Chord analysis stays on this device.\nTransposition changes chord labels; playback keeps its original pitch.", 14, ui.secondary);
        shift = ui.label("", 14, ui.text);
        updateInstrument(); arrangeStudio();
        setPlaybackFullscreen(saved != null && saved.getBoolean("fullscreen"));
    }
    private static void detach(View view) { if (view != null && view.getParent() instanceof android.view.ViewGroup) ((android.view.ViewGroup)view.getParent()).removeView(view); }
    private LinearLayout chordCard(LinearLayout parent, boolean active) {
        LinearLayout card = ui.column(); card.setPadding(dp(12), dp(10), dp(12), dp(8));
        card.setBackground(ui.shape(active ? ui.softAccent : ui.surface, 22));
        LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(0, -1, 1);
        if (active) layout.setMargins(0, 0, dp(6), 0); else layout.setMargins(dp(6), 0, 0, 0);
        parent.addView(card, layout); return card;
    }
    private void updateInstrument() {
        if (pianoChoice == null) return;
        Button[] choices = {pianoChoice, guitarChoice, videoChoice};
        boolean[] active = {!guitar, guitar, videoExpanded};
        for (int i = 0; i < choices.length; i++) {
            ui.styleButton(choices[i], false); choices[i].setTextSize(13);
            choices[i].setSelected(active[i]); choices[i].setTextColor(active[i] ? ui.text : ui.secondary);
            choices[i].setTypeface(null, active[i] ? android.graphics.Typeface.BOLD : android.graphics.Typeface.NORMAL);
            if (active[i]) choices[i].setBackground(ui.interactiveSurface(ui.elevated, 12));
        }
    }
    private String mediaName() {
        if (source != null) return source.title;
        if (document != null) try (android.database.Cursor cursor = getContentResolver().query(document, new String[]{android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null)) { if (cursor != null && cursor.moveToFirst()) return cursor.getString(0); } catch (RuntimeException ignored) { }
        return "Music Studio";
    }
    private void optionsDialog() {
        LinearLayout content = ui.column(); content.setPadding(dp(20), dp(8), dp(20), dp(16));
        if (summary.getParent() != null) ((android.view.ViewGroup)summary.getParent()).removeView(summary); content.addView(summary);
        button(content, "Instrument: " + (guitar ? "Guitar" : "Piano"), () -> new android.app.AlertDialog.Builder(this).setTitle("Chord diagrams").setItems(new String[]{"Piano", "Guitar"}, (dialog, choice) -> { guitar = choice == 1; updateInstrument(); onPlaybackTime(playbackTime); }).show());
        boolean landscape = getResources().getConfiguration().orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE;
        Button preview = button(content, landscape ? "Watch full screen" : videoExpanded ? "Hide video preview" : "Show video preview", () -> {});
        preview.setTag("studio_video_preview");
        button(content, "Edit current chord", this::editChord);
        button(content, "Rhythm & timing", () -> rhythmDialog(false));
        button(content, "Chord list", this::chordListDialog);
        LinearLayout exports = new LinearLayout(this); content.addView(exports); button(exports, "Export JSON", () -> export(false)); button(exports, "Export CSV", () -> export(true));
        detach(shift); shift.setGravity(android.view.Gravity.CENTER_HORIZONTAL); shift.setPadding(0, dp(12), 0, dp(6)); content.addView(shift);
        LinearLayout transposition = new LinearLayout(this); content.addView(transposition); button(transposition, "− semitone", () -> transpose(-1)); button(transposition, "+ semitone", () -> transpose(1)); button(content, "Reset transposition", () -> { transpose = 0; render(); });
        if (playbackOptions.getParent() != null) ((android.view.ViewGroup)playbackOptions.getParent()).removeView(playbackOptions); playbackOptions.setVisibility(View.VISIBLE); content.addView(playbackOptions);
        ScrollView scroll = new ScrollView(this); scroll.addView(content);
        android.app.AlertDialog dialog = new android.app.AlertDialog.Builder(this).setTitle("Studio options").setView(scroll).setPositiveButton("Close", null).create();
        preview.setOnClickListener(v -> {
            dialog.dismiss();
            if (landscape) setPlaybackFullscreen(true);
            else { videoExpanded = !videoExpanded; updateInstrument(); onFullscreenChanged(playbackFullscreen()); checkStudioSpace(); }
        });
        dialog.show();
    }
    private void chordListDialog() {
        if (result == null) { state.setText("Analyse this file first."); return; }
        LinearLayout panel = new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL); panel.setPadding(dp(12), dp(6), dp(12), dp(6));
        rows = new LinearLayout(this); rows.setOrientation(LinearLayout.VERTICAL); panel.addView(rows);
        LinearLayout paging = new LinearLayout(this); panel.addView(paging); previous = button(paging, "Earlier", () -> { page = Math.max(0, page - 1); render(); }); following = button(paging, "Later", () -> { page++; render(); });
        ScrollView scroll = new ScrollView(this); scroll.addView(panel); render(); new android.app.AlertDialog.Builder(this).setTitle("Chords · tap to seek").setView(scroll).setPositiveButton("Close", null).show();
    }
    private void startAnalysis() {
        if (task != null && !task.isDone() || root == null || isFinishing()) return;
        final int request = ++generation;
        analyzer = new StudioAnalyzer(); final StudioAnalyzer operation = analyzer;
        analyze.setEnabled(false); cancel.setEnabled(true); cancel.setVisibility(View.VISIBLE); root.setKeepScreenOn(true); state.setText("Reading media locally…");
        // Application context and local source only; no Activity is passed to the decoder.
        android.content.Context app = getApplicationContext();
        java.io.File file = source == null ? null : source.file;
        android.net.Uri uri = document;
        task = worker.submit(() -> {
            try {
                StudioAnalyzer.Result ready = operation.analyze(app, file, uri, message -> updates.post(() -> { if (request == generation) state.setText(message); }));
                updates.post(() -> {
                    if (request != generation || isFinishing() || isDestroyed()) return;
                    result = ready; applyEdits(); loadRhythm(); waveform.show(ready.waveform,ready.durationMs); automatic = false; task = null; analyze.setEnabled(true); cancel.setEnabled(false); cancel.setVisibility(View.GONE);
                    root.setKeepScreenOn(false); state.setText(ready.cached ? "Saved offline analysis" : "Analysis saved offline"); render();
                });
            } catch (CancellationException ignored) {
                // stopAnalysis invalidates all callbacks before cancelling the decoder.
            } catch (Exception error) {
                updates.post(() -> {
                    if (request != generation || isFinishing() || isDestroyed()) return;
                    task = null; automatic = false; analyze.setEnabled(true); cancel.setEnabled(false); cancel.setVisibility(View.GONE);
                    root.setKeepScreenOn(false); state.setText(analysisError(error));
                });
            }
        });
    }
    static String analysisError(Exception error) {
        String message = error.getMessage();
        return error instanceof java.io.IOException && message != null && !message.trim().isEmpty()
            ? message : "Could not analyse this file. No readable audio track or unsupported media. Try another file.";
    }
    private void stopAnalysis() {
        if (root != null) root.setKeepScreenOn(false);
        generation++;
        if (analyzer != null) analyzer.cancel();
        if (task != null) task.cancel(true);
        task = null; analyzer = null;
        if (analyze != null) { analyze.setEnabled(true); cancel.setEnabled(false); cancel.setVisibility(View.GONE); }
    }
    private void transpose(int delta) { transpose = Math.max(-12, Math.min(12, transpose + delta)); render(); }
    private void render() {
        if(musical!=null)flow.show(musical,transpose);
        shift.setText("Transpose: " + (transpose > 0 ? "+" : "") + transpose);
        if (rows != null) rows.removeAllViews();
        if (result == null) return;
        summary.setText(result.modelName + " · " + result.events.size() + " segments · Offline\nChords can be corrected by ear. Silent and unrecognised passages stay blank. Exports preserve the original model scores.");
        page = Math.max(0, Math.min(page, (result.events.size() - 1) / PAGE_SIZE));
        if (previous != null) { previous.setEnabled(page > 0); following.setEnabled((page + 1) * PAGE_SIZE < result.events.size()); }
        for (int i = page * PAGE_SIZE; rows != null && i < Math.min(result.events.size(), (page + 1) * PAGE_SIZE); i++) {
            ChordEngine.Event event = result.events.get(i);
            Button row = ui.button("", false); row.setTextColor(ui.accent);
            row.setText(time(event.startMs) + " – " + time(event.endMs) + "   " + StudioFlowView.visibleChord(event.chord,transpose));
            row.setContentDescription("Seek to " + time(event.startMs) + ", chord " + StudioFlowView.visibleChord(event.chord,transpose));
            row.setOnClickListener(v -> { if (player != null) { seekPlayback(event.startMs); } });
            rows.addView(row, new LinearLayout.LayoutParams(-1, -2));
        }
        onPlaybackTime(playbackTime);
    }
    @Override protected void onPlaybackTime(long millis) {
        playbackTime = millis; if (cancel != null) cancel.setVisibility(task != null && !task.isDone() ? View.VISIBLE : View.GONE); if(waveform!=null)waveform.position(millis);
        scheduleFrame();
        if(musical!=null){StudioTimeline.State live=musical.state(millis);flow.position(millis);StudioTimeline.Measure measure=musical.measures.get(live.measure);
            String info=live.ended?"End of recording":"unknown".equals(measure.kind)?"Beat timing · meter unavailable":"lead-in".equals(measure.kind)?"Before first downbeat":"Bar "+measure.barNumber+" · "+(measure.denominator == 0 ? measure.numerator + " beats/bar" : measure.numerator + "/" + measure.denominator)+" · "+("manual".equals(measure.kind)?"manual grid":"auto".equals(measure.kind)?"detected rhythm":"corrected rhythm")+(live.beat==null?"":" · Beat "+(live.beat.index+1)+" / "+live.beat.total);
            if("grid".equals(rhythm.mode))info+=" · BPM "+String.format(Locale.ROOT,"%.1f",rhythm.bpm)+" (manual)";
            else if(Double.isFinite(result.tempo))info+=" · BPM "+String.format(Locale.ROOT,"%.1f",result.tempo);
            if(!info.contentEquals(rhythmStatus.getText()))rhythmStatus.setText(info);
            int nextChord = nextKnownChord(live.chord);
            long remainingMs = nextChord < 0 ? -1 : Math.max(0, result.events.get(nextChord).startMs - millis);
            String remaining=nextChord<0?(live.ended?"End of recording":"No further chord change"):String.format(Locale.ROOT,"Change in: %.1fs",remainingMs/1000.0);if(!remaining.contentEquals(countdown.getText()))countdown.setText(remaining);
        }
        if (result == null || current == null) return;
        int low = 0, high = result.events.size() - 1, index = -1;
        while (low <= high) { int mid = (low + high) >>> 1; ChordEngine.Event event = result.events.get(mid); if (millis < event.startMs) high = mid - 1; else if (millis >= event.endMs) low = mid + 1; else { index = mid; break; } }
        selected=index;
        String now=index<0?"Now: —":"Now: "+(result.events.get(index).chord < 0 ? "—" : StudioChord.label(result.events.get(index).chord,transpose));if(!now.contentEquals(current.getText()))current.setText(now);
        int following=nextKnownChord(index);String upcoming=following>=0&&following<result.events.size()?"Next: "+(result.events.get(following).chord < 0 ? "—" : StudioChord.label(result.events.get(following).chord,transpose)):"Next: —";if(!upcoming.contentEquals(next.getText()))next.setText(upcoming);
        int chord = index < 0 ? -1 : result.events.get(index).chord;
        diagram.show(chord < 0 ? -1 : StudioChord.transpose(chord,transpose), guitar);
        int upcomingChord = following >= 0 && following < result.events.size() ? result.events.get(following).chord : -1;
        nextDiagram.show(upcomingChord < 0 ? -1 : StudioChord.transpose(upcomingChord,transpose), guitar);
    }
    private int nextKnownChord(int index) {
        if (result == null || index < 0 || index >= result.events.size()) return -1;
        int chord = result.events.get(index).chord;
        boolean gap = chord < 0;
        for (int i = index + 1; i < result.events.size(); i++) { int candidate = result.events.get(i).chord; if (candidate < 0) { gap = true; continue; } if (gap || candidate != chord) return i; }
        return -1;
    }
    @Override protected void onResume() { foreground=true;super.onResume();updates.removeCallbacks(playerMessages);updates.post(playerMessages);scheduleFrame(); if (state != null && result == null && automatic) startAnalysis(); }
    @Override protected void onStop() { foreground=false;updates.removeCallbacks(playerMessages);stopFrame();stopAnalysis(); if (state != null && result == null) state.setText("Analysis paused while Blaze is closed. Tap Analyse to retry."); automatic = false; super.onStop(); }
    @Override protected void onDestroy() { foreground=false;stopFrame();stopAnalysis(); worker.shutdownNow(); updates.removeCallbacksAndMessages(null); super.onDestroy(); }
    @Override protected void onSaveInstanceState(Bundle saved) { saved.putInt("transpose", transpose); saved.putInt("chordPage", page); saved.putBoolean("chordAutomatic", result != null); saved.putBoolean("guitar", guitar); super.onSaveInstanceState(saved); }
    @Override public void onConfigurationChanged(android.content.res.Configuration config) { super.onConfigurationChanged(config); arrangeStudio(); setPlaybackFullscreen(playbackFullscreen()); }
    @Override protected View playbackVideoContainer() { return videoHost == null ? videoViewport : videoHost; }
    @Override protected boolean videoViewsWanted() { return videoPresented; }
    @Override protected void onFullscreenChanged(boolean fullscreen) {
        if (videoHost == null) return;
        videoHost.setLayoutParams(fullscreen ? new LinearLayout.LayoutParams(-1, 0, 1)
            : new LinearLayout.LayoutParams(-1, videoExpanded ? dp(90) : 0));
        boolean showing = fullscreen || videoExpanded;
        videoHost.setVisibility(showing ? View.VISIBLE : View.GONE);
        if (videoPresented != showing) { videoPresented = showing; refreshVideoPresentation(); }
    }
    private void arrangeStudio() {
        if (studioPanel == null) return;
        View[] views = {trackName, state, flow, rhythmStatus, instrumentRow, cardRow, countdown, actionRow};
        for (View view : views) detach(view);
        studioPanel.removeAllViews();
        boolean landscape = getResources().getConfiguration().orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE;
        boolean largeText = getResources().getConfiguration().fontScale > 1.35f;
        boolean compact = getResources().getConfiguration().screenHeightDp < 680 || largeText;
        studioPanel.setOrientation(landscape ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        LinearLayout left = studioPanel, right = studioPanel;
        if (landscape) {
            left = ui.column(); right = ui.column();
            LinearLayout.LayoutParams leftSize = new LinearLayout.LayoutParams(0, -1, 1);
            leftSize.setMargins(0, 0, dp(16), 0);
            studioPanel.addView(left, leftSize); studioPanel.addView(right, new LinearLayout.LayoutParams(0, -1, 1));
            videoExpanded = false; videoHost.setLayoutParams(new LinearLayout.LayoutParams(-1, 0)); videoHost.setVisibility(View.GONE);
        } else {
            left.addView(trackName, new LinearLayout.LayoutParams(-1, -2));
            margin(trackName, 0, 4);
        }
        left.addView(state, new LinearLayout.LayoutParams(-1, -2)); margin(state, 0, landscape ? 2 : 8);
        left.addView(flow, new LinearLayout.LayoutParams(-1, dp(landscape ? 64 : compact ? 72 : 84)));
        left.addView(rhythmStatus, new LinearLayout.LayoutParams(-1, -2)); margin(rhythmStatus, 2, landscape ? 4 : 8);
        if (!landscape && !compact) { left.addView(instrumentRow, new LinearLayout.LayoutParams(-1, -2)); margin(instrumentRow, 0, 12); }
        right.addView(cardRow, new LinearLayout.LayoutParams(-1, 0, 1));
        right.addView(countdown, new LinearLayout.LayoutParams(-1, -2)); margin(countdown, 8, landscape ? 0 : 8);
        (landscape ? left : right).addView(actionRow, new LinearLayout.LayoutParams(-1, -2));
        if (landscape) { state.setMaxLines(1); trackName.setVisibility(View.GONE); } else { state.setMaxLines(2); trackName.setVisibility(View.VISIBLE); }
        updateInstrument();
        float scale = getResources().getConfiguration().fontScale;
        int height = getResources().getConfiguration().screenHeightDp;
        configureStudioScrolling(scale >= 1.8f || height < (landscape ? 280 : 520));
        checkStudioSpace();
    }
    /** Keep transport anchored while large text or a short window can scroll the workspace. */
    private void configureStudioScrolling(boolean enabled) {
        boolean landscape = getResources().getConfiguration().orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE;
        float extraScale = Math.max(0, getResources().getConfiguration().fontScale - 1);
        if (enabled) {
            if (studioScroll == null) {
                studioScroll = new ScrollView(this); studioScroll.setTag("studio_scroll_fallback");
                studioScroll.setFillViewport(true); studioScroll.setClipToPadding(false);
            }
            if (studioPanel.getParent() != studioScroll) {
                int index = root.indexOfChild(studioPanel); detach(studioPanel);
                root.addView(studioScroll, Math.max(0, index), new LinearLayout.LayoutParams(-1, 0, 1));
                studioScroll.addView(studioPanel);
            }
            // A bounded chord row gives its weighted diagrams real height under unbounded scrolling.
            // The horizontal arrangement also needs a bounded overall height for its two columns.
            studioPanel.setLayoutParams(new ScrollView.LayoutParams(-1, landscape ? ui.dp(280 + extraScale * 120) : -2));
            if (!landscape) cardRow.setLayoutParams(new LinearLayout.LayoutParams(-1, ui.dp(180 + extraScale * 40)));
            studioPanel.setVisibility(View.VISIBLE);
        } else if (studioPanel.getParent() == studioScroll && studioScroll != null) {
            int index = root.indexOfChild(studioScroll); detach(studioPanel); root.removeView(studioScroll);
            root.addView(studioPanel, Math.max(0, index), new LinearLayout.LayoutParams(-1, 0, 1));
            studioPanel.setVisibility(View.VISIBLE);
        }
        scrollFallback = enabled;
    }
    private void checkStudioSpace() {
        studioPanel.post(() -> {
            if (isFinishing() || isDestroyed() || playbackFullscreen() || scrollFallback || diagram == null) return;
            boolean landscape = getResources().getConfiguration().orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE;
            if (studioPanel.getHeight() > 0 && diagram.getHeight() < dp(landscape ? 30 : 64)) configureStudioScrolling(true);
        });
    }
    private void margin(View view, int top, int bottom) {
        LinearLayout.LayoutParams params = (LinearLayout.LayoutParams)view.getLayoutParams();
        params.topMargin = dp(top); params.bottomMargin = dp(bottom); view.setLayoutParams(params);
    }
    private void loadRhythm(){
        try{String saved=getSharedPreferences("studio-rhythm",MODE_PRIVATE).getString(result.sourceHash,"");rhythm=StudioRhythm.read(saved);musical=new StudioTimeline(result.durationMs,result.events,result.beats,result.downbeats,result.meter,rhythm);flow.show(musical,transpose);}
        catch(Exception error){rhythm=new StudioTimeline.Rhythm();musical=new StudioTimeline(result.durationMs,result.events,result.beats,result.downbeats,result.meter,rhythm);flow.show(musical,transpose);state.setText("Using automatic rhythm; the saved correction could not be read.");}
    }
    private void rhythmDialog(boolean change){
        if(result==null){state.setText("Analyse a recording first.");return;}
        LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(18),dp(8),dp(18),dp(8));text(form,"Automatic rhythm uses this recording. You can correct the meter or set a manual grid.",12);
        Spinner mode=new Spinner(this);mode.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Automatic rhythm", "Detected beats + corrected meter", "Manual fixed tempo", "Seconds only"}));ui.styleSpinner(mode); mode.setContentDescription("Rhythm source");mode.setSelection("beats".equals(rhythm.mode)?1:"grid".equals(rhythm.mode)?2:"unknown".equals(rhythm.mode)?3:0);form.addView(mode);
        text(form,"Quarter-note BPM",12);EditText bpm=new EditText(this);ui.styleInput(bpm); bpm.setContentDescription("Quarter-note beats per minute");bpm.setInputType(8194);bpm.setText(String.valueOf(Double.isFinite(result.tempo)&&"unknown".equals(rhythm.mode)?result.tempo:rhythm.bpm));form.addView(bpm);
        text(form,"Meter numerator / denominator",12);LinearLayout meters=new LinearLayout(this);form.addView(meters);Spinner num=new Spinner(this),den=new Spinner(this);Integer[] nums={1,2,3,4,5,6,7,8,9,10,11,12};Integer[] dens={2,4,8,16};num.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,nums));num.setSelection(rhythm.numerator-1);den.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,dens));for(int i=0;i<dens.length;i++)if(dens[i]==rhythm.denominator)den.setSelection(i);ui.styleSpinner(num);ui.styleSpinner(den);num.setContentDescription("Meter numerator");den.setContentDescription("Meter denominator");meters.addView(num,new LinearLayout.LayoutParams(0,-2,1));meters.addView(den,new LinearLayout.LayoutParams(0,-2,1));
        CheckBox compound=new CheckBox(this);compound.setText("Group eighth notes in threes");compound.setTextColor(ui.text);compound.setButtonTintList(android.content.res.ColorStateList.valueOf(ui.accent));compound.setMinHeight(dp(48));compound.setChecked(rhythm.compound);form.addView(compound);
        text(form,"First downbeat (seconds)",12);EditText offset=new EditText(this);ui.styleInput(offset);offset.setContentDescription("First downbeat in seconds");offset.setInputType(8194);offset.setText(String.format(Locale.ROOT,"%.3f",rhythm.offset/1000.0));form.addView(offset);button(form,"Use playback position",()->offset.setText(String.format(Locale.ROOT,"%.3f",playbackTime/1000.0)));
        TextView validation=ui.label("",13,ui.accent);validation.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);form.addView(validation);
        ScrollView formScroll=new ScrollView(this);formScroll.addView(form);
        android.app.AlertDialog dialog=new android.app.AlertDialog.Builder(this).setTitle(change?"Set meter change here":"Rhythm correction").setView(formScroll).setPositiveButton("Save",null).setNeutralButton(change?"Cancel":"Add meter change",null).setNegativeButton(change?"Close":"Revert rhythm",(d,w)->{if(!change){getSharedPreferences("studio-rhythm",MODE_PRIVATE).edit().remove(result.sourceHash).apply();loadRhythm();render();}}).create();
        dialog.setOnShowListener(d->{dialog.getButton(-1).setOnClickListener(v->{try{StudioTimeline.Rhythm candidate=StudioRhythm.read(StudioRhythm.write(rhythm));int n=(Integer)num.getSelectedItem(),de=(Integer)den.getSelectedItem();if(change){if(("unknown".equals(candidate.mode) || "auto".equals(candidate.mode)))throw new IllegalArgumentException("Save the first meter/grid before adding a change.");candidate.changes.removeIf(c->c.time==playbackTime);candidate.changes.add(new StudioTimeline.Change(playbackTime,n,de,compound.isChecked()));candidate.changes.sort(java.util.Comparator.comparingLong(c->c.time));}else{candidate.mode=mode.getSelectedItemPosition()==1?"beats":mode.getSelectedItemPosition()==2?"grid":mode.getSelectedItemPosition()==3?"unknown":"auto";candidate.bpm=Double.parseDouble(bpm.getText().toString());candidate.numerator=n;candidate.denominator=de;candidate.offset=Math.round(Double.parseDouble(offset.getText().toString())*1000);candidate.compound=compound.isChecked();}new StudioTimeline(result.durationMs,result.events,result.beats,result.downbeats,result.meter,candidate);getSharedPreferences("studio-rhythm",MODE_PRIVATE).edit().putString(result.sourceHash,StudioRhythm.write(candidate)).apply();loadRhythm();render();dialog.dismiss();}catch(Exception error){String message=error.getMessage()==null?"Enter a valid rhythm grid.":error.getMessage();validation.setText(message);state.setText(message);}});dialog.getButton(-3).setOnClickListener(v->{dialog.dismiss();if(!change)rhythmDialog(true);});});dialog.show();
    }
    private void applyEdits(){
        if(result==null||result.identity==null)return;
        try{org.json.JSONObject changes=new org.json.JSONObject(getSharedPreferences("studio-edits",MODE_PRIVATE).getString(result.identity,"{}"));
            for(int i=0;i<result.events.size();i++)if(changes.has(String.valueOf(i))){ChordEngine.Event e=result.events.get(i);int chord=changes.getInt(String.valueOf(i));if(chord>=-2 && StudioChord.valid(chord))result.events.set(i,new ChordEngine.Event(e.startMs,e.endMs,chord,0));}
        }catch(Exception ignored){state.setText("Saved corrections could not be read.");}
    }
    private void editChord() {
        if (result == null || selected < 0) { state.setText("Analyse media and tap the timeline first."); return; }
        final int index = selected;
        LinearLayout form = new LinearLayout(this); form.setOrientation(LinearLayout.VERTICAL); form.setPadding(dp(18), dp(8), dp(18), dp(8));
        text(form, "Original chord · transposition does not affect this correction", 12);
        text(form, "Chord root", 13);
        Spinner rootChoice = new Spinner(this); rootChoice.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, ChordEngine.NOTES)); ui.styleSpinner(rootChoice);form.addView(rootChoice); rootChoice.setContentDescription("Chord root");
        String[] qualities = new String[StudioChord.QUALITY.length];
        for (int i = 0; i < qualities.length; i++) qualities[i] = StudioChord.QUALITY[i].equals("maj") ? "Major" : StudioChord.QUALITY[i].equals("min") ? "Minor" : StudioChord.SUFFIX[i];
        text(form, "Chord quality", 13);
        Spinner qualityChoice = new Spinner(this); qualityChoice.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, qualities)); ui.styleSpinner(qualityChoice);form.addView(qualityChoice); qualityChoice.setContentDescription("Chord quality");
        String[] basses = new String[13]; basses[0] = "Root bass"; for (int i = 0; i < 12; i++) basses[i + 1] = ChordEngine.NOTES[i];
        text(form, "Bass note", 13);
        Spinner bassChoice = new Spinner(this); bassChoice.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, basses)); ui.styleSpinner(bassChoice);form.addView(bassChoice); bassChoice.setContentDescription("Bass note for inversion");
        int original = result.events.get(index).chord;
        if (original >= 0) { rootChoice.setSelection(StudioChord.root(original)); qualityChoice.setSelection(StudioChord.quality(original)); String name = StudioChord.canonical(original, 0); int slash = name.indexOf('/'); if (slash >= 0) for (int i = 1; i < basses.length; i++) if (basses[i].equals(name.substring(slash + 1))) bassChoice.setSelection(i); }
        ScrollView formScroll = new ScrollView(this); formScroll.addView(form);
        android.app.AlertDialog dialog = new android.app.AlertDialog.Builder(this).setTitle("Correct chord at " + time(result.events.get(index).startMs)).setView(formScroll).setPositiveButton("Save", null).setNeutralButton("Clear chord", (d, w) -> saveChord(index, -1)).setNegativeButton("Cancel", null).create();
        dialog.setOnShowListener(d -> dialog.getButton(-1).setOnClickListener(v -> {
            String name = ChordEngine.NOTES[rootChoice.getSelectedItemPosition()] + ":" + StudioChord.QUALITY[qualityChoice.getSelectedItemPosition()];
            if (bassChoice.getSelectedItemPosition() > 0) name += "/" + basses[bassChoice.getSelectedItemPosition()];
            int chord = StudioChord.parse(name);
            if (chord < 0) { state.setText("Choose a supported chord and bass note."); return; }
            saveChord(index, chord); dialog.dismiss();
        })); dialog.show();
    }
    private void saveChord(int index, int chord) {
        try { android.content.SharedPreferences preferences = getSharedPreferences("studio-edits", MODE_PRIVATE); org.json.JSONObject edits = new org.json.JSONObject(preferences.getString(result.identity, "{}")); edits.put(String.valueOf(index), chord); preferences.edit().putString(result.identity, edits.toString()).apply(); applyEdits(); loadRhythm(); render(); state.setText("Correction saved on this device."); }
        catch (Exception error) { state.setText("Could not save this correction."); }
    }
    private void export(boolean asCsv){
        if(result==null){state.setText("Analyse media first.");return;}
        try{csv=asCsv;org.json.JSONObject edits=new org.json.JSONObject(getSharedPreferences("studio-edits",MODE_PRIVATE).getString(result.identity,"{}"));
            org.json.JSONArray chords=new org.json.JSONArray();StringBuilder table=new StringBuilder("start_seconds,end_seconds,chord,uncalibrated_model_score,edited\n");
            for(int i=0;i<result.events.size();i++){ChordEngine.Event e=result.events.get(i);String label=StudioChord.canonical(e.chord,transpose);boolean edited=edits.has(String.valueOf(i));
                chords.put(new org.json.JSONObject().put("start",e.startMs/1000.0).put("end",e.endMs/1000.0).put("chord",label).put("model_score",edited?org.json.JSONObject.NULL:e.confidence).put("edited",edited));
                table.append(String.format(Locale.ROOT,"%.3f,%.3f,%s,%s,%s\n",e.startMs/1000.0,e.endMs/1000.0,label,edited?"":String.format(Locale.ROOT,"%.6f",e.confidence),edited));
            }
            org.json.JSONObject json=new org.json.JSONObject().put("schema_version",1).put("audio_file",mediaName()).put("duration",result.durationMs/1000.0).put("source_sha256",result.sourceHash).put("key",org.json.JSONObject.NULL).put("tempo_bpm",Double.isFinite(result.tempo)?result.tempo:org.json.JSONObject.NULL).put("rhythm_correction",new org.json.JSONObject(StudioRhythm.write(rhythm))).put("confidence_kind","uncalibrated_model_score").put("transpose_semitones",transpose).put("model",new org.json.JSONObject().put("name",result.modelName).put("sha256",result.modelHash).put("engine_version",result.engineVersion)).put("chords",chords);
            org.json.JSONArray beatTimes=new org.json.JSONArray();for(long beat:result.beats)beatTimes.put(beat/1000.0);json.put("beats",beatTimes); org.json.JSONArray downbeatTimes = new org.json.JSONArray(); for(long downbeat:result.downbeats) downbeatTimes.put(downbeat/1000.0); json.put("downbeats",downbeatTimes).put("meter",StudioRhythm.meterWrite(result.meter)).put("rhythm_model_sha256",result.rhythmModelHash);
            exportBytes=(csv?table.toString():json.toString(2)).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            startActivityForResult(new android.content.Intent(android.content.Intent.ACTION_CREATE_DOCUMENT).addCategory(android.content.Intent.CATEGORY_OPENABLE).setType(csv?"text/csv":"application/json").putExtra(android.content.Intent.EXTRA_TITLE,"Blaze-chords."+(csv?"csv":"json")),51);
        }catch(Exception error){state.setText("Could not prepare chord export.");}
    }
    @Override protected void onActivityResult(int request,int outcome,android.content.Intent data){
        super.onActivityResult(request,outcome,data);if(request!=51||outcome!=RESULT_OK||data==null||data.getData()==null||exportBytes==null)return;
        final byte[] bytes=exportBytes;exportBytes=null;final android.net.Uri uri=data.getData();final android.content.Context app=getApplicationContext();
        worker.submit(()->{try(java.io.OutputStream out=app.getContentResolver().openOutputStream(uri,"wt")){if(out==null)throw new java.io.IOException();out.write(bytes);updates.post(()->{if(!isDestroyed())state.setText("Chord export saved.");});}catch(Exception error){updates.post(()->{if(!isDestroyed())state.setText("Could not write chord export. Choose another location.");});}});
    }
    private TextView text(LinearLayout parent, String value, int size) { TextView v = ui.label(value, size, ui.text); parent.addView(v); return v; }
    private Button button(LinearLayout parent, String label, Runnable action) {
        Button b = ui.button(label, false); b.setTextSize(14); b.setOnClickListener(v -> action.run());
        LinearLayout.LayoutParams params = parent.getOrientation() == LinearLayout.HORIZONTAL ? new LinearLayout.LayoutParams(0, -2, 1) : new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(dp(3), dp(3), dp(3), dp(3)); parent.addView(b, params); return b;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static String time(long value) { return String.format(Locale.ROOT, "%d:%02d.%01d", value / 60000, value / 1000 % 60, value / 100 % 10); }
}
