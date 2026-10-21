package com.brooth.blaze;

import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class StartupTest {
    @Test public void formatAndPlaylistChoicesSurviveRotation(){
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(AndroidTestScreens.downloads())){
            scenario.onActivity(activity->{((android.widget.EditText)activity.findViewById(R.id.url_input)).setText("https://example.test/item");((android.widget.RadioGroup)activity.findViewById(R.id.download_mode)).check(R.id.audio_mode);((android.widget.Spinner)activity.findViewById(R.id.audio_choice)).setSelection(3);((android.widget.CheckBox)activity.findViewById(R.id.playlist_choice)).setChecked(true);});
            scenario.recreate();scenario.onActivity(activity->{assertEquals("https://example.test/item",((android.widget.EditText)activity.findViewById(R.id.url_input)).getText().toString());assertEquals(R.id.audio_mode,((android.widget.RadioGroup)activity.findViewById(R.id.download_mode)).getCheckedRadioButtonId());assertEquals(3,((android.widget.Spinner)activity.findViewById(R.id.audio_choice)).getSelectedItemPosition());assertTrue(((android.widget.CheckBox)activity.findViewById(R.id.playlist_choice)).isChecked());});
        }
    }
    @Test public void screenOpensAndEmbeddedRuntimeLoads() {
        try (ActivityScenario<MainActivity> scenario=ActivityScenario.launch(AndroidTestScreens.downloads())) {
            scenario.onActivity(activity -> {
                assertNotNull(activity.findViewById(R.id.url_input));
                android.graphics.drawable.BitmapDrawable logo=(android.graphics.drawable.BitmapDrawable)activity.getResources().getDrawable(R.drawable.blaze_logo,activity.getTheme());
                assertTrue("Logo exceeds conservative GPU texture size",logo.getBitmap().getWidth()<=2048);
                assertTrue("Logo exceeds conservative GPU texture size",logo.getBitmap().getHeight()<=2048);
            });
            android.graphics.Rect bounds=new android.graphics.Rect();
            InstrumentationRegistry.getInstrumentation().waitForIdleSync();
            boolean visible=false;
            for(int attempt=0;attempt<50&&!visible;attempt++){
                // Screenshot coordinates are screen coordinates, while
                // getGlobalVisibleRect is relative to the root view. Insets
                // and launch transitions can move that root between frames.
                scenario.onActivity(activity->{android.view.View logo=activity.findViewById(R.id.brand_logo);int[] location=new int[2];logo.getLocationOnScreen(location);bounds.set(location[0],location[1],location[0]+logo.getWidth(),location[1]+logo.getHeight());});
                android.graphics.Bitmap screen=InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();
                if(screen!=null){int colored=0;for(int y=Math.max(0,bounds.top);y<Math.min(screen.getHeight(),bounds.bottom);y++)for(int x=Math.max(0,bounds.left);x<Math.min(screen.getWidth(),bounds.right);x++){int color=screen.getPixel(x,y);if(android.graphics.Color.red(color)>150&&android.graphics.Color.red(color)>android.graphics.Color.blue(color)*2)colored++;}visible=colored>20;screen.recycle();}
                if(!visible)android.os.SystemClock.sleep(100);
            }
            assertTrue("Flame logo is missing from the rendered screen",visible);
        }
        if (!Python.isStarted()) Python.start(new AndroidPlatform(
            InstrumentationRegistry.getInstrumentation().getTargetContext()));
        PyObject module=Python.getInstance().getModule("blaze_mobile");
        assertEquals("https://example.com/video",module.callAttr("validate_url","https://example.com/video").toString());
        try { module.callAttr("validate_url","file:///etc/passwd"); fail("Unsafe link accepted"); }
        catch (PyException expected) { assertTrue(expected.getMessage().contains("HTTPS")); }
    }
}

