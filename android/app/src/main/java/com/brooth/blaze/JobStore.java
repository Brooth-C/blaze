package com.brooth.blaze;

import android.content.*;
import android.database.Cursor;
import android.database.sqlite.*;
import org.json.*;
import java.io.File;
import java.util.*;

/** Internal, durable queue. Updates are conditional on the current job state. */
public final class JobStore extends SQLiteOpenHelper {
    public static final class Job {
        public String id, url, mode, options, state, title, path, error;
        public long created, updated;
        public float progress;
    }
    public JobStore(Context context) { this(context,"blaze-jobs.db"); }
    JobStore(Context context,String name) { super(context.getApplicationContext(),name,null,1); }
    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE jobs (id TEXT PRIMARY KEY, url TEXT NOT NULL, mode TEXT NOT NULL, options TEXT NOT NULL, state TEXT NOT NULL, title TEXT NOT NULL, path TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '', progress REAL NOT NULL DEFAULT -1, created INTEGER NOT NULL, updated INTEGER NOT NULL)");
        db.execSQL("CREATE INDEX queue_order ON jobs(state,created)");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int oldVersion,int newVersion) { throw new IllegalStateException("Unsupported queue migration"); }
    public synchronized void recoverInterrupted() {
        ContentValues v=new ContentValues();v.put("state","interrupted");v.put("error","Android stopped the previous download. Tap Retry to resume.");
        getWritableDatabase().update("jobs",v,"state='running'",null);
    }
    public synchronized String enqueue(String url,String mode,String options,String title) {
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try {
            if(countPending(db)>=200)throw new IllegalStateException("Queue limit: 200 items. Finish or remove queued items first.");
            try(Cursor c=db.query("jobs",new String[]{"id"},"url=? AND mode=? AND options=? AND state IN ('queued','running')",new String[]{url,mode,options},null,null,null,"1")) {
                if(c.moveToFirst()) { db.setTransactionSuccessful();return c.getString(0); }
            }
            String id=UUID.randomUUID().toString();ContentValues v=new ContentValues();
            v.put("id",id);v.put("url",url);v.put("mode",mode);v.put("options",options);v.put("state","queued");v.put("title",title);
            long now=System.currentTimeMillis();v.put("created",now);v.put("updated",now);db.insertOrThrow("jobs",null,v);
            db.setTransactionSuccessful();return id;
        } finally { db.endTransaction(); }
    }
    private int countPending(SQLiteDatabase db) { try(Cursor c=db.rawQuery("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running','paused','interrupted')",null)) { c.moveToFirst();return c.getInt(0); } }
    public synchronized Job claimNext() {
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try(Cursor c=db.query("jobs",null,"state='queued'",null,null,null,"created ASC,rowid ASC","1")) {
            if(!c.moveToFirst())return null;
            Job job=read(c);ContentValues v=new ContentValues();v.put("state","running");v.put("error","");v.put("progress",-1);v.put("updated",System.currentTimeMillis());
            db.update("jobs",v,"id=? AND state='queued'",new String[]{job.id});db.setTransactionSuccessful();job.state="running";return job;
        } finally { db.endTransaction(); }
    }
    public synchronized void progress(String id,float value,String title) {
        ContentValues v=new ContentValues();v.put("progress",value);v.put("updated",System.currentTimeMillis());
        if(title!=null&&!title.isEmpty())v.put("title",title);
        getWritableDatabase().update("jobs",v,"id=? AND state='running'",new String[]{id});
    }
    public synchronized void finish(String id,String state,String title,String path,String error) {
        ContentValues v=new ContentValues();v.put("state",state);v.put("title",title);v.put("path",path);v.put("error",error);v.put("updated",System.currentTimeMillis());v.put("progress","complete".equals(state)?100:-1);
        getWritableDatabase().update("jobs",v,"id=? AND state='running'",new String[]{id});
    }
    public synchronized int expandPlaylist(Job parent,JSONArray entries) throws JSONException {
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();
        try {
            if(countPending(db)-1+entries.length()>200)throw new IllegalStateException("Playlist would exceed the queue's 200-item limit.");
            JSONObject opts=new JSONObject(parent.options);opts.put("playlist",false);
            for(int i=0;i<entries.length();i++) {
                JSONObject e=entries.getJSONObject(i);enqueue(e.getString("url"),parent.mode,opts.toString(),e.optString("title","Playlist item"));
            }
            finish(parent.id,"expanded",parent.title,"","Queued "+entries.length()+" playlist items");
            db.setTransactionSuccessful();return entries.length();
        } finally { db.endTransaction(); }
    }
    public synchronized void retry(String id) {
        if(countPending(getReadableDatabase())>=200)throw new IllegalStateException("Queue limit: 200 items.");
        ContentValues v=new ContentValues();v.put("state","queued");v.put("error","");v.put("progress",-1);v.put("updated",System.currentTimeMillis());
        getWritableDatabase().update("jobs",v,"id=? AND state IN ('failed','stopped','interrupted')",new String[]{id});
    }
    public synchronized void resumePending() {ContentValues v=new ContentValues();v.put("state","queued");getWritableDatabase().update("jobs",v,"state IN ('paused','interrupted')",null);}
    public synchronized void removeQueued(String id) { getWritableDatabase().delete("jobs","id=? AND state IN ('queued','paused','interrupted')",new String[]{id}); }
    public synchronized List<Job> list() {
        List<Job> out=new ArrayList<>();try(Cursor c=getReadableDatabase().query("jobs",null,null,null,null,null,"CASE state WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,CASE WHEN state IN ('queued','running') THEN created ELSE -updated END ASC,rowid ASC","250")) { while(c.moveToNext())out.add(read(c)); }return out;
    }
    private String filterWhere(int filter){return filter==2?"state='complete'":filter==1?"state NOT IN ('queued','running','paused','interrupted')":"state IN ('queued','running','paused','interrupted')";}
    public synchronized int count(int filter){try(Cursor c=getReadableDatabase().rawQuery("SELECT COUNT(*) FROM jobs WHERE "+filterWhere(filter),null)){c.moveToFirst();return c.getInt(0);}}
    public synchronized List<Job> page(int filter,int offset){List<Job> out=new ArrayList<>();String order=filter==0?"CASE state WHEN 'running' THEN 0 ELSE 1 END,created ASC,rowid ASC":"updated DESC,rowid DESC";try(Cursor c=getReadableDatabase().query("jobs",null,filterWhere(filter),null,null,null,order,Math.max(0,offset)+",50")){while(c.moveToNext())out.add(read(c));}return out;}
    public synchronized void importLegacyFiles(File root)throws java.io.IOException{
        File canonical=root.getCanonicalFile();File[] files=canonical.listFiles(File::isFile);if(files==null)return;
        SQLiteDatabase db=getWritableDatabase();db.beginTransaction();try{
            for(File file:files){File resolved=file.getCanonicalFile();String name=file.getName();int dot=name.lastIndexOf('.');if(dot<0||file.length()==0||!resolved.getParentFile().equals(canonical))continue;String ext=name.substring(dot+1).toLowerCase(Locale.ROOT);if(!Arrays.asList("mp4","mkv","webm","mp3","m4a","aac","wav","flac","ogg","opus").contains(ext))continue;
                try(Cursor c=db.query("jobs",new String[]{"id"},"path=?",new String[]{resolved.getAbsolutePath()},null,null,null,"1")){if(c.moveToFirst())continue;}
                ContentValues v=new ContentValues();v.put("id",UUID.randomUUID().toString());v.put("url","");v.put("mode",Arrays.asList("mp4","mkv","webm").contains(ext)?"video":"audio");v.put("options","{}");v.put("state","complete");v.put("title",name);v.put("path",resolved.getAbsolutePath());v.put("progress",100);v.put("created",file.lastModified());v.put("updated",file.lastModified());db.insertOrThrow("jobs",null,v);
            }db.setTransactionSuccessful();
        }finally{db.endTransaction();}
    }
    public synchronized boolean hasQueued() { try(Cursor c=getReadableDatabase().rawQuery("SELECT 1 FROM jobs WHERE state='queued' LIMIT 1",null)) { return c.moveToFirst(); } }
    public synchronized boolean deleteCompleted(String id,File root) throws java.io.IOException {
        try(Cursor c=getReadableDatabase().query("jobs",null,"id=? AND state='complete'",new String[]{id},null,null,null,"1")) {
            if(!c.moveToFirst())return false;Job job=read(c);File file=new File(job.path).getCanonicalFile();
            if(!file.getCanonicalPath().startsWith(root.getCanonicalPath()+File.separator))throw new java.io.IOException("Invalid saved-file path");
            if(file.exists()&&!file.delete())throw new java.io.IOException("Could not delete the file");
            getWritableDatabase().delete("jobs","id=? AND state='complete'",new String[]{id});return true;
        }
    }
    private Job read(Cursor c) {
        Job j=new Job();j.id=c.getString(c.getColumnIndexOrThrow("id"));j.url=c.getString(c.getColumnIndexOrThrow("url"));j.mode=c.getString(c.getColumnIndexOrThrow("mode"));j.options=c.getString(c.getColumnIndexOrThrow("options"));j.state=c.getString(c.getColumnIndexOrThrow("state"));j.title=c.getString(c.getColumnIndexOrThrow("title"));j.path=c.getString(c.getColumnIndexOrThrow("path"));j.error=c.getString(c.getColumnIndexOrThrow("error"));j.progress=c.getFloat(c.getColumnIndexOrThrow("progress"));j.created=c.getLong(c.getColumnIndexOrThrow("created"));j.updated=c.getLong(c.getColumnIndexOrThrow("updated"));return j;
    }
}
