package com.brooth.blaze;

import android.content.Context;
import java.io.File;
import java.io.IOException;
import java.util.UUID;

/** Resolves a completed download without accepting arbitrary paths or URLs. */
final class PlaybackSource {
    final String id, title, mode;
    final File file;

    private PlaybackSource(JobStore.Job job, File file) {
        id=job.id;title=job.title;mode=job.mode;this.file=file;
    }

    static PlaybackSource load(Context context, String id) throws IOException {
        try {
            if(id==null||!UUID.fromString(id).toString().equals(id))throw new IllegalArgumentException();
        } catch(IllegalArgumentException error) {
            throw new IOException("This download is unavailable.");
        }
        JobStore.Job job;
        try(JobStore store=new JobStore(context)) {job=store.completed(id);}
        if(job==null||job.path.isEmpty())throw new IOException("Choose a completed download from Files.");
        File root=DownloadService.folder(context).getCanonicalFile();
        File file=new File(job.path).getCanonicalFile();
        if(!file.getPath().startsWith(root.getPath()+File.separator)||!file.isFile()||file.length()==0)
            throw new IOException("The saved file is missing or unavailable.");
        return new PlaybackSource(job,file);
    }
}
