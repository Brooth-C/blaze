package com.brooth.blaze;

import android.content.*;
import android.os.Build;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class QueueServiceTest {
    interface Condition{boolean ok();}
    private void waitFor(Condition condition)throws Exception{long end=System.currentTimeMillis()+15000;while(!condition.ok()&&System.currentTimeMillis()<end)Thread.sleep(50);assertTrue("Queue lifecycle timed out",condition.ok());}
    @Test public void rotationPauseResumeAndQueuedCompletion()throws Exception{
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();JobStore store=new JobStore(app);assertFalse("Run only on a disposable emulator",DownloadService.busy);assertTrue("Use a fresh test app",store.list().isEmpty());
        List<String> ids=new ArrayList<>();AtomicInteger attempts=new AtomicInteger();
        DownloadService.engineOverride=(job,directory,callback)->{
            int attempt=attempts.incrementAndGet();
            if(attempt==1){while(!callback.isCancelled()){callback.onProgress(25,"Testing queued download…");Thread.sleep(50);}throw new InterruptedException("Paused fixture");}
            File output=new File(directory,"fixture.mp4");
            try(InputStream in=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open("fixture-video.mp4");OutputStream out=new FileOutputStream(output)){byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}
            return new JSONObject().put("title","Synthetic fixture").put("path",output.getAbsolutePath()).toString();
        };
        try(ActivityScenario<MainActivity> screen=ActivityScenario.launch(MainActivity.class)){
            ids.add(store.enqueue("https://example.test/first","video","{}","First"));ids.add(store.enqueue("https://example.test/second","video","{}","Second"));
            Intent resume=new Intent(app,DownloadService.class).setAction("RESUME");if(Build.VERSION.SDK_INT>=26)app.startForegroundService(resume);else app.startService(resume);
            waitFor(()->attempts.get()==1&&DownloadService.busy);screen.recreate();assertTrue(DownloadService.busy);
            app.startService(new Intent(app,DownloadService.class).setAction("PAUSE"));waitFor(()->!DownloadService.busy);
            assertEquals("paused",store.list().stream().filter(j->j.id.equals(ids.get(0))).findFirst().get().state);
            store.resumePending();if(Build.VERSION.SDK_INT>=26)app.startForegroundService(resume);else app.startService(resume);
            waitFor(()->!DownloadService.busy&&store.list().stream().filter(j->ids.contains(j.id)&&j.state.equals("complete")).count()==2);
            assertEquals(3,attempts.get());assertTrue(DownloadService.status.startsWith("Saved:"));
        }finally{
            DownloadService.engineOverride=null;
            for(JobStore.Job job:store.list())if(ids.contains(job.id)){if("complete".equals(job.state))store.deleteCompleted(job.id,DownloadService.folder(app));store.getWritableDatabase().delete("jobs","id=?",new String[]{job.id});}
            store.close();
        }
    }
}
