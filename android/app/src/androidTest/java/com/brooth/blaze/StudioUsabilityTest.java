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
        try (ActivityScenario<MainActivity> screen = ActivityScenario.launch(AndroidTestScreens.downloads())) {
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

    @Test public void studioAnalyzesAndPlaysSelectedAudio() throws Exception {
        File wave=File.createTempFile("studio-playback-", ".wav",DownloadService.folder(app));
        MusicStudioTest.writeWave(wave,false,12);
        android.net.Uri uri=androidx.core.content.FileProvider.getUriForFile(app,app.getPackageName()+".files",wave);
        try(ActivityScenario<MusicStudioActivity> screen=ActivityScenario.launch(new Intent(app,MusicStudioActivity.class).setData(uri))) {
            java.util.concurrent.atomic.AtomicBoolean analysed=new java.util.concurrent.atomic.AtomicBoolean();
            screen.onActivity(activity->activity.findViewById(R.id.chord_analyze).performClick());
            long deadline=android.os.SystemClock.uptimeMillis()+90000;
            while(!analysed.get()&&android.os.SystemClock.uptimeMillis()<deadline) {
                screen.onActivity(activity->analysed.set(activity.result!=null)); Thread.sleep(100);
            }
            assertTrue("Studio did not finish selected-file analysis",analysed.get());
            screen.onActivity(activity->{if(activity.player!=null&&!activity.player.isPlaying())activity.toggle.performClick();});
            java.util.concurrent.atomic.AtomicBoolean playing=new java.util.concurrent.atomic.AtomicBoolean();
            deadline=android.os.SystemClock.uptimeMillis()+20000;
            while(!playing.get()&&android.os.SystemClock.uptimeMillis()<deadline) {
                screen.onActivity(activity->playing.set(activity.player!=null&&activity.player.isPlaying()&&activity.player.getTime()>500)); Thread.sleep(100);
            }
            assertTrue("Studio audio did not play with the preview collapsed",playing.get());
            screen.onActivity(activity->{activity.toggle.performClick();activity.seekPlayback(4500);assertTrue(activity.result.events.size()>0);});
            screenshot("Blaze-Android-Studio-Real-Analysis.png");
        } finally {wave.delete();app.getSharedPreferences("playback",Context.MODE_PRIVATE).edit().remove("document:"+uri).apply();}
    }
    @Test public void studioVideoSwitchesKeepTheSamePlayerAndPausedFrame() throws Exception {
        File video = File.createTempFile("studio-video-", ".mkv", DownloadService.folder(app));
        try (InputStream input = instrumentation.getContext().getAssets().open("player-hevc.mkv"); OutputStream output = new FileOutputStream(video)) {
            byte[] bytes = new byte[8192]; int count; while ((count = input.read(bytes)) != -1) output.write(bytes, 0, count);
        }
        android.net.Uri uri = androidx.core.content.FileProvider.getUriForFile(app, app.getPackageName() + ".files", video);
        try (ActivityScenario<MusicStudioActivity> screen = ActivityScenario.launch(new Intent(app, MusicStudioActivity.class).setData(uri).putExtra("software", true))) {
            java.util.concurrent.atomic.AtomicBoolean ready = new java.util.concurrent.atomic.AtomicBoolean();
            long deadline = android.os.SystemClock.uptimeMillis() + 20000;
            while (!ready.get() && android.os.SystemClock.uptimeMillis() < deadline) {
                screen.onActivity(activity -> ready.set(activity.player != null && activity.player.isPlaying() && activity.player.getTime() > 100 && activity.player.getLength() > 1500)); Thread.sleep(50);
            }
            assertTrue("Collapsed Studio must play the original video's audio", ready.get());
            java.util.concurrent.atomic.AtomicReference<org.videolan.libvlc.MediaPlayer> original = new java.util.concurrent.atomic.AtomicReference<>();
            screen.onActivity(activity -> {
                activity.toggle.performClick(); activity.seekPlayback(1000); original.set(activity.player);
                assertTrue(activity.player.getAudioTracksCount() > 0);
            });
            shell("dumpsys gfxinfo com.brooth.blaze reset");
            screen.onActivity(activity -> videoChoice(activity).performClick());
            waitForVideoFrame(screen, original.get());
            screen.onActivity(activity -> {
                assertSame("Showing the preview must not reopen the media", original.get(), activity.player);
                assertFalse("Showing video must preserve a user's pause", activity.player.isPlaying());
                assertTrue(activity.videoViewport.getHeight() >= dp(activity, 112));
                activity.setPlaybackFullscreen(true);
            });
            waitForVideoFrame(screen, original.get());
            screen.onActivity(activity -> {
                assertSame(original.get(), activity.player); assertFalse(activity.player.isPlaying());
                activity.setPlaybackFullscreen(false); videoChoice(activity).performClick();
                assertSame("Hiding video must retain the audio player", original.get(), activity.player);
                activity.toggle.performClick();
            });
            ready.set(false); deadline = android.os.SystemClock.uptimeMillis() + 5000;
            while (!ready.get() && android.os.SystemClock.uptimeMillis() < deadline) {
                screen.onActivity(activity -> ready.set(activity.player == original.get() && activity.player.isPlaying() && activity.player.getTime() > 1100)); Thread.sleep(50);
            }
            assertTrue("Audio must continue from the same point after hiding video", ready.get());
            try (OutputStream output = new FileOutputStream(new File(app.getFilesDir(), "Studio-Frames.txt"))) {
                output.write(("Flow: Studio HEVC preview/fullscreen toggle, pause preserved, then resume.\n" + shell("dumpsys gfxinfo com.brooth.blaze") + "\n" + shell("dumpsys gfxinfo com.brooth.blaze framestats")).getBytes(java.nio.charset.StandardCharsets.UTF_8));
            }
        } finally { video.delete(); app.getSharedPreferences("playback", Context.MODE_PRIVATE).edit().remove("document:" + uri).apply(); }
    }
    @Test public void timelineDragPreviewsWithoutRepeatedDecoderSeeks() throws Exception {
        File wave = File.createTempFile("studio-drag-", ".wav", DownloadService.folder(app)); MusicStudioTest.writeWave(wave, false, 12);
        android.net.Uri uri = androidx.core.content.FileProvider.getUriForFile(app, app.getPackageName() + ".files", wave);
        try (ActivityScenario<MusicStudioActivity> screen = ActivityScenario.launch(new Intent(app, MusicStudioActivity.class).setData(uri))) {
            instrumentation.waitForIdleSync();
            screen.onActivity(activity -> {
                if (activity.player != null && activity.player.isPlaying()) activity.toggle.performClick(); inject(activity);
                StudioFlowView flow = (StudioFlowView)activity.root.findViewWithTag("studio_timeline");
                final int[] commits = {0}, previews = {0}; final long[] selected = {-1};
                flow.seek = new StudioFlowView.Seek() {
                    public void to(long time) { commits[0]++; selected[0] = time; }
                    public void preview(long time) { previews[0]++; }
                };
                float origin = flow.getWidth() * .32f, cell = Math.max(dp(activity, 64), flow.getWidth() / 5f), y = flow.getHeight() / 2f;
                long start = android.os.SystemClock.uptimeMillis();
                touch(flow, start, MotionEvent.ACTION_DOWN, origin, y);
                for (int step = 1; step <= 10; step++) touch(flow, start, MotionEvent.ACTION_MOVE, origin + cell * step / 10f, y);
                assertEquals("Dragging must not flood LibVLC with seeks", 0, commits[0]); assertTrue(previews[0] > 0);
                touch(flow, start, MotionEvent.ACTION_UP, origin + cell, y);
                assertEquals(1, commits[0]); assertEquals("Drag stays anchored to the starting beat", 2000, selected[0]);
            });
        } finally { wave.delete(); app.getSharedPreferences("playback", Context.MODE_PRIVATE).edit().remove("document:" + uri).apply(); }
    }
    private void touch(View view, long start, int action, float x, float y) {
        MotionEvent event = MotionEvent.obtain(start, android.os.SystemClock.uptimeMillis(), action, x, y, 0);
        try { view.onTouchEvent(event); } finally { event.recycle(); }
    }
    private Button videoChoice(MusicStudioActivity activity) {
        try { java.lang.reflect.Field field = MusicStudioActivity.class.getDeclaredField("videoChoice"); field.setAccessible(true); return (Button)field.get(activity); }
        catch (Exception failure) { throw new AssertionError(failure); }
    }
    private void waitForVideoFrame(ActivityScenario<MusicStudioActivity> screen, org.videolan.libvlc.MediaPlayer expected) throws Exception {
        long deadline = android.os.SystemClock.uptimeMillis() + 10000; boolean rendered = false;
        while (!rendered && android.os.SystemClock.uptimeMillis() < deadline) {
            Rect bounds = new Rect(); screen.onActivity(activity -> { assertSame(expected, activity.player); activity.video.getGlobalVisibleRect(bounds); });
            Bitmap image = instrumentation.getUiAutomation().takeScreenshot(); assertNotNull(image);
            try {
                int red = 0;
                for (int y = Math.max(0, bounds.top); y < Math.min(image.getHeight(), bounds.bottom); y += 2)
                    for (int x = Math.max(0, bounds.left); x < Math.min(image.getWidth(), bounds.right); x += 2) {
                        int color = image.getPixel(x, y); if (Color.red(color) > 150 && Color.red(color) > Color.blue(color) * 2) red++;
                    }
                rendered = red > 100;
            } finally { image.recycle(); }
            if (!rendered) Thread.sleep(100);
        }
        assertTrue("Studio must display the decoded HEVC picture, including while paused", rendered);
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
                        TextView chord = activity.findViewById(R.id.chord_current);
                        assertEquals("Cmaj7", chord.getText().toString());
                        assertNotNull("Current chord has no text layout", chord.getLayout());
                        assertEquals("The chord name must remain readable", 0, chord.getLayout().getEllipsisCount(0));
                        assertEquals("Current chord: Cmaj7", chord.getContentDescription().toString());
                        activity.onPlaybackTime(4200);
                        assertEquals("\u2014", ((TextView)activity.findViewById(R.id.chord_current)).getText().toString());
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
        java.util.concurrent.atomic.AtomicReference<String> details = new java.util.concurrent.atomic.AtomicReference<>("");
        screen.onActivity(activity -> details.set("orientation=" + activity.getResources().getConfiguration().orientation + " " + layoutTree(activity.root)));
        assertTrue("Studio never completed its layout: " + details.get(), ready.get());
    }
    private String layoutTree(View view) {
        String info = view.getClass().getSimpleName() + "[" + view.getWidth() + "x" + view.getHeight() + ",v=" + view.getVisibility() + ",tag=" + view.getTag()
            + (view instanceof TextView ? ",text=" + ((TextView)view).getText() : "") + "]";
        if (view instanceof ViewGroup) for (int i=0;i<((ViewGroup)view).getChildCount();i++) info += layoutTree(((ViewGroup)view).getChildAt(i));
        return info;
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
