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
    @Test public void screenOpensAndEmbeddedRuntimeLoads() {
        try (ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> assertNotNull(activity.findViewById(1001)));
        }
        if (!Python.isStarted()) Python.start(new AndroidPlatform(
            InstrumentationRegistry.getInstrumentation().getTargetContext()));
        PyObject module=Python.getInstance().getModule("blaze_mobile");
        assertEquals("https://example.com/video",module.callAttr("validate_url","https://example.com/video").toString());
        try { module.callAttr("validate_url","file:///etc/passwd"); fail("Unsafe link accepted"); }
        catch (PyException expected) { assertTrue(expected.getMessage().contains("HTTPS")); }
    }
}
