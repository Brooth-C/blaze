package com.brooth.blaze;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Canvas;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.text.Editable;
import android.text.InputFilter;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;

/** The native discovery surface. Queue and playback ownership stay outside the view. */
public final class ExploreView extends LinearLayout {
    public interface Actions {
        void onPlay(DiscoveryItem item, List<DiscoveryItem> queue);
        void onDownload(DiscoveryItem item, boolean forStudio);
        void onOpenPlayer();
        void onSettings();
    }

    private final Activity activity;
    private final Actions actions;
    private final BlazeUi ui;
    private final DiscoveryRepository repository;
    private final ScrollView scroll;
    private final LinearLayout content;
    private final ArrayDeque<SearchState> backStack = new ArrayDeque<>();
    private List<DiscoveryItem> results = new ArrayList<>();
    private String query = "", submitted = "", filter = "all", requestToken = "", error = "";
    private String homeLane = "For you";
    private DiscoveryItem collection;
    private EditText searchInput;
    private boolean home = true, loading, destroyed;
    private int generation, requestedLimit = 20;

    public ExploreView(Activity activity, Actions actions) {
        super(activity);
        this.activity = activity; this.actions = actions; ui = new BlazeUi(activity);
        repository = DiscoveryRepository.get(activity);
        setOrientation(VERTICAL); setBackgroundColor(ui.background); setTag("explore_view");
        scroll = new ScrollView(activity); scroll.setFillViewport(true);
        scroll.setClipToPadding(false); scroll.setVerticalScrollBarEnabled(false);
        content = ui.column(); content.setPadding(dp(18), dp(8), dp(18), dp(8));
        scroll.addView(content, new ScrollView.LayoutParams(-1, -2));
        addView(scroll, new LinearLayout.LayoutParams(-1, -1));
        renderHome();
    }

    public void showHome() {
        cancelRequest(); home = true; collection = null; backStack.clear();
        hideKeyboard();
        renderHome(); scroll.scrollTo(0, 0);
    }

    public void showSearch(String value) {
        query = clean(value); submitted = query; collection = null; backStack.clear();
        home = false; requestedLimit = 20; results = new ArrayList<>(); error = "";
        if (submitted.isEmpty()) { cancelRequest(); renderSearch(); }
        else request(false);
    }

    public void onResume() {
        int y = scroll.getScrollY();
        if (home) renderHome(); else renderSearch();
        scroll.post(() -> scroll.scrollTo(0, y));
    }

    public void onPause() { boolean interrupted = loading; cancelRequest(); if (interrupted && results.isEmpty()) error = "Search paused. Try again."; }
    public void onDestroy() { destroyed = true; cancelRequest(); }

    public boolean handleBack() {
        if (!backStack.isEmpty()) {
            cancelRequest(); SearchState previous = backStack.pop(); previous.apply();
            renderSearch(); scroll.post(() -> scroll.scrollTo(0, previous.scrollY)); return true;
        }
        if (!home) { showHome(); return true; }
        return false;
    }

    public void saveState(Bundle state) {
        state.putBoolean("explore_home", home); state.putString("explore_query", query);
        state.putString("explore_submitted", submitted); state.putString("explore_filter", filter);
        state.putString("explore_lane", homeLane); state.putInt("explore_scroll", scroll.getScrollY());
        state.putInt("explore_limit", requestedLimit);
        state.putString("explore_error", loading && results.isEmpty() ? "Search paused. Try again." : error);
        if (collection != null) state.putString("explore_collection", collection.toJson());
        JSONArray array = new JSONArray();
        for (DiscoveryItem item : results) {
            try { array.put(new JSONObject(item.toJson())); } catch (JSONException ignored) { /* Item can be refetched. */ }
        }
        String encoded = array.toString();
        if (encoded.length() <= 131072) state.putString("explore_results", encoded);
        else state.putString("explore_error", "Search again to refresh these results.");
        JSONArray parents = new JSONArray();
        for (SearchState parent : backStack) {
            try {
                JSONObject item = parent.toJson();
                if (parents.toString().length() + item.toString().length() > 131072) break;
                parents.put(item);
            } catch (JSONException ignored) { /* Search can still be restored without this parent. */ }
        }
        state.putString("explore_parents", parents.toString());
    }

    public void restoreState(Bundle state) {
        if (state == null || !state.containsKey("explore_home")) return;
        cancelRequest(); home = state.getBoolean("explore_home", true);
        query = clean(state.getString("explore_query", "")); submitted = clean(state.getString("explore_submitted", ""));
        filter = validFilter(state.getString("explore_filter", "all")); homeLane = state.getString("explore_lane", "For you");
        requestedLimit = Math.max(20, Math.min(60, state.getInt("explore_limit", 20)));
        error = clean(state.getString("explore_error", ""));
        results = new ArrayList<>(); collection = null; backStack.clear();
        try {
            String savedCollection = state.getString("explore_collection", "");
            if (!savedCollection.isEmpty()) collection = DiscoveryItem.fromJson(savedCollection);
            JSONArray array = new JSONArray(state.getString("explore_results", "[]"));
            for (int i = 0; i < Math.min(60, array.length()); i++) results.add(DiscoveryItem.fromJson(array.getJSONObject(i).toString()));
            JSONArray parents = new JSONArray(state.getString("explore_parents", "[]"));
            for (int i = 0; i < Math.min(8, parents.length()); i++) backStack.addLast(new SearchState(parents.getJSONObject(i)));
        } catch (JSONException ignored) { error = "Search again to refresh these results."; }
        if (home) renderHome(); else renderSearch();
        int position = state.getInt("explore_scroll", 0); scroll.post(() -> scroll.scrollTo(0, Math.max(0, position)));
    }

