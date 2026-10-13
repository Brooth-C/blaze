package com.brooth.blaze;
import java.util.*;

/** Behavior fixtures shared with the Windows conservative meter tests. */
public class StudioMeterTest {
    static void yes(boolean value){if(!value)throw new AssertionError();}
    static void eq(long a,long b){if(a!=b)throw new AssertionError(a+" != "+b);}
    static long[][] recording(int[] counts,long pulse,long offset){
        List<Long> beats=new ArrayList<>(),downbeats=new ArrayList<>();long position=offset;downbeats.add(offset);
        for(int count:counts){for(int i=0;i<count;i++){beats.add(position);position+=pulse;}downbeats.add(position);}beats.add(position);
        long[] b=new long[beats.size()],d=new long[downbeats.size()];for(int i=0;i<b.length;i++)b[i]=beats.get(i);for(int i=0;i<d.length;i++)d[i]=downbeats.get(i);return new long[][]{b,d,new long[]{position+100}};
    }
    static StudioMeter.Estimate estimate(long[][] fixture){return StudioMeter.estimate(fixture[0],fixture[1],fixture[2][0]);}
    public static void main(String[] args){
        for(int count=2;count<=12;count++){
            StudioMeter.Estimate meter=estimate(recording(new int[]{count,count,count,count},500,700));
            eq(meter.beatsPerBar,count);eq(meter.bars.size(),4);yes(meter.confidence==1);yes(meter.usable());eq(meter.bars.get(0).start,700);eq(meter.bars.get(0).beats.length,count);
        }
        yes(estimate(recording(new int[]{4,4},500,0)).bars.isEmpty());
        long[][] fixture=recording(new int[]{4,4,4},500,0);fixture[1][1]=2200;yes(estimate(fixture).bars.isEmpty());
        fixture=recording(new int[]{4,4,4,4,4,4,4},500,0);fixture[1][3]+=200;StudioMeter.Estimate partial=estimate(fixture);eq(partial.bars.size(),3);eq(partial.bars.get(0).start,8000);yes(!partial.usable());
        StudioMeter.Estimate variable=estimate(recording(new int[]{3,3,3,4,4,4},500,0));yes(variable.label.equals("Variable meter"));eq(variable.beatsPerBar,0);eq(variable.bars.size(),6);
        yes(estimate(recording(new int[]{3,4,3,4,3,4},500,0)).bars.isEmpty());
        for(long pulse:new long[]{50,4000})yes(estimate(recording(new int[]{4,4,4},pulse,0)).bars.isEmpty());
        long[] irregular={0,400,820,1260,1720,2200,2700,3220,3760,4320,4900,5500,6120};
        StudioMeter.Estimate slow=StudioMeter.estimate(irregular,new long[]{0,1720,3760,6120},6500);eq(slow.beatsPerBar,4);eq(slow.bars.get(1).end,3760);
        long[] random={0,200,1200,1400,2400,2600,3600,3800,4800,5000,6000,6200,7200};yes(StudioMeter.estimate(random,new long[]{0,2400,4800,7200},8000).bars.isEmpty());
        fixture=recording(new int[]{4,4,4},500,0);long[] reversed=fixture[0].clone();for(int i=0;i<reversed.length/2;i++){long temp=reversed[i];reversed[i]=reversed[reversed.length-i-1];reversed[reversed.length-i-1]=temp;}yes(StudioMeter.estimate(reversed,fixture[1],fixture[2][0]).bars.isEmpty());
        eq(StudioSignal.peakTimes(new float[]{0,2,2,2,0,0}).length,2);yes(Arrays.equals(StudioSignal.peakTimes(new float[]{0,2,2,2,0,0}),new long[]{30,60}));
        eq(StudioSignal.peakTimes(new float[500]).length,0);yes(!Double.isFinite(StudioSignal.tempo(new long[0])));yes(StudioSignal.tempo(new long[]{0,500,1000,1500})==120);
        List<ChordEngine.Event> chords=Arrays.asList(new ChordEngine.Event(0,1800,0,.8),new ChordEngine.Event(1800,10000,1,.8));
        fixture=recording(new int[]{3,3,3,3},500,700);StudioMeter.Estimate auto=estimate(fixture);
        StudioTimeline timeline=new StudioTimeline(10000,chords,fixture[0],fixture[1],auto,null);eq(timeline.measures.get(0).numerator,0);eq(timeline.measures.get(1).numerator,3);eq(timeline.measures.get(1).denominator,0);eq(timeline.measures.get(1).barNumber,1);eq(timeline.state(2200).beat.index,0);eq(timeline.measures.get(4).end,6700);yes(timeline.measures.get(5).kind.equals("unknown"));
        StudioTimeline.Rhythm manual=new StudioTimeline.Rhythm();manual.mode="grid";manual.numerator=4;manual.bpm=120;
        timeline=new StudioTimeline(10000,chords,fixture[0],fixture[1],auto,manual);eq(timeline.measures.get(0).numerator,4);eq(timeline.measures.get(0).end,2000);yes(timeline.measures.get(0).kind.equals("manual"));
        timeline=new StudioTimeline(10000,chords,new long[0],new long[0],new StudioMeter.Estimate(),null);eq(timeline.measures.size(),1);eq(timeline.measures.get(0).end,10000);yes(timeline.state(1000).beat==null);yes(timeline.state(10000).ended);
        System.out.println("Android meter: measured 2-12 pulse bars, pickups, variable/slow timing, gaps, weak/no rhythm, manual precedence and peak decoding PASS");
    }
}
