package com.brooth.blaze;

import android.content.*;
import android.graphics.*;
import android.view.*;
import android.widget.*;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.lang.reflect.Method;
import java.util.*;
import static org.junit.Assert.*;

/** Real rendered activity checks; reference data is injected only from instrumentation. */
@RunWith(AndroidJUnit4.class)
public class StudioUsabilityTest {
    private final android.app.Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
    private final Context app = instrumentation.getTargetContext();

    @Test public void importIsVisibleAndAudioChoicesAreClear() throws Exception {
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(MainActivity.class)) {
            instrumentation.waitForIdleSync();
            screen.onActivity(activity -> {
                View studio = activity.findViewById(R.id.find_chords);
                assertFullyVisible(studio); assertTouchTarget(studio);
                ((RadioGroup)activity.findViewById(R.id.download_mode)).check(R.id.audio_mode);
                Spinner format = activity.findViewById(R.id.audio_choice); format.setSelection(3);
                assertEquals("WAV", format.getSelectedItem().toString());
                assertEquals(View.GONE, activity.findViewById(R.id.quality_choice).getVisibility());
            });
            screenshot("Blaze-Android-Home.png");
        }
    }

    @Test public void studioFitsPhoneAndLargeTextWithoutScrolling() throws Exception {
        String oldFont = shell("settings get system font_scale").trim();
        File wave = new File(DownloadService.folder(app), "studio-ui-" + UUID.randomUUID() + ".wav");
        assertTrue(wave.getParentFile().exists() || wave.getParentFile().mkdirs());
        MusicStudioTest.writeWave(wave, false, 12);
        android.net.Uri uri = androidx.core.content.FileProvider.getUriForFile(app, app.getPackageName() + ".files", wave);
        try {
            for (String scale : new String[]{"1.0", "1.5"}) {
                shell("settings put system font_scale " + scale);
                try (ActivityScenario<MusicStudioActivity> screen = ActivityScenario.launch(new Intent(app, MusicStudioActivity.class).setData(uri))) {
                    instrumentation.waitForIdleSync();
                    screen.onActivity(activity -> {
                        activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);
                        if (activity.player != null && activity.player.isPlaying()) activity.toggle.performClick();
                        inject(activity);
                    });
                    waitForLayout(screen, android.content.res.Configuration.ORIENTATION_PORTRAIT);
                    screenshot("Blaze-Android-Studio-" + (scale.equals("1.0") ? "Portrait" : "Large-Text") + ".png");
                    screen.onActivity(activity -> {
                        assertFalse(activity.findViewById(R.id.chord_panel) instanceof ScrollView);
                        View analyse = activity.findViewById(R.id.chord_analyze), options = activity.root.findViewWithTag("studio_options");
                        assertFullyVisible(analyse); assertFullyVisible(options); assertTouchTarget(analyse); assertTouchTarget(options);
                        assertFullyVisible(activity.root.findViewWithTag("studio_timeline"));
                        View diagram = activity.root.findViewWithTag("studio_current_diagram");
                        assertTrue("Piano diagram is too shallow", diagram.getHeight() >= dp(activity, 48)); assertFullyVisible(diagram);
                        assertEquals("Now: Cmaj7", ((TextView)activity.findViewById(R.id.chord_current)).getText().toString());
                        activity.onPlaybackTime(4200);
                        assertEquals("Now: â€”", ((TextView)activity.findViewById(R.id.chord_current)).getText().toString());
                        assertFalse("Uncertainty leaked into the display", allText(activity.root).contains("Uncertain"));
                        activity.onPlaybackTime(1500);
                    });
                    screenshot("Blaze-Android-Studio-" + (scale.equals("1.0") ? "Portrait" : "Large-Text") + ".png");
                    if (scale.equals("1.0")) {
                        screen.onActivity(activity -> activity.root.findViewWithTag("studio_options").performClick());
                        instrumentation.waitForIdleSync(); screenshot("Blaze-Android-Studio-Options.png");
                        instrumentation.getUiAutomation().performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);
                        screen.onActivity(activity -> activity.setRequestedOrientation(android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
                        waitForLayout(screen, android.content.res.Configuration.ORIENTATION_LANDSCAPE);
                        screen.onActivity(activity -> { assertFullyVisible(activity.findViewById(R.id.chord_analyze)); assertFullyVisible(activity.root.findViewWithTag("studio_timeline")); assertTrue(activity.root.findViewWithTag("studio_current_diagram").getHeight() >= dp(activity, 30)); });
                        screenshot("Blaze-Android-Studio-Landscape.png");
                    }
                }
            }
        } finally {
            shell("settings put system font_scale " + (oldFont.equals("null") || oldFont.isEmpty() ? "1.0" : oldFont));
            wave.delete(); app.getSharedPreferences("playback", Context.MODE_PRIVATE).edit().remove("document:" + uri).apply();
        }
    }
    private void waitForLayout(ActivityScenario<MusicStudioActivity> screen, int orientation) throws Exception {
        java.util.concurrent.atomic.AtomicBoolean ready = new java.util.concurrent.atomic.AtomicBoolean();
        long end = android.os.SystemClock.uptimeMillis() + 8000;
        while (!ready.get() && android.os.SystemClock.uptimeMillis() < end) {
            instrumentation.waitForIdleSync();
            screen.onActivity(activity -> ready.set(activity.getResources().getConfiguration().orientation == orientation
                && activity.root.isLaidOut() && !activity.root.isLayoutRequested()
                && activity.findViewById(R.id.chord_analyze).getHeight() > 0));
            if (!ready.get()) Thread.sleep(80);
        }
        screenshot("Blaze-Android-Studio-Layout-Diagnostic.png");
        assertTrue("Studio never completed its layout", ready.get());
    }
    private void inject(MusicStudioActivity activity) {
        try {
            List<ChordEngine.Event> chords = new ArrayList<>();
            chords.add(new ChordEngine.Event(0, 4000, StudioChord.parse("C:maj7"), .8));
            chords.add(new ChordEngine.Event(4000, 4500, -2, .1));
            chords.add(new ChordEngine.Event(4500, 8000, StudioChord.parse("A:min9"), .8));
            chords.add(new ChordEngine.Event(8000, 12000, StudioChord.parse("G:13"), .8));
            StudioAnalyzer.Result result = new StudioAnalyzer.Result(chords, 12000, "C major", false, new float[]{.1f,.4f,.2f,.5f});
            result.identity = "instrumentation-ui-fixture"; result.sourceHash = "instrumentation-ui-fixture";
            result.tempo = 120; result.beats = new long[25]; for (int i = 0; i < 25; i++) result.beats[i] = i * 500;
            result.downbeats = new long[]{0, 2000, 4000, 6000, 8000, 10000, 12000}; result.meter = StudioMeter.estimate(result.beats, result.downbeats, 12000);
            activity.result = result;
            for (String name : new String[]{"loadRhythm", "render"}) { Method method = MusicStudioActivity.class.getDeclaredMethod(name); method.setAccessible(true); method.invoke(activity); }
            activity.onPlaybackTime(1500);
        } catch (Exception error) { throw new AssertionError(error); }
    }
    private static int dp(Context context, int value) { return Math.round(context.getResources().getDisplayMetrics().density * value); }
    private void assertTouchTarget(View view) { assertTrue("Control is smaller than 48dp", view.getHeight() >= dp(app, 48)); }
    private void assertFullyVisible(View view) {
        Rect visible = new Rect(); assertTrue("Control is outside the screen: " + (view instanceof TextView ? ((TextView)view).getText() : view.getTag()) + " size=" + view.getWidth() + "x" + view.getHeight(), view.getGlobalVisibleRect(visible));
        assertTrue("Control is clipped horizontally", visible.width() >= view.getWidth() - 1);
        assertTrue("Control is clipped vertically", visible.height() >= view.getHeight() - 1);
    }
    private String allText(View view) {
        StringBuilder text = new StringBuilder(); if (view instanceof TextView) text.append(((TextView)view).getText());
        if (view instanceof ViewGroup) for (int i = 0; i < ((ViewGroup)view).getChildCount(); i++) text.append(allText(((ViewGroup)view).getChildAt(i))); return text.toString();
    }
    private String shell(String command) throws IOException {
        try (InputStream input = new android.os.ParcelFileDescriptor.AutoCloseInputStream(instrumentation.getUiAutomation().executeShellCommand(command)); ByteArrayOutputStream out = new ByteArrayOutputStream()) { byte[] buffer = new byte[1024]; int count; while ((count = input.read(buffer)) != -1) out.write(buffer, 0, count); return out.toString("UTF-8"); }
    }
    private void screenshot(String name) throws Exception {
        instrumentation.waitForIdleSync(); Bitmap image = instrumentation.getUiAutomation().takeScreenshot(); assertNotNull(image);
        try (OutputStream output = new FileOutputStream(new File(app.getFilesDir(), name))) { assertTrue(image.compress(Bitmap.CompressFormat.PNG, 100, output)); } finally { image.recycle(); }
    }
}
