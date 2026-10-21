package com.brooth.blaze;

import android.content.Context;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import com.chaquo.python.PyObject;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Bounded discovery operations, separate from the durable download worker. */
public final class DiscoveryRepository {
    public interface Callback { void onResult(List<DiscoveryItem> items, String error); }
    public interface ResolveCallback { void onResolved(Stream stream, String error); }
    public interface Backend {
        List<DiscoveryItem> search(String query, String filter, int limit) throws Exception;
        List<DiscoveryItem> browse(DiscoveryItem item, int limit) throws Exception;
        Stream resolve(DiscoveryItem item) throws Exception;
    }
    public static final class Stream {
        public final String url, mimeType, audioUrl, audioMimeType;
        public final long durationMs;
        public final Map<String, String> headers;
        public Stream(String url, String mimeType, long durationMs, Map<String, String> headers) {
            this(url, mimeType, durationMs, headers, "", "");
        }
        public Stream(String url, String mimeType, long durationMs, Map<String, String> headers, String audioUrl, String audioMimeType) {
            this.url = url; this.mimeType = mimeType == null ? "" : mimeType;
            this.audioUrl = audioUrl == null ? "" : audioUrl; this.audioMimeType = audioMimeType == null ? "" : audioMimeType;
            this.durationMs = durationMs;
            this.headers = Collections.unmodifiableMap(new LinkedHashMap<>(headers == null ? Collections.emptyMap() : headers));
        }
    }

    private static volatile DiscoveryRepository instance;
    private static volatile Backend testBackend;
    private final Context app;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ThreadPoolExecutor workers = executor(2, 4, "Blaze discovery");
    private final ThreadPoolExecutor cancellation = executor(1, 8, "Blaze discovery cancel");
    private final ConcurrentHashMap<String, Operation> operations = new ConcurrentHashMap<>();
    public static final class Operation {
        final AtomicBoolean cancelled = new AtomicBoolean();
        volatile Future<?> future;
        volatile PyObject module;
        public boolean isCancelled() { return cancelled.get(); }
    }
    private DiscoveryRepository(Context context) { app = context.getApplicationContext(); }
    public static DiscoveryRepository get(Context context) {
        if (instance == null) synchronized (DiscoveryRepository.class) {
            if (instance == null) instance = new DiscoveryRepository(context);
        }
        return instance;
    }
    public static void setTestBackend(Backend backend) { testBackend = backend; }
    public static void clearTestBackend() { testBackend = null; }

    private static ThreadPoolExecutor executor(int count, int capacity, String name) {
        return new ThreadPoolExecutor(count, count, 30, TimeUnit.SECONDS, new ArrayBlockingQueue<>(capacity), task -> {
            Thread thread = new Thread(task, name); thread.setDaemon(true); return thread;
        }, new ThreadPoolExecutor.AbortPolicy());
    }

    public String search(String query, String filter, int limit, Callback callback) {
        String term = query == null ? "" : query.trim();
        if (term.isEmpty() || term.length() > 256 || term.matches("(?s).*\\p{Cntrl}.*")) {
            main.post(() -> callback.onResult(Collections.emptyList(), "Enter a search of up to 256 characters.")); return "";
        }
        if (!java.util.Arrays.asList("all", "songs", "videos", "artists", "playlists").contains(filter)) {
            main.post(() -> callback.onResult(Collections.emptyList(), "Choose a supported search filter.")); return "";
        }
        return listOperation("search", term, filter, null, Math.max(1, Math.min(limit, 60)), callback);
    }
    public String browse(DiscoveryItem item, int limit, Callback callback) {
        if (item == null || !item.browsable() || !DiscoveryItem.validSource(item.url)) {
            main.post(() -> callback.onResult(Collections.emptyList(), "This collection cannot be opened.")); return "";
        }
        return listOperation("browse", "", "all", item, Math.max(1, Math.min(limit, 60)), callback);
    }
    private String listOperation(String method, String query, String filter, DiscoveryItem item, int limit, Callback callback) {
        String token = UUID.randomUUID().toString(); Operation operation = new Operation(); operations.put(token, operation);
        try { operation.future = workers.submit(() -> {
            List<DiscoveryItem> items = Collections.emptyList(); String error = null;
            try {
                if (operation.cancelled.get()) return;
                Backend override = testBackend;
                if (override != null) items = method.equals("search") ? override.search(query, filter, limit) : override.browse(item, limit);
                else {
                    operation.module = PythonRuntime.get(app).getModule("blaze_discovery");
                    String output = operation.module.callAttr(method, method.equals("search") ? query : item.toJson(), filter, limit, token, operation).toString();
                    if (output.length() > 262144) throw new IllegalStateException("Response too large");
                    JSONObject value = new JSONObject(output);
                    if (!value.optString("error").isEmpty()) error = value.optString("error");
                    else {
                        JSONArray rows = value.getJSONArray("items");
                        LinkedHashMap<String, DiscoveryItem> unique = new LinkedHashMap<>();
                        for (int i = 0; i < rows.length() && i < 60; i++) {
                            DiscoveryItem entry = DiscoveryItem.fromJson(rows.getJSONObject(i).toString()); unique.put(entry.key(), entry);
                        }
                        items = new ArrayList<>(unique.values());
                    }
                }
                if (items == null) items = Collections.emptyList();
                items = Collections.unmodifiableList(new ArrayList<>(items.subList(0, Math.min(items.size(), limit))));
            } catch (Exception failure) { error = "Discovery is unavailable right now. Check your connection and try again."; }
            finally { if (operation.cancelled.get()) operations.remove(token); }
            List<DiscoveryItem> delivered = items; String detail = safeMessage(error);
            main.post(() -> { operations.remove(token); if (!operation.cancelled.get()) callback.onResult(delivered, detail); });
        }); } catch (RejectedExecutionException busy) {
            operations.remove(token); main.post(() -> callback.onResult(Collections.emptyList(), "Finish the current search or try again in a moment."));
        }
        return token;
    }

