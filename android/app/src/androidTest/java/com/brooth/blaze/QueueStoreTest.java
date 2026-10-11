package com.brooth.blaze;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.*;
import org.junit.*;
import org.junit.runner.RunWith;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class QueueStoreTest {
    private Context context;
    private String database;
    private JobStore store;
    @Before public void setup(){context=InstrumentationRegistry.getInstrumentation().getTargetContext();database="queue-test-"+UUID.randomUUID()+".db";store=new JobStore(context,database);}
    @After public void cleanup(){store.close();context.deleteDatabase(database);}
    @Test public void durableDedupeAndTerminalStateProtection(){
        String id=store.enqueue("https://example.test/item","video","{}","Item");
        assertEquals(id,store.enqueue("https://example.test/item","video","{}","Item"));
        store.close();store=new JobStore(context,database);
        assertEquals(id,store.claimNext().id);assertNull(store.claimNext());
        store.finish(id,"complete","Item","saved.mp4","");store.progress(id,1,"Stale callback");store.recoverInterrupted();
        assertEquals("complete",store.list().get(0).state);assertEquals("Item",store.list().get(0).title);assertEquals(100,store.list().get(0).progress,0);
    }
    @Test public void interruptedAndPausedItemsResumeWithSameIdentity(){
        String id=store.enqueue("https://example.test/item","video","{}","Item");store.claimNext();store.close();store=new JobStore(context,database);store.recoverInterrupted();
        assertEquals("interrupted",store.list().get(0).state);store.resumePending();assertEquals(id,store.claimNext().id);
        store.finish(id,"paused","Item","","");store.resumePending();assertEquals(id,store.claimNext().id);
    }
    @Test public void playlistOverflowIsAtomic()throws Exception{
        String id=store.enqueue("https://example.test/playlist","audio","{\"playlist\":true}","Playlist");JobStore.Job parent=store.claimNext();assertEquals(id,parent.id);
        for(int i=0;i<199;i++)store.enqueue("https://example.test/"+i,"audio","{}","Item "+i);
        JSONArray entries=new JSONArray().put(new JSONObject().put("url","https://example.test/new1")).put(new JSONObject().put("url","https://example.test/new2"));
        try{store.expandPlaylist(parent,entries);fail("Overflow accepted");}catch(IllegalStateException expected){assertTrue(expected.getMessage().contains("limit"));}
        assertEquals(200,store.list().size());assertEquals("running",store.list().stream().filter(j->j.id.equals(id)).findFirst().get().state);
    }
    @Test public void independentConnectionsCannotClaimSameJob()throws Exception{
        store.enqueue("https://example.test/one","video","{}","One");store.enqueue("https://example.test/two","video","{}","Two");
        JobStore other=new JobStore(context,database);ExecutorService pool=Executors.newFixedThreadPool(2);
        try{Future<JobStore.Job>a=pool.submit(()->store.claimNext());Future<JobStore.Job>b=pool.submit(()->other.claimNext());assertNotEquals(a.get(5,TimeUnit.SECONDS).id,b.get(5,TimeUnit.SECONDS).id);}finally{pool.shutdownNow();other.close();}
    }
    @Test public void exportAdmissionSurvivesWrongOwnerCleanup(){
        String token=ExportService.reserve();assertFalse(token.isEmpty());assertEquals("",ExportService.reserve());ExportService.abandon("wrong-owner");assertTrue(ExportService.owns(token));ExportService.abandon(token);assertFalse(ExportService.owns(token));
    }
    @Test public void olderSavedFilesRemainAccessibleAcrossPages(){
        for(int i=0;i<120;i++){String id=store.enqueue("https://example.test/file/"+i,"video","{}","File "+i);assertEquals(id,store.claimNext().id);store.finish(id,"complete","File "+i,"/saved/"+i+".mp4","");}
        assertEquals(120,store.count(2));assertEquals(50,store.page(2,0).size());assertEquals(50,store.page(2,50).size());assertEquals(20,store.page(2,100).size());
        Set<String> ids=new HashSet<>();for(int page=0;page<3;page++)for(JobStore.Job job:store.page(2,page*50))assertTrue(ids.add(job.id));assertEquals(120,ids.size());
    }
}
