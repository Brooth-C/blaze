package com.brooth.blaze;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.media.MediaCodecList;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import androidx.media3.common.C;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MediaMetadata;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.datasource.DefaultDataSource;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;
import androidx.media3.exoplayer.source.MediaSource;
import androidx.media3.exoplayer.source.MergingMediaSource;
import org.json.JSONArray;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/** One application-owned listening session. Persist identities, never resolved stream URLs. */
@androidx.annotation.OptIn(markerClass = androidx.media3.common.util.UnstableApi.class)
public final class PlaybackController {
    public interface Listener { void onPlaybackChanged(); }
    private static PlaybackController instance;
    public static synchronized PlaybackController get(Context context) {
        if (instance == null) instance = new PlaybackController(context.getApplicationContext());
        return instance;
    }

    private final Context app;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final SharedPreferences preferences;
    private final Set<Listener> listeners = new LinkedHashSet<>();
    private final ArrayList<DiscoveryItem> queue = new ArrayList<>(), recent = new ArrayList<>();
    private ExoPlayer player;
    private BlazePlaybackService service;
    private DiscoveryItem current;
    private int index = -1, generation, preparedGeneration = -1;
    private boolean wantedPlayback, resolving, shuffle, repeat, refreshAttempted;
    private long rememberedPosition, lastCheckpoint;
    private String resolutionToken = "", failure = "";

    private PlaybackController(Context context) {
        app = context;
        preferences = app.getSharedPreferences("listening", Context.MODE_PRIVATE);
        shuffle = preferences.getBoolean("shuffle", false);
        repeat = preferences.getBoolean("repeat", false);
        try {
            JSONArray items = new JSONArray(preferences.getString("history", "[]"));
            for (int i = 0; i < Math.min(30, items.length()); i++) {
                DiscoveryItem item = DiscoveryItem.fromJson(items.getJSONObject(i).toString());
                if (!item.browsable()) recent.add(item);
            }
            String saved = preferences.getString("current", "");
            if (!saved.isEmpty()) {
                DiscoveryItem restored = DiscoveryItem.fromJson(saved);
                if (!restored.browsable()) {
                    current = restored; queue.add(restored); index = 0;
                    rememberedPosition = Math.max(0, preferences.getLong("position", 0));
                }
            }
        } catch (Exception ignored) { /* A malformed prior snapshot must not prevent app startup. */ }
    }

    private void onMain(Runnable action) {
        if (Looper.myLooper() == Looper.getMainLooper()) action.run(); else main.post(action);
    }
    public void addListener(Listener listener) { onMain(() -> { listeners.add(listener); listener.onPlaybackChanged(); startTicker(); }); }
    public void removeListener(Listener listener) { onMain(() -> { listeners.remove(listener); }); }
    public DiscoveryItem current() { return current; }
    public DiscoveryItem upNext() {
        if (queue.size() < 2 || index < 0) return null;
        return queue.get((index + 1) % queue.size());
    }
    public List<DiscoveryItem> queue() { return Collections.unmodifiableList(new ArrayList<>(queue)); }
    public List<DiscoveryItem> history() { return Collections.unmodifiableList(new ArrayList<>(recent)); }
    public boolean isPlaying() { return player != null && player.isPlaying(); }
    public boolean isLoading() { return resolving || (player != null && player.getPlaybackState() == Player.STATE_BUFFERING); }
    public boolean shuffle() { return shuffle; }
    public boolean repeat() { return repeat; }
    public String error() { return failure; }
    public Player player() { return player; }
    public long position() { return player != null && preparedGeneration == generation ? Math.max(0, player.getCurrentPosition()) : rememberedPosition; }
    public long duration() {
        long value = player == null ? C.TIME_UNSET : player.getDuration();
        return value >= 0 ? value : current == null ? 0 : Math.max(0, current.durationMs);
    }
    public boolean isFavorite(DiscoveryItem item) { return item != null && preferences.getStringSet("favourites", Collections.emptySet()).contains(item.key()); }
    public void toggleFavorite(DiscoveryItem item) {
        if (item == null) return;
        onMain(() -> {
            Set<String> values = new LinkedHashSet<>(preferences.getStringSet("favourites", Collections.emptySet()));
            if (!values.remove(item.key())) values.add(item.key());
            while (values.size() > 500) values.remove(values.iterator().next());
            preferences.edit().putStringSet("favourites", values).apply(); changed();
        });
    }

