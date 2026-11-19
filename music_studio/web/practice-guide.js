/* Display-only phrasing and preparation cues. Recognition and audio stay intact. */
(() => {
 'use strict';
 const empty=[],grids=new WeakMap(),timelines=new WeakMap();
 const known=event=>event&&event.chord!=='N'&&event.chord!=='X';
 const after=(values,time,key=value=>value)=>{let left=0,right=values.length;while(left<right){const middle=(left+right)>>>1;if(key(values[middle])<=time)left=middle+1;else right=middle;}return left;};
 function gridFor(beats){
  if(!Array.isArray(beats))return empty;
  if(grids.has(beats))return grids.get(beats);
  const grid=[];for(const beat of beats)if(Number.isFinite(beat)&&(!grid.length||beat>grid[grid.length-1]))grid.push(beat);
  grids.set(beats,grid);return grid;
 }
 function periodAt(grid,time){
  if(grid.length<2||time<grid[0]||time>=grid[grid.length-1])return null;
  const index=Math.max(0,Math.min(grid.length-2,after(grid,time)-1));
  return grid[index+1]-grid[index];
 }
 function beatPosition(grid,time){
  const index=Math.max(0,Math.min(grid.length-2,after(grid,time)-1));
  return index+(time-grid[index])/(grid[index+1]-grid[index]);
 }
 function knownFor(events){
  if(!timelines.has(events))timelines.set(events,events.filter(known));
  return timelines.get(events);
 }
 function build(chords,{mode='piano',beats}={}){
  const copied=(chords||[]).map(event=>({...event}));
  if(mode==='detected')return copied;
  const grid=gridFor(beats),phrased=[];
  for(const event of copied){
   phrased.push(event);
   // A very brief return to the same harmony is optional accompaniment detail.
   // Only smooth this bounded pattern; retain real changes, silence, edits,
   // gaps and syncopated boundaries. Never quantize the whole song to a grid.
   while(phrased.length>=3){
    const [left,passing,right]=phrased.slice(-3),period=periodAt(grid,passing.start)??.5;
    const limit=Math.min(.24,period*.45),support=Math.min(.25,period*.5);
    if(!known(left)||!known(passing)||!known(right)||left.chord!==right.chord||
       left.chord===passing.chord||left.edited||passing.edited||right.edited||
       passing.end-passing.start>limit||passing.end<=passing.start||
       left.end-left.start<support||right.end-right.start<support||
       Math.abs(left.end-passing.start)>1e-4||Math.abs(passing.end-right.start)>1e-4)break;
    phrased.splice(-3,3,{...left,end:right.end,practice_phrased:true});
   }
  }
  return phrased;
 }
 function cue(events,position,{beats,rate=1,loopStart,loopEnd,loopEnabled=false}={}){
  position=Number.isFinite(position)?position:0;
  rate=Number.isFinite(rate)&&rate>0?rate:1;
  const index=after(events,position,event=>event.start)-1;
  const current=index>=0&&events[index].end>position?events[index]:null;
  const looping=loopEnabled&&Number.isFinite(loopStart)&&Number.isFinite(loopEnd)&&loopEnd>loopStart&&position>=loopStart&&position<loopEnd;
  const available=knownFor(events);
  let next=available[after(available,position,event=>event.start)]||null,nextAt=null,wraps=false;
  if(next&&looping&&next.start>=loopEnd)next=null;
  if(next)nextAt=next.start;
  if(!next&&looping){
   const startIndex=after(available,loopStart,event=>event.start)-1;
   const atStart=startIndex>=0&&available[startIndex].end>loopStart?available[startIndex]:available[startIndex+1];
   if(atStart&&atStart.start<loopEnd){next=atStart;nextAt=loopEnd+Math.max(0,next.start-loopStart);wraps=true;}
  }
  const grid=gridFor(beats);
  let remainingSeconds=null,remainingBeats=null;
  if(next){
   remainingSeconds=Math.max(0,(nextAt-position)/rate);
   const covers=(start,end)=>grid.length>=2&&start>=grid[0]&&end<=grid[grid.length-1];
   if(wraps?covers(position,loopEnd)&&covers(loopStart,Math.max(loopStart,next.start)):covers(position,nextAt)){
    remainingBeats=wraps?beatPosition(grid,loopEnd)-beatPosition(grid,position)+
      beatPosition(grid,Math.max(loopStart,next.start))-beatPosition(grid,loopStart):
      beatPosition(grid,nextAt)-beatPosition(grid,position);
    remainingBeats=Math.max(0,remainingBeats);
   }
  }
  const distance=remainingBeats??remainingSeconds,preparing=next!==null&&distance<=2;
  return {current,next,nextAt,remainingSeconds,remainingBeats,
   prepareProgress:next?Math.max(0,Math.min(1,1-distance/2)):0,preparing,looping:wraps};
 }
 const api={build,cue};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else globalThis.BlazePracticeGuide=api;
})();
