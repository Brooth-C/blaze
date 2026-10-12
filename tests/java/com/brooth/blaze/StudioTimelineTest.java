package com.brooth.blaze;
import java.util.*;
public class StudioTimelineTest {
    static void eq(long a,long b){if(a!=b)throw new AssertionError(a+" != "+b);}static void yes(boolean v){if(!v)throw new AssertionError();}
    public static void main(String[] args)throws Exception{
        List<ChordEngine.Event> e=new ArrayList<>();long[] boundaries={0,2000,3000,4000,6000,8000,10000,12000};String[] labels={"C:maj","G:maj","D:maj","A:min","F:maj7","C:maj","C:maj"};for(int i=0;i<labels.length;i++)e.add(new ChordEngine.Event(boundaries[i],boundaries[i+1],StudioChord.parse(labels[i]),.8));
        long[] beats=new long[24];for(int i=0;i<beats.length;i++)beats[i]=i*500;StudioTimeline.Rhythm r=new StudioTimeline.Rhythm();r.mode="grid";r.bpm=120;
        StudioTimeline map=new StudioTimeline(12000,e,beats,r);eq(map.measures.size(),6);eq(map.measures.get(1).regions.size(),2);eq(map.state(2000).chord,1);eq(map.state(3000).chord,2);eq(map.state(7999).group,0);eq(map.state(8000).group,1);yes(map.state(1000).progress==.5);yes(map.state(1000).remainingBeats==2);eq(map.state(10000).next,-1);eq(map.state(12000).chord,-1);yes(map.state(12000).ended);yes(map.state(12000).progress==1);eq(map.state(0).group,0);
        r.mode="beats";StudioTimeline variable=new StudioTimeline(12000,e,new long[]{0,500,1100,1600,2300,3100,3900,4800,5800,6900,8100,9400,10800},r);eq(variable.measures.get(0).end,2300);eq(variable.measures.get(1).end,5800);eq(variable.state(2300).measure,1);
        r.mode="grid";r.numerator=3;map=new StudioTimeline(12000,e,beats,r);eq(map.measures.get(0).end,1500);eq(map.state(1000).beat.total,3);
        r.numerator=6;r.denominator=8;r.compound=true;map=new StudioTimeline(12000,e,beats,r);eq(map.measures.get(0).end,1500);eq(map.measures.get(0).beats.size(),2);
        r.numerator=4;r.denominator=4;r.compound=false;r.changes.add(new StudioTimeline.Change(4000,3,4,false));map=new StudioTimeline(12000,e,beats,r);eq(map.measures.get(2).numerator,3);eq(map.measures.get(2).end,5500);
        r.changes.clear();r.offset=1000;map=new StudioTimeline(12000,e,beats,r);eq(map.barStart,1);eq(map.state(9000).group,1);
        map=new StudioTimeline(12000,e,beats,null);eq(map.measures.get(0).numerator,0);yes(map.state(1000).beat==null);
        for(String quality:StudioChord.QUALITY){int chord=StudioChord.parse("C:"+quality);yes(chord>=24);yes(StudioChord.canonical(chord,0).equals("C:"+quality));yes(StudioChord.canonical(StudioChord.transpose(chord,2),0).equals("D:"+quality));}
        int maj7=StudioChord.parse("F:maj7");yes(StudioChord.contains(maj7,4));yes(!StudioChord.contains(maj7,3));int diminished=StudioChord.parse("C:dim");yes(StudioChord.contains(diminished,6));yes(!StudioChord.contains(diminished,7));yes(StudioChord.voicing(StudioChord.parse("C:13"))==null);
        StudioSignal silent=new StudioSignal();for(int i=0;i<22050*5;i++)silent.sample(0);silent.finish();yes(!Double.isFinite(silent.bpm));eq(silent.beats.length,0);
        StudioSignal click=new StudioSignal();for(int i=0;i<22050*8;i++){int j=i%11025;click.sample(j<300?.6*Math.sin(2*Math.PI*800*j/22050.0):0);}click.finish();yes(Double.isFinite(click.bpm));yes(Math.abs(click.bpm-120)<3);yes(click.beats.length>=8);
        System.out.println("Native Live Flow and complete chord vocabulary: timing, split regions, grouping, variable beats, meters, transposition, advanced notes and signal estimate PASS");
    }
}
