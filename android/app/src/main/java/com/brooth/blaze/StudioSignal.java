package com.brooth.blaze;
import java.util.*;
/** Local spectral-flux estimate. Does not claim downbeats or detected meter. */
final class StudioSignal {
    private final double[] window=new double[2048],real=new double[2048],imag=new double[2048],previous=new double[1025];
    private final List<Double> flux=new ArrayList<>();private int filled;
    double bpm=Double.NaN;long[] beats=new long[0];
    void sample(double value){window[filled++]=value;if(filled<2048)return;Arrays.fill(imag,0);for(int i=0;i<2048;i++)real[i]=window[i]*(.5-.5*Math.cos(2*Math.PI*i/2047));ChordEngine.fft(real,imag);double increase=0,total=0;for(int i=0;i<1025;i++){double magnitude=Math.hypot(real[i],imag[i]);increase+=Math.max(0,magnitude-previous[i]);total+=magnitude;previous[i]=magnitude;}flux.add(Math.max(0,increase/Math.max(1e-8,total)-.05));System.arraycopy(window,256,window,0,1792);filled=1792;}
    void finish(){double fps=22050.0/256;if(flux.size()<4*fps)return;int count=Math.min(flux.size(),(int)(180*fps));double mean=0,maximum=0;for(int i=0;i<count;i++){mean+=flux.get(i);maximum=Math.max(maximum,flux.get(i));}mean/=count;if(maximum<1e-7)return;double energy=0;for(int i=0;i<count;i++)energy+=Math.pow(flux.get(i)-mean,2);if(energy<=0)return;
        int low=(int)Math.ceil(fps*60/240),high=Math.min(count-2,(int)Math.floor(fps*60/40)),best=low;double strength=0;for(int lag=low;lag<=high;lag++){double score=0;for(int i=0;i<count-lag;i++)score+=(flux.get(i)-mean)*(flux.get(i+lag)-mean);double normalized=score/(count-lag);if(normalized>strength){strength=normalized;best=lag;}}
        double corr=0;for(int i=0;i<count-best;i++)corr+=(flux.get(i)-mean)*(flux.get(i+best)-mean);if(corr/energy<.18)return;bpm=Math.round(600*fps/best)/10.0;
        List<Double> candidates=new ArrayList<>();for(int i=1;i<flux.size()-1;i++)if(flux.get(i)>flux.get(i-1)&&flux.get(i)>=flux.get(i+1))candidates.add(flux.get(i));if(candidates.isEmpty())return;Collections.sort(candidates);double threshold=Math.max(1e-7,candidates.get((int)((candidates.size()-1)*.6))*.5);List<Long> times=new ArrayList<>();for(int i=1;i<flux.size()-1;i++)if(flux.get(i)>=threshold&&flux.get(i)>flux.get(i-1)&&flux.get(i)>=flux.get(i+1)){long time=Math.round(i/fps*1000);if(times.isEmpty()||time-times.get(times.size()-1)>=.65*best/fps*1000)times.add(time);}beats=new long[times.size()];for(int i=0;i<beats.length;i++)beats[i]=times.get(i);
    }
}