    public void play(DiscoveryItem item, List<DiscoveryItem> items) {
        if (item == null || item.browsable()) return;
        onMain(() -> {
            ArrayList<DiscoveryItem> accepted = new ArrayList<>();
            Set<String> keys = new LinkedHashSet<>();
            if (items != null) for (DiscoveryItem candidate : items) {
                if (candidate != null && !candidate.browsable() && keys.add(candidate.key())) accepted.add(candidate);
                if (accepted.size() == 100) break;
            }
            if (!keys.contains(item.key())) accepted.add(0, item);
            queue.clear(); queue.addAll(accepted);
            index = 0;
            for (int i = 0; i < queue.size(); i++) if (queue.get(i).key().equals(item.key())) { index = i; break; }
            begin(item, 0, true);
        });
    }

    private void begin(DiscoveryItem item, long position, boolean play) {
        cancelResolution(); generation++; preparedGeneration = -1;
        current = preferLocalCopy(item);
        if (index >= 0 && index < queue.size() && queue.get(index).key().equals(current.key())) queue.set(index, current);
        rememberedPosition = Math.max(0, position); wantedPlayback = play;
        resolving = true; refreshAttempted = false; failure = "";
        if (player != null) { player.pause(); player.stop(); player.clearMediaItems(); }
        // pause() above emits a state callback; preserve the user's new command.
        wantedPlayback = play;
        saveSnapshot(); changed(); startService();
    }

    /** Reuse a verified owned copy without persisting or reusing a signed stream URL. */
    private DiscoveryItem preferLocalCopy(DiscoveryItem selected) {
        if (!selected.localJobId.isEmpty() || selected.url.isEmpty()) return selected;
        try (JobStore store = new JobStore(app)) {
            String canonical = DownloadCoordinator.canonicalUrl(selected.url, false);
            try (Cursor copies = store.getReadableDatabase().query("jobs", new String[]{"id"},
                    "url=? AND mode=? AND state='complete'",
                    new String[]{canonical, selected.kind.equals("video") ? "video" : "audio"},
                    null, null, "updated DESC,rowid DESC", "10")) {
                while (copies.moveToNext()) {
                    String jobId = copies.getString(0);
                    try {
                        PlaybackSource local = PlaybackSource.load(app, jobId);
                        if (!supportsPlatformPlayback(local, selected.kind.equals("video"))) continue;
                        return new DiscoveryItem(selected.id, selected.kind, selected.title, selected.creator,
                            selected.url, selected.thumbnail, selected.durationMs, jobId);
                    } catch (java.io.IOException ignored) { /* A removed copy must not block fresh playback. */ }
                }
            }
        } catch (RuntimeException ignored) { /* An unavailable library must not block source resolution. */ }
        return selected;
    }

    /** Container names do not establish codec support: inspect every audio/video track. */
    static boolean supportsPlatformPlayback(PlaybackSource source, boolean requireVideo) {
        MediaExtractor extractor = new MediaExtractor();
        try (java.io.FileInputStream input = new java.io.FileInputStream(source.file)) {
            extractor.setDataSource(input.getFD());
            int count = extractor.getTrackCount();
            if (count < 1 || count > 64) return false;
            MediaCodecList codecs = new MediaCodecList(MediaCodecList.REGULAR_CODECS);
            boolean audiovisual = false, video = false;
            for (int track = 0; track < count; track++) {
                MediaFormat format = extractor.getTrackFormat(track);
                String mime = format.getString(MediaFormat.KEY_MIME);
                if (mime == null) return false;
                boolean isVideo = mime.startsWith("video/");
                if (!isVideo && !mime.startsWith("audio/")) continue;
                audiovisual = true; video |= isVideo;
                // Media3 plays uncompressed PCM without a MediaCodec decoder.
                if (!mime.equals("audio/raw") && codecs.findDecoderForFormat(format) == null) return false;
            }
            return audiovisual && (!requireVideo || video);
        } catch (java.io.IOException | RuntimeException unsupported) {
            // Includes containers unsupported by the platform extractor, even if VLC can open them.
            return false;
        } finally { extractor.release(); }
    }