    private void renderHome() {
        content.removeAllViews(); content.setTag("explore_home"); searchInput = null;
        LinearLayout brand = horizontal(); brand.setGravity(Gravity.CENTER_VERTICAL);
        ImageView logo = new ImageView(activity); logo.setImageResource(R.drawable.blaze_brand_mark);
        logo.setTag("explore_logo"); logo.setContentDescription("Blaze"); logo.setScaleType(ImageView.ScaleType.FIT_CENTER);
        brand.addView(logo, new LinearLayout.LayoutParams(dp(26), dp(32)));
        TextView name = ui.heading("Blaze", 18); LinearLayout.LayoutParams nameSize = new LinearLayout.LayoutParams(0, -2, 1);
        nameSize.setMarginStart(dp(6)); brand.addView(name, nameSize);
        Button settings = icon("profile", "Blaze settings", ui.text); settings.setBackground(ui.interactiveSurface(ui.elevated, 24));
        settings.setOnClickListener(v -> actions.onSettings()); brand.addView(settings, new LinearLayout.LayoutParams(dp(40), dp(40)));
        content.addView(brand, new LinearLayout.LayoutParams(-1, dp(40)));
        gap(8); content.addView(ui.heading("Explore", 36)); gap(3);
        content.addView(ui.label("Find your next favourite.", 15, ui.secondary)); gap(17);
        Button search = ui.button("Search videos, songs, artists…", false); search.setTag("discovery_search");
        search.setTextSize(14); search.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        search.setTextColor(ui.secondary); search.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        search.setPadding(dp(15), 0, dp(12), 0); search.setMinHeight(dp(46)); search.setMinimumHeight(dp(46));
        search.setBackground(ui.interactiveSurface(ui.elevated, 24));
        search.setCompoundDrawablesWithIntrinsicBounds(DiscoveryIcons.get(activity, "search", ui.text), null, null, null);
        search.setCompoundDrawablePadding(dp(10)); search.setContentDescription("Search videos, songs and artists");
        search.setOnClickListener(v -> openSearch()); content.addView(search, new LinearLayout.LayoutParams(-1, dp(48)));
        gap(11); content.addView(homeSegments()); gap(10);
        String heroTitle = "An evening at the keys", heroCaption = "A mix for slowing down", heroQuery = "piano evening live session";
        int heroArt = R.drawable.discovery_piano;
        if ("Videos".equals(homeLane)) { heroTitle = "Take the front row"; heroCaption = "Live sessions, wherever you are"; heroQuery = "acoustic live music session"; heroArt = R.drawable.discovery_acoustic; }
        final String chosenQuery = heroQuery;
        FrameLayout hero = editorial(heroTitle, heroCaption, heroArt, 190, () -> showSearch(chosenQuery), () -> playCurated(chosenQuery));
        hero.setTag("explore_hero"); content.addView(hero, new LinearLayout.LayoutParams(-1, dp(190)));
        LinearLayout dots = horizontal(); dots.setGravity(Gravity.CENTER);
        for (int i = 0; i < 3; i++) {
            View dot = new View(activity); dot.setBackground(ui.shape(i == 0 ? ui.accent : ui.border, 4));
            LinearLayout.LayoutParams dotSize = new LinearLayout.LayoutParams(dp(6), dp(6)); dotSize.setMargins(dp(4), dp(7), dp(4), dp(7)); dots.addView(dot, dotSize);
        }
        content.addView(dots, new LinearLayout.LayoutParams(-1, dp(16)));
        section("Made for you", () -> showSearch("acoustic jazz live sessions")); gap(10);
        LinearLayout tiles = horizontal();
        FrameLayout acoustic = editorial("Acoustic sessions", "A mix of mellow moments", R.drawable.discovery_acoustic, 132,
                () -> showSearch("acoustic sessions"), () -> playCurated("acoustic sessions"));
        FrameLayout jazz = editorial("Late-night jazz", "Smooth sounds, deeper nights", R.drawable.discovery_jazz, 132,
                () -> showSearch("late night jazz"), () -> playCurated("late night jazz"));
        LinearLayout.LayoutParams tile = new LinearLayout.LayoutParams(0, dp(132), 1); tile.setMargins(0, 0, dp(5), 0); tiles.addView(acoustic, tile);
        LinearLayout.LayoutParams tile2 = new LinearLayout.LayoutParams(0, dp(132), 1); tile2.setMargins(dp(5), 0, 0, 0); tiles.addView(jazz, tile2);
        content.addView(tiles); gap(23);
        List<DiscoveryItem> history = PlaybackController.get(activity).history();
        section("Continue listening", history.isEmpty() ? this::openSearch : actions::onOpenPlayer); gap(8);
        if (!history.isEmpty()) {
            for (int i = 0; i < Math.min(3, history.size()); i++) content.addView(trackRow(history.get(i), history));
        } else {
            LinearLayout empty = horizontal(); empty.setGravity(Gravity.CENTER_VERTICAL); empty.setPadding(0, dp(6), 0, dp(6));
            TextView hint = ui.label("Play something you love.\nYour recent listening will appear here.", 13, ui.secondary);
            hint.setLineSpacing(dp(3), 1); empty.addView(hint, new LinearLayout.LayoutParams(0, -2, 1));
            Button begin = icon("play", "Find something to play", ui.accent); begin.setOnClickListener(v -> openSearch()); empty.addView(begin, new LinearLayout.LayoutParams(dp(48), dp(48)));
            content.addView(empty);
        }
    }

