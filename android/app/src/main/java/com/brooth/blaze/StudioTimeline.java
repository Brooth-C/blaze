package com.brooth.blaze;
import java.util.*;

/** Indexed musical timeline in media milliseconds; never owns a playback clock. */
final class StudioTimeline {
    static final class Rhythm {String mode="unknown";double bpm=120;int numerator=4,denominator=4;long offset;boolean compound;List<Change> changes=new ArrayList<>();}
    static final class Change {long time;int numerator,denominator;boolean compound;Change(long t,int n,int d,boolean c){time=t;numerator=n;denominator=d;compound=c;}}
    static final class Beat {long time;int index,total;Beat(long t,int i,int count){time=t;index=i;total=count;}}
    static final class Region {long start,end;int chord,index;Region(long a,long b,int c,int i){start=a;end=b;chord=c;index=i;}}
    static final class Measure {long start,end;int numerator,denominator;String kind;List<Beat> beats=new ArrayList<>();List<Region> regions=new ArrayList<>();Measure(long a,long b,int n,int d,String k){start=a;end=b;numerator=n;denominator=d;kind=k;}}
    static final class State {long time;boolean ended;int chord=-1,next=-1,measure=-1,group=-1;double progress,remainingBeats=Double.NaN;long remaining=-1;Beat beat;}
    final long duration;final List<ChordEngine.Event> chords;final List<Measure> measures=new ArrayList<>();final List<Beat> beats=new ArrayList<>();final int[] next;final long[] chordStarts;long[] measureStarts,beatTimes;int barStart;
    StudioTimeline(long duration,List<ChordEngine.Event> chords,long[] detected,Rhythm rhythm){
        if(duration<=0||duration>7200000)throw new IllegalArgumentException("Invalid media duration.");this.duration=duration;this.chords=chords;Rhythm c=rhythm==null?new Rhythm():rhythm;
        if(!Arrays.asList("unknown","beats","grid").contains(c.mode)||c.offset<0||c.offset>=duration||c.numerator<1||c.numerator>12||!denominator(c.denominator)||c.changes.size()>100)throw new IllegalArgumentException("Choose a valid rhythm grid and meter.");
        if("grid".equals(c.mode)&&(!Double.isFinite(c.bpm)||c.bpm<20||c.bpm>300))throw new IllegalArgumentException("Choose a BPM between 20 and 300.");
        if("beats".equals(c.mode)&&detected.length<2)throw new IllegalArgumentException("No usable beat map. Choose a manual tempo grid.");
        next=new int[chords.size()];Arrays.fill(next,-1);chordStarts=new long[chords.size()];for(int i=0;i<chords.size();i++)chordStarts[i]=chords.get(i).startMs;
        for(int i=chords.size()-2;i>=0;i--)next[i]=chords.get(i).chord==chords.get(i+1).chord?next[i+1]:i+1;
        if("unknown".equals(c.mode)){for(long t=0;t<duration;t+=4000)measures.add(new Measure(t,Math.min(duration,t+4000),0,0,"unknown"));}
        else{
            if(c.offset>0){measures.add(new Measure(0,c.offset,0,0,"lead-in"));barStart=1;}
            List<Change> sections=new ArrayList<>();sections.add(new Change(c.offset,c.numerator,c.denominator,c.compound));long previous=c.offset;
            for(Change change:c.changes){if(change.time<=previous||change.time>=duration||change.numerator<1||change.numerator>12||!denominator(change.denominator))throw new IllegalArgumentException("Meter changes need increasing times and valid signatures.");sections.add(change);previous=change.time;}
            for(int j=0;j<sections.size();j++){
                Change s=sections.get(j);long end=j+1<sections.size()?sections.get(j+1).time:duration;boolean compound=s.compound&&s.denominator==8&&s.numerator%3==0;int count=compound?s.numerator/3:s.numerator;
                List<Long> points=new ArrayList<>();points.add(s.time);
                if("grid".equals(c.mode)){double step=60000/c.bpm*4/s.denominator*(compound?3:1);for(int i=1;i<100000;i++){long t=Math.round(s.time+i*step);if(t>=end)break;if(t>points.get(points.size()-1))points.add(t);}}
                else{long last=s.time;for(long t:detected)if(t>last&&t<end){points.add(t);last=t;}}
                for(int i=0;i<points.size();i+=count){Measure m=new Measure(points.get(i),i+count<points.size()?points.get(i+count):end,s.numerator,s.denominator,"grid".equals(c.mode)?"manual":"estimated");for(int k=i;k<Math.min(points.size(),i+count);k++){Beat beat=new Beat(points.get(k),k-i,count);m.beats.add(beat);beats.add(beat);}measures.add(m);}
            }
        }
        measureStarts=new long[measures.size()];int cursor=0;for(int m=0;m<measures.size();m++){Measure measure=measures.get(m);measureStarts[m]=measure.start;while(cursor<chords.size()&&chords.get(cursor).endMs<=measure.start)cursor++;for(int i=cursor;i<chords.size()&&chords.get(i).startMs<measure.end;i++){ChordEngine.Event e=chords.get(i);long a=Math.max(e.startMs,measure.start),b=Math.min(e.endMs,measure.end);if(b>a)measure.regions.add(new Region(a,b,e.chord,i));}}
        beatTimes=new long[beats.size()];for(int i=0;i<beats.size();i++)beatTimes[i]=beats.get(i).time;
    }
    static boolean denominator(int d){return d==2||d==4||d==8||d==16;}
    static int upper(long[] values,long time){int a=0,b=values.length;while(a<b){int m=(a+b)>>>1;if(values[m]<=time)a=m+1;else b=m;}return a;}
    double coordinate(long time){int i=upper(beatTimes,time)-1;return i<0||i>=beatTimes.length-1?Double.NaN:i+(double)(time-beatTimes[i])/(beatTimes[i+1]-beatTimes[i]);}
    State state(long time){State s=new State();s.time=Math.max(0,Math.min(duration,time));s.ended=s.time>=duration;s.chord=s.ended?-1:upper(chordStarts,s.time)-1;if(s.chord>=0&&s.time>=chords.get(s.chord).endMs)s.chord=-1;s.next=s.chord<0?-1:next[s.chord];s.measure=Math.max(0,Math.min(measures.size()-1,upper(measureStarts,s.time)-1));s.group=Math.max(0,s.measure-barStart)/4;Measure m=measures.get(s.measure);s.progress=Math.max(0,Math.min(1,(double)(s.time-m.start)/(m.end-m.start)));int i=upper(beatTimes,s.time)-1;if(!s.ended&&i>=0&&m.beats.contains(beats.get(i)))s.beat=beats.get(i);if(s.next>=0){s.remaining=Math.max(0,chords.get(s.next).startMs-s.time);double a=coordinate(s.time),b=coordinate(chords.get(s.next).startMs);if(Double.isFinite(a)&&Double.isFinite(b))s.remainingBeats=Math.max(0,b-a);}return s;}
}
