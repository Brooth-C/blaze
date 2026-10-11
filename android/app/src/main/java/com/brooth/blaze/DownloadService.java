package com.brooth.blaze;

import android.app.*;
import android.content.Intent;
import android.os.*;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import java.io.File;

public class DownloadService extends Service {
    public static volatile boolean busy = false;
    public static volatile String status = "Ready for your next download";
    public static volatile float progress = 0;
    private volatile boolean cancelled;
    private Thread worker;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private static final String CHANNEL = "downloads";

    public static File folder(android.content.Context context) {
        File external = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        return external != null ? external : new File(context.getFilesDir(), "downloads");
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) { stopSelf(); return START_NOT_STICKY; }
        if ("STOP".equals(intent.getAction())) {
            cancelled = true;
            status = "Stopping…";
            return START_NOT_STICKY;
        }
        if (busy) return START_NOT_STICKY;
        busy = true;
        cancelled = false;
        progress = -1;
        status = "Preparing download…";
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26) manager.createNotificationChannel(
            new NotificationChannel(CHANNEL, "Downloads", NotificationManager.IMPORTANCE_LOW));
        startForeground(1, notification());
        String url = intent.getStringExtra("url");
        String mode = intent.getStringExtra("mode");
        worker = new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                String result = Python.getInstance().getModule("blaze_mobile")
                    .callAttr("download", url, mode, folder(this).getAbsolutePath(), this).toString();
                JSONObject saved = new JSONObject(result);
                status = "Saved: " + saved.getString("title");
                progress = 100;
            } catch (Exception error) {
                status = cancelled ? "Stopped. Retry the same link to resume." :
                    "Download failed: " + safeError(error);
            } finally {
                busy = false;
                handler.post(() -> { stopForeground(STOP_FOREGROUND_REMOVE); stopSelf(); });
            }
        }, "BlazeDownload");
        worker.start();
        return START_NOT_STICKY;
    }

    private String safeError(Exception error) {
        String message = error.getMessage();
        if (message == null) return "Check the link and your internet connection.";
        message = message.replaceAll("https?://\\S+", "[link]");
        return message.substring(0, Math.min(400, message.length()));
    }

    public boolean isCancelled() { return cancelled; }
    public void onProgress(float percent, String message) {
        progress = percent;
        status = message;
    }

    private Notification notification() {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent content = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, DownloadService.class).setAction("STOP");
        PendingIntent cancel = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26 ?
            new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        return builder.setContentTitle("Blaze is downloading").setContentText("Open Blaze for progress")
            .setSmallIcon(com.brooth.blaze.R.drawable.ic_notification).setContentIntent(content)
            .setOngoing(true).addAction(0, "Stop", cancel).build();
    }

    @Override public void onTimeout(int startId, int fgsType) {
        cancelled = true;
        if (worker != null) worker.interrupt();
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }
    @Override public void onDestroy() { cancelled = true; super.onDestroy(); }
}
