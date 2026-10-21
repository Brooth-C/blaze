package com.brooth.blaze;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.view.View;
import android.widget.*;
import org.json.JSONObject;
import java.util.Arrays;
import java.util.Map;

/** One explicit save admission path for source links, catalogue results and the player. */
public final class DownloadCoordinator {
    private DownloadCoordinator() { }
    public static final class Result {
        public final String jobId;
        public final boolean existing,paused,complete;
        Result(String id,boolean found,boolean stopped,boolean ready) {
            jobId=id;existing=found;paused=stopped;complete=ready;
        }
    }
    public static String canonicalUrl(String raw,boolean playlist) {
        String value=raw==null?"":raw.trim();Uri uri=Uri.parse(value);
        if(value.length()>8192||!"https".equalsIgnoreCase(uri.getScheme())||uri.getHost()==null
                ||uri.getUserInfo()!=null||value.matches("(?s).*\\p{Cntrl}.*"))
            throw new IllegalArgumentException("Choose a complete HTTPS link without login credentials.");
        if(playlist)return value;
        String host=uri.getHost().toLowerCase(java.util.Locale.ROOT),id=null;
        if(host.equals("youtu.be")&&!uri.getPathSegments().isEmpty())id=uri.getPathSegments().get(0);
        else if(Arrays.asList("youtube.com","www.youtube.com","music.youtube.com","m.youtube.com").contains(host)) {
            id=uri.getQueryParameter("v");
            if(id==null&&uri.getPathSegments().size()==2&&Arrays.asList("shorts","live","embed").contains(uri.getPathSegments().get(0)))id=uri.getPathSegments().get(1);
        }
        return id!=null&&id.matches("[A-Za-z0-9_-]{11}")?"https://www.youtube.com/watch?v="+id:value;
    }
    public static synchronized Result enqueue(Context context,String source,String mode,String quality,
                                               String audio,boolean playlist,String title) throws Exception {
        if(!Arrays.asList("audio","video").contains(mode)||!Arrays.asList("best","2160","1440","1080","720","480","360").contains(quality)
                ||!Arrays.asList("original","mp3","m4a","wav","flac").contains(audio))throw new IllegalArgumentException("Choose a supported format.");
        String url=canonicalUrl(source,playlist);
        // Hidden format choices must not admit a second copy of the same effective request.
        if("audio".equals(mode))quality="best";else audio="original";
        String options=new JSONObject().put("quality",quality).put("audio",audio).put("playlist",playlist).toString();
        boolean paused=context.getSharedPreferences("queue",Context.MODE_PRIVATE).getBoolean("paused",false);
        try(JobStore store=new JobStore(context)) {
            JobStore.Job active=store.matching(url,mode,options,false);
            if(active!=null)return new Result(active.id,true,paused,false);
            JobStore.Job completed=store.matching(url,mode,options,true);
            if(completed!=null) {
                try { PlaybackSource.load(context,completed.id);return new Result(completed.id,true,paused,true); }
                catch(java.io.IOException ignored) { /* A missing copy does not prevent a deliberate new save. */ }
            }
            return new Result(store.enqueue(url,mode,options,DiscoveryItem.clean(title,200)),false,paused,false);
        }
    }
    public static Result enqueue(Context context,DiscoveryItem item,String mode,String quality,String audio,boolean forStudio) throws Exception {
        if(item==null||item.browsable())throw new IllegalArgumentException("Choose a recording to save.");
        Result result=enqueue(context,item.url,mode,quality,audio,false,item.title);
        SharedPreferences.Editor edit=context.getSharedPreferences("discovery-saves",Context.MODE_PRIVATE).edit();
        edit.putString("item:"+result.jobId,item.toJson());
        if(forStudio)edit.putBoolean("studio:"+result.jobId,true);
        edit.apply();
        return result;
    }
    public static void start(Activity activity,Result result) {
        if(result.paused||result.complete)return;
        if(Build.VERSION.SDK_INT>=33&&activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED
                &&!activity.getSharedPreferences("queue",Context.MODE_PRIVATE).getBoolean("notificationAsked",false)) {
            activity.getSharedPreferences("queue",Context.MODE_PRIVATE).edit().putBoolean("notificationAsked",true).apply();
            activity.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},2);
        }
        try {
            Intent intent=new Intent(activity,DownloadService.class).setAction("RESUME");
            if(Build.VERSION.SDK_INT>=26)activity.startForegroundService(intent);else activity.startService(intent);
        } catch(RuntimeException error) { Toast.makeText(activity,"Your item is saved in the queue. Open Downloads to resume it.",Toast.LENGTH_LONG).show(); }
    }
    public static DiscoveryItem itemForJob(Context context,JobStore.Job job) {
        DiscoveryItem previous=null;
        try { previous=DiscoveryItem.fromJson(context.getSharedPreferences("discovery-saves",Context.MODE_PRIVATE).getString("item:"+job.id,"")); }
        catch(Exception ignored) { /* Imported files have no catalogue metadata. */ }
        return new DiscoveryItem(previous==null?job.id:previous.id,job.mode.equals("video")?"video":"song",
            job.title,previous==null?"On this device":previous.creator,job.url,previous==null?"":previous.thumbnail,
            previous==null?-1:previous.durationMs,job.id);
    }
    public static void openStudio(Activity activity,String jobId) {
        try {
            PlaybackSource.load(activity,jobId);
            PlaybackController.get(activity).pause();
            activity.startActivity(new Intent(activity,MusicStudioActivity.class).putExtra("job",jobId));
        } catch(Exception error) { Toast.makeText(activity,"The saved recording is no longer available.",Toast.LENGTH_LONG).show(); }
    }
    public static void showOptions(Activity activity,DiscoveryItem item,boolean forStudio) {
        if(item==null||activity.isFinishing())return;
        if(forStudio&&!item.localJobId.isEmpty()) { openStudio(activity,item.localJobId);return; }
        if(!item.localJobId.isEmpty()&&item.url.isEmpty()) {
            Toast.makeText(activity,"This recording is already saved. Use Library to share it or save a copy.",Toast.LENGTH_LONG).show();return;
        }
        BlazeUi ui=new BlazeUi(activity);
        LinearLayout form=ui.column();form.setPadding(ui.dp(24),ui.dp(8),ui.dp(24),ui.dp(12));
        TextView caption=ui.label(item.title,16,ui.text);form.addView(caption);ui.gap(form,12);
        RadioGroup modes=new RadioGroup(activity);modes.setOrientation(LinearLayout.HORIZONTAL);modes.setTag("save_mode");
        RadioButton audio=new RadioButton(activity),video=new RadioButton(activity);audio.setText("Audio");video.setText("Video");
        audio.setId(View.generateViewId());video.setId(View.generateViewId());
        for(RadioButton button:new RadioButton[]{audio,video}){button.setTextColor(ui.text);button.setMinHeight(ui.dp(48));button.setButtonTintList(android.content.res.ColorStateList.valueOf(ui.accent));modes.addView(button,new RadioGroup.LayoutParams(0,-2,1));}
        modes.check(forStudio||!item.kind.equals("video")?audio.getId():video.getId());form.addView(modes);
        Spinner formats=new Spinner(activity);formats.setTag("save_format");
        formats.setAdapter(new ArrayAdapter<>(activity,android.R.layout.simple_spinner_dropdown_item,new String[]{"Original audio","MP3 · 192 kbps","M4A","WAV","FLAC"}));ui.styleSpinner(formats);formats.setContentDescription("Saved audio format");form.addView(formats,new LinearLayout.LayoutParams(-1,-2));
        Spinner qualities=new Spinner(activity);qualities.setTag("save_quality");
        qualities.setAdapter(new ArrayAdapter<>(activity,android.R.layout.simple_spinner_dropdown_item,new String[]{"Best available","1080p","720p","480p"}));ui.styleSpinner(qualities);qualities.setContentDescription("Saved video quality");form.addView(qualities,new LinearLayout.LayoutParams(-1,-2));
        Runnable reflect=()->{boolean isAudio=modes.getCheckedRadioButtonId()==audio.getId();formats.setVisibility(isAudio?View.VISIBLE:View.GONE);qualities.setVisibility(isAudio?View.GONE:View.VISIBLE);};modes.setOnCheckedChangeListener((group,id)->reflect.run());reflect.run();
        SharedPreferences preferences=activity.getSharedPreferences("discovery-saves",Context.MODE_PRIVATE);
        formats.setSelection(Math.max(0,Math.min(4,preferences.getInt("audio-choice",0))));qualities.setSelection(Math.max(0,Math.min(3,preferences.getInt("quality-choice",0))));
        ui.gap(form,10);TextView error=ui.label("",13,ui.accent);error.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);error.setTag("save_error");form.addView(error);
        ScrollView scroll=new ScrollView(activity);scroll.addView(form);
        AlertDialog dialog=new AlertDialog.Builder(activity).setTitle(forStudio?"Save for Music Studio":"Download").setView(scroll).setNegativeButton("Cancel",null).setPositiveButton("Add to queue",null).create();
        dialog.setOnShowListener(ignored->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            try {
                String mode=modes.getCheckedRadioButtonId()==audio.getId()?"audio":"video";
                Result result=enqueue(activity,item,mode,new String[]{"best","1080","720","480"}[qualities.getSelectedItemPosition()],
                    new String[]{"original","mp3","m4a","wav","flac"}[formats.getSelectedItemPosition()],forStudio);
                preferences.edit().putInt("audio-choice",formats.getSelectedItemPosition()).putInt("quality-choice",qualities.getSelectedItemPosition()).apply();
                start(activity,result);dialog.dismiss();
                if(result.complete&&forStudio) { preferences.edit().remove("studio:"+result.jobId).apply();openStudio(activity,result.jobId); }
                else Toast.makeText(activity,result.complete?"This recording is already saved in your Library.":result.paused?"Added to paused queue.":result.existing?"This recording is already in your queue.":"Added to Downloads.",Toast.LENGTH_LONG).show();
            } catch(Exception failure) { error.setText(failure.getMessage()==null?"Could not add this recording.":failure.getMessage()); }
        }));dialog.show();
    }
    /** User-return handoff; never opens a screen from a background worker. */
    public static void offerReadyStudio(Activity activity) {
        if(activity.isFinishing()||activity.isDestroyed())return;
        SharedPreferences preferences=activity.getSharedPreferences("discovery-saves",Context.MODE_PRIVATE);
        try(JobStore store=new JobStore(activity)) {
            for(Map.Entry<String,?> value:preferences.getAll().entrySet()) {
                if(!value.getKey().startsWith("studio:")||!Boolean.TRUE.equals(value.getValue()))continue;
                String id=value.getKey().substring(7);JobStore.Job job=store.completed(id);
                if(job==null)continue;
                preferences.edit().remove(value.getKey()).apply();
                new AlertDialog.Builder(activity).setTitle("Ready for Music Studio").setMessage(job.title)
                    .setNegativeButton("Later",null).setPositiveButton("Open in Studio",(dialog,which)->openStudio(activity,id)).show();return;
            }
        }
    }
}
