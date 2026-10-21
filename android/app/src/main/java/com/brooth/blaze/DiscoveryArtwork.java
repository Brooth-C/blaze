package com.brooth.blaze;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.widget.ImageView;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.lang.ref.WeakReference;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.WeakHashMap;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/** Bounded app-private artwork loading; no network request runs on the UI thread. */
public final class DiscoveryArtwork {
    private static final int MAX_BYTES = 1024 * 1024;
    private static final int MAX_DIMENSION = 2048;
    private static final long DISK_BYTES = 32L * 1024 * 1024;
    private static final long CACHE_AGE = 24L * 60 * 60 * 1000;
    private static final Set<String> HOSTS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
        "i.ytimg.com", "i9.ytimg.com", "yt3.ggpht.com", "yt3.googleusercontent.com",
        "lh3.googleusercontent.com")));
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final AtomicLong SEQUENCE = new AtomicLong();
    private static final WeakHashMap<ImageView, Long> BINDINGS = new WeakHashMap<>();
    private static final LruCache<String, Bitmap> MEMORY = new LruCache<String, Bitmap>(8 * 1024 * 1024) {
        @Override protected int sizeOf(String key, Bitmap value) { return value.getAllocationByteCount(); }
    };
    private static final ThreadPoolExecutor WORK = new ThreadPoolExecutor(3, 3, 30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(96), action -> {
            Thread thread = new Thread(() -> {
                android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_BACKGROUND);
                action.run();
            }, "Blaze-artwork");
            thread.setDaemon(true); return thread;
        }, new ThreadPoolExecutor.AbortPolicy());

    private DiscoveryArtwork() { }

    public static void load(ImageView view, String url, int fallbackRes) {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            MAIN.post(() -> load(view, url, fallbackRes)); return;
        }
        Context app = view.getContext().getApplicationContext();
        long binding = SEQUENCE.incrementAndGet(); BINDINGS.put(view, binding);
        int wanted = Math.max(view.getWidth(), view.getHeight());
        if (wanted == 0 && view.getLayoutParams() != null)
            wanted = Math.max(view.getLayoutParams().width, view.getLayoutParams().height);
        if (wanted <= 0) wanted = view.getResources().getDisplayMetrics().widthPixels;
        final int size = wanted > 768 ? 1024 : wanted > 384 ? 768 : 384;
        String address = allowed(url) ? url : "";
        String remoteKey = address.isEmpty() ? "" : address + "@" + size;
        Bitmap ready = remoteKey.isEmpty() ? null : MEMORY.get(remoteKey);
        if (ready != null) { view.setImageBitmap(ready); return; }
        String resourceKey = "res:" + fallbackRes + "@" + size;
        Bitmap fallback = MEMORY.get(resourceKey);
        if (fallback != null) view.setImageBitmap(fallback);
        else {
            GradientDrawable placeholder = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{app.getColor(R.color.blaze_elevated), app.getColor(R.color.blaze_soft_accent)});
            view.setImageDrawable(placeholder);
        }
        WeakReference<ImageView> target = new WeakReference<>(view);
        try {
            WORK.execute(() -> {
                if (fallback == null && fallbackRes != 0) {
                    Bitmap local = resource(app, fallbackRes, size);
                    if (local != null) { MEMORY.put(resourceKey, local); apply(target, binding, local); }
                }
                if (address.isEmpty()) return;
                try {
                    Bitmap image = remote(app, address, size);
                    if (image != null) { MEMORY.put(remoteKey, image); apply(target, binding, image); }
                } catch (Exception ignored) { /* Artwork is optional; retain the local placeholder. */ }
            });
        } catch (RejectedExecutionException ignored) { /* A later row bind can retry a saturated image queue. */ }
    }

    private static void apply(WeakReference<ImageView> target, long binding, Bitmap image) {
        MAIN.post(() -> {
            ImageView view = target.get();
            if (view != null && Long.valueOf(binding).equals(BINDINGS.get(view))) view.setImageBitmap(image);
        });
    }

    static boolean allowed(String value) {
        if (value == null || value.length() > 4096) return false;
        try {
            URI uri = new URI(value);
            return "https".equalsIgnoreCase(uri.getScheme()) && uri.getRawUserInfo() == null
                && (uri.getPort() == -1 || uri.getPort() == 443) && uri.getHost() != null
                && HOSTS.contains(uri.getHost().toLowerCase(Locale.ROOT));
        } catch (Exception error) { return false; }
    }

    private static Bitmap resource(Context context, int resource, int size) {
        try {
            BitmapFactory.Options bounds = new BitmapFactory.Options(); bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeResource(context.getResources(), resource, bounds);
            BitmapFactory.Options decode = options(bounds.outWidth, bounds.outHeight, size);
            return decode == null ? null : BitmapFactory.decodeResource(context.getResources(), resource, decode);
        } catch (Exception error) { return null; }
    }

    private static Bitmap decode(byte[] bytes, int size) {
        BitmapFactory.Options bounds = new BitmapFactory.Options(); bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        BitmapFactory.Options decode = options(bounds.outWidth, bounds.outHeight, size);
        return decode == null ? null : BitmapFactory.decodeByteArray(bytes, 0, bytes.length, decode);
    }

    private static BitmapFactory.Options options(int width, int height, int size) {
        if (width < 1 || height < 1 || width > MAX_DIMENSION || height > MAX_DIMENSION) return null;
        BitmapFactory.Options result = new BitmapFactory.Options();
        result.inSampleSize = 1; result.inScaled = false; result.inPreferredConfig = Bitmap.Config.RGB_565;
        while (Math.max(width, height) / (result.inSampleSize * 2) >= size) result.inSampleSize *= 2;
        return result;
    }

    private static Bitmap remote(Context app, String address, int size) throws Exception {
        File folder = new File(app.getCacheDir(), "discovery-artwork");
        if (!folder.isDirectory() && !folder.mkdirs()) return null;
        File file = new File(folder, digest(address) + ".img");
        if (file.isFile() && file.length() <= MAX_BYTES && System.currentTimeMillis() - file.lastModified() < CACHE_AGE) {
            byte[] cached;
            try (InputStream input = new FileInputStream(file)) { cached = read(input); }
            Bitmap image = decode(cached, size);
            if (image != null) { file.setLastModified(System.currentTimeMillis()); return image; }
            file.delete();
        }
        byte[] bytes = fetch(address);
        Bitmap image = decode(bytes, size);
        if (image == null) return null;
        File temporary = File.createTempFile("art-", ".tmp", folder);
        try {
            try (FileOutputStream output = new FileOutputStream(temporary)) { output.write(bytes); }
            if (!temporary.renameTo(file)) temporary.delete();
        } finally { temporary.delete(); }
        trim(folder); return image;
    }

    private static byte[] fetch(String address) throws Exception {
        URL next = new URL(address);
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        for (int redirect = 0; redirect <= 2; redirect++) {
            if (!allowed(next.toString()) || System.nanoTime() > deadline) throw new java.io.IOException("Invalid artwork source");
            HttpURLConnection connection = (HttpURLConnection) next.openConnection();
            connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(3000);
            connection.setReadTimeout(5000); connection.setUseCaches(false);
            connection.setRequestProperty("Accept", "image/webp,image/jpeg,image/png");
            try {
                int status = connection.getResponseCode();
                if (status >= 300 && status <= 399) {
                    String location = connection.getHeaderField("Location");
                    if (location == null) throw new java.io.IOException("Missing artwork redirect");
                    next = new URL(next, location); continue;
                }
                if (status != HttpURLConnection.HTTP_OK || connection.getContentLengthLong() > MAX_BYTES)
                    throw new java.io.IOException("Artwork unavailable");
                String type = connection.getContentType();
                if (type == null || !(type.toLowerCase(Locale.ROOT).startsWith("image/jpeg")
                    || type.toLowerCase(Locale.ROOT).startsWith("image/png")
                    || type.toLowerCase(Locale.ROOT).startsWith("image/webp")))
                    throw new java.io.IOException("Invalid artwork type");
                try (InputStream input = connection.getInputStream()) { return read(input, deadline); }
            } finally { connection.disconnect(); }
        }
        throw new java.io.IOException("Too many artwork redirects");
    }

    private static byte[] read(InputStream input) throws Exception {
        return read(input, System.nanoTime() + TimeUnit.SECONDS.toNanos(10));
    }

    private static byte[] read(InputStream input, long deadline) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream(); byte[] buffer = new byte[8192];
        int count;
        while ((count = input.read(buffer)) != -1) {
            if (output.size() + count > MAX_BYTES || System.nanoTime() > deadline)
                throw new java.io.IOException("Artwork limit reached");
            output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    private static String digest(String value) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        StringBuilder text = new StringBuilder(64);
        for (byte part : hash) text.append(String.format(Locale.ROOT, "%02x", part & 0xff));
        return text.toString();
    }

    private static synchronized void trim(File folder) {
        File[] files = folder.listFiles((dir, name) -> name.endsWith(".img"));
        if (files == null) return;
        Arrays.sort(files, Comparator.comparingLong(File::lastModified));
        long bytes = 0; for (File file : files) bytes += file.length();
        int remaining = files.length;
        for (File file : files) {
            if (bytes <= DISK_BYTES && remaining <= 256) break;
            long length = file.length(); if (file.delete()) { bytes -= length; remaining--; }
        }
    }
}
