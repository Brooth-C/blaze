package com.brooth.blaze;

import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

/** Small, app-private metadata cache. Never contains signed streams or local paths. */
final class RecommendationCache {
    static final long FRESH_MS = 6L * 60 * 60 * 1000;
    private static final long MAX_AGE_MS = 7L * 24 * 60 * 60 * 1000;
    static final class Snapshot {
        final List<DiscoveryItem> items;
        final long created;
        Snapshot(List<DiscoveryItem> items, long created) { this.items = items; this.created = created; }
        boolean fresh() { return System.currentTimeMillis() - created < FRESH_MS; }
    }
    static String profile(Context context) {
        PlaybackController player = PlaybackController.get(context);
        JSONArray history = new JSONArray();
        for (DiscoveryItem item : player.history()) {
            if (history.length() == 30) break;
            if (!DiscoveryItem.validSource(item.url)) continue;
            try {
                history.put(new JSONObject().put("id", item.id).put("title", item.title)
                    .put("creator", item.creator).put("favorite", player.isFavorite(item))
                    .put("plays", player.listenCount(item)));
            } catch (Exception ignored) { /* A missing optional signal does not block discovery. */ }
        }
        return history.toString();
    }
    static Snapshot load(Context context, String lane, String profile) {
        try {
            String encoded = context.getSharedPreferences("recommendations", Context.MODE_PRIVATE).getString(lane, "");
            if (encoded.length() > 131072) return null;
            JSONObject value = new JSONObject(encoded);
            long created = value.getLong("created"), now = System.currentTimeMillis();
            if (!value.getString("profile").equals(fingerprint(profile)) || created > now + 60000 || now - created > MAX_AGE_MS) return null;
            JSONArray rows = value.getJSONArray("items"); List<DiscoveryItem> items = new ArrayList<>();
            for (int i = 0; i < Math.min(18, rows.length()); i++) {
                DiscoveryItem item = DiscoveryItem.fromJson(rows.getJSONObject(i).toString());
                if (!item.browsable() && item.localJobId.isEmpty() && DiscoveryItem.validSource(item.url)) items.add(item);
            }
            return items.isEmpty() ? null : new Snapshot(items, created);
        } catch (Exception ignored) { return null; }
    }
    static void save(Context context, String lane, String profile, List<DiscoveryItem> items) {
        try {
            JSONArray rows = new JSONArray();
            for (DiscoveryItem item : items) {
                if (rows.length() == 18) break;
                if (item.browsable() || !DiscoveryItem.validSource(item.url)) continue;
                DiscoveryItem remote = new DiscoveryItem(item.id, item.kind, item.title, item.creator,
                    item.url, item.thumbnail, item.durationMs);
                rows.put(new JSONObject(remote.toJson()));
            }
            if (rows.length() == 0) return;
            String encoded = new JSONObject().put("profile", fingerprint(profile)).put("created", System.currentTimeMillis()).put("items", rows).toString();
            if (encoded.length() <= 131072) context.getSharedPreferences("recommendations", Context.MODE_PRIVATE).edit().putString(lane, encoded).apply();
        } catch (Exception ignored) { /* Offline caching is optional. */ }
    }
    private static String fingerprint(String profile) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(profile.getBytes(StandardCharsets.UTF_8));
        StringBuilder text = new StringBuilder();
        for (byte value : digest) text.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        return text.toString();
    }
}
