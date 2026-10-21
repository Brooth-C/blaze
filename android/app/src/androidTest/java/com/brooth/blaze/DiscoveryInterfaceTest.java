package com.brooth.blaze;

import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiModeManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.graphics.drawable.GradientDrawable;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.TextView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry;
import androidx.test.runner.lifecycle.Stage;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;
import java.util.function.Consumer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Real native views and playback, with a deterministic catalogue and queue-owned synthetic audio. */
@RunWith(AndroidJUnit4.class)
public class DiscoveryInterfaceTest {
    private final Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
    private final Context app = instrumentation.getTargetContext();
    private final List<String> jobs = new ArrayList<>();
    private DiscoveryItem golden, quiet, stay, playlist, video;
    private FixtureBackend backend;

    @Before public void fixtures() throws Exception {
        onMain(() -> PlaybackController.get(app).stop());
        assertFalse("Use an idle disposable emulator", DownloadService.busy);
        try (JobStore store = new JobStore(app)) {
            assertEquals("Fixtures require an empty pending queue", 0, store.count(0));
        }
        golden = saved("BlazeRef001", "Golden Hour", "The Northlights", 222);
        quiet = saved("BlazeRef002", "Quiet Roads", "Mira Lane", 248);
        stay = new DiscoveryItem("BlazeRef003", "song", "Stay a Little", "Juniper",
            "https://www.youtube.com/watch?v=BlazeRef003", "", 196000);
        playlist = new DiscoveryItem("PL_BLAZE_REFERENCE", "playlist", "Acoustic Sessions", "Live performances",
            "https://www.youtube.com/playlist?list=PL_BLAZE_REFERENCE", "", -1);
        video = new DiscoveryItem("BlazeRef004", "video", "An intimate live session", "Juniper",
            "https://www.youtube.com/watch?v=BlazeRef004", "", 1104000);
        backend = new FixtureBackend();
        DiscoveryRepository.setTestBackend(backend);
    }

    @After public void cleanup() throws Exception {
        onMain(() -> {
            PlaybackController.get(app).stop();
            for (Stage stage : new Stage[]{Stage.RESUMED, Stage.STARTED, Stage.CREATED}) {
                for (Activity activity : new ArrayList<>(ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(stage))) {
                    if (activity instanceof NowPlayingActivity || activity instanceof MusicStudioActivity) activity.finish();
                }
            }
        });
        DiscoveryRepository.clearTestBackend();
        try (JobStore store = new JobStore(app)) {
            for (String id : jobs) {
                JobStore.Job job = store.completed(id);
                if (job != null) store.deleteCompleted(id, DownloadService.folder(app));
                store.getWritableDatabase().delete("jobs", "id=?", new String[]{id});
            }
        }
    }

