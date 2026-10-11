package com.brooth.blaze;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import androidx.media3.common.*;
import androidx.media3.common.util.RepeatModeUtil;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.exoplayer.DefaultRenderersFactory;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.ui.PlayerView;
import java.io.IOException;

/** Local playback uses Media3 inside Blaze; no external player is launched. */
@androidx.annotation.OptIn(markerClass=UnstableApi.class)
public class PlayerActivity extends Activity {
    private PlayerView view;
    private TextView status;
    private PlaybackSource source;
    private ExoPlayer player;
    private long position;
    private float speed=1;
    private int repeat=Player.REPEAT_MODE_OFF;
    private boolean playWhenReady=true, fullscreen;
    private SharedPreferences bookmarks;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC);
        try {source=PlaybackSource.load(this,getIntent().getStringExtra("job"));}
        catch(IOException|RuntimeException error){Toast.makeText(this,"This completed file is no longer available.",Toast.LENGTH_LONG).show();finish();return;}
        bookmarks=getSharedPreferences("playback",MODE_PRIVATE);
        position=Math.max(0,bookmarks.getLong(source.id,0));
        speed=bookmarks.getFloat("speed",1);
        if(!Float.isFinite(speed)||speed<0.25f||speed>3)speed=1;
        if(saved!=null){position=Math.max(0,saved.getLong("position",position));playWhenReady=saved.getBoolean("playing",true);speed=saved.getFloat("speed",speed);repeat=saved.getInt("repeat",repeat);fullscreen=saved.getBoolean("fullscreen");}
        WindowCompat.setDecorFitsSystemWindows(getWindow(),false);
        setContentView(R.layout.activity_player);
        view=findViewById(R.id.media_player);status=findViewById(R.id.player_status);
        ((TextView)findViewById(R.id.player_title)).setText(source.title);
        findViewById(R.id.player_back).setOnClickListener(v->back());
        findViewById(R.id.player_retry).setOnClickListener(v->{releasePlayer();startPlayer();});
        view.setShutterBackgroundColor(Color.BLACK);
        view.setDefaultArtwork(getDrawable(R.drawable.blaze_logo));
        View artwork=view.findViewById(androidx.media3.ui.R.id.exo_artwork);
        if(artwork!=null)artwork.setLayerType(View.LAYER_TYPE_SOFTWARE,null);
        view.setRepeatToggleModes(RepeatModeUtil.REPEAT_TOGGLE_MODE_ONE);
        view.setControllerShowTimeoutMs("audio".equals(source.mode)?0:3000);
        view.setFullscreenButtonClickListener(this::setFullscreen);
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.player_root),(root,insets)->{
            androidx.core.graphics.Insets safe=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());
            root.setPadding(safe.left,safe.top,safe.right,safe.bottom);return insets;
        });
        if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::back);
        setFullscreen(fullscreen);
    }

    private void startPlayer() {
        if(source==null||player!=null||isFinishing())return;
        try {source=PlaybackSource.load(this,source.id);}
        catch(IOException|RuntimeException error){showError("The saved file is missing or unavailable.");return;}
        findViewById(R.id.player_retry).setVisibility(View.GONE);
        status.setText("Opening your download…");view.setCustomErrorMessage(null);
        try {
            player=new ExoPlayer.Builder(this,new DefaultRenderersFactory(this).setEnableDecoderFallback(true))
                .setSeekBackIncrementMs(10000).setSeekForwardIncrementMs(10000).build();
            player.setAudioAttributes(new AudioAttributes.Builder().setUsage(C.USAGE_MEDIA)
                .setContentType("audio".equals(source.mode)?C.AUDIO_CONTENT_TYPE_MUSIC:C.AUDIO_CONTENT_TYPE_MOVIE).build(),true);
            player.setHandleAudioBecomingNoisy(true);
            player.addListener(new Player.Listener(){
                @Override public void onIsPlayingChanged(boolean playing){view.setKeepScreenOn(playing);if(playing)status.setText("Playing in Blaze");else if(player!=null&&player.getPlaybackState()==Player.STATE_READY)status.setText("Paused");}
                @Override public void onPlaybackStateChanged(int state){
                    if(state==Player.STATE_READY){status.setText(player.getPlayWhenReady()?"Playing in Blaze":"Paused");if(player.getDuration()>0&&position>=player.getDuration()-500){position=0;player.seekTo(0);}}
                    else if(state==Player.STATE_ENDED){position=0;playWhenReady=false;bookmarks.edit().remove(source.id).apply();status.setText("Playback finished");}
                }
                @Override public void onPlaybackParametersChanged(PlaybackParameters parameters){speed=parameters.speed;}
                @Override public void onRepeatModeChanged(int mode){repeat=mode;}
                @Override public void onPlayerError(PlaybackException error){showError("Could not play this file. Its codec may not be supported on this device.");}
            });
            view.setPlayer(player);
            player.setMediaItem(new MediaItem.Builder().setMediaId(source.id).setUri(Uri.fromFile(source.file))
                .setMediaMetadata(new MediaMetadata.Builder().setTitle(source.title).setArtist("Blaze").build()).build());
            player.seekTo(position);player.setPlaybackSpeed(speed);player.setRepeatMode(repeat);
            player.setPlayWhenReady(playWhenReady);player.prepare();
        }catch(RuntimeException error){releasePlayer();showError("The Blaze player could not start. Try again.");}
    }

    private void showError(String message){setFullscreen(false);status.setText(message);view.setCustomErrorMessage(message);view.setKeepScreenOn(false);findViewById(R.id.player_retry).setVisibility(View.VISIBLE);}
    private void remember(){
        if(player==null||source==null)return;
        position=player.getPlaybackState()==Player.STATE_ENDED?0:Math.max(0,player.getCurrentPosition());
        playWhenReady=player.getPlayWhenReady()&&player.getPlaybackState()!=Player.STATE_ENDED;
        speed=player.getPlaybackParameters().speed;repeat=player.getRepeatMode();
        bookmarks.edit().putLong(source.id,position).putFloat("speed",speed).apply();
    }
    private void releasePlayer(){
        if(player==null)return;remember();ExoPlayer current=player;
        view.setPlayer(null);current.release();player=null;view.setKeepScreenOn(false);
    }
    private void setFullscreen(boolean value){
        fullscreen=value;
        findViewById(R.id.player_header).setVisibility(value?View.GONE:View.VISIBLE);
        status.setVisibility(value?View.GONE:View.VISIBLE);
        view.setFullscreenButtonState(value);
        WindowInsetsControllerCompat controls=WindowCompat.getInsetsController(getWindow(),findViewById(R.id.player_root));
        controls.setSystemBarsBehavior(WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
        if(value)controls.hide(WindowInsetsCompat.Type.systemBars());else controls.show(WindowInsetsCompat.Type.systemBars());
    }
    private void back(){if(fullscreen)setFullscreen(false);else finish();}
    @Override public void onBackPressed(){back();}
    @Override protected void onStart(){super.onStart();if(source!=null)startPlayer();}
    @Override protected void onPause(){remember();super.onPause();}
    @Override protected void onStop(){releasePlayer();super.onStop();}
    @Override protected void onDestroy(){releasePlayer();super.onDestroy();}
    @Override public void onWindowFocusChanged(boolean focused){super.onWindowFocusChanged(focused);if(focused&&source!=null&&view!=null)setFullscreen(fullscreen);}
    @Override protected void onSaveInstanceState(Bundle out){remember();out.putLong("position",position);out.putBoolean("playing",playWhenReady);out.putFloat("speed",speed);out.putInt("repeat",repeat);out.putBoolean("fullscreen",fullscreen);super.onSaveInstanceState(out);}
}
