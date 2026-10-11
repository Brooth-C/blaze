package com.brooth.blaze;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import androidx.lifecycle.Lifecycle;
import androidx.media3.common.Player;
import androidx.media3.common.util.UnstableApi;
import androidx.media3.ui.PlayerView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
@androidx.annotation.OptIn(markerClass=UnstableApi.class)
public class PlaybackTest {
    private final Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
    private Player player(PlayerActivity activity){return ((PlayerView)activity.findViewById(R.id.media_player)).getPlayer();}
    private void ready(ActivityScenario<PlayerActivity> screen)throws Exception{
        long until=System.currentTimeMillis()+15000;AtomicBoolean ready=new AtomicBoolean();
        while(!ready.get()&&System.currentTimeMillis()<until){screen.onActivity(a->{Player p=player(a);ready.set(p!=null&&p.getPlaybackState()==Player.STATE_READY&&p.getPlayerError()==null);});Thread.sleep(40);}
        assertTrue("Media did not become ready",ready.get());
    }
    private final class Fixture implements AutoCloseable {
        final JobStore store=new JobStore(app);
        final String id;
        final File file, directory;
        Fixture(String asset,String mode)throws Exception{
            assertFalse("Use a fresh disposable emulator",store.hasQueued());
            String title="audio".equals(mode)?"Blaze audio demo":"Blaze video demo";
            id=store.enqueue("https://example.test/player/"+UUID.randomUUID(),mode,"{}",title);
            assertEquals(id,store.claimNext().id);
            directory=new File(DownloadService.folder(app),id);assertTrue(directory.mkdirs());file=new File(directory,asset);
            try(InputStream in=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open(asset);OutputStream out=new FileOutputStream(file)){
                byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);
            }
            store.finish(id,"complete",title,file.getAbsolutePath(),"");
        }
        Intent intent(){return new Intent(app,PlayerActivity.class).putExtra("job",id);}
        public void close(){store.getWritableDatabase().delete("jobs","id=?",new String[]{id});store.close();file.delete();directory.delete();app.getSharedPreferences("playback",Context.MODE_PRIVATE).edit().remove(id).remove("speed").apply();}
    }
    private void screenshot(String name)throws Exception{
        Bitmap image=InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();assertNotNull(image);
        File out=new File(InstrumentationRegistry.getInstrumentation().getContext().getFilesDir(),name);
        try(OutputStream stream=new FileOutputStream(out)){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,stream));}finally{image.recycle();}
    }
    @Test public void audioPlaysSeeksAndSurvivesRecreation()throws Exception{
        try(Fixture fixture=new Fixture("player-audio.mp3","audio");ActivityScenario<PlayerActivity> screen=ActivityScenario.launch(fixture.intent())){
            ready(screen);screen.onActivity(a->{Player p=player(a);assertTrue(p.getDuration()>5000);p.pause();p.seekTo(1200);p.setPlaybackSpeed(1.5f);p.setRepeatMode(Player.REPEAT_MODE_ONE);});
            screen.recreate();ready(screen);
            screen.onActivity(a->{Player p=player(a);assertFalse(p.getPlayWhenReady());assertEquals(1200,p.getCurrentPosition(),250);assertEquals(1.5f,p.getPlaybackParameters().speed,0.01f);assertEquals(Player.REPEAT_MODE_ONE,p.getRepeatMode());});
            screenshot("Blaze-Player-Audio.png");
            screen.onActivity(a->player(a).play());Thread.sleep(450);
            screen.onActivity(a->{assertTrue(player(a).isPlaying());assertTrue(player(a).getCurrentPosition()>1400);});
            screen.moveToState(Lifecycle.State.CREATED);screen.onActivity(a->assertNull(player(a)));
            screen.moveToState(Lifecycle.State.RESUMED);ready(screen);screen.onActivity(a->assertTrue(player(a).getCurrentPosition()>1400));
        }
    }
    @Test public void videoDecodesInsideBlazeAndFullscreenCanExit()throws Exception{
        try(Fixture fixture=new Fixture("player-video.mp4","video");ActivityScenario<PlayerActivity> screen=ActivityScenario.launch(fixture.intent())){
            ready(screen);Thread.sleep(350);
            screen.onActivity(a->{Player p=player(a);assertTrue(p.isPlaying());assertEquals(320,p.getVideoSize().width);assertEquals(180,p.getVideoSize().height);assertTrue(p.getCurrentPosition()>100);p.pause();((PlayerView)a.findViewById(R.id.media_player)).showController();});
            screenshot("Blaze-Player-Video.png");
            screen.onActivity(a->{a.findViewById(androidx.media3.ui.R.id.exo_fullscreen).performClick();assertEquals(android.view.View.GONE,a.findViewById(R.id.player_header).getVisibility());a.onBackPressed();assertEquals(android.view.View.VISIBLE,a.findViewById(R.id.player_header).getVisibility());assertFalse(a.isFinishing());});
        }
    }
    @Test public void unfinishedMissingAndOutsideFilesAreRejected()throws Exception{
        try(Fixture fixture=new Fixture("player-audio.mp3","audio")){
            assertEquals(fixture.file.getCanonicalFile(),PlaybackSource.load(app,fixture.id).file);
            android.content.ContentValues values=new android.content.ContentValues();values.put("state","running");fixture.store.getWritableDatabase().update("jobs",values,"id=?",new String[]{fixture.id});
            try{PlaybackSource.load(app,fixture.id);fail("Unfinished file accepted");}catch(IOException expected){}
            File outside=new File(app.getCacheDir(),"outside-"+UUID.randomUUID()+".mp3");try(OutputStream out=new FileOutputStream(outside)){out.write(1);}
            values.put("state","complete");values.put("path",outside.getAbsolutePath());fixture.store.getWritableDatabase().update("jobs",values,"id=?",new String[]{fixture.id});
            try{PlaybackSource.load(app,fixture.id);fail("Outside path accepted");}catch(IOException expected){}finally{assertTrue(outside.delete());}
            values.put("path",fixture.file.getAbsolutePath());fixture.store.getWritableDatabase().update("jobs",values,"id=?",new String[]{fixture.id});assertTrue(fixture.file.delete());
            try{PlaybackSource.load(app,fixture.id);fail("Missing file accepted");}catch(IOException expected){}
            try{PlaybackSource.load(app,"../outside");fail("Invalid ID accepted");}catch(IOException expected){}
        }
    }
}
