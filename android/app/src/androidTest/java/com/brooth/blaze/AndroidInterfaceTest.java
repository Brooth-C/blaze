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

    @Test public void libraryAndHistorySelectionSurviveRecreation() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(MainActivity.class)) {
            instrumentation.waitForIdleSync();
            for (String tag : new String[]{"nav_library", "nav_history", "nav_downloads"}) {
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
                    assertVisibleTarget(activity.findViewById(R.id.find_chords));
                });
                screenshot("Blaze-Android-" + tag.substring(4) + ".png");
            }
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
                    instrumentation.waitForIdleSync();
                    screen.onActivity(activity -> {
                        if (activity.player != null && activity.player.isPlaying()) activity.toggle.performClick();
                        java.util.List<ChordEngine.Event> events = new java.util.ArrayList<>();
                        events.add(new ChordEngine.Event(0, 6000, StudioChord.parse("C:maj7"), .8));
                        events.add(new ChordEngine.Event(6000, 12000, StudioChord.parse("A:min9"), .8));
                        activity.result = new StudioAnalyzer.Result(events, 12000, "C major", false, new float[]{.1f, .4f, .2f, .5f});
                        activity.result.identity = "instrumentation-theme-fixture";
                        activity.result.sourceHash = "instrumentation-theme-fixture";
                        try {
                            java.lang.reflect.Method render = MusicStudioActivity.class.getDeclaredMethod("render");
                            render.setAccessible(true); render.invoke(activity); activity.onPlaybackTime(1500);
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
                try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(MainActivity.class)) {
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
                    screenshot("Blaze-Android-Home-" + (dark ? "Dark" : "Light") + ".png");
                }
            }
        } finally {
            night(previous == UiModeManager.MODE_NIGHT_YES ? "yes" : previous == UiModeManager.MODE_NIGHT_NO ? "no" : "auto");
        }
    }

    private void waitForTheme(ActivityScenario<MainActivity> screen, boolean dark) throws Exception {
        AtomicBoolean ready = new AtomicBoolean();
        long end = android.os.SystemClock.uptimeMillis() + 8000;
        while (!ready.get() && android.os.SystemClock.uptimeMillis() < end) {
            instrumentation.waitForIdleSync();
            screen.onActivity(activity -> ready.set(((activity.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES) == dark
                && activity.findViewById(R.id.find_chords).isLaidOut()));
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
        try (InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(instrumentation.getUiAutomation().executeShellCommand("cmd uimode night " + value))) {
            byte[] bytes = new byte[1024]; while (input.read(bytes) != -1) { /* Wait for settings command. */ }
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
