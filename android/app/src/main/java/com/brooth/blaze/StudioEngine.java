package com.brooth.blaze;

import android.content.Context;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.*;

/** Overlapping BTC contexts and the exact file-backed Windows advanced decoder. */
final class StudioEngine implements AutoCloseable {
    private final StudioModels models;
    private final Runnable check;
    private final StudioAnalyzer.Progress progress;
    private final File work, audio, weightedFile, baselineFile;
    private final OutputStream pcmOutput;
    private final RandomAccessFile weighted;
    private final float[] chunk=new float[StudioModels.CHUNK];
    private final ByteBuffer pcmBytes=ByteBuffer.allocate(16384).order(ByteOrder.LITTLE_ENDIAN);
    private final List<Float> peaks=new ArrayList<>();
    private int filled, fresh, frameCount, peakCount, peakStride=256;
    private float peak;
    private long samples,windowStart;
    private PyObject harmony;
    String key="—";
    StudioEngine(Context context,StudioModels models,Runnable check,StudioAnalyzer.Progress progress)throws Exception{
        this.models=models;this.check=check;this.progress=progress;
        File marker=File.createTempFile("studio-harmony-",".work",context.getCacheDir());if(!marker.delete()||!marker.mkdir())throw new IOException("Could not prepare local analysis.");
        work=marker;audio=new File(work,"audio.f32");weightedFile=new File(work,"weighted.f32");baselineFile=new File(work,"baseline.f32");
        pcmOutput=new BufferedOutputStream(new FileOutputStream(audio),65536);weighted=new RandomAccessFile(weightedFile,"rw");
        PythonRuntime.get(context);
    }
    void sample(double value)throws Exception{
        if(samples%16384==0)check.run();
        float v=(float)Math.max(-1,Math.min(1,value));chunk[filled++]=v;samples++;fresh++;
        if(pcmBytes.remaining()<4)flushAudio();pcmBytes.putFloat(v);
        peak=Math.max(peak,Math.abs(v));
        if(++peakCount>=peakStride){peaks.add(peak);peak=0;peakCount=0;compact();}
        if(filled==chunk.length)flushContext();
    }
    private void flushAudio()throws IOException{pcmOutput.write(pcmBytes.array(),0,pcmBytes.position());pcmBytes.clear();}
    private void compact(){if(peaks.size()>2048){for(int i=0;i<peaks.size()/2;i++)peaks.set(i,Math.max(peaks.get(2*i),peaks.get(2*i+1)));int size=peaks.size()/2;while(peaks.size()>size)peaks.remove(peaks.size()-1);peakStride*=2;}}
    private void flushContext()throws Exception{
        if(fresh==0)return;check.run();int length=filled;
        float[][] found=models.probabilities(Arrays.copyOf(chunk,length));
        int columns=models.labels.length,rowBytes=(columns+1)*4;byte[] old=new byte[rowBytes];
        for(int i=0;i<found.length;i++){
            long global=windowStart/2048+i;if(global*2048>=samples)break;
            int index=(int)global;long position=global*rowBytes;Arrays.fill(old,(byte)0);
            if(position+rowBytes<=weighted.length()){weighted.seek(position);weighted.readFully(old);}
            ByteBuffer values=ByteBuffer.wrap(old).order(ByteOrder.LITTLE_ENDIAN);
            float weight=(float)Math.max(.05,Math.min(Math.min(i+1,found.length-i),27)/27.0);
            for(int c=0;c<columns;c++)values.putFloat(c*4,values.getFloat(c*4)+found[i][c]*weight);
            values.putFloat(columns*4,values.getFloat(columns*4)+weight);weighted.seek(position);weighted.write(old);frameCount=Math.max(frameCount,index+1);
        }
        if(length==chunk.length){int half=chunk.length/2;System.arraycopy(chunk,half,chunk,0,half);filled=half;windowStart+=half;}else filled=0;
        fresh=0;
    }
    /** Close the streaming PCM writer before the neural rhythm reader opens it. */
    void decoded()throws Exception{flushContext();flushAudio();pcmOutput.flush();}
    File audioFile(){return audio;}
    long sampleCount(){return samples;}
    static int chord(String label){return StudioChord.parse(label);}
    List<ChordEngine.Event> finish(long[] beats)throws Exception{
        check.run();writeBaseline();
        progress.update("Reading harmony and tuning locally…");
        harmony=Python.getInstance().getModule("blaze_harmony").callAttr("Harmony",models.directory.getAbsolutePath(),work.getAbsolutePath(),audio.getAbsolutePath(),samples,check);
        JSONObject prepared=new JSONObject(harmony.callAttr("prepare").toString());int frames=prepared.getInt("frames");
        if(frames<=0||frames>1+StudioAnalyzer.MAX_SAMPLES/512)throw new IOException("Invalid advanced feature length.");
        File features=new File(prepared.getString("features"));if(!features.getCanonicalFile().getParentFile().equals(work.getCanonicalFile())||features.length()!=frames*252L*4)throw new IOException("Invalid advanced features.");
        File votes=new File(work,"votes.f32");
        try(RandomAccessFile source=new RandomAccessFile(features,"r")){
            for(int start=0;start<frames;start+=1034){
                check.run();int end=Math.min(frames,start+1292),count=end-start;byte[] bytes=new byte[count*252*4];source.seek(start*252L*4);source.readFully(bytes);ByteBuffer buffer=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN);
                float[][] input=new float[count][252];for(float[] row:input)for(int c=0;c<252;c++)row[c]=buffer.getFloat();
                models.advancedContext(input,votes);harmony.callAttr("accumulate",votes.getAbsolutePath(),start,count);
                progress.update("Advanced chord ensemble · "+Math.round(end*512.0/StudioModels.RATE)+" seconds analysed");if(end==frames)break;
            }
        }
        check.run();JSONObject response=new JSONObject(harmony.callAttr("finish",baselineFile.getAbsolutePath(),models.metadata.toString(),beats).toString());
        key=response.isNull("key")?"—":response.getString("key");
        JSONArray entries=response.getJSONArray("events");List<ChordEngine.Event> result=new ArrayList<>();long previous=0;
        for(int i=0;i<entries.length();i++){
            JSONObject entry=entries.getJSONObject(i);long start=Math.round(entry.getDouble("start")*1000),end=Math.round(entry.getDouble("end")*1000);
            int chord=StudioChord.parse(entry.getString("chord"));double confidence=entry.isNull("model_score")?0:entry.getDouble("model_score");
            if(start!=previous||end<=start||end>durationMs()||!Double.isFinite(confidence)||confidence<0||confidence>1)throw new IOException("Invalid advanced chord timeline.");
            result.add(new ChordEngine.Event(start,end,chord,confidence));previous=end;
        }
        if(result.isEmpty()||previous!=durationMs())throw new IOException("Incomplete advanced chord timeline.");
        check.run();return result;
    }
    private void writeBaseline()throws Exception{
        int columns=models.labels.length;byte[] row=new byte[(columns+1)*4];ByteBuffer data=ByteBuffer.wrap(row).order(ByteOrder.LITTLE_ENDIAN);
        try(OutputStream stream=new BufferedOutputStream(new FileOutputStream(baselineFile),65536)){weighted.seek(0);for(int i=0;i<frameCount;i++){if(i%256==0)check.run();weighted.readFully(row);float weight=data.getFloat(columns*4);if(weight<=0)throw new IOException("Incomplete original chord context.");for(int c=0;c<columns;c++)data.putFloat(c*4,data.getFloat(c*4)/weight);stream.write(row,0,columns*4);}}
    }
    long durationMs(){return Math.round(samples*1000.0/StudioModels.RATE);}
    float[] waveform(){if(peakCount>0){peaks.add(peak);compact();peakCount=0;}float[] result=new float[peaks.size()];for(int i=0;i<result.length;i++)result[i]=peaks.get(i);return result;}
    @Override public void close(){if(harmony!=null){try{harmony.callAttr("close");}catch(Exception ignored){}harmony.close();harmony=null;}try{pcmOutput.close();}catch(IOException ignored){}try{weighted.close();}catch(IOException ignored){}File[] files=work.listFiles();if(files!=null)for(File file:files)if(file.isFile())file.delete();work.delete();}
}
