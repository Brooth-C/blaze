package com.brooth.blaze;

import android.app.UiModeManager;
import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class LogoThemeTest {
    @Test public void logoChangesWhenSystemThemeChanges()throws Exception{
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
        UiModeManager modes=app.getSystemService(UiModeManager.class);int previous=modes.getNightMode();
        android.app.UiAutomation automation=InstrumentationRegistry.getInstrumentation().getUiAutomation();
        automation.adoptShellPermissionIdentity("android.permission.MODIFY_DAY_NIGHT_MODE");
        try(ActivityScenario<MainActivity> screen=ActivityScenario.launch(MainActivity.class)){
            modes.setNightMode(UiModeManager.MODE_NIGHT_YES);expect(screen,Color.BLACK);
            modes.setNightMode(UiModeManager.MODE_NIGHT_NO);expect(screen,Color.WHITE);
            modes.setNightMode(UiModeManager.MODE_NIGHT_YES);expect(screen,Color.BLACK);
        }finally{modes.setNightMode(previous);automation.dropShellPermissionIdentity();}
    }
    private void expect(ActivityScenario<MainActivity> screen,int color)throws Exception{
        AtomicBoolean matches=new AtomicBoolean();long until=System.currentTimeMillis()+8000;
        while(!matches.get()&&System.currentTimeMillis()<until){
            try{screen.onActivity(a->matches.set(((ColorDrawable)a.findViewById(R.id.brand_logo).getBackground()).getColor()==color));}
            catch(IllegalStateException transition){/* System configuration recreation may be between activities. */}
            Thread.sleep(80);
        }assertTrue("Logo background did not follow system theme",matches.get());
    }
}
