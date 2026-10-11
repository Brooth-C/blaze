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
import org.videolan.libvlc.*;
import org.videolan.libvlc.util.VLCVideoLayout;
import java.io.IOException;
import java.util.Arrays;
import java.util.Locale;

/** Embedded LibVLC plays the original completed file, without another app or conversion. */
public class VlcPlayerActivity extends Activity {
    MediaPlayer player;
    private LibVLC engine;
    private PlaybackSource source;
    private VLCVideoLayout video;
    private TextView status, clock;
    private LinearLayout root, header;
    private Button toggle;
    private SeekBar seek;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private long position;
    private float speed=1;
    private boolean software, repeat, fullscreen, resume=true, pendingSeek, wantedResume;
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
        }handler.postDelayed(this,500);
    }};

    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);setVolumeControlStream(AudioManager.STREAM_MUSIC);
        try{source=PlaybackSource.load(this,getIntent().getStringExtra("job"));}
        catch(IOException|RuntimeException error){Toast.makeText(this,"This completed file is unavailable.",Toast.LENGTH_LONG).show();finish();return;}
        position=Math.max(0,getSharedPreferences("playback",MODE_PRIVATE).getLong(source.id,0));
        software=getIntent().getBooleanExtra("software",false);
        if(saved!=null){position=saved.getLong("position",position);speed=saved.getFloat("speed",1);software=saved.getBoolean("software");repeat=saved.getBoolean("repeat");resume=saved.getBoolean("playing",true);}
        if(!Float.isFinite(speed)||speed<0.5f||speed>2)speed=1;
        audio=(AudioManager)getSystemService(AUDIO_SERVICE);
        WindowCompat.setDecorFitsSystemWindows(getWindow(),false);
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(0xff0d1117);
        header=new LinearLayout(this);root.addView(header);
        button(header,"Back",this::back);TextView title=new TextView(this);title.setText(source.title);title.setTextColor(0xffeeeeee);header.addView(title,new LinearLayout.LayoutParams(0,-2,1));
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
        setContentView(root);
        ViewCompat.setOnApplyWindowInsetsListener(root,(v,insets)->{androidx.core.graphics.Insets safe=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());v.setPadding(safe.left,safe.top,safe.right,safe.bottom);return insets;});
        if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::back);
    }
    private Button button(LinearLayout parent,String text,Runnable action){Button b=new Button(this);b.setText(text);b.setTextAllCaps(false);b.setMinHeight((int)(48*getResources().getDisplayMetrics().density));b.setOnClickListener(v->action.run());parent.addView(b);return b;}
    private void start(){
        if(source==null||player!=null||isFinishing())return;
        try{
            source=PlaybackSource.load(this,source.id);
            engine=new LibVLC(this,Arrays.asList("--no-video-title-show","--file-caching=300","--avcodec-threads=2"));
            player=new MediaPlayer(engine);player.attachViews(video,null,true,false);pendingSeek=true;wantedResume=resume;
            player.setEventListener(event->{if(player==null)return;
                switch(event.type){
                    case MediaPlayer.Event.Playing:
                        if(pendingSeek){pendingSeek=false;if(position>0)player.setTime(position);player.setRate(speed);if(!wantedResume){resume=false;player.pause();}}
                        status.setText("Playing in Blaze · LibVLC");video.setKeepScreenOn(!"audio".equals(source.mode));break;
                    case MediaPlayer.Event.Paused: status.setText("Paused");video.setKeepScreenOn(false);break;
                    case MediaPlayer.Event.EndReached:
                        position=0;video.setKeepScreenOn(false);
                        getSharedPreferences("playback",MODE_PRIVATE).edit().remove(source.id).apply();
                        if(repeat){player.stop();player.play();}else{resume=false;status.setText("Playback finished");}break;
                    case MediaPlayer.Event.EncounteredError:
                        video.setKeepScreenOn(false);status.setText("Could not decode this file. Try Software decoding. Damaged or encrypted files may not play.");break;
                    default: break;
                }
            });
            Media media=new Media(engine,Uri.fromFile(source.file));
            try{media.setHWDecoderEnabled(!software,false);player.setMedia(media);}finally{media.release();}
            status.setText("Opening the original file…");play();handler.post(tick);
            ContextCompat.registerReceiver(this,noisy,new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY),ContextCompat.RECEIVER_NOT_EXPORTED);noisyRegistered=true;
        }catch(IOException|RuntimeException|UnsatisfiedLinkError error){release();status.setText("Blaze could not open this file. Try again.");}
    }
    @SuppressWarnings("deprecation") private void play(){if(player==null)return;focusGranted=audio.requestAudioFocus(focus,AudioManager.STREAM_MUSIC,AudioManager.AUDIOFOCUS_GAIN)==AudioManager.AUDIOFOCUS_REQUEST_GRANTED;if(focusGranted){resume=true;player.play();}else status.setText("Audio is in use by another app. Try Play again.");}
    private void pause(){if(player!=null){resume=false;player.pause();video.setKeepScreenOn(false);}}
    private void skip(long amount){if(player!=null)player.setTime(Math.max(0,Math.min(player.getLength(),player.getTime()+amount)));}
    private void tracks(){if(player==null)return;new AlertDialog.Builder(this).setTitle("Tracks").setItems(new String[]{"Audio","Subtitles"},(d,i)->{
        MediaPlayer.TrackDescription[] choices=i==0?player.getAudioTracks():player.getSpuTracks();
        if(choices==null||choices.length==0){Toast.makeText(this,"No tracks available",Toast.LENGTH_SHORT).show();return;}
        String[] names=new String[choices.length];for(int n=0;n<names.length;n++)names[n]=choices[n].name;
        new AlertDialog.Builder(this).setTitle(i==0?"Audio track":"Subtitles").setItems(names,(dialog,n)->{if(player!=null){if(i==0)player.setAudioTrack(choices[n].id);else player.setSpuTrack(choices[n].id);}}).show();
    }).show();}
    private void remember(){if(player!=null&&source!=null){position=Math.max(0,player.getTime());resume=player.isPlaying();getSharedPreferences("playback",MODE_PRIVATE).edit().putLong(source.id,position).apply();}}
    @SuppressWarnings("deprecation") private void release(){handler.removeCallbacks(tick);if(noisyRegistered){unregisterReceiver(noisy);noisyRegistered=false;}if(player!=null){player.setEventListener(null);player.stop();player.detachViews();player.release();player=null;}if(engine!=null){engine.release();engine=null;}if(video!=null)video.setKeepScreenOn(false);if(focusGranted){audio.abandonAudioFocus(focus);focusGranted=false;}}
    private void fullscreen(boolean value){fullscreen=value;header.setVisibility(value?View.GONE:View.VISIBLE);WindowInsetsControllerCompat bars=WindowCompat.getInsetsController(getWindow(),root);bars.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);if(value)bars.hide(WindowInsetsCompat.Type.systemBars());else bars.show(WindowInsetsCompat.Type.systemBars());}
    private void back(){if(fullscreen)fullscreen(false);else finish();}
    @Override public void onBackPressed(){back();}
    @Override protected void onStart(){super.onStart();start();}
    @Override protected void onPause(){remember();if(player!=null)player.pause();super.onPause();}
    @Override protected void onStop(){release();super.onStop();}
    @Override protected void onDestroy(){release();super.onDestroy();}
    @Override protected void onSaveInstanceState(Bundle saved){remember();saved.putLong("position",position);saved.putFloat("speed",speed);saved.putBoolean("playing",resume);saved.putBoolean("software",software);saved.putBoolean("repeat",repeat);super.onSaveInstanceState(saved);}
    private static String time(long millis){long seconds=Math.max(0,millis)/1000;return String.format(Locale.ROOT,"%d:%02d",seconds/60,seconds%60);}
}
