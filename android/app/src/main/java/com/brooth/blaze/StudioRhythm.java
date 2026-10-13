package com.brooth.blaze;
import org.json.*;
final class StudioRhythm {
    static StudioTimeline.Rhythm read(String text)throws Exception{StudioTimeline.Rhythm r=new StudioTimeline.Rhythm();if(text==null||text.isEmpty())return r;JSONObject o=new JSONObject(text);r.mode=o.getString("mode");r.bpm=o.optDouble("bpm",120);r.numerator=o.optInt("numerator",4);r.denominator=o.optInt("denominator",4);r.offset=Math.round(o.optDouble("offset",0)*1000);r.compound=o.optBoolean("compound");JSONArray a=o.optJSONArray("changes");if(a!=null)for(int i=0;i<a.length();i++){JSONObject c=a.getJSONObject(i);r.changes.add(new StudioTimeline.Change(Math.round(c.getDouble("time")*1000),c.getInt("numerator"),c.getInt("denominator"),c.optBoolean("compound")));}return r;}
    static String write(StudioTimeline.Rhythm r)throws Exception{JSONArray a=new JSONArray();for(StudioTimeline.Change c:r.changes)a.put(new JSONObject().put("time",c.time/1000.0).put("numerator",c.numerator).put("denominator",c.denominator).put("compound",c.compound));return new JSONObject().put("mode",r.mode).put("bpm",r.bpm).put("numerator",r.numerator).put("denominator",r.denominator).put("offset",r.offset/1000.0).put("compound",r.compound).put("changes",a).toString();}
    static JSONObject meterWrite(StudioMeter.Estimate meter)throws Exception{
        JSONArray bars=new JSONArray();
        for(StudioMeter.Bar bar:meter.bars){JSONArray beats=new JSONArray();for(long time:bar.beats)beats.put(time/1000.0);bars.put(new JSONObject().put("start",bar.start/1000.0).put("end",bar.end/1000.0).put("beats",beats).put("beats_per_bar",bar.beatsPerBar));}
        return new JSONObject().put("beats_per_bar",meter.beatsPerBar>0?meter.beatsPerBar:JSONObject.NULL).put("denominator",JSONObject.NULL).put("label",meter.label).put("confidence_kind","bar_consistency").put("confidence",Double.isFinite(meter.confidence)?meter.confidence:JSONObject.NULL).put("bars",bars);
    }
    static StudioMeter.Estimate meterRead(JSONObject object,long duration)throws Exception{
        StudioMeter.Estimate result=new StudioMeter.Estimate();if(object==null)return result;
        JSONArray bars=object.optJSONArray("bars");if(bars==null||bars.length()==0)return result;
        double confidence=object.optDouble("confidence",Double.NaN);if(!Double.isFinite(confidence)||confidence<0||confidence>1||bars.length()>40000)throw new IllegalArgumentException("Invalid meter result.");
        long previous=0;int count=-1;
        for(int i=0;i<bars.length();i++){
            JSONObject bar=bars.getJSONObject(i);long start=Math.round(bar.getDouble("start")*1000),end=Math.round(bar.getDouble("end")*1000);JSONArray values=bar.getJSONArray("beats");int n=bar.getInt("beats_per_bar");
            if(start<previous||end<=start||end>duration||n<2||n>12||values.length()!=n)throw new IllegalArgumentException("Invalid meter boundaries.");
            long[] beats=new long[n];long last=start-1;
            for(int j=0;j<n;j++){double seconds=values.getDouble(j);if(!Double.isFinite(seconds))throw new IllegalArgumentException("Invalid meter pulse.");long time=Math.round(seconds*1000);if(time<=last||time<start||time>=end||(j==0&&time!=start))throw new IllegalArgumentException("Invalid meter pulse.");beats[j]=time;last=time;}
            result.bars.add(new StudioMeter.Bar(start,end,beats));previous=end;count=count<0?n:count==n?count:0;
        }
        result.beatsPerBar=count;result.label=count>0?count+" beats/bar":"Variable meter";result.confidence=confidence;return result;
    }
}