    public void toggle() {
        onMain(() -> {
            if (current == null) return;
            if (isPlaying() || (resolving && wantedPlayback)) { pause(); return; }
            failure = ""; wantedPlayback = true;
            if (player != null && preparedGeneration == generation && player.getPlaybackState() == Player.STATE_ENDED) {
                rememberedPosition = 0; player.seekTo(0);
            }
            startService(); changed();
        });
    }
    public void pause() {
        onMain(() -> {
            wantedPlayback = false;
            if (player != null) player.pause();
            rememberedPosition = position(); saveSnapshot(); changed();
        });
    }
    public void stop() {
        onMain(() -> {
            wantedPlayback = false; cancelResolution(); generation++; preparedGeneration = -1;
            resolving = false; current = null; index = -1; queue.clear(); rememberedPosition = 0; failure = "";
            if (player != null) { player.pause(); player.stop(); player.clearMediaItems(); }
            preferences.edit().remove("current").remove("position").apply();
            if (service != null) service.stopSelf(); else app.stopService(new Intent(app, BlazePlaybackService.class));
            changed();
        });
    }
    public void next() { onMain(() -> advance(true)); }
    public void previous() {
        onMain(() -> {
            if (position() > 3000) { seekTo(0); return; }
            advance(false);
        });
    }
    private void advance(boolean forward) {
        if (queue.isEmpty()) return;
        if (shuffle && queue.size() > 1 && forward) {
            int step = 1 + new java.util.Random().nextInt(queue.size() - 1);
            index = (Math.max(0, index) + step) % queue.size();
        } else index = (Math.max(0, index) + (forward ? 1 : queue.size() - 1)) % queue.size();
        begin(queue.get(index), 0, true);
    }
    public void seekTo(long position) {
        onMain(() -> {
            long duration = duration();
            rememberedPosition = Math.max(0, duration > 0 ? Math.min(position, duration) : position);
            if (player != null && preparedGeneration == generation) player.seekTo(rememberedPosition);
            saveSnapshot(); changed();
        });
    }
    public void setShuffle(boolean enabled) { onMain(() -> { shuffle = enabled; preferences.edit().putBoolean("shuffle", enabled).apply(); changed(); }); }
    public void setRepeat(boolean enabled) { onMain(() -> { repeat = enabled; preferences.edit().putBoolean("repeat", enabled).apply(); changed(); }); }

    private void startService() {
        try {
            Intent intent = new Intent(app, BlazePlaybackService.class).setAction(BlazePlaybackService.ACTION_OPEN);
            if (android.os.Build.VERSION.SDK_INT >= 26) app.startForegroundService(intent); else app.startService(intent);
        } catch (RuntimeException error) {
            resolving = false; wantedPlayback = false; failure = "Android could not start playback. Open Blaze and try again."; changed();
        }
    }

    /** Called after the service has entered foreground, before preparing any audio. */
    void attach(ExoPlayer nextPlayer, BlazePlaybackService nextService) {
        if (player != nextPlayer) {
            if (player != null) player.removeListener(playerEvents);
            player = nextPlayer; player.addListener(playerEvents); preparedGeneration = -1;
        }
        service = nextService;
        if (current == null) return;
        if (preparedGeneration == generation) {
            player.setPlayWhenReady(wantedPlayback); changed(); return;
        }
        prepare();
    }

    private void prepare() {
        if (current == null || player == null || !resolutionToken.isEmpty()) return;
        final int request = generation;
        final DiscoveryItem selected = current;
        resolving = true; failure = ""; changed();
        if (!selected.localJobId.isEmpty()) {
            try {
                PlaybackSource local = PlaybackSource.load(app, selected.localJobId);
                configure(Uri.fromFile(local.file).toString(), "", Collections.emptyMap(), "", "", request);
            } catch (Exception error) { failed(request, "The saved file is missing. Choose another recording or save it again."); }
            return;
        }
        resolutionToken = DiscoveryRepository.get(app).resolve(selected, (stream, error) -> {
            if (request != generation || player == null || current == null || !current.key().equals(selected.key())) return;
            resolutionToken = "";
            if (stream == null || (error != null && !error.isEmpty())) { failed(request, error == null || error.isEmpty() ? "This recording could not be opened." : error); return; }
            configure(stream.url, stream.mimeType, stream.headers, stream.audioUrl, stream.audioMimeType, request);
        });
    }

    private void configure(String url, String mime, java.util.Map<String, String> headers, String audioUrl, String audioMime, int request) {
        if (request != generation || player == null || current == null) return;
        try {
            DefaultHttpDataSource.Factory http = new DefaultHttpDataSource.Factory()
                .setUserAgent("Blaze Android")
                .setConnectTimeoutMs(10000).setReadTimeoutMs(10000)
                .setAllowCrossProtocolRedirects(false)
                .setDefaultRequestProperties(headers == null ? Collections.emptyMap() : headers);
            DefaultMediaSourceFactory sources = new DefaultMediaSourceFactory(new DefaultDataSource.Factory(app, http));
            MediaMetadata metadata = new MediaMetadata.Builder().setTitle(current.title).setArtist(current.creator).build();
            MediaItem.Builder item = new MediaItem.Builder().setMediaId(current.key()).setUri(url).setMediaMetadata(metadata);
            if (mime != null && !mime.isEmpty()) item.setMimeType(mime);
            MediaSource source = sources.createMediaSource(item.build());
            if (audioUrl != null && !audioUrl.isEmpty()) {
                MediaItem.Builder audio = new MediaItem.Builder().setUri(audioUrl);
                if (audioMime != null && !audioMime.isEmpty()) audio.setMimeType(audioMime);
                source = new MergingMediaSource(true, source, sources.createMediaSource(audio.build()));
            }
            preparedGeneration = request; resolving = false;
            player.setMediaSource(source, rememberedPosition);
            player.prepare(); player.setPlayWhenReady(wantedPlayback); changed();
        } catch (RuntimeException error) { failed(request, "This recording's media format could not be opened."); }
    }

