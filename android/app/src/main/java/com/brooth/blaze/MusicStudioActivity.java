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
    private TextView state, current, next, summary, shift;
    private LinearLayout rows;
    private Button analyze, cancel, previous, following;
    private ChordDiagramView diagram, nextDiagram;
    private LinearLayout playbackOptions, studioPanel, instrumentRow, cardRow, actionRow;
    private boolean videoExpanded;
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
        // Keep normal playback available; uncommon decoder/track options live in a dialog.
        playbackOptions = new LinearLayout(this); playbackOptions.setOrientation(LinearLayout.VERTICAL);
        while (root.getChildCount() > 6) { View extra = root.getChildAt(6); root.removeView(extra); playbackOptions.addView(extra); }
        if (root.getChildAt(2) instanceof TextView) { playerStatus = (TextView)root.getChildAt(2); playerStatus.setTextSize(11); playerStatus.setMaxLines(2); playerStatus.setVisibility(View.GONE); }
        // LibVLC resizes its surface frame. Contain it so it cannot consume the
        // Studio's control area when audio is playing or the preview is collapsed.
        videoHost = videoViewport;
        videoHost.setLayoutParams(new LinearLayout.LayoutParams(-1, 0));
        videoHost.setVisibility(View.GONE);
        LinearLayout header = (LinearLayout)root.getChildAt(0);
        if (header.getChildCount() > 1 && header.getChildAt(1) instanceof TextView) { TextView title = (TextView)header.getChildAt(1); title.setTextSize(16); title.setTypeface(null, android.graphics.Typeface.BOLD); title.setText(mediaName()); title.setContentDescription("Blaze Music Studio, " + mediaName()); }
        LinearLayout panel = new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL); studioPanel = panel; panel.setId(R.id.chord_panel); panel.setPadding(dp(12), dp(2), dp(12), dp(4));
        root.addView(panel, new LinearLayout.LayoutParams(-1, 0, 1));
        state = text(panel, "Ready · advanced offline chords", 13); state.setId(R.id.chord_status); state.setMaxLines(2); state.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        flow = new StudioFlowView(this); flow.setTag("studio_timeline"); flow.seek = this::seekPlayback; panel.addView(flow, new LinearLayout.LayoutParams(-1, dp(88)));
        waveform = new StudioWaveformView(this); waveform.seek = this::seekPlayback; waveform.setVisibility(View.GONE);
        rhythmStatus = text(panel, "Rhythm is detected during analysis", 12); rhythmStatus.setMaxLines(1); rhythmStatus.setEllipsize(android.text.TextUtils.TruncateAt.END);
        LinearLayout instruments = new LinearLayout(this); instrumentRow = instruments; panel.addView(instruments);
        button(instruments, "Piano", () -> { guitar = false; onPlaybackTime(playbackTime); });
        button(instruments, "Guitar", () -> { guitar = true; onPlaybackTime(playbackTime); });
        button(instruments, "Video", () -> { videoExpanded = !videoExpanded; videoHost.setLayoutParams(new LinearLayout.LayoutParams(-1, videoExpanded ? dp(90) : 0)); videoHost.setVisibility(videoExpanded ? View.VISIBLE : View.GONE); });
        LinearLayout cards = new LinearLayout(this); cardRow = cards; panel.addView(cards, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout nowCard = chordCard(cards); current = text(nowCard, "Now: —", 23); current.setId(R.id.chord_current); current.setTypeface(null, android.graphics.Typeface.BOLD); current.setMaxLines(1); current.setEllipsize(android.text.TextUtils.TruncateAt.END);
        diagram = new ChordDiagramView(this); diagram.setTag("studio_current_diagram"); nowCard.addView(diagram, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout nextCard = chordCard(cards); next = text(nextCard, "Next: —", 21); next.setTypeface(null, android.graphics.Typeface.BOLD); next.setMaxLines(1); next.setEllipsize(android.text.TextUtils.TruncateAt.END);
        nextDiagram = new ChordDiagramView(this); nextDiagram.setTag("studio_next_diagram"); nextCard.addView(nextDiagram, new LinearLayout.LayoutParams(-1, 0, 1));
        countdown = text(panel, "Tap Analyse chords to begin", 12); countdown.setMaxLines(1);
        LinearLayout actions = new LinearLayout(this); actionRow = actions; panel.addView(actions);
        analyze = button(actions, "Analyse", () -> { automatic = true; startAnalysis(); }); analyze.setId(R.id.chord_analyze); analyze.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xffff8c42)); analyze.setTextColor(0xff101820);
        cancel = button(actions, "Cancel", () -> { automatic = false; stopAnalysis(); state.setText("Analysis cancelled. Tap Analyse chords to retry."); }); cancel.setId(R.id.chord_cancel); cancel.setEnabled(false); cancel.setVisibility(View.GONE);
        button(actions, "Studio options", this::optionsDialog).setTag("studio_options");
        summary = new TextView(this); summary.setTextColor(0xffa8b1c5); summary.setTextSize(13); summary.setText("Advanced chord analysis runs entirely on this device.\nImport audio or video from Blaze or your files. Transposition changes labels; playback keeps its original pitch.");
        shift = new TextView(this); shift.setTextColor(0xffeeeeee);
        arrangeStudio();
        setPlaybackFullscreen(saved != null && saved.getBoolean("fullscreen"));
    }
    private LinearLayout chordCard(LinearLayout parent) {
        LinearLayout card = new LinearLayout(this); card.setOrientation(LinearLayout.VERTICAL); card.setPadding(dp(6), dp(3), dp(6), dp(3));
        android.graphics.drawable.GradientDrawable background = new android.graphics.drawable.GradientDrawable(); background.setColor(0xff17212b); background.setCornerRadius(dp(8)); card.setBackground(background);
        LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(0, -1, 1); layout.setMargins(dp(2), dp(3), dp(2), dp(3)); parent.addView(card, layout); return card;
    }
    private String mediaName() {
        if (source != null) return source.title;
        if (document != null) try (android.database.Cursor cursor = getContentResolver().query(document, new String[]{android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null)) { if (cursor != null && cursor.moveToFirst()) return cursor.getString(0); } catch (RuntimeException ignored) { }
        return "Music Studio";
    }
    private void optionsDialog() {
        LinearLayout content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL); content.setPadding(dp(12), dp(6), dp(12), dp(6));
        if (summary.getParent() != null) ((android.view.ViewGroup)summary.getParent()).removeView(summary); content.addView(summary);
        button(content, "Instrument: " + (guitar ? "Guitar" : "Piano"), () -> new android.app.AlertDialog.Builder(this).setTitle("Chord diagrams").setItems(new String[]{"Piano", "Guitar"}, (dialog, choice) -> { guitar = choice == 1; onPlaybackTime(playbackTime); }).show());
        button(content, "Edit current chord", this::editChord);
        button(content, "Rhythm & timing", () -> rhythmDialog(false));
        button(content, "Chord list", this::chordListDialog);
        LinearLayout exports = new LinearLayout(this); content.addView(exports); button(exports, "Export JSON", () -> export(false)); button(exports, "Export CSV", () -> export(true));
        LinearLayout transposition = new LinearLayout(this); content.addView(transposition); button(transposition, "− semitone", () -> transpose(-1));
        if (shift.getParent() != null) ((android.view.ViewGroup)shift.getParent()).removeView(shift); transposition.addView(shift, new LinearLayout.LayoutParams(0, -2, 1)); button(transposition, "+ semitone", () -> transpose(1)); button(content, "Reset transposition", () -> { transpose = 0; render(); });
        if (playbackOptions.getParent() != null) ((android.view.ViewGroup)playbackOptions.getParent()).removeView(playbackOptions); content.addView(playbackOptions);
        ScrollView scroll = new ScrollView(this); scroll.addView(content);
        new android.app.AlertDialog.Builder(this).setTitle("Studio options").setView(scroll).setPositiveButton("Close", null).show();
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
        analyze.setEnabled(false); cancel.setEnabled(true); cancel.setVisibility(View.VISIBLE); state.setText("Reading media locally…");
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
                    state.setText(ready.cached ? "Saved offline analysis" : "Analysis saved offline"); render();
                });
            } catch (CancellationException ignored) {
                // stopAnalysis invalidates all callbacks before cancelling the decoder.
            } catch (Exception error) {
                updates.post(() -> {
                    if (request != generation || isFinishing() || isDestroyed()) return;
                    task = null; automatic = false; analyze.setEnabled(true); cancel.setEnabled(false); cancel.setVisibility(View.GONE);
                    state.setText(analysisError(error));
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
            Button row = new Button(this); row.setAllCaps(false); row.setTextColor(0xffff8c42);
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
    @Override public void onConfigurationChanged(android.content.res.Configuration config) { super.onConfigurationChanged(config); arrangeStudio(); }
    @Override protected View playbackVideoContainer() { return videoHost == null ? videoViewport : videoHost; }
    @Override protected void onFullscreenChanged(boolean fullscreen) {
        if (videoHost == null) return;
        videoHost.setLayoutParams(fullscreen ? new LinearLayout.LayoutParams(-1, 0, 1)
            : new LinearLayout.LayoutParams(-1, videoExpanded ? dp(90) : 0));
        videoHost.setVisibility(fullscreen || videoExpanded ? View.VISIBLE : View.GONE);
    }
    private void arrangeStudio() {
        if (studioPanel == null) return;
        View[] views = {state, flow, rhythmStatus, instrumentRow, cardRow, countdown, actionRow};
        for (View view : views) if (view.getParent() != null) ((android.view.ViewGroup)view.getParent()).removeView(view);
        studioPanel.removeAllViews();
        boolean landscape = getResources().getConfiguration().orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE;
        studioPanel.setOrientation(landscape ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        LinearLayout left = studioPanel, right = studioPanel;
        if (landscape) {
            left = new LinearLayout(this); left.setOrientation(LinearLayout.VERTICAL); right = new LinearLayout(this); right.setOrientation(LinearLayout.VERTICAL);
            studioPanel.addView(left, new LinearLayout.LayoutParams(0, -1, 3)); studioPanel.addView(right, new LinearLayout.LayoutParams(0, -1, 2));
            videoExpanded = false; videoHost.setLayoutParams(new LinearLayout.LayoutParams(-1, 0)); videoHost.setVisibility(View.GONE);
        }
        left.addView(state, new LinearLayout.LayoutParams(-1, -2)); left.addView(flow, new LinearLayout.LayoutParams(-1, dp(landscape ? 72 : 88)));
        left.addView(rhythmStatus, new LinearLayout.LayoutParams(-1, -2));
        if (getResources().getConfiguration().fontScale <= 1.35f) left.addView(instrumentRow, new LinearLayout.LayoutParams(-1, -2));
        right.addView(cardRow, landscape ? new LinearLayout.LayoutParams(-1, 0, 1) : new LinearLayout.LayoutParams(-1, dp(164)));
        right.addView(countdown, new LinearLayout.LayoutParams(-1, -2));
        if (!landscape) right.addView(new Space(this), new LinearLayout.LayoutParams(-1, 0, 1));
        right.addView(actionRow, new LinearLayout.LayoutParams(-1, -2));
    }
    private void loadRhythm(){
        try{String saved=getSharedPreferences("studio-rhythm",MODE_PRIVATE).getString(result.sourceHash,"");rhythm=StudioRhythm.read(saved);musical=new StudioTimeline(result.durationMs,result.events,result.beats,result.downbeats,result.meter,rhythm);flow.show(musical,transpose);}
        catch(Exception error){rhythm=new StudioTimeline.Rhythm();musical=new StudioTimeline(result.durationMs,result.events,result.beats,result.downbeats,result.meter,rhythm);flow.show(musical,transpose);state.setText("Using automatic rhythm; the saved correction could not be read.");}
    }
    private void rhythmDialog(boolean change){
        if(result==null){state.setText("Analyse a recording first.");return;}
        LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(18),dp(8),dp(18),dp(8));text(form,"Automatic rhythm uses this recording. You can correct the meter or set a manual grid.",12);
        Spinner mode=new Spinner(this);mode.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Automatic rhythm", "Detected beats + corrected meter", "Manual fixed tempo", "Seconds only"}));mode.setSelection("beats".equals(rhythm.mode)?1:"grid".equals(rhythm.mode)?2:"unknown".equals(rhythm.mode)?3:0);form.addView(mode);
        text(form,"Quarter-note BPM",12);EditText bpm=new EditText(this);bpm.setInputType(8194);bpm.setText(String.valueOf(Double.isFinite(result.tempo)&&"unknown".equals(rhythm.mode)?result.tempo:rhythm.bpm));form.addView(bpm);
        text(form,"Meter numerator / denominator",12);LinearLayout meters=new LinearLayout(this);form.addView(meters);Spinner num=new Spinner(this),den=new Spinner(this);Integer[] nums={1,2,3,4,5,6,7,8,9,10,11,12};Integer[] dens={2,4,8,16};num.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,nums));num.setSelection(rhythm.numerator-1);den.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,dens));for(int i=0;i<dens.length;i++)if(dens[i]==rhythm.denominator)den.setSelection(i);meters.addView(num);meters.addView(den);
        CheckBox compound=new CheckBox(this);compound.setText("Group eighth notes in threes");compound.setChecked(rhythm.compound);form.addView(compound);
        text(form,"First downbeat (seconds)",12);EditText offset=new EditText(this);offset.setInputType(8194);offset.setText(String.format(Locale.ROOT,"%.3f",rhythm.offset/1000.0));form.addView(offset);button(form,"Use playback position",()->offset.setText(String.format(Locale.ROOT,"%.3f",playbackTime/1000.0)));
        android.app.AlertDialog dialog=new android.app.AlertDialog.Builder(this).setTitle(change?"Set meter change here":"Rhythm correction").setView(form).setPositiveButton("Save",null).setNeutralButton(change?"Cancel":"Add meter change",null).setNegativeButton(change?"Close":"Revert rhythm",(d,w)->{if(!change){getSharedPreferences("studio-rhythm",MODE_PRIVATE).edit().remove(result.sourceHash).apply();loadRhythm();render();}}).create();
        dialog.setOnShowListener(d->{dialog.getButton(-1).setOnClickListener(v->{try{StudioTimeline.Rhythm candidate=StudioRhythm.read(StudioRhythm.write(rhythm));int n=(Integer)num.getSelectedItem(),de=(Integer)den.getSelectedItem();if(change){if(("unknown".equals(candidate.mode) || "auto".equals(candidate.mode)))throw new IllegalArgumentException("Save the first meter/grid before adding a change.");candidate.changes.removeIf(c->c.time==playbackTime);candidate.changes.add(new StudioTimeline.Change(playbackTime,n,de,compound.isChecked()));candidate.changes.sort(java.util.Comparator.comparingLong(c->c.time));}else{candidate.mode=mode.getSelectedItemPosition()==1?"beats":mode.getSelectedItemPosition()==2?"grid":mode.getSelectedItemPosition()==3?"unknown":"auto";candidate.bpm=Double.parseDouble(bpm.getText().toString());candidate.numerator=n;candidate.denominator=de;candidate.offset=Math.round(Double.parseDouble(offset.getText().toString())*1000);candidate.compound=compound.isChecked();}new StudioTimeline(result.durationMs,result.events,result.beats,result.downbeats,result.meter,candidate);getSharedPreferences("studio-rhythm",MODE_PRIVATE).edit().putString(result.sourceHash,StudioRhythm.write(candidate)).apply();loadRhythm();render();dialog.dismiss();}catch(Exception error){state.setText(error.getMessage()==null?"Enter a valid rhythm grid.":error.getMessage());}});dialog.getButton(-3).setOnClickListener(v->{dialog.dismiss();if(!change)rhythmDialog(true);});});dialog.show();
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
        Spinner rootChoice = new Spinner(this); rootChoice.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, ChordEngine.NOTES)); form.addView(rootChoice); rootChoice.setContentDescription("Chord root");
        String[] qualities = new String[StudioChord.QUALITY.length];
        for (int i = 0; i < qualities.length; i++) qualities[i] = StudioChord.QUALITY[i].equals("maj") ? "Major" : StudioChord.QUALITY[i].equals("min") ? "Minor" : StudioChord.SUFFIX[i];
        Spinner qualityChoice = new Spinner(this); qualityChoice.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, qualities)); form.addView(qualityChoice); qualityChoice.setContentDescription("Chord quality");
        String[] basses = new String[13]; basses[0] = "Root bass"; for (int i = 0; i < 12; i++) basses[i + 1] = ChordEngine.NOTES[i];
        Spinner bassChoice = new Spinner(this); bassChoice.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, basses)); form.addView(bassChoice); bassChoice.setContentDescription("Bass note for inversion");
        int original = result.events.get(index).chord;
        if (original >= 0) { rootChoice.setSelection(StudioChord.root(original)); qualityChoice.setSelection(StudioChord.quality(original)); String name = StudioChord.canonical(original, 0); int slash = name.indexOf('/'); if (slash >= 0) for (int i = 1; i < basses.length; i++) if (basses[i].equals(name.substring(slash + 1))) bassChoice.setSelection(i); }
        android.app.AlertDialog dialog = new android.app.AlertDialog.Builder(this).setTitle("Correct chord at " + time(result.events.get(index).startMs)).setView(form).setPositiveButton("Save", null).setNeutralButton("Clear chord", (d, w) -> saveChord(index, -1)).setNegativeButton("Cancel", null).create();
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
    private TextView text(LinearLayout parent, String value, int size) { TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(0xffeeeeee); parent.addView(v); return v; }
    private Button button(LinearLayout parent, String label, Runnable action) { Button b = new Button(this); b.setText(label); b.setAllCaps(false); b.setTextSize(13); b.setMinHeight(dp(48)); b.setMinWidth(0); b.setMinimumWidth(0); b.setTextColor(0xffff8c42); b.setOnClickListener(v -> action.run()); parent.addView(b, parent.getOrientation() == LinearLayout.HORIZONTAL ? new LinearLayout.LayoutParams(0, -2, 1) : new LinearLayout.LayoutParams(-1, -2)); return b; }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static String time(long value) { return String.format(Locale.ROOT, "%d:%02d.%01d", value / 60000, value / 1000 % 60, value / 100 % 10); }
}