    private View homeSegments() {
        LinearLayout row = horizontal(); row.setPadding(dp(3), dp(3), dp(3), dp(3)); row.setBackground(ui.shape(ui.elevated, 23));
        for (String label : new String[]{"For you", "Music", "Videos"}) {
            boolean selected = label.equals(homeLane);
            Button choice = textButton(label, selected ? ui.accent : ui.secondary, selected ? ui.softAccent : Color.TRANSPARENT, 20);
            choice.setSelected(selected); choice.setContentDescription(label + (selected ? ", selected" : ""));
            choice.setOnClickListener(v -> { homeLane = label; renderHome(); }); row.addView(choice, new LinearLayout.LayoutParams(0, dp(40), 1));
        }
        return row;
    }

    private void openSearch() {
        cancelRequest(); home = false; collection = null; backStack.clear(); submitted = ""; error = ""; results = new ArrayList<>();
        renderSearch();
        if (searchInput != null) searchInput.post(() -> {
            if (!destroyed && searchInput != null) {
                searchInput.requestFocus(); InputMethodManager keyboard = (InputMethodManager) activity.getSystemService(Activity.INPUT_METHOD_SERVICE);
                if (keyboard != null) keyboard.showSoftInput(searchInput, InputMethodManager.SHOW_IMPLICIT);
            }
        });
    }

