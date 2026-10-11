package com.brooth.blaze;

import android.content.Context;
import android.content.Intent;
import androidx.lifecycle.Lifecycle;
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
public class VlcPlaybackTest {
    private final Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
    @Test public void originalHevcTenBitMkvAndAc3PlayWithSoftwareDecoder()throws Exception{
        String id;File directory,file;
        try(JobStore store=new JobStore(app)){
            assertFalse(store.hasQueued());
            id=store.enqueue("https://example.test/vlc/"+UUID.randomUUID(),"video","{}","HEVC MKV demo");assertEquals(id,store.claimNext().id);
            directory=new File(DownloadService.folder(app),id);assertTrue(directory.mkdirs());file=new File(directory,"player-hevc.mkv");
            try(InputStream in=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open("player-hevc.mkv");OutputStream out=new FileOutputStream(file)){byte[] buffer=new byte[4096];int n;while((n=in.read(buffer))!=-1)out.write(buffer,0,n);}
            store.finish(id,"complete","HEVC MKV demo",file.getAbsolutePath(),"");
        }
        android.net.Uri selected=androidx.core.content.FileProvider.getUriForFile(app,app.getPackageName()+".files",file);
        android.media.AudioManager audio=app.getSystemService(android.media.AudioManager.class);
        AtomicBoolean focusStolen=new AtomicBoolean();android.media.AudioManager.OnAudioFocusChangeListener music=change->{if(change<0)focusStolen.set(true);};
        try{
        try(ActivityScenario<VlcPlayerActivity> screen=ActivityScenario.launch(new Intent(app,VlcPlayerActivity.class).putExtra("job",id).putExtra("software",true))){
            ready(screen,true);
            screen.onActivity(a->{assertTrue(a.player.isPlaying());assertTrue(a.player.getAudioTracksCount()>0);assertTrue(a.player.getVideoTracksCount()>0);assertEquals(320,a.player.getCurrentVideoTrack().width);a.toggle.performClick();a.player.setTime(1500);});
            assertEquals(android.media.AudioManager.AUDIOFOCUS_REQUEST_GRANTED,audio.requestAudioFocus(music,android.media.AudioManager.STREAM_MUSIC,android.media.AudioManager.AUDIOFOCUS_GAIN));
            Thread.sleep(250);screen.recreate();ready(screen,false);
            screen.onActivity(a->{assertTrue(a.player.getTime()>=1200);assertFalse(a.player.isPlaying());});
            Thread.sleep(200);assertFalse("Restoring a paused video must not interrupt other audio",focusStolen.get());
            Thread.sleep(550); // Allow the visible timeline to refresh before the release screenshot.
            android.graphics.Bitmap image=null;boolean rendered=false;android.graphics.Rect bounds=new android.graphics.Rect();
            for(int attempt=0;attempt<40&&!rendered;attempt++){
                screen.onActivity(a->{int[] location=new int[2];a.video.getLocationOnScreen(location);bounds.set(location[0],location[1],location[0]+a.video.getWidth(),location[1]+a.video.getHeight());});
                if(image!=null)image.recycle();image=InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();assertNotNull(image);
                int colored=0;for(int y=Math.max(0,bounds.top);y<Math.min(image.getHeight(),bounds.bottom);y++)for(int x=Math.max(0,bounds.left);x<Math.min(image.getWidth(),bounds.right);x++){int color=image.getPixel(x,y);if(android.graphics.Color.red(color)>150&&android.graphics.Color.red(color)>android.graphics.Color.blue(color)*2)colored++;}
                rendered=colored>100;if(!rendered)Thread.sleep(100);
            }
            assertTrue("HEVC video must render, not only play its audio",rendered);
            try(OutputStream out=new FileOutputStream(new File(app.getFilesDir(),"Blaze-VLC-Player.png"))){assertTrue(image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out));}finally{image.recycle();}
            screen.moveToState(Lifecycle.State.CREATED);screen.onActivity(a->assertNull(a.player));
            screen.moveToState(Lifecycle.State.RESUMED);ready(screen,false);
        }
        audio.abandonAudioFocus(music);
        try(ActivityScenario<VlcPlayerActivity> selectedFile=ActivityScenario.launch(new Intent(app,VlcPlayerActivity.class).setData(selected).putExtra("software",true))){
            ready(selectedFile,true);
            selectedFile.onActivity(a->{assertEquals(320,a.player.getCurrentVideoTrack().width);assertTrue(a.player.getAudioTracksCount()>0);});
            selectedFile.moveToState(Lifecycle.State.CREATED);selectedFile.onActivity(a->assertNull(a.player));
            selectedFile.moveToState(Lifecycle.State.RESUMED);ready(selectedFile,true);
        }
        }finally{
            audio.abandonAudioFocus(music);
            try(JobStore store=new JobStore(app)){store.getWritableDatabase().delete("jobs","id=?",new String[]{id});}
            file.delete();directory.delete();app.getSharedPreferences("playback",Context.MODE_PRIVATE).edit().remove(id).remove("document:"+selected).apply();
        }
    }
    private void ready(ActivityScenario<VlcPlayerActivity> screen,boolean playing)throws Exception{
        long until=System.currentTimeMillis()+20000;AtomicBoolean ready=new AtomicBoolean();
        while(!ready.get()&&System.currentTimeMillis()<until){screen.onActivity(a->ready.set(a.player!=null&&a.player.getTime()>100&&a.player.getCurrentVideoTrack()!=null&&a.player.isPlaying()==playing));Thread.sleep(50);}
        if(!ready.get())screen.onActivity(a->System.out.println("Blaze player: "+(a.player==null?"not initialized":"state="+a.player.getPlayerState()+", time="+a.player.getTime()+", playing="+a.player.isPlaying()+", tracks="+a.player.getVideoTracksCount())));
        assertTrue("LibVLC did not decode the original HEVC MKV",ready.get());
    }
}
