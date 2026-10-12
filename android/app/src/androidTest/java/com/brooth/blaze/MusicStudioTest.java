package com.brooth.blaze;
import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.util.*;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class MusicStudioTest {
    private final Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
    @Test public void pretrainedAudioIsLocalTimedAndCached() throws Exception {
        File wave=File.createTempFile("studio-reference-",".wav",app.getCacheDir());
        try{writeWave(wave,false,12);StudioAnalyzer.Result r=new StudioAnalyzer().analyze(app,wave,null,message->{});
            Set<String> labels=new HashSet<>();long end=0;for(ChordEngine.Event e:r.events){assertEquals(end,e.startMs);assertTrue(e.endMs>e.startMs);labels.add(e.label(0));end=e.endMs;}
            assertEquals(12000,end);assertTrue(labels.contains("C"));assertTrue(labels.contains("Am"));assertTrue(labels.contains("G"));assertTrue(r.waveform.length>0);
            StudioAnalyzer.Result cached=new StudioAnalyzer().analyze(app,wave,null,message->{});assertTrue(cached.cached);assertEquals(r.identity,cached.identity);
            StudioAnalyzer cancelled=new StudioAnalyzer();cancelled.cancel();try{cancelled.analyze(app,wave,null,message->{});fail("Cancelled analysis ran");}catch(java.util.concurrent.CancellationException expected){}
        }finally{wave.delete();}
    }
    @Test public void silenceHasNoChord() throws Exception {
        File wave=File.createTempFile("studio-silence-",".wav",app.getCacheDir());
        try{writeWave(wave,true,1);StudioAnalyzer.Result r=new StudioAnalyzer().analyze(app,wave,null,message->{});for(ChordEngine.Event e:r.events)assertEquals(-1,e.chord);}finally{wave.delete();}
    }
    static void writeWave(File file,boolean silence,int seconds)throws Exception{
        int rate=22050,count=rate*seconds;try(DataOutputStream out=new DataOutputStream(new FileOutputStream(file))){out.writeBytes("RIFF");le(out,36+count*2,4);out.writeBytes("WAVEfmt ");le(out,16,4);le(out,1,2);le(out,1,2);le(out,rate,4);le(out,rate*2,4);le(out,2,2);le(out,16,2);out.writeBytes("data");le(out,count*2,4);
            for(int i=0;i<count;i++){double sample=0;int segment=Math.min(2,i/(rate*4)),root=new int[]{48,57,55}[segment];double time=(i%(rate*4))/(double)rate;for(int interval:new int[]{0,segment==1?3:4,7}){double f=440*Math.pow(2,(root+interval-69)/12.0);for(int h=1;h<=4;h++)sample+=.12/(h*h)*Math.sin(2*Math.PI*f*h*time);}le(out,silence?0:(int)(sample*32767),2);}
        }
    }
    static void le(DataOutputStream out,int value,int bytes)throws IOException{for(int i=0;i<bytes;i++)out.writeByte(value>>>(8*i));}
}
