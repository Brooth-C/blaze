package com.brooth.blaze;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import androidx.media3.ui.AspectRatioFrameLayout;
import androidx.media3.ui.PlayerView;
import org.json.JSONArray;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Native now-playing screen translated from the approved Blaze discovery reference. */
@androidx.annotation.OptIn(markerClass = androidx.media3.common.util.UnstableApi.class)
public final class NowPlayingActivity extends Activity {
    private BlazeUi ui;
    private PlaybackController playback;
    private ImageView artwork, nextArtwork;
    private PlayerView video;
    private TextView title, creator, elapsed, duration, nextTitle, nextCreator, quality, status;
    private ImageButton toggle, favorite, shuffle, repeat;
    private SeekBar seek;
    private LinearLayout nextCard;
    private FrameLayout mediaHost;
    private boolean scrubbing;
    private String renderedKey = "", renderedNext = "";
    private final PlaybackController.Listener listener = this::render;

    @Override public void onCreate(Bundle saved) {
        BlazeUi.apply(this); super.onCreate(saved);
        ui = new BlazeUi(this); playback = PlaybackController.get(this);
        acceptIntent(getIntent());
        LinearLayout shell = ui.column(); shell.setTag("now_playing"); shell.setBackgroundColor(ui.background);
        ui.inset(shell); setContentView(shell);

        LinearLayout header = new LinearLayout(this); header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(14), dp(5), dp(14), dp(4)); shell.addView(header);
        ImageButton back = icon("back", "Back", () -> finish()); header.addView(back, new LinearLayout.LayoutParams(dp(48), dp(48)));
        TextView caption = ui.label("NOW PLAYING", 10, ui.text); caption.setLetterSpacing(.14f); caption.setGravity(Gravity.CENTER);
        header.addView(caption, new LinearLayout.LayoutParams(0, -2, 1));
        ImageButton more = icon("more", "Playback options", () -> showMenu(header)); header.addView(more, new LinearLayout.LayoutParams(dp(48), dp(48)));

        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setClipToPadding(false);
        scroll.setVerticalScrollBarEnabled(false); shell.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout content = ui.column(); content.setPadding(dp(24), dp(8), dp(24), dp(12)); scroll.addView(content);

