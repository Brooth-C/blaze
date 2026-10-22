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
import java.util.concurrent.CopyOnWriteArrayList;
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
        onMain(() -> { PlaybackController.get(app).stop(); PlaybackController.get(app).clearListeningHistory(); PlaybackController.get(app).setRepeat(false); });
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
        seedRecommendationArtwork();
        DiscoveryRepository.setTestBackend(backend);
    }

    @After public void cleanup() throws Exception {
        onMain(() -> {
            PlaybackController.get(app).stop();
            PlaybackController.get(app).clearListeningHistory();
            PlaybackController.get(app).setRepeat(false);
            for (Stage stage : new Stage[]{Stage.RESUMED, Stage.STARTED, Stage.CREATED}) {
                for (Activity activity : new ArrayList<>(ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(stage))) {
                    if (activity instanceof NowPlayingActivity || activity instanceof VlcPlayerActivity) activity.finish();
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
        PlaybackSource savedAudio = PlaybackSource.load(app, golden.localJobId);
        assertTrue("The platform playback probe rejected the real PCM recording", PlaybackController.supportsPlatformPlayback(savedAudio, false));
        assertFalse("An audio-only recording satisfied video playback", PlaybackController.supportsPlatformPlayback(savedAudio, true));
        String size = override(shell("wm size"), "size");
        String density = override(shell("wm density"), "density");
        String font = shell("settings get system font_scale").trim();
        int night = app.getSystemService(UiModeManager.class).getNightMode();
        String navigation = activeNavigationOverlay(shell("cmd overlay list"));
        try {
            shell("wm size 1080x2460"); shell("wm density 420");
            shell("settings put system font_scale 1.0"); setNight("no");
            referenceGestureNavigation(navigation);
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
                withForeground(MusicStudioActivity.class, Activity::finish);
                withForeground(NowPlayingActivity.class, activity -> tagged(activity, "now_nav_library").performClick());
                waitScreen(screen, "Now Playing did not return to the saved Library", activity -> tagged(activity, "nav_library").isSelected()
                    && tagged(activity, "saved_play_" + golden.localJobId) != null);
                screen.onActivity(activity -> {
                    View savedPlay = tagged(activity, "saved_play_" + golden.localJobId);
                    savedPlay.requestRectangleOnScreen(new Rect(0, 0, savedPlay.getWidth(), savedPlay.getHeight()), true);
                });
                awaitFrames(screen);
                onMain(() -> PlaybackController.get(app).toggle());
                awaitPlayback(quiet, true);
                screen.onActivity(activity -> {
                    View savedPlay = tagged(activity, "saved_play_" + golden.localJobId);
                    visible(savedPlay, true); savedPlay.performClick();
                });
                AtomicReference<VlcPlayerActivity> localPlayer = new AtomicReference<>();
                withForeground(VlcPlayerActivity.class, activity -> {
                    assertEquals("Library playback changed its decoder route", VlcPlayerActivity.class, activity.getClass());
                    assertEquals(golden.localJobId, activity.getIntent().getStringExtra("job"));
                    assertNotNull("Library lost the owned recording", activity.source);
                    assertEquals(golden.localJobId, activity.source.id);
                    localPlayer.set(activity);
                });
                waitMain("Library VLC player did not decode the actual saved recording", () -> {
                    VlcPlayerActivity activity = localPlayer.get();
                    return activity.player != null && activity.player.isPlaying() && activity.player.getTime() > 100
                        && activity.player.getAudioTracksCount() > 0 && Math.abs(activity.player.getLength() - 222000) < 1000;
                });
                waitMain("Discovery audio kept playing over Library playback", () -> !PlaybackController.get(app).isPlaying());
                onMain(() -> assertEquals("Library playback did not update local listening history", golden.id,
                    PlaybackController.get(app).history().get(0).id));
                withForeground(VlcPlayerActivity.class, Activity::finish);
            }
            assertEquals("Local playback unexpectedly used a remote resolver", 0, backend.resolves);
        } finally {
            try {
                onMain(() -> PlaybackController.get(app).stop());
                shell("wm size " + size); shell("wm density " + density);
                shell("settings put system font_scale " + fontValue(font)); restoreNight(night);
            } finally {
                if (!navigation.isEmpty()) {
                    shell("cmd overlay enable-exclusive --category " + navigation);
                    assertTrue("Reference capture did not restore the navigation overlay", awaitNavigationOverlay(navigation));
                }
            }
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
            waitScreen(screen, "Songs filter did not settle", activity -> tagged(activity, "search_filter_songs").isSelected()
                && tagged(activity, "discovery_loading") == null && tagged(activity, "discovery_item_" + golden.id) != null);
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

    @Test public void typingCoalescesSearchAndKeepsTheFocusedFieldAcrossResultsAndFilters() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            screen.onActivity(activity -> tagged(activity, "discovery_search").performClick());
            AtomicReference<EditText> field = new AtomicReference<>();
            shell("dumpsys gfxinfo com.brooth.blaze reset");
            screen.onActivity(activity -> {
                EditText input = (EditText)tagged(activity, "discovery_search"); field.set(input);
                input.requestFocus(); input.setText("a");
            });
            Thread.sleep(90);
            screen.onActivity(activity -> field.get().append("coustic"));
            Thread.sleep(90);
            screen.onActivity(activity -> {
                assertTrue("Typing sent an intermediate query immediately", backend.searches.isEmpty());
                field.get().append(" sessions"); field.get().setSelection(8);
            });
            waitScreen(screen, "Typing never submitted the final search", activity -> backend.searches.contains("acoustic sessions|all|20")
                && tagged(activity, "discovery_loading") == null && tagged(activity, "discovery_item_" + golden.id) != null);
            screen.onActivity(activity -> {
                assertSame("Search completion replaced the input view", field.get(), tagged(activity, "discovery_search"));
                assertTrue("Search completion dismissed input focus", field.get().hasFocus());
                assertEquals("Search completion moved the cursor", 8, field.get().getSelectionStart());
                assertEquals("Typing fetched more than the final query", Collections.singletonList("acoustic sessions|all|20"), backend.searches);
                tagged(activity, "search_filter_videos").performClick();
            });
            waitScreen(screen, "Videos filter did not return the recording", activity -> backend.searches.contains("acoustic sessions|videos|20")
                && tagged(activity, "discovery_loading") == null && tagged(activity, "discovery_item_" + video.id) != null);
            screen.onActivity(activity -> {
                assertSame("Changing filters rebuilt the focused input", field.get(), tagged(activity, "discovery_search"));
                assertEquals("Changing filters changed the query", "acoustic sessions", field.get().getText().toString());
                assertNull("Videos filter retained a song row", tagged(activity, "discovery_item_" + golden.id));
            });
            instrumentation.waitForIdleSync();
            String evidence = "Flow: focus search; type a, acoustic, acoustic sessions with 90ms gaps; await result; choose Videos; await result.\n"
                + "Build: debug; API " + android.os.Build.VERSION.SDK_INT + "; deterministic metadata and cached/local artwork.\n"
                + "Single emulator capture, not a device FPS benchmark. No network latency is measured.\n\n"
                + shell("dumpsys gfxinfo com.brooth.blaze") + "\nFRAMES\n" + shell("dumpsys gfxinfo com.brooth.blaze framestats");
            try (FileOutputStream out = new FileOutputStream(new File(app.getFilesDir(), "Blaze-Android-Search-Frames.txt"))) {
                out.write(evidence.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            }
        }
    }

    @Test public void editingAnInFlightSearchCannotPublishItsOldResults() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            screen.onActivity(activity -> explore(activity).showSearch("slow query"));
            assertTrue("Slow search did not start", backend.slowEntered.await(4, TimeUnit.SECONDS));
            AtomicReference<EditText> field = new AtomicReference<>();
            screen.onActivity(activity -> {
                field.set((EditText)tagged(activity, "discovery_search")); field.get().requestFocus();
                field.get().setText("acoustic sessions"); field.get().setSelection(5);
            });
            backend.releaseSlow.countDown();
            assertTrue("Cancelled old request did not finish", backend.slowFinished.await(4, TimeUnit.SECONDS));
            instrumentation.waitForIdleSync();
            screen.onActivity(activity -> assertFalse("Old results appeared under newly typed text", text(activity).contains("Outdated result")));
            waitScreen(screen, "Typed replacement search did not complete", activity -> tagged(activity, "discovery_item_" + golden.id) != null
                && tagged(activity, "discovery_loading") == null);
            screen.onActivity(activity -> {
                assertSame(field.get(), tagged(activity, "discovery_search"));
                assertEquals("acoustic sessions", field.get().getText().toString());
                assertEquals(5, field.get().getSelectionStart());
                assertFalse(text(activity).contains("Outdated result"));
            });
        } finally { backend.releaseSlow.countDown(); }
    }

    @Test public void allSearchKeepsEveryReturnedVideoAndDispatchesTheExactSelection() throws Exception {
        backend.extraVideos = true;
        AtomicReference<ExploreView> custom = new AtomicReference<>();
        AtomicReference<DiscoveryItem> selected = new AtomicReference<>();
        AtomicReference<List<DiscoveryItem>> selectedQueue = new AtomicReference<>();
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            screen.onActivity(activity -> {
                explore(activity).onDestroy();
                ExploreView view = new ExploreView(activity, new ExploreView.Actions() {
                    @Override public void onPlay(DiscoveryItem item, List<DiscoveryItem> queue) { selected.set(item); selectedQueue.set(queue); }
                    @Override public void onDownload(DiscoveryItem item, boolean forStudio) { fail("Selecting a video queued a download"); }
                    @Override public void onOpenPlayer() { fail("Selecting a video lost its recording identity"); }
                    @Override public void onSettings() { }
                });
                custom.set(view); activity.setContentView(view); view.showSearch("four live videos");
            });
            waitScreen(screen, "All search hid the third or fourth returned video", activity -> tagged(activity, "discovery_item_BlazeVid006") != null
                && tagged(activity, "discovery_item_BlazeVid007") != null);
            screen.onActivity(activity -> {
                assertNotNull(tagged(activity, "discovery_item_" + video.id));
                assertNotNull(tagged(activity, "discovery_item_BlazeVid005"));
                assertFalse("Search started playback without selecting a recording", PlaybackController.get(app).isPlaying());
                tagged(activity, "discovery_item_BlazeVid007").performClick();
                assertNotNull("Selected video was not dispatched", selected.get());
                assertEquals("BlazeVid007", selected.get().id); assertEquals("video", selected.get().kind);
                assertTrue("The selected recording was missing from its queue", selectedQueue.get().stream().anyMatch(item -> item.id.equals("BlazeVid007")));
            });
        } finally { onMain(() -> { if (custom.get() != null) custom.get().onDestroy(); }); }
    }

    @Test public void repeatedSearchCachesOnlyExactSuccessfulRequestsAndCancelledHitsStaySilent() throws Exception {
        searchOnce("repeat catalogue", "all", 20, false);
        searchOnce("repeat catalogue", "all", 20, false);
        assertEquals("Repeating a fresh search fetched the provider again", 1, backend.searches.size());
        searchOnce("repeat catalogue", "videos", 20, false);
        searchOnce("repeat catalogue", "all", 10, false);
        assertEquals("Filter or limit reused an incompatible cached response", 3, backend.searches.size());
        searchOnce("offline fixture", "all", 20, true);
        searchOnce("offline fixture", "all", 20, true);
        assertEquals("A provider failure was cached instead of retried", 5, backend.searches.size());
        AtomicBoolean callback = new AtomicBoolean();
        onMain(() -> {
            String token = DiscoveryRepository.get(app).search("repeat catalogue", "all", 20, (items, error) -> callback.set(true));
            DiscoveryRepository.get(app).cancel(token);
        });
        instrumentation.waitForIdleSync(); assertFalse("A cancelled cache hit delivered its callback", callback.get());
        backend = new FixtureBackend(); DiscoveryRepository.setTestBackend(backend);
        searchOnce("repeat catalogue", "all", 20, false);
        assertEquals("Resetting the provider reused a previous provider's cache", 1, backend.searches.size());
    }

    @Test public void streamResolutionDoesNotWaitBehindTwoBlockedSearches() throws Exception {
        CountDownLatch entered = new CountDownLatch(2), release = new CountDownLatch(1), searchesDone = new CountDownLatch(2);
        List<String> tokens = new ArrayList<>();
        DiscoveryRepository repository = DiscoveryRepository.get(app);
        DiscoveryRepository.setTestBackend(new DiscoveryRepository.Backend() {
            @Override public List<DiscoveryItem> search(String query, String filter, int limit) throws Exception {
                entered.countDown();
                try { release.await(8, TimeUnit.SECONDS); return Collections.singletonList(stay); }
                finally { searchesDone.countDown(); }
            }
            @Override public List<DiscoveryItem> browse(DiscoveryItem item, int limit) { return Collections.emptyList(); }
            @Override public DiscoveryRepository.Stream resolve(DiscoveryItem item) {
                return new DiscoveryRepository.Stream("https://fixture.googlevideo.com/audio", "audio/mp4", 1000, Collections.emptyMap());
            }
        });
        try {
            onMain(() -> {
                tokens.add(repository.search("blocked one", "all", 20, (items, error) -> { }));
                tokens.add(repository.search("blocked two", "all", 20, (items, error) -> { }));
            });
            assertTrue("Both metadata workers did not block", entered.await(4, TimeUnit.SECONDS));
            CountDownLatch resolved = new CountDownLatch(1); AtomicReference<DiscoveryRepository.Stream> stream = new AtomicReference<>();
            onMain(() -> tokens.add(repository.resolve(stay, (value, error) -> { stream.set(value); resolved.countDown(); })));
            assertTrue("Playback resolution waited behind background searches", resolved.await(3, TimeUnit.SECONDS));
            assertNotNull("Playback resolution failed while search was busy", stream.get());
            assertEquals("The searches completed before priority was established", 2, searchesDone.getCount());
        } finally {
            release.countDown();
            assertTrue("Blocked search fixtures did not finish", searchesDone.await(5, TimeUnit.SECONDS));
            onMain(() -> { for (String token : tokens) repository.cancel(token); });
            DiscoveryRepository.setTestBackend(backend);
        }
    }

    private List<DiscoveryItem> searchOnce(String query, String filter, int limit, boolean failureExpected) throws Exception {
        CountDownLatch done = new CountDownLatch(1); AtomicReference<List<DiscoveryItem>> result = new AtomicReference<>();
        AtomicReference<String> failure = new AtomicReference<>();
        onMain(() -> DiscoveryRepository.get(app).search(query, filter, limit, (items, error) -> {
            result.set(items); failure.set(error); done.countDown();
        }));
        assertTrue("Repository request never completed", done.await(5, TimeUnit.SECONDS));
        if (failureExpected) assertNotNull("Provider failure was hidden", failure.get());
        else assertNull("Repository search failed", failure.get());
        return result.get();
    }

    @Test public void exploreRecommendationsUseProviderArtworkAndPlayTheirExactRecording() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            waitScreen(screen, "Fresh Explore did not load real recommendation metadata", activity -> tagged(activity, "explore_hero") != null
                && tagged(activity, "explore_recommendation_" + quiet.id) != null);
            assertEquals("A fresh user should not send listening history", "[]", backend.profile);
            screen.onActivity(activity -> {
                assertTrue(text(activity).contains("Music from YouTube"));
                assertFalse(text(activity).contains("An evening at the keys"));
                assertFalse(text(activity).contains("Late-night jazz"));
                assertFalse("Loading recommendations started playback", PlaybackController.get(app).isPlaying());
                assertTrue(tagged(activity, "explore_hero").getContentDescription().toString().contains(golden.title));
            });
            waitScreen(screen, "The provider thumbnail was replaced by stock artwork", activity -> {
                ImageView image = (ImageView)tagged(activity, "recommendation_artwork_" + golden.id);
                if (image == null || !(image.getDrawable() instanceof android.graphics.drawable.BitmapDrawable)) return false;
                Bitmap bitmap = ((android.graphics.drawable.BitmapDrawable)image.getDrawable()).getBitmap();
                int pixel = bitmap.getPixel(bitmap.getWidth() / 2, bitmap.getHeight() / 2);
                return android.graphics.Color.green(pixel) > android.graphics.Color.red(pixel) * 2;
            });
            screen.onActivity(activity -> tagged(activity, "explore_hero").performClick());
            awaitPlayback(golden, true);
            withForeground(NowPlayingActivity.class, activity -> assertEquals(golden.title, ((TextView)tagged(activity, "now_title")).getText().toString()));
            onMain(() -> {
                assertEquals(golden.id, PlaybackController.get(app).current().id);
                assertEquals(golden.localJobId, PlaybackController.get(app).current().localJobId);
                assertEquals(3, PlaybackController.get(app).queue().size());
            });
            assertEquals("A verified local recording unexpectedly resolved remotely", 0, backend.resolves);
        }
    }

    @Test public void recommendationsLearnFromRealListeningAndKeepCachedPicksOffline() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            waitScreen(screen, "Initial recommendations missing", activity -> tagged(activity, "explore_hero") != null);
            onMain(() -> PlaybackController.get(app).play(golden, Arrays.asList(golden, quiet)));
            awaitPlayback(golden, true);
            onMain(() -> {
                PlaybackController player = PlaybackController.get(app);
                assertEquals("A play was counted before actual listening", 0, player.listenCount(golden));
                player.seekTo(100000);
                if (!player.isFavorite(golden)) player.toggleFavorite(golden);
                player.pause();
            });
            screen.onActivity(activity -> explore(activity).showHome());
            waitScreen(screen, "Listening history did not change the recommendation request", activity -> backend.profile.contains(golden.id)
                && text(activity).contains("Based on your listening in Blaze") && tagged(activity, "explore_hero") != null);
            org.json.JSONObject signal = new org.json.JSONArray(backend.profile).getJSONObject(0);
            assertEquals(golden.creator, signal.getString("creator")); assertTrue(signal.getBoolean("favorite"));
            assertFalse("A local file identity leaked into the recommendation profile", backend.profile.contains(golden.localJobId));
            assertFalse("Playback or thumbnail URLs leaked into the local signals", backend.profile.contains("https://"));
            int beforeRotation = backend.recommendations;
            screen.recreate();
            waitScreen(screen, "Rotation lost cached recommendations", activity -> tagged(activity, "explore_hero") != null);
            assertEquals("A fresh profile cache was fetched again after rotation", beforeRotation, backend.recommendations);
            backend.recommendationFailure = true;
            screen.onActivity(activity -> tagged(activity, "recommendation_refresh").performClick());
            waitScreen(screen, "Offline refresh hid cached picks or its retry action", activity -> tagged(activity, "recommendations_error") != null
                && tagged(activity, "recommendations_retry") != null && tagged(activity, "explore_hero") != null
                && text(activity).contains("Showing saved picks"));
            onMain(() -> {
                PlaybackController player = PlaybackController.get(app);
                if (player.isFavorite(golden)) player.toggleFavorite(golden);
            });
        }
    }

    @Test public void coldRecommendationFailureHasAnHonestRetryAndVideoLaneUsesVideoResults() throws Exception {
        backend.recommendationFailure = true;
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            waitScreen(screen, "Provider failure did not offer recovery", activity -> tagged(activity, "recommendations_retry") != null);
            screen.onActivity(activity -> assertNull("Failed recommendations invented a featured recording", tagged(activity, "explore_hero")));
            backend.recommendationFailure = false;
            screen.onActivity(activity -> tagged(activity, "recommendations_retry").performClick());
            waitScreen(screen, "Recommendation retry did not restore provider cards", activity -> tagged(activity, "explore_recommendation_" + quiet.id) != null);
            screen.onActivity(activity -> tagged(activity, "explore_lane_Videos").performClick());
            waitScreen(screen, "Videos did not replace music recommendations", activity -> tagged(activity, "explore_hero") != null
                && tagged(activity, "explore_hero").getContentDescription().toString().contains(video.title));
            screen.onActivity(activity -> assertFalse("Changing lanes started playback", PlaybackController.get(app).isPlaying()));
        }
    }

    @Test public void repeatSignalsRequireActualListeningRatherThanSeekingOrPauseResume() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(exploreIntent())) {
            onMain(() -> PlaybackController.get(app).play(golden, Arrays.asList(golden, quiet)));
            awaitPlayback(golden, true);
            onMain(() -> {
                PlaybackController player = PlaybackController.get(app);
                player.seekTo(170000);
                assertEquals("Seeking fabricated a repeat-listening signal", 0, player.listenCount(golden));
            });
            long deadline = SystemClock.uptimeMillis() + 22000;
            AtomicBoolean counted = new AtomicBoolean();
            do {
                onMain(() -> counted.set(PlaybackController.get(app).listenCount(golden) == 1));
                if (!counted.get()) Thread.sleep(150);
            } while (!counted.get() && SystemClock.uptimeMillis() < deadline);
            assertTrue("15 seconds of real playback did not contribute to personalization", counted.get());
            onMain(() -> { PlaybackController.get(app).pause(); PlaybackController.get(app).toggle(); });
            awaitPlayback(golden, true);
            onMain(() -> assertEquals("Pause/resume was counted as another listen", 1, PlaybackController.get(app).listenCount(golden)));
            onMain(() -> { PlaybackController.get(app).setRepeat(true); PlaybackController.get(app).seekTo(221500); });
            waitMain("Repeat did not restart the recording", () -> PlaybackController.get(app).isPlaying() && PlaybackController.get(app).position() < 10000);
            deadline = SystemClock.uptimeMillis() + 22000; counted.set(false);
            do {
                onMain(() -> counted.set(PlaybackController.get(app).listenCount(golden) == 2));
                if (!counted.get()) Thread.sleep(150);
            } while (!counted.get() && SystemClock.uptimeMillis() < deadline);
            assertTrue("A repeated recording did not qualify a second real listen", counted.get());
            onMain(() -> PlaybackController.get(app).setRepeat(false));
        }
    }

    private void seedRecommendationArtwork() throws Exception {
        File cache = new File(app.getCacheDir(), "discovery-artwork"); assertTrue(cache.isDirectory() || cache.mkdirs());
        int[] colors = {0xff167738, 0xff245999, 0xff8c3699}; int index = 0;
        for (DiscoveryItem item : Arrays.asList(golden, quiet, stay)) {
            String url = "https://i.ytimg.com/vi/" + item.id + "/mqdefault.jpg";
            byte[] hash = java.security.MessageDigest.getInstance("SHA-256").digest(url.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder name = new StringBuilder(); for (byte value : hash) name.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
            Bitmap image = Bitmap.createBitmap(320, 180, Bitmap.Config.ARGB_8888); image.eraseColor(colors[index++]);
            try (FileOutputStream out = new FileOutputStream(new File(cache, name + ".img"))) { assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, out)); }
            finally { image.recycle(); }
        }
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
            // Both real save dialogs post short system Toasts, which Android may queue.
            // Let both expire before the next test captures the reference interface.
            Thread.sleep(4600);
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
        volatile int recommendations;
        volatile String profile = "";
        volatile boolean recommendationFailure;
        volatile boolean extraVideos;
        final List<String> searches = new CopyOnWriteArrayList<>();
        @Override public List<DiscoveryItem> recommend(String signals, String lane, int limit) throws Exception {
            recommendations++; profile = signals;
            if (recommendationFailure) throw new java.io.IOException("Synthetic offline recommendations");
            if (lane.equals("videos")) return Collections.singletonList(video);
            List<DiscoveryItem> picks = new ArrayList<>();
            for (DiscoveryItem item : tracks()) picks.add(new DiscoveryItem(item.id, item.kind, item.title, item.creator,
                item.url, "https://i.ytimg.com/vi/" + item.id + "/mqdefault.jpg", item.durationMs));
            return picks;
        }
        @Override public List<DiscoveryItem> search(String query, String filter, int limit) throws Exception {
            searches.add(query + "|" + filter + "|" + limit);
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
            List<DiscoveryItem> found = new ArrayList<>(Arrays.asList(playlist, catalogue(golden), catalogue(quiet), stay, video));
            if (extraVideos) for (String id : Arrays.asList("BlazeVid005", "BlazeVid006", "BlazeVid007")) {
                found.add(new DiscoveryItem(id, "video", "Live video " + id, "Fixture",
                    "https://www.youtube.com/watch?v=" + id, "", 120000));
            }
            return found;
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
        if (view instanceof ImageView && ((ImageView)view).getDrawable() instanceof GradientDrawable) {
            Object tag = view.getTag();
            if (!(tag instanceof String) || !(tag.equals("artwork_placeholder_allowed") || ((String)tag).startsWith("recommendation_artwork_"))) return false;
        }
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
    private String activeNavigationOverlay(String overlays) {
        Matcher active = Pattern.compile("(?m)^\\s*\\[x\\]\\s+(com\\.android\\.internal\\.systemui\\.navbar\\.[A-Za-z0-9_.]+)\\s*$").matcher(overlays);
        return active.find() ? active.group(1) : "";
    }
    private void referenceGestureNavigation(String original) throws Exception {
        if (original.isEmpty()) return; // Keep native mode if its exact previous overlay is unknown.
        String overlays = shell("cmd overlay list"), gestures = "com.android.internal.systemui.navbar.gestural";
        if (original.equals(gestures) || !Pattern.compile("(?m)^\\s*\\[[x ]\\]\\s+" + Pattern.quote(gestures) + "\\s*$").matcher(overlays).find()) return;
        shell("cmd overlay enable-exclusive --category " + gestures);
        if (awaitNavigationOverlay(gestures)) return;
        // Optional presentation setup may be unavailable on an emulator. Keep its native mode.
        shell("cmd overlay enable-exclusive --category " + original);
        assertTrue("Unavailable gesture overlay changed the original navigation mode", awaitNavigationOverlay(original));
    }
    private boolean awaitNavigationOverlay(String name) throws Exception {
        Pattern enabled = Pattern.compile("(?m)^\\s*\\[x\\]\\s+" + Pattern.quote(name) + "\\s*$");
        long deadline = SystemClock.uptimeMillis() + 3000;
        do {
            if (enabled.matcher(shell("cmd overlay list")).find()) return true;
            Thread.sleep(80);
        } while (SystemClock.uptimeMillis() < deadline);
        return false;
    }
    private String fontValue(String value) { return value.isEmpty() || value.equals("null") ? "1.0" : value; }
    private void setNight(String value) throws Exception { assertTrue("Night mode command failed", shell("cmd uimode night " + value).contains("Night mode: " + value)); }
    private void restoreNight(int value) throws Exception { setNight(value == UiModeManager.MODE_NIGHT_YES ? "yes" : value == UiModeManager.MODE_NIGHT_NO ? "no" : "auto"); }
}