    private void renderSearch() {
        content.removeAllViews(); content.setTag("discovery_results");
        LinearLayout top = horizontal(); top.setGravity(Gravity.CENTER_VERTICAL);
        Button back = icon("back", "Back to Explore", ui.text); back.setOnClickListener(v -> handleBack());
        LinearLayout.LayoutParams backSize = new LinearLayout.LayoutParams(dp(40), dp(48)); backSize.setMargins(dp(-8), 0, dp(5), 0); top.addView(back, backSize);
        LinearLayout field = horizontal(); field.setGravity(Gravity.CENTER_VERTICAL); field.setPadding(dp(12), 0, 0, 0); field.setBackground(ui.shape(ui.elevated, 24));
        ImageView magnifier = new ImageView(activity); magnifier.setImageDrawable(DiscoveryIcons.get(activity, "search", ui.text)); magnifier.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        field.addView(magnifier, new LinearLayout.LayoutParams(dp(21), dp(21)));
        searchInput = new EditText(activity); searchInput.setTag("discovery_search"); searchInput.setSingleLine(true); searchInput.setTextSize(14);
        searchInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(256)});
        searchInput.setTextColor(ui.text); searchInput.setHintTextColor(ui.secondary); searchInput.setHint("Search videos, songs, artists…"); searchInput.setText(query);
        searchInput.setBackgroundColor(Color.TRANSPARENT); searchInput.setPadding(dp(9), 0, dp(2), 0); searchInput.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        searchInput.setContentDescription("Search videos, songs and artists");
        searchInput.addTextChangedListener(new TextWatcher() { public void beforeTextChanged(CharSequence s, int a, int count, int after) {} public void onTextChanged(CharSequence s, int start, int before, int count) { query = s.toString(); } public void afterTextChanged(Editable value) {} });
        searchInput.setOnEditorActionListener((view, action, event) -> { if (action == EditorInfo.IME_ACTION_SEARCH || (event != null && event.getKeyCode() == android.view.KeyEvent.KEYCODE_ENTER)) { submitInput(); return true; } return false; });
        field.addView(searchInput, new LinearLayout.LayoutParams(0, dp(48), 1));
        Button clear = icon("close", "Clear search", ui.secondary); clear.setOnClickListener(v -> { cancelRequest(); query = ""; submitted = ""; collection = null; backStack.clear(); requestedLimit = 20; results = new ArrayList<>(); error = ""; renderSearch(); });
        field.addView(clear, new LinearLayout.LayoutParams(dp(42), dp(48))); top.addView(field, new LinearLayout.LayoutParams(0, dp(48), 1));
        content.addView(top, new LinearLayout.LayoutParams(-1, dp(52))); gap(14);
        TextView heading = ui.heading(collection == null ? "Search results" : collection.title, 23); heading.setMaxLines(2); content.addView(heading); gap(5);
        if (collection == null) { content.addView(searchFilters()); gap(9); }
        else { content.addView(ui.label(collection.creator.isEmpty() ? kindLabel(collection.kind) : collection.creator, 13, ui.secondary)); gap(13); }
        if (loading) {
            ProgressBar progress = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal); progress.setIndeterminate(true);
            progress.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(ui.accent)); progress.setTag("discovery_loading");
            content.addView(progress, new LinearLayout.LayoutParams(-1, dp(3))); gap(12);
        }
        if (!error.isEmpty()) {
            TextView failure = ui.label(error, 14, ui.secondary); failure.setTag("discovery_error"); failure.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
            content.addView(failure); gap(12); Button retry = ui.button("Try again", false); retry.setTag("discovery_retry"); retry.setOnClickListener(v -> request(false)); content.addView(retry); gap(16);
        }
        if (results.isEmpty()) {
            if (!loading && error.isEmpty()) {
                gap(24); TextView empty = ui.heading(submitted.isEmpty() && collection == null ? "Find something you love" : "Nothing found", 20); empty.setTag("discovery_empty"); content.addView(empty); gap(8);
                content.addView(ui.label(submitted.isEmpty() && collection == null ? "Search for a song, video, artist or playlist." : "Try a different title or artist.", 14, ui.secondary));
            }
            return;
        }
        if (collection != null) renderTrackGroup("Tracks", results, results.size(), null);
        else if ("all".equals(filter)) renderGroupedResults();
        else {
            boolean cards = "artists".equals(filter) || "playlists".equals(filter);
            for (DiscoveryItem item : results) content.addView(cards ? collectionRow(item) : "video".equals(item.kind) ? videoRow(item) : trackRow(item, playable(results)));
        }
        if (results.size() >= requestedLimit && requestedLimit < 60 && !loading) {
            gap(15); Button more = ui.button("Show more", false); more.setTag("discovery_more");
            more.setOnClickListener(v -> { requestedLimit = Math.min(60, requestedLimit + 20); request(false); }); content.addView(more);
        } else if (requestedLimit >= 60 && results.size() >= 60) { gap(12); content.addView(ui.label("Refine your search to find more.", 13, ui.secondary)); }
    }

    private View searchFilters() {
        HorizontalScrollView scroller = new HorizontalScrollView(activity); scroller.setHorizontalScrollBarEnabled(false); scroller.setClipToPadding(false);
        LinearLayout row = horizontal(); row.setGravity(Gravity.CENTER_VERTICAL);
        String[] keys = {"all", "songs", "videos", "artists", "playlists"}; String[] labels = {"All", "Songs", "Videos", "Artists", "Playlists"};
        for (int i = 0; i < keys.length; i++) {
            final String key = keys[i]; boolean selected = filter.equals(key);
            FrameLayout touch = new FrameLayout(activity); touch.setTag("search_filter_" + key); touch.setFocusable(true); touch.setClickable(true);
            touch.setSelected(selected); touch.setContentDescription(labels[i] + (selected ? ", selected" : ""));
            touch.setBackground(ui.interactiveSurface(Color.TRANSPARENT, 22));
            TextView label = ui.label(labels[i], 12, selected ? ui.accentText : ui.text); label.setGravity(Gravity.CENTER); label.setPadding(dp(14), 0, dp(14), 0);
            label.setBackground(ui.shape(selected ? ui.accent : ui.elevated, 20)); label.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            touch.addView(label, new FrameLayout.LayoutParams(-2, dp(34), Gravity.CENTER));
            LinearLayout.LayoutParams size = new LinearLayout.LayoutParams(-2, dp(48)); size.setMargins(0, 0, dp(6), 0); touch.setMinimumWidth(dp(54)); row.addView(touch, size);
            touch.setOnClickListener(v -> { filter = key; collection = null; requestedLimit = 20; results = new ArrayList<>(); submitted = clean(query); request(false); });
        }
        scroller.addView(row); return scroller;
    }

    private void renderGroupedResults() {
        DiscoveryItem feature = null;
        for (DiscoveryItem item : results) if ("playlist".equals(item.kind)) { feature = item; break; }
        if (feature != null) {
            final DiscoveryItem chosen = feature;
            FrameLayout tile = mediaTile(feature.title, feature.creator.isEmpty() ? "Playlist" : feature.creator + " · Playlist", feature.thumbnail, R.drawable.discovery_acoustic, 174,
                    () -> browse(chosen), () -> browse(chosen, true));
            tile.setTag("discovery_featured"); content.addView(tile, new LinearLayout.LayoutParams(-1, dp(174))); gap(16);
        }
        List<DiscoveryItem> songs = ofKind("song", "local"), videos = ofKind("video"), artists = ofKind("artist"), playlists = ofKind("playlist");
        if (!songs.isEmpty()) renderTrackGroup("Songs", songs, 3, () -> selectFilter("songs"));
        if (!videos.isEmpty()) { if (!songs.isEmpty()) gap(14); section("Videos", () -> selectFilter("videos")); gap(8); for (int i = 0; i < Math.min(2, videos.size()); i++) content.addView(videoRow(videos.get(i))); }
        if (!artists.isEmpty()) { gap(16); section("Artists", () -> selectFilter("artists")); gap(8); for (int i = 0; i < Math.min(3, artists.size()); i++) content.addView(collectionRow(artists.get(i))); }
        if (!playlists.isEmpty() && (feature == null || playlists.size() > 1)) {
            gap(16); section("Playlists", () -> selectFilter("playlists")); gap(8);
            for (DiscoveryItem item : playlists) { if (feature != null && item.key().equals(feature.key())) continue; content.addView(collectionRow(item)); }
        }
        if (songs.isEmpty() && videos.isEmpty() && artists.isEmpty() && playlists.isEmpty()) for (DiscoveryItem item : results) content.addView(trackRow(item, playable(results)));
    }

    private void renderTrackGroup(String label, List<DiscoveryItem> tracks, int count, Runnable more) {
        section(label, more); gap(5);
        List<DiscoveryItem> queue = playable(tracks);
        for (int i = 0; i < Math.min(count, tracks.size()); i++) content.addView(trackRow(tracks.get(i), queue));
    }

    private View trackRow(DiscoveryItem item, List<DiscoveryItem> queue) {
        LinearLayout row = horizontal(); row.setGravity(Gravity.CENTER_VERTICAL); row.setMinimumHeight(dp(70)); row.setPadding(0, dp(5), 0, dp(5));
        row.setTag("discovery_item_" + item.id); row.setBackground(ui.interactiveSurface(Color.TRANSPARENT, 12));
        ImageView art = artwork(item.thumbnail, fallback(item), 11); row.addView(art, new LinearLayout.LayoutParams(dp(60), dp(60)));
        LinearLayout words = ui.column(); words.setPadding(dp(14), 0, dp(4), 0);
        TextView title = ui.heading(item.title, 14); title.setMaxLines(2); title.setEllipsize(TextUtils.TruncateAt.END); words.addView(title); ui.gap(words, 4);
        String detail = item.creator;
        if (item.durationMs > 0) detail += (detail.isEmpty() ? "" : " · ") + time(item.durationMs);
        TextView subtitle = ui.label(detail, 12, ui.secondary); subtitle.setMaxLines(2); subtitle.setEllipsize(TextUtils.TruncateAt.END); words.addView(subtitle);
        row.addView(words, new LinearLayout.LayoutParams(0, -2, 1));
        Button options = icon("more", "More options for " + item.title, ui.secondary); options.setOnClickListener(v -> itemMenu(v, item, queue)); row.addView(options, new LinearLayout.LayoutParams(dp(42), dp(48)));
        row.setContentDescription(item.title + (item.creator.isEmpty() ? "" : ", " + item.creator)); row.setFocusable(true);
        row.setOnClickListener(v -> openItem(item, queue)); return row;
    }

    private View videoRow(DiscoveryItem item) {
        LinearLayout row = horizontal(); row.setGravity(Gravity.CENTER_VERTICAL); row.setPadding(0, dp(5), 0, dp(7)); row.setMinimumHeight(dp(92));
        row.setTag("discovery_item_" + item.id); row.setBackground(ui.interactiveSurface(Color.TRANSPARENT, 12));
        FrameLayout thumb = new FrameLayout(activity); thumb.setBackground(ui.shape(ui.elevated, 12)); thumb.setClipToOutline(true);
        ImageView image = artwork(item.thumbnail, R.drawable.discovery_acoustic, 12); thumb.addView(image, new FrameLayout.LayoutParams(-1, -1));
        if (item.durationMs > 0) { TextView duration = ui.label(time(item.durationMs), 11, Color.WHITE); duration.setPadding(dp(5), dp(2), dp(5), dp(2)); duration.setBackground(ui.shape(0xbb000000, 4)); FrameLayout.LayoutParams badge = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.END); badge.setMargins(0, 0, dp(5), dp(5)); thumb.addView(duration, badge); }
        row.addView(thumb, new LinearLayout.LayoutParams(dp(146), dp(86)));
        LinearLayout words = ui.column(); words.setPadding(dp(12), 0, 0, 0); TextView title = ui.heading(item.title, 13); title.setMaxLines(3); title.setEllipsize(TextUtils.TruncateAt.END); words.addView(title); ui.gap(words, 5);
        TextView creator = ui.label(item.creator, 12, ui.secondary); creator.setMaxLines(2); creator.setEllipsize(TextUtils.TruncateAt.END); words.addView(creator); row.addView(words, new LinearLayout.LayoutParams(0, -2, 1));
        Button more = icon("more", "More options for " + item.title, ui.secondary); more.setOnClickListener(v -> itemMenu(v, item, playable(results))); row.addView(more, new LinearLayout.LayoutParams(dp(32), dp(48)));
        row.setFocusable(true); row.setOnClickListener(v -> openItem(item, playable(results))); return row;
    }

    private View collectionRow(DiscoveryItem item) {
        LinearLayout row = horizontal(); row.setGravity(Gravity.CENTER_VERTICAL); row.setMinimumHeight(dp(76)); row.setPadding(0, dp(5), 0, dp(5)); row.setTag("discovery_item_" + item.id);
        row.setBackground(ui.interactiveSurface(Color.TRANSPARENT, 12)); ImageView art = artwork(item.thumbnail, R.drawable.discovery_acoustic, "artist".equals(item.kind) ? 32 : 10);
        row.addView(art, new LinearLayout.LayoutParams(dp(62), dp(62))); LinearLayout words = ui.column(); words.setPadding(dp(14), 0, dp(7), 0);
        TextView title = ui.heading(item.title, 15); title.setMaxLines(2); title.setEllipsize(TextUtils.TruncateAt.END); words.addView(title); ui.gap(words, 4);
        words.addView(ui.label(item.creator.isEmpty() ? kindLabel(item.kind) : item.creator, 12, ui.secondary)); row.addView(words, new LinearLayout.LayoutParams(0, -2, 1));
        ImageView chevron = new ImageView(activity); chevron.setImageDrawable(DiscoveryIcons.get(activity, "chevron", ui.secondary)); row.addView(chevron, new LinearLayout.LayoutParams(dp(24), dp(24)));
        row.setFocusable(true); row.setContentDescription("Open " + kindLabel(item.kind).toLowerCase(Locale.ROOT) + ", " + item.title); row.setOnClickListener(v -> browse(item)); return row;
    }

    private void submitInput() {
        String term = clean(query); if (term.isEmpty()) return;
        if (searchInput != null) { InputMethodManager keyboard = (InputMethodManager) activity.getSystemService(Activity.INPUT_METHOD_SERVICE); if (keyboard != null) keyboard.hideSoftInputFromWindow(searchInput.getWindowToken(), 0); searchInput.clearFocus(); }
        submitted = term; query = term; collection = null; backStack.clear(); requestedLimit = 20; results = new ArrayList<>(); request(false);
    }

    private void selectFilter(String chosen) { filter = validFilter(chosen); collection = null; requestedLimit = 20; results = new ArrayList<>(); request(false); }
    private void playCurated(String term) { home = false; query = submitted = term; filter = "Videos".equals(homeLane) ? "videos" : "songs"; collection = null; requestedLimit = 20; results = new ArrayList<>(); backStack.clear(); request(true); }

    private void browse(DiscoveryItem item) {
        browse(item, false);
    }

    private void browse(DiscoveryItem item, boolean playFirst) {
        if (!item.browsable()) { openItem(item, playable(results)); return; }
        backStack.push(new SearchState()); if (backStack.size() > 8) backStack.removeLast();
        collection = item; home = false; results = new ArrayList<>(); requestedLimit = 20; request(playFirst);
    }

    private void request(boolean playFirst) {
        cancelRequest(); home = false; submitted = clean(submitted.isEmpty() ? query : submitted); query = submitted;
        if (collection == null && submitted.isEmpty()) { renderSearch(); return; }
        final int currentGeneration = ++generation; final int previousScroll = requestedLimit > 20 ? scroll.getScrollY() : 0;
        loading = true; error = ""; renderSearch();
        DiscoveryRepository.Callback callback = (items, failure) -> {
            if (destroyed || currentGeneration != generation) return;
            requestToken = ""; loading = false; error = failure == null ? "" : failure;
            if (items != null && !items.isEmpty()) {
                LinkedHashMap<String, DiscoveryItem> merged = new LinkedHashMap<>();
                if (requestedLimit > 20) for (DiscoveryItem item : results) merged.put(item.key(), item);
                for (DiscoveryItem item : items) { if (item != null && merged.size() < 60) merged.put(item.key(), item); }
                results = new ArrayList<>(merged.values());
            } else if (error.isEmpty()) results = new ArrayList<>();
            renderSearch(); scroll.post(() -> scroll.scrollTo(0, previousScroll));
            if (playFirst && error.isEmpty()) { List<DiscoveryItem> queue = playable(results); if (!queue.isEmpty()) actions.onPlay(queue.get(0), queue); }
        };
        try { requestToken = collection == null ? repository.search(submitted, filter, requestedLimit, callback) : repository.browse(collection, requestedLimit, callback); }
        catch (RuntimeException failure) { loading = false; error = "Could not start this search. Try again."; renderSearch(); }
    }

    private void cancelRequest() { generation++; if (!requestToken.isEmpty()) repository.cancel(requestToken); requestToken = ""; loading = false; }
    private void openItem(DiscoveryItem item, List<DiscoveryItem> queue) { if (item.browsable()) browse(item); else actions.onPlay(item, queue.isEmpty() ? Collections.singletonList(item) : queue); }

    private void itemMenu(View anchor, DiscoveryItem item, List<DiscoveryItem> queue) {
        PopupMenu menu = new PopupMenu(activity, anchor);
        if (item.browsable()) menu.getMenu().add(0, 0, 0, "Open " + kindLabel(item.kind).toLowerCase(Locale.ROOT));
        else { menu.getMenu().add(0, 0, 0, "Play now"); menu.getMenu().add(0, 1, 1, "Download"); menu.getMenu().add(0, 2, 2, "Open in Studio"); }
        menu.getMenu().add(0, 3, 3, "Open original");
        menu.setOnMenuItemClickListener(choice -> { switch (choice.getItemId()) {
            case 0: openItem(item, queue); break;
            case 1: actions.onDownload(item, false); break;
            case 2: actions.onDownload(item, true); break;
            case 3: try { Uri uri = Uri.parse(item.url); if ("https".equalsIgnoreCase(uri.getScheme()) && uri.getUserInfo() == null) activity.startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (RuntimeException ignored) { android.widget.Toast.makeText(activity, "No app could open this source.", android.widget.Toast.LENGTH_SHORT).show(); } break;
        } return true; }); menu.show();
    }

    private FrameLayout editorial(String title, String caption, int art, int height, Runnable open, Runnable play) { return mediaTile(title, caption, "", art, height, open, play); }
    private FrameLayout mediaTile(String title, String caption, String url, int fallback, int height, Runnable open, Runnable play) {
        FrameLayout tile = new FrameLayout(activity); tile.setBackground(ui.shape(ui.elevated, 14)); tile.setClipToOutline(true); tile.setFocusable(true); tile.setOnClickListener(v -> open.run()); tile.setContentDescription(title + ", " + caption);
        ImageView photo = artwork(url, fallback, 14); tile.addView(photo, new FrameLayout.LayoutParams(-1, -1));
        View shade = new View(activity); shade.setBackground(new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{0x00000000, 0x11000000, 0xdc000000})); tile.addView(shade, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout labels = ui.column(); labels.setPadding(dp(16), dp(5), dp(height > 150 ? 62 : 12), dp(15));
        TextView name = ui.heading(title, height > 150 ? 18 : 14); name.setTextColor(Color.WHITE); name.setMaxLines(2); name.setEllipsize(TextUtils.TruncateAt.END); labels.addView(name); ui.gap(labels, 5);
        TextView description = ui.label(caption, height > 150 ? 13 : 10, Color.WHITE); description.setMaxLines(height > 150 ? 2 : 1); description.setEllipsize(TextUtils.TruncateAt.END); labels.addView(description);
        tile.addView(labels, new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM));
        Button button = icon("play", "Play " + title, height > 150 ? ui.accentText : Color.WHITE);
        button.setBackground(ui.interactiveSurface(height > 150 ? ui.accent : 0x88ffffff, 28));
        FrameLayout.LayoutParams buttonSize = new FrameLayout.LayoutParams(dp(height > 150 ? 48 : 34), dp(height > 150 ? 48 : 34), Gravity.BOTTOM | Gravity.END);
        buttonSize.setMargins(0, 0, dp(height > 150 ? 14 : 10), dp(height > 150 ? 17 : 31)); tile.addView(button, buttonSize); button.setOnClickListener(v -> play.run());
        return tile;
    }

    private ImageView artwork(String url, int fallback, int radius) { ImageView view = new ImageView(activity); view.setScaleType(ImageView.ScaleType.CENTER_CROP); view.setBackground(ui.shape(ui.elevated, radius)); view.setClipToOutline(true); view.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO); DiscoveryArtwork.load(view, url, fallback); return view; }
    private Button icon(String name, String description, int color) { Button button = new IconButton(name, color); ui.styleButton(button, false); button.setPadding(0, 0, 0, 0); button.setMinWidth(0); button.setMinimumWidth(0); button.setMinHeight(0); button.setMinimumHeight(0); button.setBackground(ui.interactiveSurface(Color.TRANSPARENT, 24)); button.setContentDescription(description); expandTouchTarget(button); return button; }
    private Button textButton(String text, int color, int fill, int radius) { Button button = ui.button(text, false); button.setTextSize(12); button.setTextColor(color); button.setMinHeight(0); button.setMinimumHeight(0); button.setPadding(dp(8), 0, dp(8), 0); button.setBackground(ui.interactiveSurface(fill, radius)); return button; }
    private LinearLayout horizontal() { LinearLayout row = new LinearLayout(activity); row.setOrientation(HORIZONTAL); return row; }
    private void section(String title, Runnable click) { LinearLayout row = horizontal(); row.setGravity(Gravity.CENTER_VERTICAL); row.addView(ui.heading(title, 20), new LinearLayout.LayoutParams(0, -2, 1)); if (click != null) { Button more = icon("chevron", "See all " + title.toLowerCase(Locale.ROOT), ui.secondary); more.setOnClickListener(v -> click.run()); LinearLayout.LayoutParams size = new LinearLayout.LayoutParams(dp(32), dp(32)); row.addView(more, size); } content.addView(row, new LinearLayout.LayoutParams(-1, -2)); }
    private List<DiscoveryItem> ofKind(String... kinds) { List<DiscoveryItem> values = new ArrayList<>(); for (DiscoveryItem item : results) for (String kind : kinds) if (kind.equals(item.kind)) { values.add(item); break; } return values; }
    private static List<DiscoveryItem> playable(List<DiscoveryItem> items) { List<DiscoveryItem> values = new ArrayList<>(); for (DiscoveryItem item : items) if (!item.browsable()) values.add(item); return values; }
    private static String validFilter(String value) { return "songs".equals(value) || "videos".equals(value) || "artists".equals(value) || "playlists".equals(value) ? value : "all"; }
    private static String clean(String value) { String text = value == null ? "" : value.trim(); if (text.length() <= 256) return text; int end = Character.isHighSurrogate(text.charAt(255)) ? 255 : 256; return text.substring(0, end); }
    private static String kindLabel(String kind) { if ("artist".equals(kind)) return "Artist"; if ("playlist".equals(kind)) return "Playlist"; if ("album".equals(kind)) return "Album"; return "Recording"; }
    private static String time(long value) { long seconds = Math.max(0, value) / 1000; return String.format(Locale.ROOT, "%d:%02d", seconds / 60, seconds % 60); }
    private int fallback(DiscoveryItem item) { String title = item.title.toLowerCase(Locale.ROOT); if (title.contains("jazz")) return R.drawable.discovery_jazz; if (title.contains("piano") || title.contains("keys")) return R.drawable.discovery_piano; if ("video".equals(item.kind)) return R.drawable.discovery_acoustic; return R.drawable.discovery_sunset; }
    private int dp(float value) { return ui.dp(value); }
    private void gap(float value) { ui.gap(content, value); }

    private void hideKeyboard() { InputMethodManager keyboard = (InputMethodManager) activity.getSystemService(Activity.INPUT_METHOD_SERVICE); if (keyboard != null) keyboard.hideSoftInputFromWindow(getWindowToken(), 0); }
    private void expandTouchTarget(View target) {
        target.post(() -> {
            if (!(target.getParent() instanceof View)) return;
            View parent = (View) target.getParent(); android.graphics.Rect bounds = new android.graphics.Rect(); target.getHitRect(bounds);
            int horizontal = Math.max(0, (dp(48) - bounds.width()) / 2), vertical = Math.max(0, (dp(48) - bounds.height()) / 2);
            bounds.inset(-horizontal, -vertical); parent.setTouchDelegate(new android.view.TouchDelegate(bounds, target));
        });
    }

    private final class IconButton extends Button {
        private final Drawable image;
        private IconButton(String name, int color) { super(ExploreView.this.activity); image = DiscoveryIcons.get(activity, name, color); }
        @Override protected void onDraw(Canvas canvas) { super.onDraw(canvas); int size = dp(23); int left = (getWidth() - size) / 2, top = (getHeight() - size) / 2; image.setBounds(left, top, left + size, top + size); image.setAlpha(isEnabled() ? 255 : 100); image.draw(canvas); }
    }

    private final class SearchState {
        private final String savedQuery, savedSubmitted, savedFilter, savedError;
        private final List<DiscoveryItem> savedResults;
        private final DiscoveryItem savedCollection;
        private final int scrollY, savedLimit;
        private SearchState() { savedQuery = query; savedSubmitted = submitted; savedFilter = filter; savedError = error; savedResults = new ArrayList<>(results); savedCollection = collection; scrollY = scroll.getScrollY(); savedLimit = requestedLimit; }
        private SearchState(JSONObject data) throws JSONException {
            savedQuery = clean(data.optString("query")); savedSubmitted = clean(data.optString("submitted")); savedFilter = validFilter(data.optString("filter")); savedError = "";
            savedResults = new ArrayList<>(); JSONArray items = data.optJSONArray("items");
            if (items != null) for (int i = 0; i < Math.min(60, items.length()); i++) savedResults.add(DiscoveryItem.fromJson(items.getJSONObject(i).toString()));
            savedCollection = data.has("collection") ? DiscoveryItem.fromJson(data.getJSONObject("collection").toString()) : null;
            scrollY = Math.max(0, data.optInt("scroll")); savedLimit = Math.max(20, Math.min(60, data.optInt("limit", 20)));
        }
        private JSONObject toJson() throws JSONException {
            JSONArray items = new JSONArray(); for (DiscoveryItem item : savedResults) items.put(new JSONObject(item.toJson()));
            JSONObject data = new JSONObject().put("query", savedQuery).put("submitted", savedSubmitted).put("filter", savedFilter).put("items", items).put("scroll", scrollY).put("limit", savedLimit);
            if (savedCollection != null) data.put("collection", new JSONObject(savedCollection.toJson())); return data;
        }
        private void apply() { home = false; query = savedQuery; submitted = savedSubmitted; filter = savedFilter; error = savedError; results = savedResults; collection = savedCollection; requestedLimit = savedLimit; }
    }
}