        mediaHost = new FrameLayout(this); mediaHost.setBackground(ui.shape(ui.elevated, 16)); mediaHost.setClipToOutline(true);
        LinearLayout.LayoutParams mediaSize = new LinearLayout.LayoutParams(dp(300), dp(300)); mediaSize.gravity = Gravity.CENTER_HORIZONTAL;
        content.addView(mediaHost, mediaSize);
        artwork = new ImageView(this); artwork.setTag("now_artwork"); artwork.setScaleType(ImageView.ScaleType.CENTER_CROP);
        artwork.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO); mediaHost.addView(artwork, new FrameLayout.LayoutParams(-1, -1));
        video = new PlayerView(this); video.setUseController(false); video.setResizeMode(AspectRatioFrameLayout.RESIZE_MODE_FIT);
        video.setBackgroundColor(Color.BLACK); video.setVisibility(View.GONE); video.setContentDescription("Video playback");
        mediaHost.addView(video, new FrameLayout.LayoutParams(-1, -1));
        content.addOnLayoutChangeListener((view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) -> {
            int available = content.getWidth() - dp(48);
            if (available <= 0) return;
            int side = Math.min(dp(420), Math.max(dp(160), available - dp(48)));
            if (getResources().getConfiguration().orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE) side = Math.min(side, dp(240));
            android.view.ViewGroup.LayoutParams params = mediaHost.getLayoutParams();
            if (params.width != side || params.height != side) { params.width = side; params.height = side; mediaHost.setLayoutParams(params); }
        });
        gap(content, 18);

        LinearLayout identity = new LinearLayout(this); identity.setGravity(Gravity.CENTER_VERTICAL); content.addView(identity);
        LinearLayout names = ui.column(); identity.addView(names, new LinearLayout.LayoutParams(0, -2, 1));
        title = ui.heading("Choose a recording", 25); title.setTag("now_title"); title.setMaxLines(2); title.setEllipsize(TextUtils.TruncateAt.END); names.addView(title);
        creator = ui.label("", 14, ui.secondary); creator.setMaxLines(2); creator.setEllipsize(TextUtils.TruncateAt.END); margin(creator, 4, 0); names.addView(creator);
        favorite = icon("heart", "Add to favourites", () -> playback.toggleFavorite(playback.current())); favorite.setTag("now_favorite");
        identity.addView(favorite, new LinearLayout.LayoutParams(dp(48), dp(48)));
        gap(content, 8);

        seek = new SeekBar(this); seek.setTag("now_seek"); seek.setMax(1000); seek.setProgressTintList(ColorStateList.valueOf(ui.accent));
        seek.setThumbTintList(ColorStateList.valueOf(ui.accent)); seek.setPadding(0, 0, 0, 0); seek.setContentDescription("Playback position");
        content.addView(seek, new LinearLayout.LayoutParams(-1, dp(30)));
        LinearLayout times = new LinearLayout(this); content.addView(times);
        elapsed = ui.label("0:00", 11, ui.secondary); duration = ui.label("0:00", 11, ui.secondary); duration.setGravity(Gravity.END);
        times.addView(elapsed, new LinearLayout.LayoutParams(0, -2, 1)); times.addView(duration, new LinearLayout.LayoutParams(0, -2, 1));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onStartTrackingTouch(SeekBar bar) { scrubbing = true; }
            @Override public void onStopTrackingTouch(SeekBar bar) { playback.seekTo(Math.round(playback.duration() * (bar.getProgress() / 1000.0))); scrubbing = false; render(); }
            @Override public void onProgressChanged(SeekBar bar, int progress, boolean user) { if (user) elapsed.setText(time(Math.round(playback.duration() * progress / 1000.0))); }
        });
        gap(content, 4);

        LinearLayout controls = new LinearLayout(this); controls.setGravity(Gravity.CENTER_VERTICAL); content.addView(controls, new LinearLayout.LayoutParams(-1, dp(96)));
        shuffle = icon("shuffle", "Shuffle off", () -> playback.setShuffle(!playback.shuffle())); shuffle.setTag("now_shuffle"); controls.addView(shuffle, new LinearLayout.LayoutParams(0, dp(48), 1));
        ImageButton previous = icon("previous", "Previous recording", () -> playback.previous()); previous.setTag("now_previous"); controls.addView(previous, new LinearLayout.LayoutParams(0, dp(48), 1));
        toggle = icon("play", "Play", () -> playback.toggle()); toggle.setTag("now_toggle"); toggle.setPadding(dp(23), dp(23), dp(23), dp(23));
        toggle.setScaleType(ImageView.ScaleType.FIT_CENTER); toggle.setBackground(ui.interactiveSurface(ui.accent, 100));
        controls.addView(toggle, new LinearLayout.LayoutParams(dp(78), dp(78)));
        ImageButton next = icon("next", "Next recording", () -> playback.next()); next.setTag("now_next"); controls.addView(next, new LinearLayout.LayoutParams(0, dp(48), 1));
        repeat = icon("repeat", "Repeat off", () -> playback.setRepeat(!playback.repeat())); repeat.setTag("now_repeat"); controls.addView(repeat, new LinearLayout.LayoutParams(0, dp(48), 1));

        LinearLayout actions = new LinearLayout(this); content.addView(actions);
        Button download = action("Download", "download", () -> { DiscoveryItem item = playback.current(); if (item != null) DownloadCoordinator.showOptions(this, item, false); });
        download.setTag("now_download"); LinearLayout.LayoutParams downloadSize = new LinearLayout.LayoutParams(0, -2, 1); downloadSize.setMarginEnd(dp(6)); actions.addView(download, downloadSize);
        Button studio = action("Open in Studio", "studio", this::openStudio); studio.setTag("now_studio");
        LinearLayout.LayoutParams studioSize = new LinearLayout.LayoutParams(0, -2, 1); studioSize.setMarginStart(dp(6)); actions.addView(studio, studioSize);
        gap(content, 16);

        nextCard = ui.column(); nextCard.setTag("now_up_next"); nextCard.setPadding(dp(16), dp(12), dp(12), dp(12));
        nextCard.setBackground(ui.shape(ui.surface, 18)); content.addView(nextCard);
        TextView upNext = ui.heading("Up next", 18); nextCard.addView(upNext); gap(nextCard, 10);
        LinearLayout nextRow = new LinearLayout(this); nextRow.setGravity(Gravity.CENTER_VERTICAL); nextCard.addView(nextRow);
        nextArtwork = new ImageView(this); nextArtwork.setScaleType(ImageView.ScaleType.CENTER_CROP); nextArtwork.setBackground(ui.shape(ui.elevated, 7)); nextArtwork.setClipToOutline(true);
        nextArtwork.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO); nextRow.addView(nextArtwork, new LinearLayout.LayoutParams(dp(50), dp(50)));
        LinearLayout nextNames = ui.column(); LinearLayout.LayoutParams nextNamesSize = new LinearLayout.LayoutParams(0, -2, 1); nextNamesSize.setMarginStart(dp(12)); nextRow.addView(nextNames, nextNamesSize);
        nextTitle = ui.heading("Your queue is clear", 13); nextTitle.setMaxLines(2); nextTitle.setEllipsize(TextUtils.TruncateAt.END); nextNames.addView(nextTitle);
        nextCreator = ui.label("Find something in Explore", 11, ui.secondary); nextCreator.setMaxLines(1); nextCreator.setEllipsize(TextUtils.TruncateAt.END); nextNames.addView(nextCreator);
        ImageButton queue = icon("queue", "Show playback queue", this::showQueue); nextRow.addView(queue, new LinearLayout.LayoutParams(dp(48), dp(48)));
        nextRow.setOnClickListener(view -> { if (playback.upNext() != null) playback.next(); });
        gap(content, 10);
        quality = ui.label("Audio · Original quality", 11, ui.secondary); quality.setGravity(Gravity.CENTER);
        android.graphics.drawable.Drawable wave = DiscoveryIcons.get(this, "studio", ui.secondary); wave.setBounds(0, 0, dp(14), dp(14));
        quality.setCompoundDrawables(wave, null, null, null); quality.setCompoundDrawablePadding(dp(6)); content.addView(quality, new LinearLayout.LayoutParams(-1, dp(28)));
        status = ui.label("", 13, ui.secondary); status.setTag("now_status"); status.setGravity(Gravity.CENTER); status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE); content.addView(status); status.setVisibility(View.GONE);

        shell.addView(ui.divider(), new LinearLayout.LayoutParams(-1, Math.max(1, dp(.5f))));
        LinearLayout navigation = new LinearLayout(this); navigation.setPadding(dp(8), 0, dp(8), 0); navigation.setGravity(Gravity.CENTER_VERTICAL); shell.addView(navigation);
        for (String destination : new String[]{"explore", "downloads", "library", "studio"}) {
            String text = destination.substring(0, 1).toUpperCase(Locale.ROOT) + destination.substring(1);
            Button tab = ui.button(text, false); tab.setTag("now_nav_" + destination); tab.setTextSize(10);
            tab.setTypeface(android.graphics.Typeface.create("sans-serif", android.graphics.Typeface.NORMAL));
            tab.setMinHeight(dp(60)); tab.setMinimumHeight(dp(60)); tab.setMinWidth(0); tab.setMinimumWidth(0);
            tab.setPadding(dp(2), dp(5), dp(2), dp(5)); tab.setCompoundDrawablePadding(dp(3));
            int color = destination.equals("explore") ? ui.accent : ui.secondary; tab.setTextColor(color);
            tab.setCompoundDrawablesWithIntrinsicBounds(null, DiscoveryIcons.get(this, destination.equals("downloads") ? "download" : destination, color), null, null);
            tab.setBackground(ui.interactiveSurface(Color.TRANSPARENT, 12)); tab.setOnClickListener(view -> navigate(destination));
            navigation.addView(tab, new LinearLayout.LayoutParams(0, -2, 1));
        }
        render();
    }

    @Override protected void onNewIntent(Intent intent) { super.onNewIntent(intent); setIntent(intent); acceptIntent(intent); render(); }
    private void acceptIntent(Intent intent) {
        String encoded = intent.getStringExtra("item");
        if (encoded == null || encoded.isEmpty()) return;
        try {
            DiscoveryItem selected = DiscoveryItem.fromJson(encoded);
            if (playback.current() != null && playback.current().key().equals(selected.key())) return;
            List<DiscoveryItem> queue = new ArrayList<>(); String rawQueue = intent.getStringExtra("queue");
            if (rawQueue != null && rawQueue.length() <= 262144) {
                JSONArray items = new JSONArray(rawQueue);
                for (int i = 0; i < Math.min(items.length(), 100); i++) queue.add(DiscoveryItem.fromJson(items.getJSONObject(i).toString()));
            }
            playback.play(selected, queue);
        } catch (Exception ignored) { /* Invalid optional navigation data cannot start arbitrary playback. */ }
    }

    private void render() {
        if (ui == null || playback == null || title == null || isFinishing()) return;
        DiscoveryItem item = playback.current();
        if (item == null) {
            renderedKey = ""; renderedNext = "";
            video.setPlayer(null); video.setVisibility(View.GONE); artwork.setVisibility(View.VISIBLE);
            title.setText("Choose a recording"); creator.setText("Find videos and music in Explore");
            DiscoveryArtwork.load(artwork, "", R.drawable.discovery_sunset); toggle.setEnabled(false); favorite.setEnabled(false); seek.setEnabled(false);
            toggle.setImageDrawable(DiscoveryIcons.get(this, "play", ui.accentText)); toggle.setContentDescription("Play");
            seek.setProgress(0); elapsed.setText("0:00"); duration.setText("0:00");
            nextTitle.setText("Your queue is clear"); nextCreator.setText("Find something in Explore"); nextArtwork.setVisibility(View.GONE);
            status.setVisibility(View.GONE);
            return;
        }
        toggle.setEnabled(true); favorite.setEnabled(true); seek.setEnabled(playback.duration() > 0);
        if (!renderedKey.equals(item.key())) {
            renderedKey = item.key(); title.setText(item.title); creator.setText(item.creator);
            DiscoveryArtwork.load(artwork, item.thumbnail, R.drawable.discovery_sunset);
        }
        boolean watching = item.kind.equals("video");
        video.setVisibility(watching ? View.VISIBLE : View.GONE); artwork.setVisibility(watching ? View.GONE : View.VISIBLE);
        if (video.getPlayer() != (watching ? playback.player() : null)) video.setPlayer(watching ? playback.player() : null);
        boolean playing = playback.isPlaying();
        toggle.setImageDrawable(DiscoveryIcons.get(this, playing ? "pause" : "play", ui.accentText));
        toggle.setContentDescription(playing || (playback.isLoading() && playback.wantsPlayback()) ? "Pause" : "Play");
        boolean liked = playback.isFavorite(item);
        favorite.setImageDrawable(DiscoveryIcons.get(this, liked ? "heart_filled" : "heart", liked ? ui.accent : ui.text));
        favorite.setContentDescription(liked ? "Remove from favourites" : "Add to favourites");
        shuffle.setImageDrawable(DiscoveryIcons.get(this, "shuffle", playback.shuffle() ? ui.accent : ui.text));
        shuffle.setContentDescription(playback.shuffle() ? "Shuffle on" : "Shuffle off");
        repeat.setImageDrawable(DiscoveryIcons.get(this, "repeat", playback.repeat() ? ui.accent : ui.text));
        repeat.setContentDescription(playback.repeat() ? "Repeat current recording on" : "Repeat off");
        if (!scrubbing) {
            long position = playback.position(), length = playback.duration();
            seek.setProgress(length > 0 ? (int)Math.min(1000, position * 1000 / length) : 0);
            elapsed.setText(time(position)); duration.setText(time(length));
        }
        DiscoveryItem next = playback.upNext();
        if (next == null) { nextTitle.setText("Your queue is clear"); nextCreator.setText("Find something in Explore"); nextArtwork.setVisibility(View.GONE); }
        else {
            nextArtwork.setVisibility(View.VISIBLE); nextTitle.setText(next.title); nextCreator.setText(next.creator);
            if (!renderedNext.equals(next.key())) { renderedNext = next.key(); DiscoveryArtwork.load(nextArtwork, next.thumbnail, R.drawable.discovery_acoustic); }
        }
        quality.setText(watching ? "Video · Source quality" : "Audio · Original quality");
        String detail = playback.error();
        if (detail == null || detail.isEmpty()) detail = playback.isLoading() ? "Opening recording…" : "";
        if (!detail.contentEquals(status.getText())) status.setText(detail);
        status.setVisibility(detail.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private void openStudio() {
        DiscoveryItem item = playback.current(); if (item == null) return;
        if (!item.localJobId.isEmpty()) {
            try {
                PlaybackSource.load(this, item.localJobId); playback.pause();
                startActivity(new Intent(this, MusicStudioActivity.class).putExtra("job", item.localJobId));
            } catch (Exception error) { new AlertDialog.Builder(this).setTitle("Saved recording unavailable").setMessage("The local file is missing. Save a copy again before opening Studio.").setPositiveButton("Close", null).show(); }
        } else DownloadCoordinator.showOptions(this, item, true);
    }
    private void showMenu(View anchor) {
        PopupMenu menu = new PopupMenu(this, anchor); menu.getMenu().add(0, 1, 0, "Show queue"); menu.getMenu().add(0, 2, 1, "Stop playback");
        menu.setOnMenuItemClickListener(item -> { if (item.getItemId() == 1) showQueue(); else { playback.stop(); finish(); } return true; }); menu.show();
    }
    private void showQueue() {
        List<DiscoveryItem> queue = playback.queue();
        if (queue.isEmpty()) { new AlertDialog.Builder(this).setTitle("Your queue is clear").setMessage("Choose a recording in Explore to start listening.").setPositiveButton("Close", null).show(); return; }
        String[] names = new String[queue.size()]; for (int i = 0; i < names.length; i++) names[i] = queue.get(i).title;
        new AlertDialog.Builder(this).setTitle("Playback queue").setItems(names, (dialog, which) -> playback.play(queue.get(which), queue)).setNegativeButton("Close", null).show();
    }
    private void navigate(String destination) {
        if (destination.equals("studio")) playback.pause();
        startActivity(new Intent(this, MainActivity.class).putExtra("destination", destination).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP)); finish();
    }
    private ImageButton icon(String name, String description, Runnable action) {
        ImageButton button = new ImageButton(this); button.setImageDrawable(DiscoveryIcons.get(this, name, ui.text));
        button.setScaleType(ImageView.ScaleType.CENTER); button.setPadding(dp(12), dp(12), dp(12), dp(12));
        button.setBackground(ui.interactiveSurface(Color.TRANSPARENT, 100)); button.setContentDescription(description); button.setOnClickListener(view -> action.run()); return button;
    }
    private Button action(String text, String glyph, Runnable click) {
        Button button = ui.button(text, false); button.setTextSize(12); button.setTextColor(ui.accent);
        button.setPadding(dp(10), dp(10), dp(10), dp(10)); button.setCompoundDrawablePadding(dp(8));
        button.setCompoundDrawablesWithIntrinsicBounds(DiscoveryIcons.get(this, glyph, ui.accent), null, null, null);
        button.setBackground(ui.interactiveSurface(ui.softAccent, 20)); button.setOnClickListener(view -> click.run()); return button;
    }
    private void gap(LinearLayout parent, int value) { ui.gap(parent, value); }
    private void margin(View view, int top, int bottom) { LinearLayout.LayoutParams size = new LinearLayout.LayoutParams(-1, -2); size.topMargin = dp(top); size.bottomMargin = dp(bottom); view.setLayoutParams(size); }
    private int dp(float value) { return ui.dp(value); }
    private static String time(long millis) { long seconds = Math.max(0, millis) / 1000; return seconds >= 3600 ? String.format(Locale.ROOT, "%d:%02d:%02d", seconds/3600, (seconds/60)%60, seconds%60) : String.format(Locale.ROOT, "%d:%02d", seconds/60, seconds%60); }
    @Override protected void onStart() { super.onStart(); playback.addListener(listener); }
    @Override protected void onStop() { playback.removeListener(listener); video.setPlayer(null); super.onStop(); }
}
