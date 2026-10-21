package com.brooth.blaze;

import android.content.Context;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

/** One application-scoped interpreter startup boundary for independent workers. */
public final class PythonRuntime {
    private PythonRuntime() { }
    public static Python get(Context context) {
        synchronized (Python.class) {
            if (!Python.isStarted()) Python.start(new AndroidPlatform(context.getApplicationContext()));
            return Python.getInstance();
        }
    }
}
