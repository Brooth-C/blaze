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
    private TextView status, clock;
    protected LinearLayout root;
    private LinearLayout header;
    Button toggle;
    private SeekBar seek;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private long position;
    private float speed=1;
    private boolean software, repeat, fullscreen, resume=true, pendingSeek, wantedResume, ended, foreground;
    private AudioManager audio;
    private boolean focusGranted, noisyRegistered;
    private final AudioManager.OnAudioFocusChangeListener focus=change->{if(change<0)pause();};
    private final BroadcastReceiver noisy=new BroadcastReceiver(){
        @Override public void onReceive(Context context,Intent intent){pause();}
    };
    private final Runnable tick=new Runnable(){public void run(){
        if(player!=null){long length=player.getLength(), time=Math.max(0,player.getTime());
            if(!seek.isPressed())seek.setProgress(length>0?(int)(time*1000/length):0);
            clock.setText(time(time)+" / "+time(length));toggle.setText(player.isPlaying()?"Pause":"Play");
            onPlaybackTime(time);
        }handler.postDelayed(this,500);
    }};

    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);setVolumeControlStream(AudioManager.STREAM_MUSIC);
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
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(0xff0d1117);
        header=new LinearLayout(this);root.addView(header);
        Button back=button(header,"Back",this::back);back.setLayoutParams(new LinearLayout.LayoutParams((int)(64*getResources().getDisplayMetrics().density),-2));TextView title=new TextView(this);title.setText(mediaTitle);title.setSingleLine(true);title.setEllipsize(android.text.TextUtils.TruncateAt.END);title.setTextColor(0xffeeeeee);header.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        video=new VLCVideoLayout(this);root.addView(video,new LinearLayout.LayoutParams(-1,0,1));
        status=new TextView(this);status.setTextColor(0xffeeeeee);root.addView(status);
        clock=new TextView(this);clock.setTextColor(0xffeeeeee);root.addView(clock);
        seek=new SeekBar(this);seek.setMax(1000);seek.setContentDescription("Seek through media");root.addView(seek);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar bar){}public void onProgressChanged(SeekBar bar,int value,boolean user){}public void onStopTrackingTouch(SeekBar bar){if(player!=null&&player.getLength()>0)player.setTime(player.getLength()*bar.getProgress()/1000);}});
        LinearLayout controls=new LinearLayout(this);root.addView(controls);
        button(controls,"−10s",()->skip(-10000));toggle=button(controls,"Pause",()->{if(player!=null){if(player.isPlaying())pause();else play();}});button(controls,"+10s",()->skip(10000));button(controls,"Full screen",()->fullscreen(!fullscreen));
        LinearLayout extra=new LinearLayout(this);root.addView(extra);
        button(extra,"Speed",()->new AlertDialog.Builder(this).setTitle("Playback speed").setItems(new String[]{"0.5×","1×","1.5×","2×"},(d,i)->{speed=new float[]{.5f,1,1.5f,2}[i];if(player!=null)player.setRate(speed);}).show());
        button(extra,"Tracks",this::tracks);button(extra,"Repeat",()->{repeat=!repeat;Toast.makeText(this,repeat?"Repeat on":"Repeat off",Toast.LENGTH_SHORT).show();});
        button(root,"Decoder: automatic / software",()->new AlertDialog.Builder(this).setTitle("Video decoding").setItems(new String[]{"Automatic (recommended)","Software (for unsupported hardware codecs)"},(d,i)->{remember();software=i==1;release();resume=true;start();}).show());
        button(root,"Try again",()->{remember();release();resume=true;start();});
        if(source!=null && !(this instanceof ChordActivity))button(root,"Use Android playback engine",()->{startActivity(new Intent(this,PlayerActivity.class).putExtra("job",source.id));finish();});
        setContentView(root);
        video.setOnClickListener(v->{if(fullscreen)fullscreen(false);});
        fullscreen(fullscreen);
        ViewCompat.setOnApplyWindowInsetsListener(root,(v,insets)->{androidx.core.graphics.Insets safe=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());v.setPadding(safe.left,safe.top,safe.right,safe.bottom);return insets;});
        if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::back);
    }
    private Button button(LinearLayout parent,String text,Runnable action){Button b=new Button(this);b.setText(text);b.setTextSize(12);b.setAllCaps(false);b.setMinWidth(0);b.setMinimumWidth(0);b.setMinHeight((int)(48*getResources().getDisplayMetrics().density));b.setOnClickListener(v->action.run());parent.addView(b,parent.getOrientation()==LinearLayout.HORIZONTAL?new LinearLayout.LayoutParams(0,-2,1):new LinearLayout.LayoutParams(-1,-2));return b;}
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
            ArrayList<String> options=new ArrayList<>(Arrays.asList("--no-video-title-show","--file-caching=300","--avcodec-threads=2"));
            // Software fallback must also work without 10-bit OpenGL texture support.
            if(software){options.add("--vout=android-display");options.add("--android-display-chroma=RV32");}
            engine=new LibVLC(this,options);
            player=new MediaPlayer(engine);player.attachViews(video,null,true,false);pendingSeek=true;wantedResume=resume;ended=false;
            MediaPlayer active=player;
            player.setEventListener(event->{if(player!=active)return;
                switch(event.type){
                    case MediaPlayer.Event.Playing:
                        if(pendingSeek){pendingSeek=false;player.setRate(speed);}
                        if(!foreground||!resume||!wantedResume){player.pause();status.setText("Paused");video.setKeepScreenOn(false);break;}
                        toggle.setText("Pause");status.setText("Playing in Blaze · LibVLC");video.setKeepScreenOn(player.getCurrentVideoTrack()!=null);break;
                    case MediaPlayer.Event.Paused:
                        if(pendingSeek){pendingSeek=false;player.setRate(speed);}
                        player.setVolume(100);toggle.setText("Play");status.setText("Paused");video.setKeepScreenOn(false);
                        if(foreground&&resume&&wantedResume)beginPlayback();break;
                    case MediaPlayer.Event.EndReached:
                        position=0;ended=!repeat;video.setKeepScreenOn(false);
                        getSharedPreferences("playback",MODE_PRIVATE).edit().remove(mediaId).apply();
                        if(repeat){player.stop();player.play();}else{resume=false;status.setText("Playback finished");}break;
                    case MediaPlayer.Event.EncounteredError:
                        video.setKeepScreenOn(false);status.setText("Could not decode this file. Try Software decoding. Damaged or encrypted files may not play.");break;
                    default: break;
                }
            });
            Media media=document==null?new Media(engine,Uri.fromFile(source.file)):new Media(engine,descriptor.getFileDescriptor());
            try{
                // Let VLC preroll the restored frame before pausing; pausing in Playing races decoding.
                if(position>0)media.addOption(":start-time="+Double.toString(position/1000.0));
                if(!resume)media.addOption(":start-paused");
                media.setHWDecoderEnabled(!software,false);player.setMedia(media);
            }finally{media.release();}
            status.setText("Opening the original file…");beginPlayback();handler.post(tick);
            ContextCompat.registerReceiver(this,noisy,new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY),ContextCompat.RECEIVER_NOT_EXPORTED);noisyRegistered=true;
        }catch(IOException|RuntimeException|UnsatisfiedLinkError error){android.util.Log.e("BlazePlayer","Player initialization failed",error);release();status.setText("Blaze could not open this file. Try again.");}
    }
    private void play(){resume=true;wantedResume=true;beginPlayback();}
    @SuppressWarnings("deprecation") private void beginPlayback(){if(player==null)return;if(!resume){player.setVolume(0);player.play();return;}focusGranted=audio.requestAudioFocus(focus,AudioManager.STREAM_MUSIC,AudioManager.AUDIOFOCUS_GAIN)==AudioManager.AUDIOFOCUS_REQUEST_GRANTED;if(focusGranted){player.setVolume(100);player.play();}else status.setText("Audio is in use by another app. Try Play again.");}
    private void pause(){resume=false;wantedResume=false;if(player!=null){player.pause();video.setKeepScreenOn(false);}}
    private void skip(long amount){if(player!=null)player.setTime(Math.max(0,Math.min(player.getLength(),player.getTime()+amount)));}
    private void tracks(){if(player==null)return;new AlertDialog.Builder(this).setTitle("Tracks").setItems(new String[]{"Audio","Subtitles"},(d,i)->{
        MediaPlayer.TrackDescription[] choices=i==0?player.getAudioTracks():player.getSpuTracks();
        if(choices==null||choices.length==0){Toast.makeText(this,"No tracks available",Toast.LENGTH_SHORT).show();return;}
        String[] names=new String[choices.length];for(int n=0;n<names.length;n++)names[n]=choices[n].name;
        new AlertDialog.Builder(this).setTitle(i==0?"Audio track":"Subtitles").setItems(names,(dialog,n)->{if(player!=null){if(i==0)player.setAudioTrack(choices[n].id);else player.setSpuTrack(choices[n].id);}}).show();
    }).show();}
    private void remember(){if(player!=null&&mediaId!=null){position=ended?0:Math.max(0,player.getTime());getSharedPreferences("playback",MODE_PRIVATE).edit().putLong(mediaId,position).apply();}}
    private static void close(ParcelFileDescriptor value){if(value!=null)try{value.close();}catch(IOException ignored){}}
    @SuppressWarnings("deprecation") private void release(){generation++;opening=false;if(openingTask!=null){openingTask.cancel(true);openingTask=null;}handler.removeCallbacks(tick);if(noisyRegistered){unregisterReceiver(noisy);noisyRegistered=false;}if(player!=null){player.setEventListener(null);player.stop();player.detachViews();player.release();player=null;}if(engine!=null){engine.release();engine=null;}close(descriptor);descriptor=null;if(video!=null)video.setKeepScreenOn(false);if(focusGranted){audio.abandonAudioFocus(focus);focusGranted=false;}}
    private void fullscreen(boolean value){fullscreen=value;for(int i=0;i<root.getChildCount();i++){View child=root.getChildAt(i);if(child!=video)child.setVisibility(value?View.GONE:View.VISIBLE);}WindowInsetsControllerCompat bars=WindowCompat.getInsetsController(getWindow(),root);bars.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);if(value)bars.hide(WindowInsetsCompat.Type.systemBars());else bars.show(WindowInsetsCompat.Type.systemBars());}
    private void back(){if(fullscreen)fullscreen(false);else finish();}
    @Override public void onBackPressed(){back();}
    @Override protected void onResume(){super.onResume();foreground=true;if(player==null)start();else if(!pendingSeek&&resume&&!player.isPlaying())play();}
    @Override protected void onPause(){foreground=false;remember();if(player!=null)player.pause();super.onPause();}
    @Override protected void onStop(){release();super.onStop();}
    @Override protected void onDestroy(){release();documents.shutdownNow();super.onDestroy();}
    @Override protected void onSaveInstanceState(Bundle saved){remember();saved.putLong("position",position);saved.putFloat("speed",speed);saved.putBoolean("playing",resume);saved.putBoolean("software",software);saved.putBoolean("repeat",repeat);saved.putBoolean("fullscreen",fullscreen);super.onSaveInstanceState(saved);}
    private static String time(long millis){long seconds=Math.max(0,millis)/1000;return String.format(Locale.ROOT,"%d:%02d",seconds/60,seconds%60);}
    protected void onPlaybackTime(long millis) { }
}