    @Test public void referenceScreensConnectSearchRealPlaybackAndStudio() throws Exception {
        String size = override(shell("wm size"), "size");
        String density = override(shell("wm density"), "density");
        String font = shell("settings get system font_scale").trim();
        int night = app.getSystemService(UiModeManager.class).getNightMode();
        try {
            shell("wm size 1080x2400"); shell("wm density 420");
            shell("settings put system font_scale 1.0"); setNight("no");
            try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
                screen.onActivity(activity -> activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
                onMain(() -> PlaybackController.get(app).play(golden, Arrays.asList(golden, quiet)));
                awaitPlayback(golden, true);
                onMain(() -> PlaybackController.get(app).seekTo(84000));
                waitMain("Seek did not reach the recording", () -> PlaybackController.get(app).position() >= 83000);
                screen.onActivity(activity -> explore(activity).showHome());
                waitScreen(screen, "Home did not show the actual listening history", activity -> text(activity).contains("Golden Hour"));
                screen.onActivity(activity -> {
                    visible(tagged(activity, "mini_toggle"), true);
                    visible(tagged(activity, "mini_next"), true);
                    tagged(activity, "mini_toggle").performClick();
                });
                waitMain("Mini-player did not pause the actual recording", () -> !PlaybackController.get(app).isPlaying());
                screen.onActivity(activity -> tagged(activity, "mini_toggle").performClick());
                awaitPlayback(golden, true);
                awaitFrames(screen);
                screenshot("Blaze-Android-Explore.png");

                screen.onActivity(activity -> explore(activity).showSearch("acoustic sessions"));
                waitScreen(screen, "Search did not show the injected catalogue", activity -> tagged(activity, "discovery_item_" + golden.id) != null
                    && tagged(activity, "discovery_item_" + video.id) != null);
                screen.onActivity(activity -> {
                    assertEquals("acoustic sessions", ((EditText)tagged(activity, "discovery_search")).getText().toString());
                    assertNotNull(tagged(activity, "search_filter_all"));
                    assertNotNull(tagged(activity, "discovery_item_" + golden.id));
                });
                awaitFrames(screen);
                screenshot("Blaze-Android-Search.png");
                screen.onActivity(activity -> tagged(activity, "discovery_item_" + golden.id).performClick());
                withForeground(NowPlayingActivity.class, activity -> assertEquals("Golden Hour", ((TextView)tagged(activity, "now_title")).getText().toString()));
                awaitPlayback(golden, true);
                onMain(() -> assertEquals("Search did not reuse the verified saved recording", golden.localJobId,
                    PlaybackController.get(app).current().localJobId));
                withForeground(NowPlayingActivity.class, activity -> tagged(activity, "now_toggle").performClick());
                waitMain("Pause did not reach the player", () -> !PlaybackController.get(app).isPlaying());
                seekWithTouch(.38f);
                waitMain("The seek bar did not change the actual recording position", () -> PlaybackController.get(app).position() > 75000
                    && PlaybackController.get(app).position() < 95000);
                onMain(() -> PlaybackController.get(app).seekTo(84000));
                waitMain("Paused seek was not retained", () -> Math.abs(PlaybackController.get(app).position() - 84000) < 2000);
                withForeground(NowPlayingActivity.class, activity -> tagged(activity, "now_toggle").performClick());
                awaitPlayback(golden, true);
                waitMain("Wrong synthetic recording duration", () -> Math.abs(PlaybackController.get(app).duration() - 222000) < 1000);
                withForeground(NowPlayingActivity.class, activity -> {
                    visible(tagged(activity, "now_toggle"), true);
                    visible(tagged(activity, "now_download"), true);
                    visible(tagged(activity, "now_studio"), true);
                });
                waitForegroundFrames(NowPlayingActivity.class);
                screenshot("Blaze-Android-Now-Playing.png");

                withForeground(NowPlayingActivity.class, activity -> tagged(activity, "now_next").performClick());
                awaitPlayback(quiet, true);
                waitMain("Next did not load the second recording", () -> Math.abs(PlaybackController.get(app).duration() - 248000) < 1000);
                withForeground(NowPlayingActivity.class, activity -> tagged(activity, "now_studio").performClick());
                withForeground(MusicStudioActivity.class, activity -> {
                    assertNotNull("Studio lost the queue-owned source", activity.source);
                    assertEquals(quiet.localJobId, activity.source.id);
                });
                waitMain("Remote session kept playing over Studio", () -> !PlaybackController.get(app).isPlaying());
            }
            assertEquals("Local playback unexpectedly used a remote resolver", 0, backend.resolves);
        } finally {
            onMain(() -> PlaybackController.get(app).stop());
            shell("wm size " + size); shell("wm density " + density);
            shell("settings put system font_scale " + fontValue(font)); restoreNight(night);
        }
    }

