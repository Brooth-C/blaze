package com.brooth.blaze;

import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;
import static org.junit.Assert.*;

/** Android ONNX/Python parity on a generated musical fixture; no private recordings. */
@RunWith(AndroidJUnit4.class)
public class StudioBeatDetectorTest {
    private final Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
    @Test public void nativeBeatMapMatchesWindowsAndDoesNotInventSilenceBars() throws Exception {
        JSONObject reference;
        try(InputStream input=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open("rhythm_parity.json")){
            reference=new JSONObject(new String(StudioModels.read(input,65536),java.nio.charset.StandardCharsets.UTF_8));
        }
        File pcm=File.createTempFile("rhythm-reference-",".f32",app.getCacheDir());
        try{
            writeFixture(pcm,16,false);
            StudioBeatDetector.Result found=StudioBeatDetector.analyze(app,pcm,16L*22050,()->{},message->{});
            assertArrayEquals(milliseconds(reference.getJSONArray("beats")),found.beats);
            assertArrayEquals(milliseconds(reference.getJSONArray("downbeats")),found.downbeats);
            assertEquals(reference.getDouble("tempo_bpm"),found.bpm,0);
            assertEquals(reference.getString("rhythm_model_sha256"),found.modelHash);
            JSONObject meter=reference.getJSONObject("meter");
            assertEquals(meter.getString("label"),found.meter.label);
            assertEquals(meter.getJSONArray("bars").length(),found.meter.bars.size());
            assertTrue(found.meter.usable());assertTrue(StudioRhythm.meterWrite(found.meter).isNull("denominator"));
            StudioMeter.Estimate roundTrip=StudioRhythm.meterRead(StudioRhythm.meterWrite(found.meter),16000);
            assertEquals(found.meter.bars.size(),roundTrip.bars.size());
            for(int i=0;i<roundTrip.bars.size();i++)assertArrayEquals(found.meter.bars.get(i).beats,roundTrip.bars.get(i).beats);
            writeFixture(pcm,5,true);
            StudioBeatDetector.Result silent=StudioBeatDetector.analyze(app,pcm,5L*22050,()->{},message->{});
            assertEquals(0,silent.beats.length);assertEquals(0,silent.downbeats.length);assertFalse(silent.meter.usable());assertFalse(Double.isFinite(silent.bpm));
            File[] leftovers=app.getCacheDir().listFiles(file->file.getName().startsWith("blaze-rhythm-")&&file.getName().endsWith(".f32"));
            assertNotNull(leftovers);assertEquals(0,leftovers.length);
        }finally{pcm.delete();}
    }
    private static long[] milliseconds(JSONArray values)throws Exception{
        long[] result=new long[values.length()];for(int i=0;i<result.length;i++)result[i]=Math.round(values.getDouble(i)*1000);return result;
    }
    private static void writeFixture(File file,int seconds,boolean silence)throws Exception{
        final int rate=22050;ByteBuffer buffer=ByteBuffer.allocate(16384*4).order(ByteOrder.LITTLE_ENDIAN);
        double[] notes={130.81278265,164.81377846,195.99771799};
        try(OutputStream output=new BufferedOutputStream(new FileOutputStream(file))){
            for(int position=0;position<rate*seconds;position++){
                double time=position/(double)rate,local=(position%11025)/(double)rate;int pulse=position/11025;double accent=pulse%4==0?1:.55;
                double value=accent*(.42*Math.exp(-local*45)*Math.sin(2*Math.PI*(65*local+35*local*Math.exp(-local*25)))+.13*Math.exp(-local*130)*Math.sin(2*Math.PI*3200*local));
                for(double frequency:notes)value+=.04*Math.sin(2*Math.PI*frequency*time)*(.4+.6*Math.exp(-local*8));
                buffer.putFloat(silence?0:(float)value);
                if(!buffer.hasRemaining()){output.write(buffer.array());buffer.clear();}
            }
            output.write(Arrays.copyOf(buffer.array(),buffer.position()));
        }
    }
}
