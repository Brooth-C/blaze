package com.brooth.blaze;

import android.net.Uri;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.Locale;
import java.util.UUID;

/** Stable catalogue identity. Signed playback URLs never belong in this model. */
public final class DiscoveryItem {
    public final String id, kind, title, creator, url, thumbnail, localJobId;
    public final long durationMs;

    public DiscoveryItem(String id, String kind, String title, String creator, String url,
                         String thumbnail, long durationMs, String localJobId) {
        this.id = clean(id, 160);
        if (this.id.isEmpty()) throw new IllegalArgumentException("Missing media identity");
        String type = clean(kind, 20).toLowerCase(Locale.ROOT);
        if (!type.equals("song") && !type.equals("video") && !type.equals("artist")
                && !type.equals("playlist") && !type.equals("album") && !type.equals("local"))
            throw new IllegalArgumentException("Unsupported media kind");
        this.kind = type;
        this.title = clean(title, 300).isEmpty() ? "Untitled recording" : clean(title, 300);
        this.creator = clean(creator, 200);
        this.url = url == null ? "" : url.trim();
        if (this.url.length() > 8192 || this.url.matches("(?s).*\\p{Cntrl}.*"))
            throw new IllegalArgumentException("Invalid media URL");
        this.thumbnail = safeThumbnail(thumbnail);
        this.durationMs = durationMs >= 0 && durationMs <= 604800000L ? durationMs : -1;
        String job = localJobId == null ? "" : localJobId;
        if (!job.isEmpty()) {
            try { if (!UUID.fromString(job).toString().equals(job)) throw new IllegalArgumentException(); }
            catch (IllegalArgumentException error) { throw new IllegalArgumentException("Invalid saved media identity"); }
        }
        this.localJobId = job;
    }

    public DiscoveryItem(String id, String kind, String title, String creator, String url,
                         String thumbnail, long durationMs) {
        this(id, kind, title, creator, url, thumbnail, durationMs, "");
    }

    public String key() { return "youtube:" + (browsable() ? kind : "video") + ":" + id; }
    public boolean browsable() { return kind.equals("artist") || kind.equals("playlist") || kind.equals("album"); }

    public String toJson() {
        try {
            return new JSONObject().put("id", id).put("kind", kind).put("title", title)
                .put("creator", creator).put("url", url).put("thumbnail", thumbnail)
                .put("durationMs", durationMs).put("localJobId", localJobId).toString();
        } catch (JSONException error) { throw new IllegalStateException("Could not encode media", error); }
    }

    public static DiscoveryItem fromJson(String text) throws JSONException {
        if (text == null || text.length() > 12000) throw new JSONException("Invalid media metadata");
        JSONObject item = new JSONObject(text);
        try {
            DiscoveryItem result = new DiscoveryItem(item.getString("id"), item.getString("kind"),
                item.optString("title", ""), item.optString("creator", ""), item.optString("url", ""),
                item.optString("thumbnail", ""), item.optLong("durationMs", -1), item.optString("localJobId", ""));
            if (result.localJobId.isEmpty() && !validSource(result.url))
                throw new IllegalArgumentException("Unsupported source URL");
            return result;
        } catch (IllegalArgumentException error) { throw new JSONException("Invalid media metadata"); }
    }

    static String clean(String value, int maximum) {
        String text = value == null ? "" : value.replaceAll("\\p{Cntrl}", " ").trim();
        return text.length() > maximum ? text.substring(0, maximum) : text;
    }

    static boolean validSource(String url) {
        Uri uri = Uri.parse(url);
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getUserInfo() != null || uri.getPort() != -1) return false;
        String host = uri.getHost();
        return host != null && (host.equalsIgnoreCase("www.youtube.com") || host.equalsIgnoreCase("youtube.com")
            || host.equalsIgnoreCase("music.youtube.com") || host.equalsIgnoreCase("youtu.be"));
    }

    private static String safeThumbnail(String candidate) {
        if (candidate == null || candidate.length() > 4096 || candidate.matches("(?s).*\\p{Cntrl}.*")) return "";
        Uri uri = Uri.parse(candidate);
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getUserInfo() != null || uri.getPort() != -1) return "";
        String host = uri.getHost();
        if (host == null) return "";
        host = host.toLowerCase(Locale.ROOT);
        return host.equals("i.ytimg.com") || host.equals("i9.ytimg.com") || host.equals("yt3.ggpht.com")
            || host.equals("lh3.googleusercontent.com") || host.equals("yt3.googleusercontent.com") ? candidate : "";
    }
}