    private void failed(int request, String message) {
        if (request != generation) return;
        resolving = false; wantedPlayback = false; failure = message; preparedGeneration = -1;
        if (player != null) player.pause();
        changed();
        if (service != null) service.playbackFailed();
    }
    private void cancelResolution() {
        if (!resolutionToken.isEmpty()) DiscoveryRepository.get(app).cancel(resolutionToken);
        resolutionToken = "";
    }
    void detach(ExoPlayer oldPlayer) {
        if (player != oldPlayer) return;
        rememberedPosition = position(); cancelResolution(); generation++; preparedGeneration = -1;
        resolving = false; player.removeListener(playerEvents); player = null; service = null;
        saveSnapshot(); changed();
    }
    boolean wantsPlayback() { return wantedPlayback; }

    private final Player.Listener playerEvents = new Player.Listener() {
        @Override public void onIsPlayingChanged(boolean playing) { if (playing) rememberPlayed(); changed(); }
        @Override public void onPlayWhenReadyChanged(boolean playWhenReady, int reason) {
            if (preparedGeneration == generation) wantedPlayback = playWhenReady;
            changed();
        }
        @Override public void onPlaybackStateChanged(int state) {
            if (state == Player.STATE_ENDED && current != null) {
                if (repeat) { seekTo(0); wantedPlayback = true; if (player != null) player.play(); }
                else if (index + 1 < queue.size() || (shuffle && queue.size() > 1)) advance(true);
                else { wantedPlayback = false; saveSnapshot(); }
            }
            changed();
        }
        @Override public void onPlayerError(PlaybackException error) {
            // A selected remote representation may expire. Resolve once, retaining time.
            if (current != null && current.localJobId.isEmpty() && !refreshAttempted && expiredResponse(error)) {
                refreshAttempted = true; rememberedPosition = position();
                preparedGeneration = -1; cancelResolution(); resolving = true; prepare();
            } else failed(generation, current != null && !current.localJobId.isEmpty()
                ? "Use the file player for this recording."
                : "Playback was interrupted. Check your connection or try saving this recording.");
        }
        @Override public void onEvents(Player value, Player.Events events) { changed(); }
    };

    private static boolean expiredResponse(Throwable failure) {
        for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
            if (cause instanceof androidx.media3.datasource.HttpDataSource.InvalidResponseCodeException) {
                int status = ((androidx.media3.datasource.HttpDataSource.InvalidResponseCodeException) cause).responseCode;
                return status == 403 || status == 410;
            }
        }
        return false;
    }

    private void rememberPlayed() {
        if (current == null) return;
        recent.removeIf(item -> item.key().equals(current.key())); recent.add(0, current);
        while (recent.size() > 30) recent.remove(recent.size() - 1);
        JSONArray items = new JSONArray();
        for (DiscoveryItem item : recent) try { items.put(new org.json.JSONObject(item.toJson())); } catch (Exception ignored) { }
        preferences.edit().putString("history", items.toString()).apply(); saveSnapshot();
    }
    private void saveSnapshot() {
        if (current == null) return;
        preferences.edit().putString("current", current.toJson()).putLong("position", position()).apply();
        lastCheckpoint = android.os.SystemClock.uptimeMillis();
    }
    private void changed() {
        if (Looper.myLooper() != Looper.getMainLooper()) { main.post(this::changed); return; }
        for (Listener listener : new ArrayList<>(listeners)) listener.onPlaybackChanged();
        startTicker();
    }
    private void startTicker() {
        main.removeCallbacks(tick);
        if (player != null || !listeners.isEmpty()) main.postDelayed(tick, 500);
    }
    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (player != null && android.os.SystemClock.uptimeMillis() - lastCheckpoint > 15000) saveSnapshot();
            for (Listener listener : new ArrayList<>(listeners)) listener.onPlaybackChanged();
            startTicker();
        }
    };
}
