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
        try(ActivityScenario<VlcPlayerActivity> screen=ActivityScenario.launch(new Intent(app,VlcPlayerActivity.class).putExtra("job",id).putExtra("software",true))){
            ready(screen);
            screen.onActivity(a->{assertTrue(a.player.getAudioTracksCount()>0);assertTrue(a.player.getVideoTracksCount()>0);assertEquals(320,a.player.getCurrentVideoTrack().width);a.player.pause();a.player.setTime(1500);});
            Thread.sleep(250);screen.recreate();ready(screen);
            screen.onActivity(a->{assertTrue(a.player.getTime()>=1200);});
            screen.moveToState(Lifecycle.State.CREATED);screen.onActivity(a->assertNull(a.player));
            screen.moveToState(Lifecycle.State.RESUMED);ready(screen);
        }finally{
            try(JobStore store=new JobStore(app)){store.getWritableDatabase().delete("jobs","id=?",new String[]{id});}
            file.delete();directory.delete();app.getSharedPreferences("playback",Context.MODE_PRIVATE).edit().remove(id).apply();
        }
    }
    private void ready(ActivityScenario<VlcPlayerActivity> screen)throws Exception{
        long until=System.currentTimeMillis()+20000;AtomicBoolean ready=new AtomicBoolean();
        while(!ready.get()&&System.currentTimeMillis()<until){screen.onActivity(a->ready.set(a.player!=null&&a.player.getTime()>100&&a.player.getCurrentVideoTrack()!=null));Thread.sleep(50);}
        assertTrue("LibVLC did not decode the original HEVC MKV",ready.get());
    }
}
