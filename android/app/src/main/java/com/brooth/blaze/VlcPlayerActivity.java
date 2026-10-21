package com.brooth.blaze;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.*;
import android.media.AudioManager;
import android.net.Uri;
import android.os.*;
import android.view.View;
import android.widget.*;
import androidx.core.view.*;
import androidx.core.content.ContextCompat;
import org.videolan.libvlc.*;
import org.videolan.libvlc.util.VLCVideoLayout;
import java.io.IOException;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.*;

/** Embedded LibVLC plays the original completed file, without another app or conversion. */
public class VlcPlayerActivity extends Activity {
    MediaPlayer player;
    private LibVLC engine;
    protected PlaybackSource source;
    protected Uri document;
    private String mediaId, mediaTitle;
    private ParcelFileDescriptor descriptor;
    private final ExecutorService documents=Executors.newSingleThreadExecutor();
    private Future<?> openingTask;
    private int generation;
    private boolean opening;
    VLCVideoLayout video;
    protected FrameLayout videoViewport;
    private TextView status, clock;
    protected BlazeUi ui;
    protected LinearLayout playbackHeader, playbackControls, playbackSettings;
    protected TextView playbackTitle, playbackStatus;
    protected LinearLayout root;
    private LinearLayout header;
    Button toggle;
    protected Button playbackMenu;
    private Button fullscreenToggle;
    private SeekBar seek;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private long position;
    private long restorePosition,restoreDeadline;
    private int restorePictures;
    private boolean restoringFrame;
    private float speed=1;
    private boolean software, repeat, fullscreen, resume=true, pendingSeek, wantedResume, ended, foreground;
    private AudioManager audio;
    private boolean focusGranted, noisyRegistered;
    private DiscoveryItem recommendationItem;
    private long listeningMillis, listeningTick;
    private boolean listeningCounted;
    private boolean videoAttached, scrubbing, previewAtEnd;
    private long scrubPosition, pendingPosition = -1, seekDeadline;
    private final AudioManager.OnAudioFocusChangeListener focus=change->{if(change<0)pause();};
    private final BroadcastReceiver noisy=new BroadcastReceiver(){
        @Override public void onReceive(Context context,Intent intent){pause();}
    };
    private final Runnable tick=new Runnable(){public void run(){
        if(player!=null){long length=player.getLength(), time=playbackPosition();
            if(!scrubbing)seek.setProgress(length>0?(int)(time*1000/length):0);
            setText(clock,time(time)+" / "+time(length));setText(toggle,!restoringFrame&&player.isPlaying()?"Pause":"Play");
            onPlaybackTime(time);
            long now=SystemClock.elapsedRealtime();
            if(foreground&&!restoringFrame&&player.isPlaying()&&recommendationItem!=null){
                if(listeningTick>0)listeningMillis+=Math.max(0,Math.min(2000,now-listeningTick));
                listeningTick=now;
                if(!listeningCounted&&listeningMillis>=15000){listeningCounted=true;PlaybackController.get(VlcPlayerActivity.this).recordQualifiedListen(recommendationItem);}
            }else listeningTick=0;
        }handler.postDelayed(this,500);
    }};
    private final Runnable restoreTick=new Runnable(){public void run(){
        if(player==null||!foreground||!restoringFrame||resume||wantedResume)return;
        org.videolan.libvlc.interfaces.IMedia media=player.getMedia();boolean rendered=false;
        try{org.videolan.libvlc.interfaces.IMedia.Stats stats=media==null?null:media.getStats();
            rendered=stats!=null&&(videoViewsWanted()&&player.getVideoTracksCount()>0?stats.displayedPictures>restorePictures:stats.decodedAudio>0);
        }finally{if(media!=null)media.release();}
        if(rendered||SystemClock.uptimeMillis()>=restoreDeadline){restoringFrame=false;player.pause();player.setTime(restorePosition);status.setText(!rendered&&videoViewsWanted()?"Video preview unavailable. Try Software decoding.":"Paused");video.setKeepScreenOn(false);}
        else handler.postDelayed(this,50);
    }};

