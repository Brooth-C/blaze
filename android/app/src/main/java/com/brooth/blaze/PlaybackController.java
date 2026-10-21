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
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

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
    // File validation and platform codec discovery can involve SQLite, disk and
    // binder calls. Keep them off the tap/navigation thread and retain only the
    // newest pending choice if a previous probe is still unwinding.
    private final ThreadPoolExecutor localFiles = new ThreadPoolExecutor(1, 1, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(1), action -> {
            Thread thread = new Thread(action, "Blaze local playback"); thread.setDaemon(true); return thread;
        }, new ThreadPoolExecutor.AbortPolicy());
    private Future<?> localLookup;
    private final Set<Listener> listeners = new LinkedHashSet<>();
    private final ArrayList<DiscoveryItem> queue = new ArrayList<>(), recent = new ArrayList<>();
    private ExoPlayer player;
    private BlazePlaybackService service;
    private DiscoveryItem current;
    private int index = -1, generation, preparedGeneration = -1;
    private boolean wantedPlayback, resolving, shuffle, repeat, refreshAttempted;
    private long rememberedPosition, lastCheckpoint;
    private String resolutionToken = "", failure = "";
    private long listeningMillis, listeningTick;
    private boolean listeningCounted;

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
    int listenCount(DiscoveryItem item) {
        return Math.max(0, Math.min(1000, preferences.getInt("plays_" + item.id, 0)));
    }
    void recordQualifiedListen(DiscoveryItem item) {
        if (item != null && DiscoveryItem.validSource(item.url))
            preferences.edit().putInt("plays_" + item.id, Math.min(1000, listenCount(item) + 1)).apply();
    }
    DiscoveryItem rememberSavedPlayback(PlaybackSource source) {
        if (source == null) return null;
        try (JobStore store = new JobStore(app)) {
            JobStore.Job job = store.completed(source.id);
            if (job == null || !DiscoveryItem.validSource(job.url)) return null;
            Uri uri = Uri.parse(job.url);
            String id = "youtu.be".equals(uri.getHost()) ? uri.getLastPathSegment() : uri.getQueryParameter("v");
            if (id == null || !id.matches("[A-Za-z0-9_-]{11}")) return null;
            DiscoveryItem item = null;
            for (DiscoveryItem previous : recent) if (previous.id.equals(id)) { item = previous; break; }
            if (item == null) item = new DiscoveryItem(id, "video".equals(job.mode) ? "video" : "song", job.title, "",
                "https://www.youtube.com/watch?v=" + id, "https://i.ytimg.com/vi/" + id + "/mqdefault.jpg", -1);
            rememberItem(item); changed(); return item;
        } catch (RuntimeException ignored) { return null; }
    }
    public void clearListeningHistory() {
        onMain(() -> {
            recent.clear(); SharedPreferences.Editor edit = preferences.edit().remove("history");
            for (String key : preferences.getAll().keySet()) if (key.startsWith("plays_")) edit.remove(key);
            edit.apply(); app.getSharedPreferences("recommendations", Context.MODE_PRIVATE).edit().clear().apply();
            listeningMillis = 0; listeningCounted = false; changed();
        });
    }
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
        listeningMillis = 0; listeningTick = 0; listeningCounted = false;
        cancelResolution(); generation++; preparedGeneration = -1;
        current = item;
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
                    if (Thread.currentThread().isInterrupted()) return selected;
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
        if (current == null || player == null || !resolutionToken.isEmpty() || localLookup != null) return;
        final int request = generation;
        final DiscoveryItem selected = current;
        resolving = true; failure = ""; changed();
        try {
            localLookup = localFiles.submit(() -> {
                DiscoveryItem preferred = preferLocalCopy(selected);
                String localUrl = "";
                boolean missing = false;
                if (!preferred.localJobId.isEmpty()) {
                    try { localUrl = Uri.fromFile(PlaybackSource.load(app, preferred.localJobId).file).toString(); }
                    catch (Exception unavailable) { missing = true; }
                }
                if (Thread.currentThread().isInterrupted()) return;
                final String location = localUrl;
                final boolean unavailable = missing;
                main.post(() -> {
                    if (request != generation || player == null || current == null || !current.key().equals(selected.key())) return;
                    localLookup = null;
                    if (unavailable) { failed(request, "The saved file is missing. Choose another recording or save it again."); return; }
                    current = preferred;
                    if (index >= 0 && index < queue.size() && queue.get(index).key().equals(current.key())) queue.set(index, current);
                    saveSnapshot();
                    if (!location.isEmpty()) configure(location, "", Collections.emptyMap(), "", "", request);
                    else resolveRemote(preferred, request);
                });
            });
        } catch (RejectedExecutionException busy) {
            failed(request, "Playback is busy. Try again in a moment.");
        }
    }

    private void resolveRemote(DiscoveryItem selected, int request) {
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
        if (localLookup != null) localLookup.cancel(true);
        localLookup = null; localFiles.purge();
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
        @Override public void onIsPlayingChanged(boolean playing) {
            listeningTick = playing ? android.os.SystemClock.elapsedRealtime() : 0;
            if (playing) rememberPlayed(); changed();
        }
        @Override public void onPlayWhenReadyChanged(boolean playWhenReady, int reason) {
            if (preparedGeneration == generation) wantedPlayback = playWhenReady;
            changed();
        }
        @Override public void onPlaybackStateChanged(int state) {
            if (state == Player.STATE_ENDED && current != null) {
                if (repeat) {
                    listeningMillis = 0; listeningTick = 0; listeningCounted = false;
                    seekTo(0); wantedPlayback = true; if (player != null) player.play();
                }
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
        rememberItem(current); saveSnapshot();
    }
    private void rememberItem(DiscoveryItem played) {
        recent.removeIf(item -> item.key().equals(played.key())); recent.add(0, played);
        while (recent.size() > 30) recent.remove(recent.size() - 1);
        JSONArray items = new JSONArray();
        for (DiscoveryItem item : recent) try { items.put(new org.json.JSONObject(item.toJson())); } catch (Exception ignored) { }
        SharedPreferences.Editor edit = preferences.edit().putString("history", items.toString());
        // Keep repeat-listening counters bounded by the retained history too.
        Set<String> retained = new LinkedHashSet<>(); for (DiscoveryItem item : recent) retained.add("plays_" + item.id);
        for (String key : preferences.getAll().keySet()) if (key.startsWith("plays_") && !retained.contains(key)) edit.remove(key);
        edit.apply();
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
            long now = android.os.SystemClock.elapsedRealtime();
            if (current != null && isPlaying()) {
                if (listeningTick > 0) listeningMillis += Math.max(0, Math.min(2000, now - listeningTick));
                listeningTick = now;
                if (!listeningCounted && listeningMillis >= 15000) {
                    listeningCounted = true;
                    recordQualifiedListen(current);
                }
            } else listeningTick = 0;
            if (player != null && android.os.SystemClock.uptimeMillis() - lastCheckpoint > 15000) saveSnapshot();
            for (Listener listener : new ArrayList<>(listeners)) listener.onPlaybackChanged();
            startTicker();
        }
    };
}
