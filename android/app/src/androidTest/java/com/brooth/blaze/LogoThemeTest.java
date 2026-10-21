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
    @Test public void logoStaysClearAcrossSystemThemeChanges()throws Exception{
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
        UiModeManager modes=app.getSystemService(UiModeManager.class);int previous=modes.getNightMode();
        android.app.UiAutomation automation=InstrumentationRegistry.getInstrumentation().getUiAutomation();
        try(ActivityScenario<MainActivity> screen=ActivityScenario.launch(AndroidTestScreens.downloads())){
            night(automation,"yes");expect(screen,Color.TRANSPARENT);
            night(automation,"no");expect(screen,Color.TRANSPARENT);
            night(automation,"yes");expect(screen,Color.TRANSPARENT);
        }finally{night(automation,new String[]{"auto","no","yes"}[Math.max(0,Math.min(2,previous))]);}
    }
    private void night(android.app.UiAutomation automation,String value)throws Exception{
        try(java.io.InputStream input=new android.os.ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("cmd uimode night "+value))){byte[] buffer=new byte[1024];while(input.read(buffer)!=-1){/* Wait for command completion. */}}
    }
    private void expect(ActivityScenario<MainActivity> screen,int color)throws Exception{
        AtomicBoolean matches=new AtomicBoolean();long until=System.currentTimeMillis()+8000;
        while(!matches.get()&&System.currentTimeMillis()<until){
            try{screen.onActivity(a->matches.set(((ColorDrawable)a.findViewById(R.id.brand_logo).getBackground()).getColor()==color));}
            catch(IllegalStateException transition){/* System configuration recreation may be between activities. */}
            Thread.sleep(80);
        }assertTrue("Logo gained a mismatched opaque background",matches.get());
    }
}
