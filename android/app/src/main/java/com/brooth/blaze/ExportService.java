package com.brooth.blaze;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.*;
import android.provider.DocumentsContract;
import android.widget.Toast;
import java.io.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.UUID;

/** Copies only a completed app file to a document explicitly chosen by the user. */
public class ExportService extends Service {
    private static final AtomicBoolean COPYING=new AtomicBoolean();
    private static volatile String reservation="";
    private Thread worker;
    private String owner="";
    private volatile boolean stopped;
    public static synchronized String reserve(){if(!COPYING.compareAndSet(false,true))return "";reservation=UUID.randomUUID().toString();return reservation;}
    public static synchronized void abandon(String token){if(token!=null&&token.equals(reservation)){reservation="";COPYING.set(false);}}
    public static synchronized boolean owns(String token){return token!=null&&!token.isEmpty()&&token.equals(reservation);}
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public int onStartCommand(Intent intent,int flags,int id){
        if(intent==null){stopSelf();return START_NOT_STICKY;}
        stopped=false;
        NotificationManager manager=getSystemService(NotificationManager.class);
        if(Build.VERSION.SDK_INT>=26)manager.createNotificationChannel(new NotificationChannel("exports","Saving copies",NotificationManager.IMPORTANCE_LOW));
        Notification.Builder builder=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,"exports"):new Notification.Builder(this);
        try{startForeground(2,builder.setContentTitle("Blaze is saving a copy").setSmallIcon(R.drawable.ic_notification).setOngoing(true).build());}
        catch(RuntimeException e){abandon(intent.getStringExtra("token"));toast("Android could not start the copy. Try again with Blaze open.");stopSelf();return START_NOT_STICKY;}
        String incoming=intent.getStringExtra("token");
        if(incoming==null||!incoming.equals(reservation)||worker!=null){if(worker==null){stopForeground(STOP_FOREGROUND_REMOVE);stopSelf(id);}return START_NOT_STICKY;}
        owner=incoming;
        String path=intent.getStringExtra("path"),destination=intent.getStringExtra("uri");
        worker=new Thread(()->{
            boolean success=false;Uri uri=null;
            try{
                if(path==null||destination==null)throw new IOException("Missing copy details");
                File source=new File(path).getCanonicalFile();
                if(!source.getCanonicalPath().startsWith(DownloadService.folder(this).getCanonicalPath()+File.separator)||!source.isFile())throw new IOException("Invalid source file");
                uri=Uri.parse(destination);if(!"content".equals(uri.getScheme()))throw new IOException("Invalid destination");
                try(InputStream in=new FileInputStream(source);OutputStream out=getContentResolver().openOutputStream(uri,"w")){
                    if(out==null)throw new IOException("Cannot open destination");byte[] buffer=new byte[65536];int count;
                    while((count=in.read(buffer))!=-1){if(stopped)throw new InterruptedIOException("Copy stopped");out.write(buffer,0,count);}out.flush();
                }
                success=true;toast("Copy saved");
            }catch(Exception e){toast("Copy failed. Try another folder; check for an incomplete copy.");}
            finally{
                if(!success&&uri!=null){try{DocumentsContract.deleteDocument(getContentResolver(),uri);}catch(Exception ignored){/* Provider may not support deletion. */}}
                new Handler(Looper.getMainLooper()).post(()->{abandon(owner);worker=null;stopForeground(STOP_FOREGROUND_REMOVE);stopSelf(id);});
            }
        },"BlazeExport");worker.start();
        return START_NOT_STICKY;
    }
    private void toast(String text){new Handler(Looper.getMainLooper()).post(()->Toast.makeText(getApplicationContext(),text,Toast.LENGTH_LONG).show());}
    @Override public void onTimeout(int id,int type){stopped=true;stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();}
    @Override public void onDestroy(){stopped=true;if(worker==null&&!owner.isEmpty())abandon(owner);super.onDestroy();}
}