    @Test public void changedSearchDiscardsLateResultsAndShowsRecoverableErrors() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            screen.onActivity(activity -> explore(activity).showSearch("slow query"));
            assertTrue("Slow fixture never started", backend.slowEntered.await(4, TimeUnit.SECONDS));
            screen.onActivity(activity -> explore(activity).showSearch("acoustic sessions"));
            waitScreen(screen, "New search result never appeared", activity -> tagged(activity, "discovery_item_" + golden.id) != null);
            backend.releaseSlow.countDown();
            assertTrue("Slow fixture did not finish", backend.slowFinished.await(4, TimeUnit.SECONDS));
            instrumentation.waitForIdleSync();
            screen.onActivity(activity -> {
                assertFalse("Old search overwrote the current result", text(activity).contains("Outdated result"));
                assertEquals("acoustic sessions", ((EditText)tagged(activity, "discovery_search")).getText().toString());
                tagged(activity, "search_filter_songs").performClick();
            });
            waitScreen(screen, "Songs filter did not settle", activity -> tagged(activity, "search_filter_songs").isSelected());
            screen.recreate();
            waitScreen(screen, "Search state lost after recreation", activity -> tagged(activity, "discovery_item_" + golden.id) != null
                && "acoustic sessions".equals(((EditText)tagged(activity, "discovery_search")).getText().toString())
                && tagged(activity, "search_filter_songs").isSelected());
            screen.onActivity(activity -> explore(activity).showSearch("offline fixture"));
            waitScreen(screen, "Provider failure disappeared into an empty state", activity -> tagged(activity, "discovery_error") != null
                && tagged(activity, "discovery_error").isShown() && tagged(activity, "discovery_retry") != null);
            screen.onActivity(activity -> {
                assertNull("A failed provider was shown as a successful empty query", tagged(activity, "discovery_empty"));
                backend.fail = false;
                tagged(activity, "discovery_retry").performClick();
            });
            waitScreen(screen, "Retry did not restore results", activity -> tagged(activity, "discovery_item_" + golden.id) != null
                && tagged(activity, "discovery_error") == null);
        } finally { backend.releaseSlow.countDown(); }
    }

    @Test public void discoveredRecordingUsesPausedQueueAndKeepsDuplicateIdentity() throws Exception {
        boolean paused = app.getSharedPreferences("queue", Context.MODE_PRIVATE).getBoolean("paused", false);
        List<String> added = new ArrayList<>();
        app.getSharedPreferences("queue", Context.MODE_PRIVATE).edit().putBoolean("paused", true).commit();
        try (JobStore store = new JobStore(app);
             ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            for (int attempt = 0; attempt < 2; attempt++) {
                screen.onActivity(activity -> DownloadCoordinator.showOptions(activity, stay, false));
                clickDialogText("Add to queue");
                waitFor("Save did not enter the existing queue", () -> store.count(0) == 1);
                List<JobStore.Job> pending = store.page(0, 0);
                assertEquals(1, pending.size());
                if (added.isEmpty()) added.add(pending.get(0).id);
                assertEquals("Duplicate tap created another queue identity", added.get(0), pending.get(0).id);
                assertEquals(stay.url, pending.get(0).url);
                assertEquals("queued", pending.get(0).state);
                assertFalse("Adding to a paused queue started a worker", DownloadService.busy);
                assertTrue(app.getSharedPreferences("queue", Context.MODE_PRIVATE).getBoolean("paused", false));
            }
            DownloadCoordinator.Result audio = DownloadCoordinator.enqueue(app, stay, "audio", "720", "original", false);
            assertTrue("A hidden video quality duplicated the audio request", audio.existing);
            assertEquals(added.get(0), audio.jobId);
            assertEquals(1, store.count(0));
            DownloadCoordinator.Result firstVideo = DownloadCoordinator.enqueue(app, stay, "video", "720", "original", false);
            DownloadCoordinator.Result sameVideo = DownloadCoordinator.enqueue(app, stay, "video", "720", "flac", false);
            assertNotEquals("Audio and video must keep distinct queue identities", audio.jobId, firstVideo.jobId);
            assertTrue("A hidden audio codec duplicated the video request", sameVideo.existing);
            assertEquals(firstVideo.jobId, sameVideo.jobId);
            assertTrue(audio.paused && firstVideo.paused && sameVideo.paused);
            assertEquals(2, store.count(0));
            assertFalse("Paused admission started a worker", DownloadService.busy);
        } finally {
            try (JobStore store = new JobStore(app)) {
                for (JobStore.Job job : store.page(0, 0)) if (job.url.equals(stay.url)) {
                    store.removeQueued(job.id, DownloadService.folder(app));
                    app.getSharedPreferences("discovery-saves", Context.MODE_PRIVATE).edit().remove("item:" + job.id).remove("studio:" + job.id).commit();
                }
            }
            app.getSharedPreferences("queue", Context.MODE_PRIVATE).edit().putBoolean("paused", paused).commit();
        }
    }

    @Test public void darkLargeTextKeepsSearchAndPlaybackActionsReachable() throws Exception {
        String font = shell("settings get system font_scale").trim();
        int night = app.getSystemService(UiModeManager.class).getNightMode();
        try {
            shell("settings put system font_scale 1.5"); setNight("yes");
            try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
                screen.onActivity(activity -> explore(activity).showSearch("acoustic sessions"));
                waitScreen(screen, "Large-text search did not finish", activity -> tagged(activity, "discovery_item_" + golden.id) != null
                    && new BlazeUi(activity).dark && activity.getResources().getConfiguration().fontScale >= 1.49f);
                screen.onActivity(activity -> {
                    assertTrue("Dark resources were not applied", new BlazeUi(activity).dark);
                    visible(tagged(activity, "discovery_search"), true);
                    visible(tagged(activity, "nav_explore"), true);
                });
                awaitFrames(screen); screenshot("Blaze-Android-Search-Dark.png");
                onMain(() -> PlaybackController.get(app).play(golden, Arrays.asList(golden, quiet)));
                awaitPlayback(golden, true);
                try (ActivityScenario<NowPlayingActivity> player = ActivityScenario.launch(new Intent(app, NowPlayingActivity.class))) {
                    waitScreen(player, "Now Playing never displayed its source", activity -> tagged(activity, "now_toggle") != null);
                    player.onActivity(activity -> {
                        assertTrue(new BlazeUi(activity).dark);
                        tagged(activity, "now_toggle").requestRectangleOnScreen(new Rect(0, 0,
                            tagged(activity, "now_toggle").getWidth(), tagged(activity, "now_toggle").getHeight()), true);
                    });
                    awaitFrames(player);
                    player.onActivity(activity -> visible(tagged(activity, "now_toggle"), true));
                    player.onActivity(activity -> tagged(activity, "now_studio").requestRectangleOnScreen(new Rect(0, 0,
                        tagged(activity, "now_studio").getWidth(), tagged(activity, "now_studio").getHeight()), true));
                    awaitFrames(player);
                    player.onActivity(activity -> {
                        visible(tagged(activity, "now_download"), true);
                        visible(tagged(activity, "now_studio"), true);
                    });
                    screenshot("Blaze-Android-Now-Playing-Large-Text.png");
                }
            }
        } finally {
            shell("settings put system font_scale " + fontValue(font)); restoreNight(night);
        }
    }

    private final class FixtureBackend implements DiscoveryRepository.Backend {
        final CountDownLatch slowEntered = new CountDownLatch(1), releaseSlow = new CountDownLatch(1), slowFinished = new CountDownLatch(1);
        volatile boolean fail = true;
        volatile int resolves;
        @Override public List<DiscoveryItem> search(String query, String filter, int limit) throws Exception {
            if (query.equals("slow query")) {
                slowEntered.countDown();
                try { releaseSlow.await(4, TimeUnit.SECONDS); } catch (InterruptedException ignored) { /* Model a transport that returns after cancellation. */ }
                finally { slowFinished.countDown(); }
                return Collections.singletonList(new DiscoveryItem("BlazeRef099", "song", "Outdated result", "Fixture",
                    "https://www.youtube.com/watch?v=BlazeRef099", "", 1000));
            }
            if (query.equals("offline fixture") && fail) throw new java.io.IOException("Synthetic provider failure");
            if (filter.equals("songs")) return tracks();
            if (filter.equals("videos")) return Collections.singletonList(video);
            if (filter.equals("artists")) return Collections.singletonList(new DiscoveryItem("UC_BLAZE_REFERENCE", "artist", "The Northlights", "Artist",
                "https://www.youtube.com/channel/UC_BLAZE_REFERENCE", "", -1));
            if (filter.equals("playlists")) return Collections.singletonList(playlist);
            return Arrays.asList(playlist, catalogue(golden), catalogue(quiet), stay, video);
        }
        @Override public List<DiscoveryItem> browse(DiscoveryItem item, int limit) { return tracks(); }
        private List<DiscoveryItem> tracks() { return Arrays.asList(catalogue(golden), catalogue(quiet), stay); }
        private DiscoveryItem catalogue(DiscoveryItem item) {
            return new DiscoveryItem(item.id, item.kind, item.title, item.creator, item.url, item.thumbnail, item.durationMs);
        }
        @Override public DiscoveryRepository.Stream resolve(DiscoveryItem item) {
            resolves++; throw new IllegalStateException("Queue-owned local media must not use remote resolution");
        }
    }

    private DiscoveryItem saved(String identity, String title, String creator, int seconds) throws Exception {
        try (JobStore store = new JobStore(app)) {
            String url = "https://www.youtube.com/watch?v=" + identity;
            String id = store.enqueue(url, "audio", "{\"quality\":\"best\",\"audio\":\"original\",\"playlist\":false}", title);
            jobs.add(id); assertEquals(id, store.claimNext().id);
            File directory = new File(DownloadService.folder(app), id); assertTrue(directory.mkdirs());
            File wave = new File(directory, "synthetic-reference.wav"); writeWave(wave, seconds);
            store.finish(id, "complete", title, wave.getAbsolutePath(), "");
            return new DiscoveryItem(identity, "song", title, creator, url, "", seconds * 1000L, id);
        }
    }

    private void writeWave(File file, int seconds) throws Exception {
        int rate = 8000, samples = rate * seconds, data = samples * 2;
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write("RIFF".getBytes("US-ASCII")); little(out, data + 36, 4); out.write("WAVEfmt ".getBytes("US-ASCII"));
            little(out, 16, 4); little(out, 1, 2); little(out, 1, 2); little(out, rate, 4); little(out, rate * 2, 4);
            little(out, 2, 2); little(out, 16, 2); out.write("data".getBytes("US-ASCII")); little(out, data, 4);
            byte[] buffer = new byte[8192];
            for (int sample = 0; sample < samples;) {
                int count = Math.min(buffer.length / 2, samples - sample);
                for (int i = 0; i < count; i++, sample++) {
                    short value = (short)(Math.sin(sample * 2 * Math.PI * 220 / rate) * 900);
                    buffer[i * 2] = (byte)value; buffer[i * 2 + 1] = (byte)(value >>> 8);
                }
                out.write(buffer, 0, count * 2);
            }
        }
    }
    private void little(FileOutputStream out, int value, int count) throws Exception { for (int i = 0; i < count; i++) out.write(value >>> (i * 8)); }
    private Intent exploreIntent() { return new Intent(app, MainActivity.class).putExtra("destination", "explore"); }
    private View tagged(Activity activity, String tag) { return activity.getWindow().getDecorView().findViewWithTag(tag); }
    private ExploreView explore(Activity activity) {
        ExploreView view = findExplore(activity.getWindow().getDecorView()); assertNotNull("Missing native Explore view", view); return view;
    }
    private ExploreView findExplore(View view) {
        if (view instanceof ExploreView) return (ExploreView)view;
        if (view instanceof ViewGroup) for (int i = 0; i < ((ViewGroup)view).getChildCount(); i++) {
            ExploreView found = findExplore(((ViewGroup)view).getChildAt(i)); if (found != null) return found;
        }
        return null;
    }
    private String text(Activity activity) { return text(activity.getWindow().getDecorView()); }
    private String text(View view) {
        if (view.getVisibility() != View.VISIBLE) return "";
        StringBuilder value = new StringBuilder(view instanceof TextView ? ((TextView)view).getText().toString() : "");
        if (view instanceof ViewGroup) for (int i = 0; i < ((ViewGroup)view).getChildCount(); i++) value.append('\n').append(text(((ViewGroup)view).getChildAt(i)));
        return value.toString();
    }
    private void visible(View view, boolean touch) {
        assertNotNull("Missing control", view); Rect bounds = new Rect();
        assertTrue("Control is not visible: " + view.getTag(), view.getGlobalVisibleRect(bounds));
        assertTrue("Control is horizontally clipped: " + view.getTag(), bounds.width() >= view.getWidth() - 1);
        assertTrue("Control is vertically clipped: " + view.getTag(), bounds.height() >= view.getHeight() - 1);
        if (touch) assertTrue("Touch target is below 48dp: " + view.getTag(), view.getHeight() >= Math.round(view.getResources().getDisplayMetrics().density * 48));
    }
    private void onMain(Runnable action) { instrumentation.runOnMainSync(action); }
    private void awaitPlayback(DiscoveryItem item, boolean playing) throws Exception {
        waitMain("Player did not load " + item.title, () -> {
            PlaybackController player = PlaybackController.get(app);
            return player.current() != null && player.current().key().equals(item.key()) && !player.isLoading()
                && player.isPlaying() == playing && player.duration() > 1000;
        });
    }
    private void waitMain(String message, BooleanSupplier condition) throws Exception {
        AtomicBoolean ready = new AtomicBoolean();
        waitFor(message, () -> { onMain(() -> ready.set(condition.getAsBoolean())); return ready.get(); });
    }
    private <T extends Activity> void waitScreen(ActivityScenario<T> screen, String message, java.util.function.Predicate<T> condition) throws Exception {
        AtomicBoolean ready = new AtomicBoolean();
        waitFor(message, () -> { screen.onActivity(activity -> ready.set(condition.test(activity))); return ready.get(); });
    }
    private void waitFor(String message, BooleanSupplier condition) throws Exception {
        long deadline = SystemClock.uptimeMillis() + 15000;
        while (!condition.getAsBoolean() && SystemClock.uptimeMillis() < deadline) Thread.sleep(80);
        assertTrue(message, condition.getAsBoolean());
    }
    private <T extends Activity> void withForeground(Class<T> type, Consumer<T> action) throws Exception {
        AtomicReference<T> target = new AtomicReference<>();
        waitFor("Expected foreground " + type.getSimpleName(), () -> {
            onMain(() -> {
                for (Activity activity : ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED))
                    if (type.isInstance(activity)) target.set(type.cast(activity));
            }); return target.get() != null;
        });
        onMain(() -> action.accept(target.get()));
    }
    private <T extends Activity> void awaitFrames(ActivityScenario<T> screen) throws Exception {
        waitScreen(screen, "Local artwork did not decode", activity -> artworkReady(activity.getWindow().getDecorView()));
        CountDownLatch frames = new CountDownLatch(1);
        screen.onActivity(activity -> {
            View root = activity.getWindow().getDecorView(); root.postOnAnimation(() -> root.postOnAnimation(frames::countDown)); root.invalidate();
        });
        assertTrue("View did not render", frames.await(4, TimeUnit.SECONDS));
        instrumentation.waitForIdleSync(); Thread.sleep(180);
    }
    private <T extends Activity> void waitForegroundFrames(Class<T> type) throws Exception {
        AtomicBoolean ready = new AtomicBoolean();
        waitFor("Foreground artwork did not decode", () -> {
            try { withForeground(type, activity -> ready.set(artworkReady(activity.getWindow().getDecorView()))); }
            catch (Exception error) { throw new AssertionError(error); }
            return ready.get();
        });
        CountDownLatch frames = new CountDownLatch(1);
        withForeground(type, activity -> {
            View root = activity.getWindow().getDecorView(); root.postOnAnimation(() -> root.postOnAnimation(frames::countDown)); root.invalidate();
        });
        assertTrue("Foreground view did not render", frames.await(4, TimeUnit.SECONDS)); Thread.sleep(180);
    }
    private boolean artworkReady(View view) {
        if (!view.isShown()) return true;
        if (view instanceof ImageView && ((ImageView)view).getDrawable() instanceof GradientDrawable) return false;
        if (view instanceof ViewGroup) for (int i = 0; i < ((ViewGroup)view).getChildCount(); i++)
            if (!artworkReady(((ViewGroup)view).getChildAt(i))) return false;
        return true;
    }
    private void seekWithTouch(float fraction) throws Exception {
        int[] point = new int[2];
        withForeground(NowPlayingActivity.class, activity -> {
            View seek = tagged(activity, "now_seek"); visible(seek, false); seek.getLocationOnScreen(point);
            point[0] += Math.round(seek.getWidth() * fraction); point[1] += seek.getHeight() / 2;
        });
        long now = SystemClock.uptimeMillis();
        MotionEvent down = MotionEvent.obtain(now, now, MotionEvent.ACTION_DOWN, point[0], point[1], 0);
        MotionEvent up = MotionEvent.obtain(now, now + 60, MotionEvent.ACTION_UP, point[0], point[1], 0);
        try { instrumentation.sendPointerSync(down); instrumentation.sendPointerSync(up); }
        finally { down.recycle(); up.recycle(); }
        instrumentation.waitForIdleSync();
    }
    private void clickDialogText(String title) throws Exception {
        AtomicBoolean clicked = new AtomicBoolean();
        waitFor("Missing dialog action " + title, () -> {
            AccessibilityNodeInfo root = instrumentation.getUiAutomation().getRootInActiveWindow();
            if (root == null) return false;
            List<AccessibilityNodeInfo> matches = root.findAccessibilityNodeInfosByText(title);
            for (AccessibilityNodeInfo node : matches) {
                AccessibilityNodeInfo candidate = node;
                for (int depth = 0; candidate != null && depth < 3; depth++, candidate = candidate.getParent()) {
                    if (candidate.isClickable() && candidate.performAction(AccessibilityNodeInfo.ACTION_CLICK)) { clicked.set(true); break; }
                }
                if (clicked.get()) break;
            }
            return clicked.get();
        });
        instrumentation.waitForIdleSync();
    }
    private void screenshot(String name) throws Exception {
        Bitmap image = instrumentation.getUiAutomation().takeScreenshot(); assertNotNull(image);
        try (FileOutputStream out = new FileOutputStream(new File(app.getFilesDir(), name))) { assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, out)); }
        finally { image.recycle(); }
    }
    private String shell(String command) throws Exception {
        try (InputStream in = new ParcelFileDescriptor.AutoCloseInputStream(instrumentation.getUiAutomation().executeShellCommand(command));
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[2048]; int count; while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count); return out.toString("UTF-8");
        }
    }
    private String override(String output, String kind) {
        Matcher match = Pattern.compile("Override " + kind + ":\\s*(\\d+(?:x\\d+)?)").matcher(output);
        return match.find() ? match.group(1) : "reset";
    }
    private String fontValue(String value) { return value.isEmpty() || value.equals("null") ? "1.0" : value; }
    private void setNight(String value) throws Exception { assertTrue("Night mode command failed", shell("cmd uimode night " + value).contains("Night mode: " + value)); }
    private void restoreNight(int value) throws Exception { setNight(value == UiModeManager.MODE_NIGHT_YES ? "yes" : value == UiModeManager.MODE_NIGHT_NO ? "no" : "auto"); }
}
