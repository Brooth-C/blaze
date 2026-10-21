package com.brooth.blaze;

import android.content.Intent;
import androidx.test.platform.app.InstrumentationRegistry;

/** Explicit destinations keep the existing queue regressions independent of the new Explore default. */
final class AndroidTestScreens {
    private AndroidTestScreens() { }
    static Intent downloads() {
        return new Intent(InstrumentationRegistry.getInstrumentation().getTargetContext(), MainActivity.class)
            .putExtra("destination", "downloads");
    }
}
