package com.brooth.blaze;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.*;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import org.json.*;
import java.io.File;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

public class DownloadService extends Service {
    public static volatile boolean busy;
    public static volatile String status="Ready for your next download", activeId="";
    public static volatile float progress=-1;
    private static final AtomicBoolean WORKER=new AtomicBoolean();
    private static volatile DownloadService live;
    private volatile boolean paused, cancelled, destroyed, pauseCancellation;
    private volatile String token="";
    private JobStore store;
    private Thread worker;
    private PowerManager.WakeLock wakeLock;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private static final String CHANNEL="downloads";
    private long lastUpdate;
    private int latestStartId;

    // Tests substitute an engine to exercise Android lifecycle/queue behavior offline.
    interface Engine { String run(JobStore.Job job,File directory,DownloadService callback) throws Exception; }
    static volatile Engine engineOverride;

    public static File folder(Context context) {
        File external=context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        return external!=null?external:new File(context.getFilesDir(),"downloads");
    }
    @Override public void onCreate() {
        super.onCreate();live=this;store=new JobStore(this);
        if(!WORKER.get())store.recoverInterrupted();
        if(Build.VERSION.SDK_INT>=26)getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel(CHANNEL,"Download progress",NotificationManager.IMPORTANCE_LOW));
    }
    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public int onStartCommand(Intent intent,int flags,int startId) {
        if(startId>0)latestStartId=startId;
        if(intent==null) { stopSelf();return START_NOT_STICKY; }
        String action=intent.getAction();
        if("PAUSE".equals(action)||"CANCEL_CURRENT".equals(action)) {
            if("PAUSE".equals(action)){paused=true;pauseCancellation=true;getSharedPreferences("queue",MODE_PRIVATE).edit().putBoolean("paused",true).apply();}
            cancelActive();
            if(!WORKER.get()) { status="Queue paused. Tap Resume queue.";stopSelf(); }
            return START_NOT_STICKY;
        }
        paused=false;getSharedPreferences("queue",MODE_PRIVATE).edit().putBoolean("paused",false).apply();
        // Foreground setup happens on every start, even while another request is finishing.
        try { foreground(false); }
        catch(RuntimeException error) { status="Android could not start background downloading. Open Blaze and tap Resume queue.";stopSelf();return START_NOT_STICKY; }
        if(!WORKER.compareAndSet(false,true))return START_NOT_STICKY;
        busy=true;destroyed=false;
        PowerManager power=(PowerManager)getSystemService(POWER_SERVICE);
        wakeLock=power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"Blaze:downloads");
        wakeLock.acquire(6*60*60*1000L);
        worker=new Thread(this::runQueue,"BlazeQueue");worker.start();
        return START_NOT_STICKY;
    }
    private void runQueue() {
        try {
            while(!paused&&!destroyed) {
                JobStore.Job job=store.claimNext();if(job==null)break;
                activeId=job.id;token=UUID.randomUUID().toString();cancelled=false;pauseCancellation=false;progress=-1;status="Preparing: "+job.title;
                handler.post(()->updateForeground(false));
                try {
                    File directory=new File(folder(this),job.id);
                    if(!directory.isDirectory()&&!directory.mkdirs())throw new java.io.IOException("Storage is unavailable or full.");
                    String output;
                    Engine override=engineOverride;
                    if(override!=null)output=override.run(job,directory,this);
                    else {
                        if(!Python.isStarted())Python.start(new AndroidPlatform(getApplicationContext()));
                        File lib=new File(getApplicationInfo().nativeLibraryDir);
                        output=Python.getInstance().getModule("blaze_mobile").callAttr("download",job.url,job.mode,directory.getAbsolutePath(),this,job.options,new File(lib,"libblaze_ffmpeg.so").getAbsolutePath(),new File(lib,"libblaze_qjs.so").getAbsolutePath(),token).toString();
                    }
                    JSONObject result=new JSONObject(output);
                    if(cancelled||destroyed)throw new InterruptedException("Stopped");
                    if(result.has("playlist_entries")) {
                        job.title=result.optString("title",job.title);
                        int count=store.expandPlaylist(job,result.getJSONArray("playlist_entries"));status="Queued "+count+" playlist items";
                    } else {
                        File file=new File(result.getString("path")).getCanonicalFile();
                        if(!file.getCanonicalPath().startsWith(directory.getCanonicalPath()+File.separator)||!file.isFile()||file.length()==0)throw new java.io.IOException("No complete output file");
                        String title=result.optString("title",job.title);
                        store.finish(job.id,"complete",title,file.getAbsolutePath(),"");status="Saved: "+title;progress=100;
                    }
                } catch(Exception error) {
                    boolean stopped=cancelled||destroyed||paused;
                    String detail=stopped?"Stopped. Retry this item to resume supported partial files.":safeError(error);
                    String terminal=destroyed?"interrupted":pauseCancellation?"paused":cancelled?"stopped":"failed";
                    store.finish(job.id,terminal,job.title,"",detail);status=detail;
                    if(pauseCancellation&&!paused&&!destroyed)store.resumePending();
                } finally { activeId="";token=""; }
            }
        } finally {
            handler.post(()->{
                busy=false;WORKER.set(false);
                if(wakeLock!=null&&wakeLock.isHeld())wakeLock.release();
                // An enqueue arriving between the last DB read and this callback must not be lost.
                if(live!=null&&live!=this&&!live.destroyed&&!live.paused&&live.store.hasQueued()) {
                    live.onStartCommand(new Intent(live,DownloadService.class).setAction("RESUME"),0,0);
                    store.close();
                } else if(!paused&&!destroyed&&store.hasQueued()) {
                    onStartCommand(new Intent(this,DownloadService.class).setAction("RESUME"),0,0);
                } else {
                    if(paused)status="Queue paused. Tap Resume queue.";
                    stopForeground(STOP_FOREGROUND_REMOVE);stopSelf(latestStartId);if(destroyed)store.close();
                }
            });
        }
    }
    private void cancelActive() {
        cancelled=true;if(!activeId.isEmpty())status="Stopping…";String captured=token;
        if(!captured.isEmpty())new Thread(()->{
            try { if(Python.isStarted())Python.getInstance().getModule("blaze_mobile").callAttr("cancel",captured); }
            catch(Exception ignored) { /* Progress/network boundaries also check the flag. */ }
        },"BlazeCancel").start();
    }
    public boolean isCancelled() { return cancelled||paused||destroyed; }
    public void onProgress(float percent,String message) {
        if(isCancelled())return;
        progress=percent;status=message;
        long now=System.currentTimeMillis();
        if(now-lastUpdate>=500) { lastUpdate=now;String id=activeId;store.progress(id,percent,null);handler.post(()->{ if(!destroyed)updateForeground(message.contains("merging")||message.contains("Converting")); }); }
    }
    private void updateForeground(boolean processing) {try{if(!destroyed)foreground(processing);}catch(RuntimeException error){paused=true;pauseCancellation=true;getSharedPreferences("queue",MODE_PRIVATE).edit().putBoolean("paused",true).apply();cancelActive();status="Android paused background processing. Resume the queue from Blaze.";}}
    private String safeError(Exception error) {
        String message=error.getMessage();if(message==null)return "Download failed. Check your link, storage and connection.";
        message=message.replaceAll("https?://\\S+","[link]").replaceAll("[\\p{Cntrl}&&[^\\n]]","");
        return message.substring(0,Math.min(400,message.length()));
    }
    private void foreground(boolean processing) {
        Notification notification=notification();
        if(Build.VERSION.SDK_INT>=35)startForeground(1,notification,processing?ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROCESSING:ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else if(Build.VERSION.SDK_INT>=29)startForeground(1,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else startForeground(1,notification);
    }
    private Notification notification() {
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent pause=PendingIntent.getService(this,1,new Intent(this,DownloadService.class).setAction("PAUSE"),PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,CHANNEL):new Notification.Builder(this);
        builder.setContentTitle("Blaze downloads").setContentText(status).setSmallIcon(R.drawable.ic_notification).setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true).addAction(0,"Pause queue",pause);
        if(progress>=0)builder.setProgress(100,(int)progress,false);else builder.setProgress(100,0,true);
        return builder.build();
    }
    @Override public void onTimeout(int startId,int type) { paused=true;pauseCancellation=true;getSharedPreferences("queue",MODE_PRIVATE).edit().putBoolean("paused",true).apply();cancelActive();stopForeground(STOP_FOREGROUND_REMOVE);stopSelf(); }
    @Override public void onDestroy() { destroyed=true;paused=true;cancelActive();if(live==this)live=null;if(wakeLock!=null&&wakeLock.isHeld())wakeLock.release();if(!WORKER.get())store.close();super.onDestroy(); }
}
