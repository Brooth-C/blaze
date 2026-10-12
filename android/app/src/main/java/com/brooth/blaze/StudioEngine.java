package com.brooth.blaze;
import java.util.*;

/** Streaming adapter for the frozen neural model; no heuristic fallback. */
final class StudioEngine {
    private final StudioModels models;
    private final float[] chunk=new float[StudioModels.CHUNK];
    private final List<ChordEngine.Event> frames=new ArrayList<>();
    private final List<Float> peaks=new ArrayList<>();
    private int filled,peakCount,peakStride=256;
    private float peak;
    private long samples,processed;
    StudioEngine(StudioModels models){this.models=models;}
    void sample(double value)throws Exception{
        float v=(float)Math.max(-1,Math.min(1,value));chunk[filled++]=v;samples++;
        peak=Math.max(peak,Math.abs(v));
        if(++peakCount>=peakStride){peaks.add(peak);peak=0;peakCount=0;compact();}
        if(filled==chunk.length)flush();
    }
    private void compact(){if(peaks.size()>2048){for(int i=0;i<peaks.size()/2;i++)peaks.set(i,Math.max(peaks.get(2*i),peaks.get(2*i+1)));int size=peaks.size()/2;while(peaks.size()>size)peaks.remove(peaks.size()-1);peakStride*=2;}}
    private void flush()throws Exception{
        if(filled==0)return;
        int length=filled;float[] input=Arrays.copyOf(chunk,Math.max(4410,length));
        StudioModels.Prediction[] found=models.predict(input);
        for(int i=0;i<found.length;i++){
            long start=Math.round((processed+Math.min(length,i*2048L))*1000.0/StudioModels.RATE);
            long end=Math.round((processed+(i+1==found.length?length:Math.min(length,(i+1)*2048L)))*1000.0/StudioModels.RATE);
            if(end>start)frames.add(new ChordEngine.Event(start,end,chord(found[i].chord),found[i].score));
        }
        processed+=length;filled=0;
    }
    static int chord(String label){if("N".equals(label))return -1;if("X".equals(label))return -2;String[] parts=label.split(":");for(int i=0;i<12;i++)if(ChordEngine.NOTES[i].equals(parts[0]))return i+(parts.length>1&&"min".equals(parts[1])?12:0);return -2;}
    List<ChordEngine.Event> finish()throws Exception{
        flush();List<ChordEngine.Event> result=new ArrayList<>();
        for(ChordEngine.Event e:frames){if(!result.isEmpty()&&result.get(result.size()-1).chord==e.chord){ChordEngine.Event prev=result.remove(result.size()-1);double score=(prev.confidence*(prev.endMs-prev.startMs)+e.confidence*(e.endMs-e.startMs))/(e.endMs-prev.startMs);result.add(new ChordEngine.Event(prev.startMs,e.endMs,e.chord,score));}else result.add(e);}
        return result;
    }
    long durationMs(){return Math.round(samples*1000.0/StudioModels.RATE);}
    float[] waveform(){if(peakCount>0){peaks.add(peak);compact();peakCount=0;}float[] result=new float[peaks.size()];for(int i=0;i<result.length;i++)result[i]=peaks.get(i);return result;}
}
