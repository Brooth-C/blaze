package com.brooth.blaze;
import java.util.*;

/** Indexed media timeline; detected timestamps and explicit corrections stay distinct. */
final class StudioTimeline {
    static final class Rhythm {String mode="auto";double bpm=120;int numerator=4,denominator=4;long offset;boolean compound;List<Change> changes=new ArrayList<>();}
    static final class Change {long time;int numerator,denominator;boolean compound;Change(long t,int n,int d,boolean c){time=t;numerator=n;denominator=d;compound=c;}}
    static final class Beat {long time;int index,total;Beat(long t,int i,int count){time=t;index=i;total=count;}}
    static final class Region {long start,end;int chord,index;Region(long a,long b,int c,int i){start=a;end=b;chord=c;index=i;}}
    static final class Measure {long start,end;int numerator,denominator,barNumber;String kind;List<Beat> beats=new ArrayList<>();List<Region> regions=new ArrayList<>();Measure(long a,long b,int n,int d,String k){start=a;end=b;numerator=n;denominator=d;kind=k;}}
    static final class State {long time;boolean ended;int chord=-1,next=-1,measure=-1,group=-1;double progress,remainingBeats=Double.NaN;long remaining=-1;Beat beat;}
    final long duration;final List<ChordEngine.Event> chords;final List<Measure> measures=new ArrayList<>();final List<Beat> beats=new ArrayList<>();final int[] next;final long[] chordStarts;long[] measureStarts,beatTimes;int barStart;
    StudioTimeline(long duration,List<ChordEngine.Event> chords,long[] detected,Rhythm rhythm){this(duration,chords,detected,new long[0],new StudioMeter.Estimate(),rhythm);}
    StudioTimeline(long duration,List<ChordEngine.Event> chords,long[] detected,long[] downbeats,StudioMeter.Estimate meter,Rhythm rhythm){
        if(duration<=0||duration>7200000)throw new IllegalArgumentException("Invalid media duration.");
        this.duration=duration;this.chords=chords;Rhythm c=rhythm==null?new Rhythm():rhythm;detected=cleanBeats(detected,duration);
        if(!Arrays.asList("auto","unknown","beats","grid").contains(c.mode)||c.offset<0||c.offset>=duration||c.numerator<1||c.numerator>12||!denominator(c.denominator)||c.changes.size()>100)throw new IllegalArgumentException("Choose a valid rhythm grid and meter.");
        if("grid".equals(c.mode)&&(!Double.isFinite(c.bpm)||c.bpm<20||c.bpm>300))throw new IllegalArgumentException("Choose a BPM between 20 and 300.");
        if("beats".equals(c.mode)&&detected.length<2)throw new IllegalArgumentException("No usable beat map. Choose a manual tempo grid.");
        next=new int[chords.size()];Arrays.fill(next,-1);chordStarts=new long[chords.size()];for(int i=0;i<chords.size();i++)chordStarts[i]=chords.get(i).startMs;
        for(int i=chords.size()-2;i>=0;i--)next[i]=chords.get(i).chord==chords.get(i+1).chord?next[i+1]:i+1;
        if("auto".equals(c.mode)) automatic(detected,meter);
        else if("unknown".equals(c.mode)) measures.add(new Measure(0,duration,0,0,"unknown"));
        else corrected(detected,c);
        measureStarts=new long[measures.size()];int cursor=0,bar=0;
        for(int m=0;m<measures.size();m++){
            Measure measure=measures.get(m);measureStarts[m]=measure.start;
            if(measure.numerator>0)measure.barNumber=++bar;
            while(cursor<chords.size()&&chords.get(cursor).endMs<=measure.start)cursor++;
            for(int i=cursor;i<chords.size()&&chords.get(i).startMs<measure.end;i++){
                ChordEngine.Event e=chords.get(i);long a=Math.max(e.startMs,measure.start),b=Math.min(e.endMs,measure.end);
                if(b>a)measure.regions.add(new Region(a,b,e.chord,i));
            }
        }
        beats.sort(Comparator.comparingLong(b->b.time));beatTimes=new long[beats.size()];for(int i=0;i<beats.size();i++)beatTimes[i]=beats.get(i).time;
    }
    private static long[] cleanBeats(long[] detected,long duration){
        if(detected==null)return new long[0];long[] clean=new long[detected.length];int count=0;long previous=-1;
        for(long time:detected){if(time<0||time>=duration)continue;if(time<previous)throw new IllegalArgumentException("Beat timestamps must increase.");if(time==previous)continue;clean[count++]=time;previous=time;}return Arrays.copyOf(clean,count);
    }
    private void automatic(long[] detected,StudioMeter.Estimate meter){
        for(long time:detected)beats.add(new Beat(time,0,0));
        long cursor=0;
        if(meter!=null&&meter.usable())for(StudioMeter.Bar bar:meter.bars){
            if(bar.start<cursor||bar.end>duration||bar.end<=bar.start)throw new IllegalArgumentException("Invalid detected bar boundaries.");
            if(bar.start>cursor){measures.add(new Measure(cursor,bar.start,0,0,cursor==0?"lead-in":"unknown"));if(cursor==0)barStart=1;}
            Measure measure=new Measure(bar.start,bar.end,bar.beatsPerBar,0,"auto");
            for(int i=0;i<bar.beats.length;i++){
                int position=Arrays.binarySearch(detected,bar.beats[i]);
                if(position<0)throw new IllegalArgumentException("A detected bar needs matching beat timestamps.");
                Beat beat=beats.get(position);beat.index=i;beat.total=bar.beatsPerBar;measure.beats.add(beat);
            }
            measures.add(measure);cursor=bar.end;
        }
        if(cursor<duration)measures.add(new Measure(cursor,duration,0,0,"unknown"));
    }
    private void corrected(long[] detected,Rhythm c){
        if(c.offset>0){measures.add(new Measure(0,c.offset,0,0,"lead-in"));barStart=1;}
        List<Change> sections=new ArrayList<>();sections.add(new Change(c.offset,c.numerator,c.denominator,c.compound));long previous=c.offset;
        for(Change change:c.changes){if(change.time<=previous||change.time>=duration||change.numerator<1||change.numerator>12||!denominator(change.denominator))throw new IllegalArgumentException("Meter changes need increasing times and valid signatures.");sections.add(change);previous=change.time;}
        for(int j=0;j<sections.size();j++){
            Change section=sections.get(j);long end=j+1<sections.size()?sections.get(j+1).time:duration;
            boolean compound=section.compound&&section.denominator==8&&section.numerator%3==0;int count=compound?section.numerator/3:section.numerator;
            List<Long> points=new ArrayList<>();points.add(section.time);
            if("grid".equals(c.mode)){
                double step=60000/c.bpm*4/section.denominator*(compound?3:1);
                for(int i=1;i<400000;i++){long time=Math.round(section.time+i*step);if(time>=end)break;if(time>points.get(points.size()-1))points.add(time);}
            }else{long last=section.time;for(long time:detected)if(time>last&&time<end){points.add(time);last=time;}}
            for(int i=0;i<points.size();i+=count){
                Measure measure=new Measure(points.get(i),i+count<points.size()?points.get(i+count):end,section.numerator,section.denominator,"grid".equals(c.mode)?"manual":"corrected");
                for(int k=i;k<Math.min(points.size(),i+count);k++){Beat beat=new Beat(points.get(k),k-i,count);measure.beats.add(beat);beats.add(beat);}measures.add(measure);
            }
        }
    }
    static boolean denominator(int d){return d==2||d==4||d==8||d==16;}
    static int upper(long[] values,long time){int a=0,b=values.length;while(a<b){int m=(a+b)>>>1;if(values[m]<=time)a=m+1;else b=m;}return a;}
    double coordinate(long time){int i=upper(beatTimes,time)-1;return i<0||i>=beatTimes.length-1?Double.NaN:i+(double)(time-beatTimes[i])/(beatTimes[i+1]-beatTimes[i]);}
    State state(long time){
        State state=new State();state.time=Math.max(0,Math.min(duration,time));state.ended=state.time>=duration;
        state.chord=state.ended?-1:upper(chordStarts,state.time)-1;if(state.chord>=0&&state.time>=chords.get(state.chord).endMs)state.chord=-1;
        state.next=state.chord<0?-1:next[state.chord];state.measure=Math.max(0,Math.min(measures.size()-1,upper(measureStarts,state.time)-1));
        Measure measure=measures.get(state.measure);state.group=Math.max(0,state.measure-barStart)/4;
        state.progress=Math.max(0,Math.min(1,(double)(state.time-measure.start)/(measure.end-measure.start)));
        int index=upper(beatTimes,state.time)-1;if(!state.ended&&index>=0&&measure.beats.contains(beats.get(index)))state.beat=beats.get(index);
        if(state.next>=0){state.remaining=Math.max(0,chords.get(state.next).startMs-state.time);double a=coordinate(state.time),b=coordinate(chords.get(state.next).startMs);if(Double.isFinite(a)&&Double.isFinite(b))state.remainingBeats=Math.max(0,b-a);}return state;
    }
}
