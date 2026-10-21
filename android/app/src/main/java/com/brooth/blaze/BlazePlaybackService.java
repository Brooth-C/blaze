package com.brooth.blaze;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import androidx.media3.common.AudioAttributes;
import androidx.media3.common.C;
import androidx.media3.common.ForwardingPlayer;
import androidx.media3.common.Player;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.session.DefaultMediaNotificationProvider;
import androidx.media3.session.MediaSession;
import androidx.media3.session.MediaSessionService;

/** The media session keeps listening independent of a visible screen. */
@androidx.annotation.OptIn(markerClass = androidx.media3.common.util.UnstableApi.class)
public final class BlazePlaybackService extends MediaSessionService {
    static final String ACTION_OPEN = "com.brooth.blaze.PLAY";
    private static final String CHANNEL = "blaze-listening";
    private static final int NOTIFICATION = 7301;
    private ExoPlayer player;
    private MediaSession session;
    private PlaybackController controller;

    @Override public void onCreate() {
        super.onCreate();
        controller = PlaybackController.get(this);
        if (Build.VERSION.SDK_INT >= 26) getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel(CHANNEL, "Blaze playback", NotificationManager.IMPORTANCE_LOW));
        setMediaNotificationProvider(new DefaultMediaNotificationProvider.Builder(this)
            .setNotificationId(NOTIFICATION).setChannelId(CHANNEL).build());
        player = new ExoPlayer.Builder(this).build();
        player.setAudioAttributes(new AudioAttributes.Builder().setUsage(C.USAGE_MEDIA)
            .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), true);
        player.setHandleAudioBecomingNoisy(true);
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, NowPlayingActivity.class),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        session = new MediaSession.Builder(this, new QueueSessionPlayer(player, controller))
            .setSessionActivity(open)
            .setCallback(new MediaSession.Callback() {
                @Override public MediaSession.ConnectionResult onConnect(MediaSession mediaSession, MediaSession.ControllerInfo info) {
                    if (info.getUid() != android.os.Process.myUid() && !info.isTrusted()) return MediaSession.ConnectionResult.reject();
                    return MediaSession.Callback.super.onConnect(mediaSession, info);
                }
            }).build();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        super.onStartCommand(intent, flags, startId);
        DiscoveryItem current = controller.current();
        if (current == null) { stopSelf(); return START_NOT_STICKY; }
        // Enter foreground before potentially slow resolution, not after the first byte.
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        builder.setSmallIcon(android.R.drawable.ic_media_play).setContentTitle(current.title)
            .setContentText("Opening in Blaze…").setOnlyAlertOnce(true).setOngoing(true)
            .setContentIntent(PendingIntent.getActivity(this, 0, new Intent(this, NowPlayingActivity.class),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        startForeground(NOTIFICATION, builder.build());
        controller.attach(player, this);
        return START_NOT_STICKY;
    }

    @Override public MediaSession onGetSession(MediaSession.ControllerInfo controllerInfo) { return session; }
    void playbackFailed() { stopForeground(STOP_FOREGROUND_REMOVE); }

    @Override public void onTaskRemoved(Intent intent) {
        if (controller == null || (!controller.isPlaying() && !controller.isLoading())) stopSelf();
        else super.onTaskRemoved(intent);
    }

    @Override public void onDestroy() {
        if (controller != null && player != null) controller.detach(player);
        if (session != null) { session.release(); session = null; }
        if (player != null) { player.release(); player = null; }
        super.onDestroy();
    }

    /** Expose our application queue to lock-screen/headset skip controls. */
    private static final class QueueSessionPlayer extends ForwardingPlayer {
        private final PlaybackController controller;
        QueueSessionPlayer(Player player, PlaybackController controller) { super(player); this.controller = controller; }
        @Override public void seekToNext() { controller.next(); }
        @Override public void seekToNextMediaItem() { controller.next(); }
        @Override public void seekToPrevious() { controller.previous(); }
        @Override public void seekToPreviousMediaItem() { controller.previous(); }
        @Override public boolean hasNextMediaItem() { return controller.upNext() != null; }
        @Override public boolean hasPreviousMediaItem() { return !controller.queue().isEmpty(); }
        @Override public int getNextMediaItemIndex() { return hasNextMediaItem() ? 0 : C.INDEX_UNSET; }
        @Override public int getPreviousMediaItemIndex() { return hasPreviousMediaItem() ? 0 : C.INDEX_UNSET; }
        @Override public Player.Commands getAvailableCommands() {
            return super.getAvailableCommands().buildUpon()
                .add(Player.COMMAND_SEEK_TO_NEXT).add(Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM)
                .add(Player.COMMAND_SEEK_TO_PREVIOUS).add(Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM).build();
        }
    }
}
