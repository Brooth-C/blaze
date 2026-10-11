package com.brooth.blaze;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.util.UUID;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class NativeMediaTest {
    @Test public void realNativeMp3MergeProbeAndJavaScript() throws Exception {
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
        Context tests=InstrumentationRegistry.getInstrumentation().getContext();
        File folder=new File(app.getCacheDir(),"native-test-"+UUID.randomUUID());assertTrue(folder.mkdirs());
        for(String name:new String[]{"fixture-audio.wav","fixture-video.mp4"}) {
            try(InputStream in=tests.getAssets().open(name);OutputStream out=new FileOutputStream(new File(folder,name))) {byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}
        }
        String script;try(InputStream in=tests.getAssets().open("native_test.py");ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);script=out.toString("UTF-8");}
        if(!Python.isStarted())Python.start(new AndroidPlatform(app));
        PyObject globals=Python.getInstance().getModule("builtins").callAttr("dict");
        globals.put("fixture_directory",folder.getAbsolutePath());
        File libs=new File(app.getApplicationInfo().nativeLibraryDir);
        globals.put("ffmpeg_path",new File(libs,"libblaze_ffmpeg.so").getAbsolutePath());
        globals.put("ffprobe_path",new File(libs,"libblaze_ffprobe.so").getAbsolutePath());
        globals.put("quickjs_path",new File(libs,"libblaze_qjs.so").getAbsolutePath());
        Python.getInstance().getModule("builtins").callAttr("exec",script,globals);
        assertTrue(new File(folder,"merged.mkv").length()>0);
    }
}
