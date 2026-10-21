package com.brooth.blaze;

import android.app.Instrumentation;
import android.app.UiModeManager;
import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Rect;
import android.os.ParcelFileDescriptor;
import android.view.View;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

/** Checks the new shell's navigation contract and readable system-theme surfaces. */
@RunWith(AndroidJUnit4.class)
public class AndroidInterfaceTest {
    private final Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
    private final Context app = instrumentation.getTargetContext();

    @Test public void pausedAndInterruptedQueuesKeepResumeReachable() throws Exception {
        try (JobStore store = new JobStore(app)) {
            assertFalse("Use an idle disposable emulator", DownloadService.busy);
            assertEquals("Fixture must be the only pending job", 0, store.count(0));
            String id = store.enqueue("https://example.test/resume-ui/" + java.util.UUID.randomUUID(), "video", "{}", "Paused local fixture");
            try {
                android.content.ContentValues values = new android.content.ContentValues();
                values.put("state", "paused");
                store.getWritableDatabase().update("jobs", values, "id=?", new String[]{id});
                assertFalse("Paused jobs are not queued", store.hasQueued());
                try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(AndroidTestScreens.downloads())) {
                    assertResumeReachable(screen);
                    values.put("state", "interrupted");
                    store.getWritableDatabase().update("jobs", values, "id=?", new String[]{id});
                    assertFalse("Interrupted jobs are not queued", store.hasQueued());
                    screen.recreate();
                    assertResumeReachable(screen);
                }
                assertFalse("Viewing queue controls must not start a download", store.hasQueued());
            } finally {
                store.getWritableDatabase().delete("jobs", "id=?", new String[]{id});
            }
        }
    }

    private void assertResumeReachable(ActivityScenario<MainActivity> screen) {
        instrumentation.waitForIdleSync();
        screen.onActivity(activity -> {
            View panel = activity.getWindow().getDecorView().findViewWithTag("queue_panel");
            View resume = activity.getWindow().getDecorView().findViewWithTag("resume_queue");
            assertNotNull("Missing queue panel", panel); assertEquals(View.VISIBLE, panel.getVisibility());
            assertNotNull("Missing Resume queue control", resume); assertEquals(View.VISIBLE, resume.getVisibility());
            assertTrue("Resume queue should be enabled", resume.isEnabled());
            resume.requestRectangleOnScreen(new Rect(0, 0, resume.getWidth(), resume.getHeight()), true);
        });
        instrumentation.waitForIdleSync();
        screen.onActivity(activity -> assertVisibleTarget(activity.getWindow().getDecorView().findViewWithTag("resume_queue")));
    }

    @Test public void libraryAndHistorySelectionSurviveRecreation() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(AndroidTestScreens.downloads())) {
            instrumentation.waitForIdleSync();
            for (String tag : new String[]{"nav_library", "nav_history", "nav_queue"}) {
                if (!tag.equals("nav_library")) {
                    screen.onActivity(activity -> activity.getWindow().getDecorView().findViewWithTag("nav_downloads").performClick());
                    awaitRenderedFrames(screen);
                }
                screen.onActivity(activity -> {
                    View selected = activity.getWindow().getDecorView().findViewWithTag(tag);
                    assertNotNull("Missing navigation destination " + tag, selected);
                    assertVisibleTarget(selected);
                    selected.performClick();
                    assertTrue("Selected destination is not exposed", selected.isSelected());
                });
                screen.recreate();
                instrumentation.waitForIdleSync();
                screen.onActivity(activity -> {
                    View selected = activity.getWindow().getDecorView().findViewWithTag(tag);
                    assertTrue("Navigation lost after recreation", selected.isSelected());
                    View destination = activity.getWindow().getDecorView().findViewWithTag(tag.equals("nav_library") ? "nav_library" : "nav_downloads");
                    assertTrue("Top-level destination lost after recreation", destination.isSelected());
                    assertVisibleTarget(activity.findViewById(R.id.find_chords));
                });
                awaitRenderedFrames(screen);
                screenshot("Blaze-Android-" + (tag.equals("nav_queue") ? "downloads" : tag.substring(4)) + ".png");
            }
        }
    }

    @Test public void veryLargeTypeKeepsStudioActionsReachable() throws Exception {
        String previous = shell("settings get system font_scale").trim();
        File wave = File.createTempFile("studio-accessibility-", ".wav", DownloadService.folder(app));
        MusicStudioTest.writeWave(wave, false, 12);
        android.net.Uri uri = androidx.core.content.FileProvider.getUriForFile(app, app.getPackageName() + ".files", wave);
        try {
            shell("settings put system font_scale 2.0");
            try (ActivityScenario<MusicStudioActivity> screen = ActivityScenario.launch(new android.content.Intent(app, MusicStudioActivity.class).setData(uri))) {
                screen.onActivity(activity -> activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
                AtomicBoolean ready = new AtomicBoolean();
                long deadline = android.os.SystemClock.uptimeMillis() + 8000;
                while (!ready.get() && android.os.SystemClock.uptimeMillis() < deadline) {
                    instrumentation.waitForIdleSync();
                    screen.onActivity(activity -> {
                        View fallback = activity.root.findViewWithTag("studio_scroll_fallback");
                        ready.set(activity.getResources().getConfiguration().orientation == Configuration.ORIENTATION_PORTRAIT
                            && activity.getResources().getConfiguration().fontScale >= 1.9f
                            && fallback instanceof ScrollView && fallback.isLaidOut() && !fallback.isLayoutRequested());
                    });
                    if (!ready.get()) Thread.sleep(80);
                }
                assertTrue("Studio needs a scrolling fallback at very large type", ready.get());
                screen.onActivity(activity -> {
                    if (activity.player != null && activity.player.isPlaying()) activity.toggle.performClick();
                    assertVisibleTarget(activity.toggle);
                    View diagram = activity.root.findViewWithTag("studio_current_diagram");
                    assertTrue("Chord diagram collapsed at large type", diagram.getHeight() >= Math.round(app.getResources().getDisplayMetrics().density * 48));
                    ScrollView fallback = activity.root.findViewWithTag("studio_scroll_fallback");
                    fallback.setSmoothScrollingEnabled(false);
                    fallback.scrollTo(0, Math.max(0, fallback.getChildAt(0).getHeight() - fallback.getHeight() + fallback.getPaddingTop() + fallback.getPaddingBottom()));
                });
                instrumentation.waitForIdleSync();
                awaitRenderedFrames(screen);
                screen.onActivity(activity -> {
                    assertVisibleTarget(activity.findViewById(R.id.chord_analyze));
                    assertVisibleTarget(activity.root.findViewWithTag("studio_options"));
                });
                screenshot("Blaze-Android-Studio-Accessibility.png");
            }
        } finally {
            shell("settings put system font_scale " + (previous.isEmpty() || previous.equals("null") ? "1.0" : previous));
            wave.delete();
            app.getSharedPreferences("playback", Context.MODE_PRIVATE).edit().remove("document:" + uri).apply();
        }
    }

    @Test public void studioUsesSystemThemesWithVisibleTransportAndActions() throws Exception {
        int previous = app.getSystemService(UiModeManager.class).getNightMode();
        File wave = File.createTempFile("studio-theme-", ".wav", DownloadService.folder(app));
        MusicStudioTest.writeWave(wave, false, 12);
        android.net.Uri uri = androidx.core.content.FileProvider.getUriForFile(app, app.getPackageName() + ".files", wave);
        try {
            for (boolean dark : new boolean[]{false, true}) {
                night(dark ? "yes" : "no");
                try (ActivityScenario<MusicStudioActivity> screen = ActivityScenario.launch(new android.content.Intent(app, MusicStudioActivity.class).setData(uri))) {
                    waitForTheme(screen, dark);
                    screen.onActivity(activity -> {
                        if (activity.player != null && activity.player.isPlaying()) activity.toggle.performClick();
                        java.util.List<ChordEngine.Event> events = new java.util.ArrayList<>();
                        events.add(new ChordEngine.Event(0, 6000, StudioChord.parse("C:maj7"), .8));
                        events.add(new ChordEngine.Event(6000, 12000, StudioChord.parse("A:min9"), .8));
                        activity.result = new StudioAnalyzer.Result(events, 12000, "C major", false, new float[]{.1f, .4f, .2f, .5f});
                        activity.result.identity = "instrumentation-theme-fixture";
                        activity.result.sourceHash = "instrumentation-theme-fixture";
                        activity.result.tempo = 120;
                        activity.result.beats = new long[25];
                        for (int i = 0; i < 25; i++) activity.result.beats[i] = i * 500;
                        activity.result.downbeats = new long[]{0, 2000, 4000, 6000, 8000, 10000, 12000};
                        activity.result.meter = StudioMeter.estimate(activity.result.beats, activity.result.downbeats, 12000);
                        try {
                            for (String name : new String[]{"loadRhythm", "render"}) {
                                java.lang.reflect.Method method = MusicStudioActivity.class.getDeclaredMethod(name);
                                method.setAccessible(true); method.invoke(activity);
                            }
                            activity.onPlaybackTime(1500);
                        } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
                    });
                    instrumentation.waitForIdleSync();
                    screen.onActivity(activity -> {
                        assertEquals(dark, new BlazeUi(activity).dark);
                        assertVisibleTarget(activity.findViewById(R.id.chord_analyze));
                        assertVisibleTarget(activity.toggle);
                        assertVisibleTarget(activity.root.findViewWithTag("studio_options"));
                        assertNotNull(activity.root.findViewWithTag("studio_current_diagram"));
                    });
                    awaitRenderedFrames(screen);
                    screenshot("Blaze-Android-Studio-" + (dark ? "Dark" : "Light") + ".png");
                }
            }
        } finally {
            night(previous == UiModeManager.MODE_NIGHT_YES ? "yes" : previous == UiModeManager.MODE_NIGHT_NO ? "no" : "auto");
            wave.delete();
            app.getSharedPreferences("playback", Context.MODE_PRIVATE).edit().remove("document:" + uri).apply();
        }
    }

    @Test public void systemThemesHaveReadableTokensAndKeepStudioReachable() throws Exception {
        UiModeManager modes = app.getSystemService(UiModeManager.class);
        int previous = modes.getNightMode();
        try {
            for (boolean dark : new boolean[]{false, true}) {
                night(dark ? "yes" : "no");
                try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(AndroidTestScreens.downloads())) {
                    waitForTheme(screen, dark);
                    screen.onActivity(activity -> {
                        BlazeUi ui = new BlazeUi(activity);
                        assertTrue("Body text contrast", contrast(ui.text, ui.background) >= 4.5);
                        assertTrue("Secondary text contrast", contrast(ui.secondary, ui.background) >= 4.5);
                        assertTrue("Surface text contrast", contrast(ui.text, ui.surface) >= 4.5);
                        assertTrue("Surface secondary contrast", contrast(ui.secondary, ui.surface) >= 4.5);
                        assertTrue("Primary action contrast", contrast(ui.accentText, ui.accent) >= 4.5);
                        assertVisibleTarget(activity.findViewById(R.id.find_chords));
                        ((RadioGroup)activity.findViewById(R.id.download_mode)).check(R.id.audio_mode);
                        assertEquals(View.VISIBLE, activity.findViewById(R.id.audio_choice).getVisibility());
                        assertEquals(View.GONE, activity.findViewById(R.id.quality_choice).getVisibility());
                    });
                    awaitRenderedFrames(screen);
                    screenshot("Blaze-Android-Home-" + (dark ? "Dark" : "Light") + ".png");
                }
            }
        } finally {
            night(previous == UiModeManager.MODE_NIGHT_YES ? "yes" : previous == UiModeManager.MODE_NIGHT_NO ? "no" : "auto");
        }
    }

    private <T extends android.app.Activity> void waitForTheme(ActivityScenario<T> screen, boolean dark) throws Exception {
        AtomicBoolean ready = new AtomicBoolean();
        long end = android.os.SystemClock.uptimeMillis() + 8000;
        while (!ready.get() && android.os.SystemClock.uptimeMillis() < end) {
            instrumentation.waitForIdleSync();
            screen.onActivity(activity -> ready.set(((activity.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES) == dark
                && activity.getWindow().getDecorView().isLaidOut()));
            if (!ready.get()) Thread.sleep(80);
        }
        assertTrue("System theme did not settle", ready.get());
    }

    private void assertVisibleTarget(View view) {
        assertNotNull(view);
        Rect bounds = new Rect();
        assertTrue("Control is outside viewport", view.getGlobalVisibleRect(bounds));
        assertTrue("Control is horizontally clipped", bounds.width() >= view.getWidth() - 1);
        assertTrue("Control is vertically clipped", bounds.height() >= view.getHeight() - 1);
        assertTrue("Control height is below 48dp", view.getHeight() >= Math.round(app.getResources().getDisplayMetrics().density * 48));
    }

    private void night(String value) throws Exception {
        String result = shell("cmd uimode night " + value).trim();
        assertTrue("Emulator rejected night-mode request: " + result, result.contains("Night mode: " + value));
    }

    private <T extends android.app.Activity> void awaitRenderedFrames(ActivityScenario<T> screen) throws Exception {
        java.util.concurrent.CountDownLatch frames = new java.util.concurrent.CountDownLatch(1);
        screen.onActivity(activity -> {
            View root = activity.getWindow().getDecorView();
            root.postOnAnimation(() -> root.postOnAnimation(frames::countDown));
            root.invalidate();
        });
        assertTrue("UI did not draw after scrolling", frames.await(3, java.util.concurrent.TimeUnit.SECONDS));
        instrumentation.waitForIdleSync();
    }

    private String shell(String command) throws Exception {
        try (InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(instrumentation.getUiAutomation().executeShellCommand(command));
             java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream()) {
            byte[] buffer = new byte[1024]; int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            return output.toString("UTF-8");
        }
    }

    private void screenshot(String name) throws Exception {
        instrumentation.waitForIdleSync();
        Bitmap bitmap = instrumentation.getUiAutomation().takeScreenshot();
        assertNotNull(bitmap);
        try (FileOutputStream output = new FileOutputStream(new File(app.getFilesDir(), name))) {
            assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, output));
        } finally { bitmap.recycle(); }
    }

    private static double contrast(int first, int second) {
        double a = luminance(first), b = luminance(second);
        return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    }
    private static double luminance(int color) {
        return .2126 * linear(Color.red(color)) + .7152 * linear(Color.green(color)) + .0722 * linear(Color.blue(color));
    }
    private static double linear(int component) {
        double value = component / 255.0;
        return value <= .04045 ? value / 12.92 : Math.pow((value + .055) / 1.055, 2.4);
    }
}