    public String resolve(DiscoveryItem item, ResolveCallback callback) {
        if (item == null || item.browsable() || !DiscoveryItem.validSource(item.url)) {
            main.post(() -> callback.onResolved(null, "This recording cannot be streamed.")); return "";
        }
        String token = UUID.randomUUID().toString(); Operation operation = new Operation(); operations.put(token, operation);
        try { operation.future = workers.submit(() -> {
            Stream stream = null; String error = null;
            try {
                if (operation.cancelled.get()) return;
                Backend override = testBackend;
                if (override != null) stream = override.resolve(item);
                else {
                    operation.module = PythonRuntime.get(app).getModule("blaze_discovery");
                    File quickjs = new File(app.getApplicationInfo().nativeLibraryDir, "libblaze_qjs.so");
                    String output = operation.module.callAttr("resolve", item.toJson(), quickjs.getAbsolutePath(), token, operation).toString();
                    if (output.length() > 32768) throw new IllegalStateException("Response too large");
                    JSONObject value = new JSONObject(output);
                    if (!value.optString("error").isEmpty()) error = value.optString("error");
                    else {
                        JSONObject media = value.getJSONObject("stream");
                        String remote = media.getString("url"); Uri uri = Uri.parse(remote);
                        String host = uri.getHost();
                        if (!"https".equalsIgnoreCase(uri.getScheme()) || host == null || uri.getUserInfo() != null
                            || uri.getPort() != -1 || !(host.equals("googlevideo.com") || host.endsWith(".googlevideo.com")))
                            throw new IllegalStateException("Invalid stream URL");
                        Map<String, String> headers = new LinkedHashMap<>(); JSONObject raw = media.optJSONObject("headers");
                        if (raw != null) for (String name : new String[]{"User-Agent", "Referer", "Origin", "Accept", "Accept-Language"}) {
                            String text = raw.optString(name); if (!text.isEmpty() && text.length() <= 2048 && !text.matches("(?s).*\\p{Cntrl}.*")) headers.put(name, text);
                        }
                        String audioUrl = media.optString("audioUrl");
                        if (!audioUrl.isEmpty()) {
                            Uri audio = Uri.parse(audioUrl); String audioHost = audio.getHost();
                            if (!"https".equalsIgnoreCase(audio.getScheme()) || audio.getUserInfo() != null || audio.getPort() != -1
                                || audioHost == null || !(audioHost.equals("googlevideo.com") || audioHost.endsWith(".googlevideo.com")))
                                throw new IllegalStateException("Invalid audio stream URL");
                        }
                        stream = new Stream(remote, media.optString("mimeType"), media.optLong("durationMs", -1), headers,
                            audioUrl, media.optString("audioMimeType"));
                    }
                }
                if (stream == null && error == null) error = "No playable audio was returned for this recording.";
            } catch (Exception failure) { error = "Playback is unavailable for this recording. Try again or save a copy."; }
            finally { if (operation.cancelled.get()) operations.remove(token); }
            Stream delivered = stream; String detail = safeMessage(error);
            main.post(() -> { operations.remove(token); if (!operation.cancelled.get()) callback.onResolved(delivered, detail); });
        }); } catch (RejectedExecutionException busy) {
            operations.remove(token); main.post(() -> callback.onResolved(null, "Playback is busy. Try again in a moment."));
        }
        return token;
    }

    public void cancel(String token) {
        if (token == null || token.isEmpty()) return;
        Operation operation = operations.remove(token); if (operation == null) return;
        operation.cancelled.set(true); if (operation.future != null) operation.future.cancel(true);
        workers.purge();
        if (operation.module != null) try { cancellation.execute(() -> { try { operation.module.callAttr("cancel", token); } catch (Exception ignored) { } }); }
        catch (RejectedExecutionException ignored) { /* Callback flag and Python deadline still stop this operation. */ }
    }
    private static String safeMessage(String message) {
        if (message == null || message.isEmpty()) return null;
        return DiscoveryItem.clean(message, 240);
    }
}