    @Override public void onCreate(Bundle saved){
        BlazeUi.apply(this);
        super.onCreate(saved);ui=new BlazeUi(this);setVolumeControlStream(AudioManager.STREAM_MUSIC);
        try{
            String job=getIntent().getStringExtra("job");
            if(job!=null){source=PlaybackSource.load(this,job);mediaId=source.id;mediaTitle=source.title;}
            else{document=getIntent().getData();if(document==null||!"content".equals(document.getScheme())||document.getAuthority()==null)throw new IOException();mediaId="document:"+document;mediaTitle="Selected media";}
        }
        catch(IOException|RuntimeException error){Toast.makeText(this,"This file is unavailable.",Toast.LENGTH_LONG).show();finish();return;}
        position=Math.max(0,getSharedPreferences("playback",MODE_PRIVATE).getLong(mediaId,0));
        software=getIntent().getBooleanExtra("software",false);
        if(saved!=null){position=saved.getLong("position",position);speed=saved.getFloat("speed",1);software=saved.getBoolean("software");repeat=saved.getBoolean("repeat");resume=saved.getBoolean("playing",true);fullscreen=saved.getBoolean("fullscreen");}
        if(!Float.isFinite(speed)||speed<0.5f||speed>2)speed=1;
        audio=(AudioManager)getSystemService(AUDIO_SERVICE);
        WindowCompat.setDecorFitsSystemWindows(getWindow(),false);
        root=ui.column();root.setBackgroundColor(ui.background);
        header=new LinearLayout(this);playbackHeader=header;header.setGravity(android.view.Gravity.CENTER_VERTICAL);header.setPadding(ui.dp(16),ui.dp(8),ui.dp(16),ui.dp(8));root.addView(header);
        Button back=ui.button("Back",false);back.setCompoundDrawablesRelativeWithIntrinsicBounds(ui.icon("back",ui.accent),null,null,null);back.setText("");back.setPadding(ui.dp(12),ui.dp(12),ui.dp(12),ui.dp(12));back.setContentDescription("Back to Blaze");back.setOnClickListener(v->back());header.addView(back,new LinearLayout.LayoutParams(ui.dp(48),ui.dp(48)));
        playbackTitle=ui.heading(mediaTitle,18);playbackTitle.setMaxLines(2);playbackTitle.setEllipsize(android.text.TextUtils.TruncateAt.END);playbackTitle.setPadding(ui.dp(12),0,ui.dp(8),0);header.addView(playbackTitle,new LinearLayout.LayoutParams(0,-2,1));
        Button options=ui.button("Options",false);playbackMenu=options;options.setCompoundDrawablesRelativeWithIntrinsicBounds(ui.icon("more",ui.accent),null,null,null);options.setText("");options.setPadding(ui.dp(12),ui.dp(12),ui.dp(12),ui.dp(12));options.setContentDescription("Playback options");options.setOnClickListener(v->showPlaybackOptions());header.addView(options,new LinearLayout.LayoutParams(ui.dp(48),ui.dp(48)));
        video=new VLCVideoLayout(this);videoViewport=new FrameLayout(this);videoViewport.setBackgroundColor(android.graphics.Color.BLACK);videoViewport.setClipChildren(true);videoViewport.setClipToPadding(true);videoViewport.addView(video,new FrameLayout.LayoutParams(-1,-1));root.addView(videoViewport,new LinearLayout.LayoutParams(-1,0,1));
        if(source!=null&&"audio".equals(source.mode)){
            videoViewport.setBackgroundColor(ui.background);
            LinearLayout artwork=ui.column();artwork.setGravity(android.view.Gravity.CENTER);artwork.setPadding(ui.dp(32),ui.dp(16),ui.dp(32),ui.dp(16));
            android.widget.ImageView note=new android.widget.ImageView(this);note.setImageDrawable(ui.icon("music",ui.accent));note.setBackground(ui.shape(ui.softAccent,28));note.setPadding(ui.dp(28),ui.dp(28),ui.dp(28),ui.dp(28));note.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);artwork.addView(note,new LinearLayout.LayoutParams(ui.dp(132),ui.dp(132)));
            TextView audioLabel=ui.label("Local audio",13,ui.secondary);audioLabel.setPadding(0,ui.dp(16),0,0);artwork.addView(audioLabel);videoViewport.addView(artwork,new FrameLayout.LayoutParams(-1,-1));
        }
        status=ui.label("Opening your file…",13,ui.secondary);playbackStatus=status;status.setPadding(ui.dp(24),ui.dp(10),ui.dp(24),ui.dp(2));status.setMaxLines(2);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);root.addView(status);
        playbackControls=ui.column();playbackControls.setPadding(ui.dp(20),ui.dp(4),ui.dp(20),ui.dp(16));root.addView(playbackControls);
        clock=ui.label("0:00 / 0:00",12,ui.secondary);clock.setGravity(android.view.Gravity.CENTER_HORIZONTAL);clock.setTypeface(android.graphics.Typeface.create("sans-serif-medium",android.graphics.Typeface.NORMAL));playbackControls.addView(clock);
        seek=new SeekBar(this);seek.setMax(1000);seek.setProgressTintList(android.content.res.ColorStateList.valueOf(ui.accent));seek.setThumbTintList(android.content.res.ColorStateList.valueOf(ui.accent));seek.setContentDescription("Seek through media");playbackControls.addView(seek,new LinearLayout.LayoutParams(-1,ui.dp(40)));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onStartTrackingTouch(SeekBar bar){previewPlaybackPosition(playbackPosition());}
            public void onProgressChanged(SeekBar bar,int value,boolean user){if(user&&player!=null&&player.getLength()>0){previewPlaybackPosition(player.getLength()*value/1000);setText(clock,time(scrubPosition)+" / "+time(player.getLength()));}}
            public void onStopTrackingTouch(SeekBar bar){if(player!=null&&player.getLength()>0)seekPlayback(player.getLength()*bar.getProgress()/1000);else endPlaybackPositionPreview();}
        });
        LinearLayout controls=new LinearLayout(this);controls.setGravity(android.view.Gravity.CENTER_VERTICAL);playbackControls.addView(controls);
        button(controls,"−10s",()->skip(-10000)).setContentDescription("Back ten seconds");toggle=button(controls,"Pause",()->{if(player!=null){if(!restoringFrame&&player.isPlaying())pause();else play();}});ui.styleButton(toggle,true);toggle.setPadding(ui.dp(8),ui.dp(12),ui.dp(8),ui.dp(12));button(controls,"+10s",()->skip(10000)).setContentDescription("Forward ten seconds");
        fullscreenToggle=button(controls,"",()->fullscreen(!fullscreen));fullscreenToggle.setCompoundDrawablesRelativeWithIntrinsicBounds(ui.icon("expand",ui.accent),null,null,null);fullscreenToggle.setContentDescription("Enter full screen");fullscreenToggle.setPadding(ui.dp(12),ui.dp(12),ui.dp(12),ui.dp(12));LinearLayout.LayoutParams expandLayout=new LinearLayout.LayoutParams(ui.dp(48),ui.dp(50));expandLayout.setMargins(ui.dp(3),ui.dp(3),ui.dp(3),ui.dp(3));fullscreenToggle.setLayoutParams(expandLayout);
        playbackSettings=ui.column();playbackSettings.setPadding(ui.dp(20),ui.dp(8),ui.dp(20),ui.dp(16));root.addView(playbackSettings);playbackSettings.setVisibility(View.GONE);
        LinearLayout extra=new LinearLayout(this);playbackSettings.addView(extra);
        button(extra,"Speed",()->new AlertDialog.Builder(this).setTitle("Playback speed").setItems(new String[]{"0.5×","1×","1.5×","2×"},(d,i)->{speed=new float[]{.5f,1,1.5f,2}[i];if(player!=null)player.setRate(speed);}).show());
        button(extra,"Tracks",this::tracks);button(extra,"Repeat",()->{repeat=!repeat;Toast.makeText(this,repeat?"Repeat on":"Repeat off",Toast.LENGTH_SHORT).show();});
        button(playbackSettings,"Decoder: automatic / software",()->new AlertDialog.Builder(this).setTitle("Video decoding").setItems(new String[]{"Automatic (recommended)","Software (for unsupported hardware codecs)"},(d,i)->{remember();software=i==1;release();resume=true;start();}).show());
        button(playbackSettings,"Try again",()->{remember();release();resume=true;start();});
        if(source!=null && !(this instanceof ChordActivity))button(playbackSettings,"Use Android playback engine",()->{startActivity(new Intent(this,PlayerActivity.class).putExtra("job",source.id));finish();});
        setContentView(root);
        video.setOnClickListener(v->{if(fullscreen)fullscreen(false);});
        fullscreen(fullscreen);
        ViewCompat.setOnApplyWindowInsetsListener(root,(v,insets)->{androidx.core.graphics.Insets safe=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());v.setPadding(safe.left,safe.top,safe.right,safe.bottom);return insets;});
        if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::back);
    }
    private void showPlaybackOptions(){
        if(playbackSettings.getParent()!=null)((android.view.ViewGroup)playbackSettings.getParent()).removeView(playbackSettings);
        playbackSettings.setVisibility(View.VISIBLE);ScrollView scroll=new ScrollView(this);scroll.addView(playbackSettings);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Playback options").setView(scroll).setPositiveButton("Done",null).create();
        dialog.setOnDismissListener(d->{scroll.removeView(playbackSettings);playbackSettings.setVisibility(View.GONE);if(playbackSettings.getParent()==null)root.addView(playbackSettings);});dialog.show();
    }
    private Button button(LinearLayout parent,String text,Runnable action){Button b=ui.button(text,false);b.setTextSize(13);b.setMinWidth(0);b.setMinimumWidth(0);b.setPadding(ui.dp(8),ui.dp(12),ui.dp(8),ui.dp(12));b.setOnClickListener(v->action.run());LinearLayout.LayoutParams layout=parent.getOrientation()==LinearLayout.HORIZONTAL?new LinearLayout.LayoutParams(0,-2,1):new LinearLayout.LayoutParams(-1,-2);layout.setMargins(ui.dp(3),ui.dp(3),ui.dp(3),ui.dp(3));parent.addView(b,layout);return b;}
    private void start(){
        if((source==null&&document==null)||player!=null||opening||isFinishing())return;
        if(document!=null){
            opening=true;int request=++generation;status.setText("Opening the selected file…");
            openingTask=documents.submit(()->{
                ParcelFileDescriptor opened=null;
                try{opened=getContentResolver().openFileDescriptor(document,"r");if(opened==null)throw new IOException();}
                catch(IOException|RuntimeException error){close(opened);handler.post(()->{if(request==generation){opening=false;status.setText("The selected file is unavailable. Choose it again from Files.");}});return;}
                ParcelFileDescriptor ready=opened;
                handler.post(()->{if(request!=generation){close(ready);return;}opening=false;if(!foreground||isFinishing()){close(ready);return;}descriptor=ready;buildPlayer();});
            });return;
        }
        buildPlayer();
    }
    private void buildPlayer(){
        try{
            if(source!=null)source=PlaybackSource.load(this,source.id);
            ArrayList<String> options=new ArrayList<>(Arrays.asList("--no-video-title-show","--file-caching=300","--avcodec-threads=2","--stats"));
            // Software fallback must also work without 10-bit OpenGL texture support.
            if(software){options.add("--vout=android-display");options.add("--android-display-chroma=RV32");}
            engine=new LibVLC(this,options);
            boolean showVideo=videoViewsWanted();
            player=new MediaPlayer(engine);videoAttached=false;if(showVideo){player.attachViews(video,null,true,false);videoAttached=true;}pendingSeek=true;wantedResume=resume;ended=false;
            restoringFrame=!resume;restorePosition=position;restorePictures=0;restoreDeadline=SystemClock.uptimeMillis()+5000;
            MediaPlayer active=player;
            player.setEventListener(event->{if(player!=active)return;
                switch(event.type){
                    case MediaPlayer.Event.ESAdded:
                        // Preview may be opened before the demuxer discovers its tracks.
                        if(videoViewsWanted())refreshVideoPresentation();else player.setVideoTrackEnabled(false);
                        break;
                    case MediaPlayer.Event.Playing:
                        if(previewAtEnd){previewAtEnd=false;player.setTime(position);}
                        player.setVideoTrackEnabled(videoViewsWanted());
                        if(pendingSeek){pendingSeek=false;player.setRate(speed);}
                        if(!foreground){player.pause();video.setKeepScreenOn(false);break;}
                        if(!resume||!wantedResume){
                            video.setKeepScreenOn(false);
                            if(restoringFrame){player.setVolume(0);status.setText("Restoring paused frame…");handler.removeCallbacks(restoreTick);handler.post(restoreTick);}
                            else{player.pause();status.setText("Paused");}break;
                        }
                        if(recommendationItem==null)recommendationItem=PlaybackController.get(this).rememberSavedPlayback(source);
                        listeningTick=SystemClock.elapsedRealtime();
                        toggle.setText("Pause");status.setText("Playing in Blaze");video.setKeepScreenOn(player.getCurrentVideoTrack()!=null);break;
                    case MediaPlayer.Event.Paused:
                        if(pendingSeek){pendingSeek=false;player.setRate(speed);}
                        player.setVolume(100);toggle.setText("Play");status.setText("Paused");video.setKeepScreenOn(false);
                        if(foreground&&resume&&wantedResume)beginPlayback();break;
                    case MediaPlayer.Event.EndReached:
                        if(restoringFrame&&!resume&&!wantedResume){
                            // A silent preview near EOF must not repeat or reopen the file.
                            restoringFrame=false;handler.removeCallbacks(restoreTick);position=restorePosition;
                            previewAtEnd=true;player.pause();video.setKeepScreenOn(false);status.setText("Paused");break;
                        }
                        position=0;ended=!repeat;video.setKeepScreenOn(false);
                        getSharedPreferences("playback",MODE_PRIVATE).edit().remove(mediaId).apply();
                        if(repeat){listeningMillis=0;listeningTick=0;listeningCounted=false;release();resume=true;start();}else{resume=false;status.setText("Playback finished");}break;
                    case MediaPlayer.Event.EncounteredError:
                        restoringFrame=false;handler.removeCallbacks(restoreTick);video.setKeepScreenOn(false);status.setText("Could not decode this file. Try Software decoding. Damaged or encrypted files may not play.");break;
                    default: break;
                }
            });
            Media media=document==null?new Media(engine,Uri.fromFile(source.file)):new Media(engine,descriptor.getFileDescriptor());
            try{
                // Seek before starting; paused restoration waits for a displayed frame, muted.
                if(position>0)media.addOption(":start-time="+Double.toString(position/1000.0));
                // Keep the video track available: opening a preview must not reopen the file.
                if(!showVideo)media.addOption(":video-track=-1");
                media.setHWDecoderEnabled(!software,false);player.setMedia(media);
            }finally{media.release();}
            status.setText("Opening the original file…");beginPlayback();handler.post(tick);
            ContextCompat.registerReceiver(this,noisy,new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY),ContextCompat.RECEIVER_NOT_EXPORTED);noisyRegistered=true;
        }catch(IOException|RuntimeException|UnsatisfiedLinkError error){android.util.Log.e("BlazePlayer","Player initialization failed",error);release();status.setText("Blaze could not open this file. Try again.");}
    }
    private void play(){restoringFrame=false;handler.removeCallbacks(restoreTick);resume=true;wantedResume=true;if(ended){position=0;listeningMillis=0;listeningTick=0;listeningCounted=false;release();start();}else beginPlayback();}
    @SuppressWarnings("deprecation") private void beginPlayback(){if(player==null)return;if(!resume){player.setVolume(0);player.play();return;}focusGranted=audio.requestAudioFocus(focus,AudioManager.STREAM_MUSIC,AudioManager.AUDIOFOCUS_GAIN)==AudioManager.AUDIOFOCUS_REQUEST_GRANTED;if(focusGranted){player.setVolume(100);player.play();}else status.setText("Audio is in use by another app. Try Play again.");}
    private void pause(){restoringFrame=false;handler.removeCallbacks(restoreTick);resume=false;wantedResume=false;if(player!=null){player.pause();video.setKeepScreenOn(false);}}
    private void skip(long amount){if(player!=null)seekPlayback(playbackPosition()+amount);}
    private void tracks(){if(player==null)return;new AlertDialog.Builder(this).setTitle("Tracks").setItems(new String[]{"Audio","Subtitles"},(d,i)->{
        MediaPlayer.TrackDescription[] choices=i==0?player.getAudioTracks():player.getSpuTracks();
        if(choices==null||choices.length==0){Toast.makeText(this,"No tracks available",Toast.LENGTH_SHORT).show();return;}
        String[] names=new String[choices.length];for(int n=0;n<names.length;n++)names[n]=choices[n].name;
        new AlertDialog.Builder(this).setTitle(i==0?"Audio track":"Subtitles").setItems(names,(dialog,n)->{if(player!=null){if(i==0)player.setAudioTrack(choices[n].id);else player.setSpuTrack(choices[n].id);}}).show();
    }).show();}
    private void remember(){if(player!=null&&mediaId!=null){position=ended?0:playbackPosition();getSharedPreferences("playback",MODE_PRIVATE).edit().putLong(mediaId,position).apply();}}
    private static void close(ParcelFileDescriptor value){if(value!=null)try{value.close();}catch(IOException ignored){}}
    @SuppressWarnings("deprecation") private void release(){restoringFrame=false;handler.removeCallbacks(restoreTick);generation++;opening=false;if(openingTask!=null){openingTask.cancel(true);openingTask=null;}handler.removeCallbacks(tick);scrubbing=false;pendingPosition=-1;videoAttached=false;previewAtEnd=false;if(noisyRegistered){unregisterReceiver(noisy);noisyRegistered=false;}if(player!=null){player.setEventListener(null);player.stop();player.detachViews();player.release();player=null;}if(engine!=null){engine.release();engine=null;}close(descriptor);descriptor=null;if(video!=null)video.setKeepScreenOn(false);if(focusGranted){audio.abandonAudioFocus(focus);focusGranted=false;}}
    private void fullscreen(boolean value){fullscreen=value;if(fullscreenToggle!=null)fullscreenToggle.setContentDescription(value?"Exit full screen":"Enter full screen");for(int i=0;i<root.getChildCount();i++){View child=root.getChildAt(i);if(child!=playbackVideoContainer())child.setVisibility(value?View.GONE:View.VISIBLE);}WindowInsetsControllerCompat bars=WindowCompat.getInsetsController(getWindow(),root);bars.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);if(value)bars.hide(WindowInsetsCompat.Type.systemBars());else bars.show(WindowInsetsCompat.Type.systemBars());if(playbackSettings.getParent()==root)playbackSettings.setVisibility(View.GONE);onFullscreenChanged(value);}
    protected View playbackVideoContainer(){return videoViewport;}
    protected boolean videoViewsWanted(){return true;}
    protected boolean playbackFullscreen(){return fullscreen;}
    /** Switch only the video output. Audio, decoder choice and playback position stay owned by the same player. */
    protected void refreshVideoPresentation(){
        if(player==null)return;
        if(videoViewsWanted()){
            if(!videoAttached){player.attachViews(video,null,true,false);videoAttached=true;}
            MediaPlayer active=player;
            video.post(()->{
                if(player!=active||!foreground||!videoViewsWanted())return;
                active.setVideoTrackEnabled(true);active.updateVideoSurfaces();
                if(!resume&&!wantedResume&&!restoringFrame)restorePausedVideoFrame();
            });
        }else if(videoAttached){
            player.detachViews();videoAttached=false;video.setKeepScreenOn(false);
            if(restoringFrame&&!resume){restoringFrame=false;handler.removeCallbacks(restoreTick);player.pause();player.setTime(restorePosition);}
        }
    }
    /** A newly attached paused output needs one decoded frame; prime it silently on the same player. */
    private void restorePausedVideoFrame(){
        if(player==null||!foreground||resume||wantedResume)return;
        restorePosition=playbackPosition();restorePictures=0;
        org.videolan.libvlc.interfaces.IMedia media=player.getMedia();
        try{org.videolan.libvlc.interfaces.IMedia.Stats stats=media==null?null:media.getStats();if(stats!=null)restorePictures=stats.displayedPictures;}
        finally{if(media!=null)media.release();}
        restoringFrame=true;restoreDeadline=SystemClock.uptimeMillis()+5000;
        player.setVolume(0);player.setTime(restorePosition);player.play();
        handler.removeCallbacks(restoreTick);handler.postDelayed(restoreTick,50);
    }
    protected void setPlaybackFullscreen(boolean value){fullscreen(value);}
    protected void onFullscreenChanged(boolean fullscreen){}
    private void back(){if(fullscreen)fullscreen(false);else finish();}
    @Override public void onBackPressed(){back();}
    @Override protected void onResume(){super.onResume();foreground=true;if(player==null)start();else if(restoringFrame&&!resume){restoreDeadline=SystemClock.uptimeMillis()+5000;beginPlayback();}else if(!pendingSeek&&resume&&!player.isPlaying())play();}
    @Override protected void onPause(){foreground=false;listeningTick=0;remember();handler.removeCallbacks(restoreTick);if(player!=null)player.pause();super.onPause();}
    @Override protected void onStop(){release();super.onStop();}
    @Override protected void onDestroy(){release();documents.shutdownNow();super.onDestroy();}
    @Override protected void onSaveInstanceState(Bundle saved){remember();saved.putLong("position",position);saved.putFloat("speed",speed);saved.putBoolean("playing",resume);saved.putBoolean("software",software);saved.putBoolean("repeat",repeat);saved.putBoolean("fullscreen",fullscreen);super.onSaveInstanceState(saved);}
    private static void setText(TextView view,String value){if(!value.contentEquals(view.getText()))view.setText(value);}
    private static String time(long millis){long seconds=Math.max(0,millis)/1000;return String.format(Locale.ROOT,"%d:%02d",seconds/60,seconds%60);}
    protected long playbackPosition(){
        if(scrubbing)return scrubPosition;
        if(player==null||previewAtEnd)return position;
        if(restoringFrame)return restorePosition;
        long actual=Math.max(0,player.getTime());
        if(pendingPosition>=0){if(Math.abs(actual-pendingPosition)<300||SystemClock.uptimeMillis()>=seekDeadline)pendingPosition=-1;else return pendingPosition;}
        return actual;
    }
    protected boolean playbackMoving(){return player!=null&&player.isPlaying()&&!restoringFrame&&!scrubbing;}
    protected void previewPlaybackPosition(long millis){scrubbing=true;scrubPosition=Math.max(0,millis);onPlaybackTime(scrubPosition);}
    protected void endPlaybackPositionPreview(){scrubbing=false;onPlaybackTime(playbackPosition());}
    protected void seekPlayback(long millis){
        scrubbing=false;long length=player==null?0:player.getLength();position=Math.max(0,length>0?Math.min(length,millis):millis);
        if(restoringFrame)restorePosition=position;
        if(player!=null){pendingPosition=position;seekDeadline=SystemClock.uptimeMillis()+1500;player.setTime(position);}
        onPlaybackTime(position);
    }
    protected void onPlaybackTime(long millis) { }
}
