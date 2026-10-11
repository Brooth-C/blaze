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
        try(ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)){
            scenario.onActivity(activity->{((android.widget.EditText)activity.findViewById(R.id.url_input)).setText("https://example.test/item");((android.widget.RadioGroup)activity.findViewById(R.id.download_mode)).check(R.id.audio_mode);((android.widget.Spinner)activity.findViewById(R.id.audio_choice)).setSelection(3);((android.widget.CheckBox)activity.findViewById(R.id.playlist_choice)).setChecked(true);});
            scenario.recreate();scenario.onActivity(activity->{assertEquals("https://example.test/item",((android.widget.EditText)activity.findViewById(R.id.url_input)).getText().toString());assertEquals(R.id.audio_mode,((android.widget.RadioGroup)activity.findViewById(R.id.download_mode)).getCheckedRadioButtonId());assertEquals(3,((android.widget.Spinner)activity.findViewById(R.id.audio_choice)).getSelectedItemPosition());assertTrue(((android.widget.CheckBox)activity.findViewById(R.id.playlist_choice)).isChecked());});
        }
    }
    @Test public void screenOpensAndEmbeddedRuntimeLoads() {
        try (ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> assertNotNull(activity.findViewById(R.id.url_input)));
        }
        if (!Python.isStarted()) Python.start(new AndroidPlatform(
            InstrumentationRegistry.getInstrumentation().getTargetContext()));
        PyObject module=Python.getInstance().getModule("blaze_mobile");
        assertEquals("https://example.com/video",module.callAttr("validate_url","https://example.com/video").toString());
        try { module.callAttr("validate_url","file:///etc/passwd"); fail("Unsafe link accepted"); }
        catch (PyException expected) { assertTrue(expected.getMessage().contains("HTTPS")); }
    }
}

