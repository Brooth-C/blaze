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
    private ChordDiagramView diagram;
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
        LinearLayout panel = new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(12), dp(6), dp(12), dp(6));
        // Keep the chord panel near the player. A bounded scroll area fits small screens.
        ScrollView scroll = new ScrollView(this); scroll.setId(R.id.chord_panel); scroll.addView(panel);
        root.addView(scroll, 2, new LinearLayout.LayoutParams(-1, panelHeight()));
        state = text(panel, "Music Studio · offline", 18); state.setId(R.id.chord_status);
        waveform=new StudioWaveformView(this);panel.addView(waveform,new LinearLayout.LayoutParams(-1,dp(70)));
        waveform.seek=millis->{seekPlayback(millis);};
        current = text(panel, "Now: —", 24); current.setId(R.id.chord_current);
        next = text(panel, "Next: —", 16);
        rhythmStatus=text(panel,"Meter/downbeat unknown · timing windows",12);countdown=text(panel,"Change in: —",14);
        HorizontalScrollView strip=new HorizontalScrollView(this);strip.setFillViewport(true);flow=new StudioFlowView(this);flow.seek=this::seekPlayback;strip.addView(flow,new android.widget.FrameLayout.LayoutParams(dp(Math.round(640*Math.max(1,getResources().getConfiguration().fontScale))),dp(Math.round(125*Math.max(1,getResources().getConfiguration().fontScale)))));panel.addView(strip,new LinearLayout.LayoutParams(-1,dp(Math.round(132*Math.max(1,getResources().getConfiguration().fontScale)))));
        button(panel,"Rhythm & timing correction",()->rhythmDialog(false));

        LinearLayout instruments = new LinearLayout(this); panel.addView(instruments);
        button(instruments, "Piano", () -> { guitar = false; onPlaybackTime(playbackTime); });
        button(instruments, "Guitar", () -> { guitar = true; onPlaybackTime(playbackTime); });
        diagram = new ChordDiagramView(this); panel.addView(diagram, new LinearLayout.LayoutParams(-1, dp(150)));
        summary = text(panel, "Pretrained BTC extended-chord model · all processing stays on this device. N = no chord; X = uncertain.", 12);
        LinearLayout actions = new LinearLayout(this); panel.addView(actions);
        analyze = button(actions, "Analyse", () -> { automatic = true; startAnalysis(); }); analyze.setId(R.id.chord_analyze);
        cancel = button(actions, "Cancel", () -> { automatic = false; stopAnalysis(); state.setText("Analysis cancelled. Tap Analyse to retry."); }); cancel.setId(R.id.chord_cancel); cancel.setEnabled(false);
        LinearLayout editing=new LinearLayout(this);panel.addView(editing);
        button(editing,"Edit chord",this::editChord);button(editing,"Export JSON",()->export(false));button(editing,"Export CSV",()->export(true));
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
        analyzer = new StudioAnalyzer(); final StudioAnalyzer operation = analyzer;
        analyze.setEnabled(false); cancel.setEnabled(true); state.setText("Reading media locally…");
        // Application context and local source only; no Activity is passed to the decoder.
        android.content.Context app = getApplicationContext();
        java.io.File file = source == null ? null : source.file;
        android.net.Uri uri = document;
        task = worker.submit(() -> {
            try {
                StudioAnalyzer.Result ready = operation.analyze(app, file, uri, message -> updates.post(() -> { if (request == generation) state.setText(message); }));
                updates.post(() -> {
                    if (request != generation || isFinishing() || isDestroyed()) return;
                    result = ready; applyEdits(); loadRhythm(); waveform.show(ready.waveform,ready.durationMs); automatic = false; task = null; analyze.setEnabled(true); cancel.setEnabled(false);
                    state.setText(ready.cached ? "Saved offline analysis" : "Analysis saved offline"); render();
                });
            } catch (CancellationException ignored) {
                // stopAnalysis invalidates all callbacks before cancelling the decoder.
            } catch (Exception error) {
                updates.post(() -> {
                    if (request != generation || isFinishing() || isDestroyed()) return;
                    task = null; automatic = false; analyze.setEnabled(true); cancel.setEnabled(false);
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
        if (analyze != null) { analyze.setEnabled(true); cancel.setEnabled(false); }
    }
    private void transpose(int delta) { transpose = Math.max(-12, Math.min(12, transpose + delta)); render(); }
    private void render() {
        if(musical!=null)flow.show(musical,transpose);
        shift.setText("Transpose: " + (transpose > 0 ? "+" : "") + transpose);
        rows.removeAllViews();
        if (result == null) return;
        summary.setText("BTC-170 extended model · " + result.events.size() + " segments · Offline\nModel scores are uncalibrated. Check uncertain passages by ear.");
        page = Math.max(0, Math.min(page, (result.events.size() - 1) / PAGE_SIZE));
        previous.setEnabled(page > 0); following.setEnabled((page + 1) * PAGE_SIZE < result.events.size());
        for (int i = page * PAGE_SIZE; i < Math.min(result.events.size(), (page + 1) * PAGE_SIZE); i++) {
            ChordEngine.Event event = result.events.get(i);
            Button row = new Button(this); row.setAllCaps(false); row.setTextColor(0xffff8c42);
            row.setText(time(event.startMs) + " – " + time(event.endMs) + "   " + StudioChord.label(event.chord,transpose));
            row.setContentDescription("Seek to " + time(event.startMs) + ", chord " + StudioChord.label(event.chord,transpose));
            row.setOnClickListener(v -> { if (player != null) { seekPlayback(event.startMs); } });
            rows.addView(row, new LinearLayout.LayoutParams(-1, -2));
        }
        onPlaybackTime(playbackTime);
    }
    @Override protected void onPlaybackTime(long millis) {
        playbackTime = millis; if(waveform!=null)waveform.position(millis);
        scheduleFrame();
        if(musical!=null){StudioTimeline.State live=musical.state(millis);flow.position(millis);StudioTimeline.Measure measure=musical.measures.get(live.measure);
            String info=live.ended?"End of recording":"unknown".equals(measure.kind)?"Meter/downbeat unknown · timing windows":"lead-in".equals(measure.kind)?"Before first downbeat":"Bar "+(live.measure-musical.barStart+1)+" · "+measure.numerator+"/"+measure.denominator+" · "+("manual".equals(measure.kind)?"manual grid":"estimated beats; corrected meter")+(live.beat==null?"":" · Beat "+(live.beat.index+1)+" / "+live.beat.total);
            if("grid".equals(rhythm.mode))info+=" · BPM "+String.format(Locale.ROOT,"%.1f",rhythm.bpm)+" (manual)";
            else if(Double.isFinite(result.tempo))info+=" · BPM ≈ "+String.format(Locale.ROOT,"%.1f",result.tempo);
            if(!info.contentEquals(rhythmStatus.getText()))rhythmStatus.setText(info);
            String remaining=live.next<0?(live.ended?"End of recording":"No further chord change"):String.format(Locale.ROOT,"Change in: %.1fs",live.remaining/1000.0)+(Double.isFinite(live.remainingBeats)?String.format(Locale.ROOT," · ≈ %.1f beats",live.remainingBeats):"");if(!remaining.contentEquals(countdown.getText()))countdown.setText(remaining);
        }
        if (result == null || current == null) return;
        int low = 0, high = result.events.size() - 1, index = -1;
        while (low <= high) { int mid = (low + high) >>> 1; ChordEngine.Event event = result.events.get(mid); if (millis < event.startMs) high = mid - 1; else if (millis >= event.endMs) low = mid + 1; else { index = mid; break; } }
        selected=index;
        String now=index<0?"Now: —":"Now: "+StudioChord.label(result.events.get(index).chord,transpose);if(!now.contentEquals(current.getText()))current.setText(now);
        int following=musical!=null&&index>=0?musical.next[index]:index+1;String upcoming=following>=0&&following<result.events.size()?"Next: "+StudioChord.label(result.events.get(following).chord,transpose):"Next: —";if(!upcoming.contentEquals(next.getText()))next.setText(upcoming);
        int chord = index < 0 ? -1 : result.events.get(index).chord;
        diagram.show(chord < 0 ? -1 : StudioChord.transpose(chord,transpose), guitar);
    }
    @Override protected void onResume() { foreground=true;super.onResume();scheduleFrame(); if (state != null && result == null && automatic) startAnalysis(); }
    @Override protected void onStop() { foreground=false;stopFrame();stopAnalysis(); if (state != null && result == null) state.setText("Analysis paused while Blaze is closed. Tap Analyse to retry."); automatic = false; super.onStop(); }
    @Override protected void onDestroy() { foreground=false;stopFrame();stopAnalysis(); worker.shutdownNow(); updates.removeCallbacksAndMessages(null); super.onDestroy(); }
    @Override protected void onSaveInstanceState(Bundle saved) { saved.putInt("transpose", transpose); saved.putInt("chordPage", page); saved.putBoolean("chordAutomatic", result != null); saved.putBoolean("guitar", guitar); super.onSaveInstanceState(saved); }
    @Override public void onConfigurationChanged(android.content.res.Configuration config) { super.onConfigurationChanged(config); View panel = findViewById(R.id.chord_panel); if (panel != null) { android.view.ViewGroup.LayoutParams layout = panel.getLayoutParams(); layout.height = panelHeight(); panel.setLayoutParams(layout); } }
    private void loadRhythm(){
        try{String saved=getSharedPreferences("studio-rhythm",MODE_PRIVATE).getString(result.sourceHash,"");rhythm=StudioRhythm.read(saved);musical=new StudioTimeline(result.durationMs,result.events,result.beats,rhythm);flow.show(musical,transpose);}
        catch(Exception error){rhythm=new StudioTimeline.Rhythm();musical=new StudioTimeline(result.durationMs,result.events,result.beats,rhythm);flow.show(musical,transpose);state.setText("Saved rhythm could not be read; meter remains unknown.");}
    }
    private void rhythmDialog(boolean change){
        if(result==null){state.setText("Analyse a recording first.");return;}
        LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(18),dp(8),dp(18),dp(8));text(form,"Downbeats and meter are not detected. Confirm a grid; detected beats remain an estimate.",12);
        Spinner mode=new Spinner(this);mode.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Meter unknown · timing windows","Detected beat timestamps · estimated","Manual fixed tempo"}));mode.setSelection("beats".equals(rhythm.mode)?1:"grid".equals(rhythm.mode)?2:0);form.addView(mode);
        text(form,"Quarter-note BPM",12);EditText bpm=new EditText(this);bpm.setInputType(8194);bpm.setText(String.valueOf(Double.isFinite(result.tempo)&&"unknown".equals(rhythm.mode)?result.tempo:rhythm.bpm));form.addView(bpm);
        text(form,"Meter numerator / denominator",12);LinearLayout meters=new LinearLayout(this);form.addView(meters);Spinner num=new Spinner(this),den=new Spinner(this);Integer[] nums={1,2,3,4,5,6,7,8,9,10,11,12};Integer[] dens={2,4,8,16};num.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,nums));num.setSelection(rhythm.numerator-1);den.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,dens));for(int i=0;i<dens.length;i++)if(dens[i]==rhythm.denominator)den.setSelection(i);meters.addView(num);meters.addView(den);
        CheckBox compound=new CheckBox(this);compound.setText("Group eighth notes in threes");compound.setChecked(rhythm.compound);form.addView(compound);
        text(form,"First downbeat (seconds)",12);EditText offset=new EditText(this);offset.setInputType(8194);offset.setText(String.format(Locale.ROOT,"%.3f",rhythm.offset/1000.0));form.addView(offset);button(form,"Use playback position",()->offset.setText(String.format(Locale.ROOT,"%.3f",playbackTime/1000.0)));
        android.app.AlertDialog dialog=new android.app.AlertDialog.Builder(this).setTitle(change?"Set meter change here":"Rhythm correction").setView(form).setPositiveButton("Save",null).setNeutralButton(change?"Cancel":"Add meter change",null).setNegativeButton(change?"Close":"Revert rhythm",(d,w)->{if(!change){getSharedPreferences("studio-rhythm",MODE_PRIVATE).edit().remove(result.sourceHash).apply();loadRhythm();render();}}).create();
        dialog.setOnShowListener(d->{dialog.getButton(-1).setOnClickListener(v->{try{StudioTimeline.Rhythm candidate=StudioRhythm.read(StudioRhythm.write(rhythm));int n=(Integer)num.getSelectedItem(),de=(Integer)den.getSelectedItem();if(change){if("unknown".equals(candidate.mode))throw new IllegalArgumentException("Save the first meter/grid before adding a change.");candidate.changes.removeIf(c->c.time==playbackTime);candidate.changes.add(new StudioTimeline.Change(playbackTime,n,de,compound.isChecked()));candidate.changes.sort(java.util.Comparator.comparingLong(c->c.time));}else{candidate.mode=mode.getSelectedItemPosition()==1?"beats":mode.getSelectedItemPosition()==2?"grid":"unknown";candidate.bpm=Double.parseDouble(bpm.getText().toString());candidate.numerator=n;candidate.denominator=de;candidate.offset=Math.round(Double.parseDouble(offset.getText().toString())*1000);candidate.compound=compound.isChecked();}new StudioTimeline(result.durationMs,result.events,result.beats,candidate);getSharedPreferences("studio-rhythm",MODE_PRIVATE).edit().putString(result.sourceHash,StudioRhythm.write(candidate)).apply();loadRhythm();render();dialog.dismiss();}catch(Exception error){state.setText(error.getMessage()==null?"Enter a valid rhythm grid.":error.getMessage());}});dialog.getButton(-3).setOnClickListener(v->{dialog.dismiss();if(!change)rhythmDialog(true);});});dialog.show();
    }
    private void applyEdits(){
        if(result==null||result.identity==null)return;
        try{org.json.JSONObject changes=new org.json.JSONObject(getSharedPreferences("studio-edits",MODE_PRIVATE).getString(result.identity,"{}"));
            for(int i=0;i<result.events.size();i++)if(changes.has(String.valueOf(i))){ChordEngine.Event e=result.events.get(i);int chord=changes.getInt(String.valueOf(i));if(chord>=-2&&chord<252)result.events.set(i,new ChordEngine.Event(e.startMs,e.endMs,chord,0));}
        }catch(Exception ignored){state.setText("Saved corrections could not be read.");}
    }
    private void editChord(){
        if(result==null||selected<0){state.setText("Analyse media and select a chord first.");return;}
        final int index=selected;String[] names=new String[230];for(int i=0;i<228;i++)names[i]=StudioChord.label(24+i,0);names[228]="No chord";names[229]="Uncertain";
        new android.app.AlertDialog.Builder(this).setTitle("Correct original chord").setItems(names,(dialog,choice)->{
            try{int chord=choice==228?-1:choice==229?-2:24+choice;android.content.SharedPreferences prefs=getSharedPreferences("studio-edits",MODE_PRIVATE);org.json.JSONObject edits=new org.json.JSONObject(prefs.getString(result.identity,"{}"));edits.put(String.valueOf(index),chord);prefs.edit().putString(result.identity,edits.toString()).apply();applyEdits();loadRhythm();render();state.setText("Correction saved on this device.");}
            catch(Exception error){state.setText("Could not save this correction.");}
        }).setNegativeButton("Cancel",null).show();
    }
    private void export(boolean asCsv){
        if(result==null){state.setText("Analyse media first.");return;}
        try{csv=asCsv;org.json.JSONObject edits=new org.json.JSONObject(getSharedPreferences("studio-edits",MODE_PRIVATE).getString(result.identity,"{}"));
            org.json.JSONArray chords=new org.json.JSONArray();StringBuilder table=new StringBuilder("start_seconds,end_seconds,chord,uncalibrated_model_score,edited\n");
            for(int i=0;i<result.events.size();i++){ChordEngine.Event e=result.events.get(i);String label=StudioChord.canonical(e.chord,transpose);boolean edited=edits.has(String.valueOf(i));
                chords.put(new org.json.JSONObject().put("start",e.startMs/1000.0).put("end",e.endMs/1000.0).put("chord",label).put("model_score",edited?org.json.JSONObject.NULL:e.confidence).put("edited",edited));
                table.append(String.format(Locale.ROOT,"%.3f,%.3f,%s,%s,%s\n",e.startMs/1000.0,e.endMs/1000.0,label,edited?"":String.format(Locale.ROOT,"%.6f",e.confidence),edited));
            }
            org.json.JSONObject json=new org.json.JSONObject().put("schema_version",1).put("audio_file",source==null?"Imported media":source.file.getName()).put("duration",result.durationMs/1000.0).put("source_sha256",result.sourceHash).put("key",org.json.JSONObject.NULL).put("tempo_bpm",Double.isFinite(result.tempo)?result.tempo:org.json.JSONObject.NULL).put("rhythm_correction",new org.json.JSONObject(StudioRhythm.write(rhythm))).put("confidence_kind","uncalibrated_model_score").put("transpose_semitones",transpose).put("model",new org.json.JSONObject().put("name","BTC-170").put("source_commit","2682317be668032e6e4b269ded36adaa2ad57df0" )).put("chords",chords);
            org.json.JSONArray beatTimes=new org.json.JSONArray();for(long beat:result.beats)beatTimes.put(beat/1000.0);json.put("beats",beatTimes);
            exportBytes=(csv?table.toString():json.toString(2)).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            startActivityForResult(new android.content.Intent(android.content.Intent.ACTION_CREATE_DOCUMENT).addCategory(android.content.Intent.CATEGORY_OPENABLE).setType(csv?"text/csv":"application/json").putExtra(android.content.Intent.EXTRA_TITLE,"Blaze-chords."+(csv?"csv":"json")),51);
        }catch(Exception error){state.setText("Could not prepare chord export.");}
    }
    @Override protected void onActivityResult(int request,int outcome,android.content.Intent data){
        super.onActivityResult(request,outcome,data);if(request!=51||outcome!=RESULT_OK||data==null||data.getData()==null||exportBytes==null)return;
        final byte[] bytes=exportBytes;exportBytes=null;final android.net.Uri uri=data.getData();final android.content.Context app=getApplicationContext();
        worker.submit(()->{try(java.io.OutputStream out=app.getContentResolver().openOutputStream(uri,"wt")){if(out==null)throw new java.io.IOException();out.write(bytes);updates.post(()->{if(!isDestroyed())state.setText("Chord export saved.");});}catch(Exception error){updates.post(()->{if(!isDestroyed())state.setText("Could not write chord export. Choose another location.");});}});
    }
    private int panelHeight() { return dp(Math.max(100, Math.min(240, getResources().getConfiguration().screenHeightDp / 3))); }
    private TextView text(LinearLayout parent, String value, int size) { TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(0xffeeeeee); parent.addView(v); return v; }
    private Button button(LinearLayout parent, String label, Runnable action) { Button b = new Button(this); b.setText(label); b.setAllCaps(false); b.setTextSize(12); b.setMinWidth(0); b.setMinimumWidth(0); b.setTextColor(0xffff8c42); b.setOnClickListener(v -> action.run()); parent.addView(b, new LinearLayout.LayoutParams(0, -2, 1)); return b; }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private static String time(long value) { return String.format(Locale.ROOT, "%d:%02d.%01d", value / 60000, value / 1000 % 60, value / 100 % 10); }
}
