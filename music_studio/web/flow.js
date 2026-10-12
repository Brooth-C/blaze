/* Indexed musical timing in media seconds. Playback never advances here. */
(function(root){
  'use strict';
  const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  function upper(values,time){let a=0,b=values.length;while(a<b){const m=(a+b)>>>1;if(values[m]<=time)a=m+1;else b=m;}return a;}
  function validBeats(values,duration){if(!Array.isArray(values))return [];let last=-1;return values.filter(x=>{if(typeof x!=='number'||!Number.isFinite(x)||x<0||x>=duration||x<=last)return false;last=x;return true;});}
  function validateCorrection(c){
    if(!c||!['unknown','beats','grid'].includes(c.mode))throw Error('Choose a rhythm grid mode.');
    if(!Number.isInteger(c.numerator)||c.numerator<1||c.numerator>12||![2,4,8,16].includes(c.denominator))throw Error('Choose a supported time signature.');
    if(!Number.isFinite(c.offset)||c.offset<0||c.offset>7200)throw Error('Enter a valid first downbeat time.');
    if(c.mode==='grid'&&(!Number.isFinite(c.bpm)||c.bpm<20||c.bpm>300))throw Error('Enter a tempo between 20 and 300 quarter notes per minute.');
    if(c.mode==='beats'&&c.compound&&c.denominator===8&&c.numerator%3!==0)throw Error('Compound grouping needs a multiple of three eighth notes.');
    const changes=c.changes||[];if(!Array.isArray(changes)||changes.length>100)throw Error('Too many meter changes.');
    let previous=c.offset;for(const change of changes){if(!Number.isFinite(change.time)||change.time<=previous||!Number.isInteger(change.numerator)||change.numerator<1||change.numerator>12||![2,4,8,16].includes(change.denominator))throw Error('Meter changes must have increasing times and valid signatures.');previous=change.time;}
    return c;
  }
  function build(result,correction){
    if(!result)return {duration:0,measures:[],beats:[],chords:[],next:[],measureStarts:[],chordStarts:[],beatTimes:[]};
    const duration=result.duration,chords=result.chords,c=correction?validateCorrection(correction):{mode:'unknown',numerator:4,denominator:4,offset:0};
    const detected=validBeats(result.beats,duration),measures=[],beats=[];
    function add(start,end,num,den,inside,kind){if(end>start)measures.push({start,end,index:measures.length,numerator:num,denominator:den,beats:inside,kind,regions:[]});}
    if(c.mode==='unknown'){
      // Four neutral timing windows, explicitly NOT asserted musical bars.
      for(let t=0;t<duration;t+=4)add(t,Math.min(duration,t+4),null,null,[],'unknown');
    }else{
      if(c.offset>=duration)throw Error('The first downbeat must be inside the recording.');
      if(c.mode==='beats'&&detected.length<2)throw Error('No usable detected beat map. Choose a manual tempo grid.');
      if(c.offset>0)add(0,c.offset,null,null,[],'lead-in');
      const sections=[{time:c.offset,numerator:c.numerator,denominator:c.denominator,compound:c.compound},...(c.changes||[])].filter(s=>s.time<duration);
      sections.forEach((s,n)=>{
        const end=sections[n+1]?.time??duration;
        const compound=!!s.compound&&s.denominator===8&&s.numerator%3===0;
        const count=compound?s.numerator/3:s.numerator;
        let points=[];
        if(c.mode==='grid'){
          const step=60/c.bpm*4/s.denominator*(compound?3:1);
          for(let i=0;i<100000;i++){const t=s.time+i*step;if(t>=end-1e-8)break;points.push(t);}
        }else{
          // A corrected downbeat anchors the existing irregular beat timestamps.
          points=[s.time,...detected.filter(t=>t>s.time+1e-6&&t<end)];
        }
        for(let i=0;i<points.length;i+=count){
          const inside=points.slice(i,i+count),following=points[i+count]??end;
          add(points[i],following,s.numerator,s.denominator,inside,c.mode==='grid'?'manual':'estimated');
          inside.forEach((t,k)=>beats.push({time:t,index:k,total:count,downbeat:k===0}));
        }
      });
    }
    let cursor=0;
    for(const measure of measures){while(cursor<chords.length&&chords[cursor].end<=measure.start)cursor++;for(let i=cursor;i<chords.length&&chords[i].start<measure.end;i++){const event=chords[i];const start=Math.max(event.start,measure.start),end=Math.min(event.end,measure.end);if(end>start)measure.regions.push({start,end,chord:event.chord,chordIndex:i});}}
    const next=new Array(chords.length).fill(-1);
    for(let i=chords.length-2;i>=0;i--)next[i]=chords[i+1].chord===chords[i].chord?next[i+1]:i+1;
    return {duration,chords,measures,beats,next,barStart:measures[0]?.kind==='lead-in'?1:0,measureStarts:measures.map(m=>m.start),chordStarts:chords.map(e=>e.start),beatTimes:beats.map(b=>b.time),kind:c.mode};
  }
  function beatCoordinate(map,time){const points=map.beatTimes;if(points.length<2)return null;const i=upper(points,time)-1;if(i<0||i>=points.length-1)return null;return i+(time-points[i])/(points[i+1]-points[i]);}
  function state(map,time){
    time=clamp(Number.isFinite(time)?time:0,0,map.duration);
    const ended=time>=map.duration;
    let chord=ended?-1:upper(map.chordStarts||[],time)-1;if(chord>=0&&time>=map.chords[chord].end)chord=-1;
    const measure=map.measures.length?clamp(upper(map.measureStarts,time)-1,0,map.measures.length-1):-1;
    const active=map.measures[measure],next=chord>=0?map.next[chord]:-1;
    const beatIndex=upper(map.beatTimes||[],time)-1,beat=ended?null:map.beats[beatIndex];
    const a=beatCoordinate(map,time),b=next>=0?beatCoordinate(map,map.chords[next].start):null;
    return {time,ended,chord,next,measure,group:measure<0?-1:Math.floor(Math.max(0,measure-(map.barStart||0))/4),progress:active?clamp((time-active.start)/(active.end-active.start),0,1):0,beat:beat&&active?.beats.includes(beat.time)?beat:null,seconds:next<0?null:Math.max(0,map.chords[next].start-time),remainingBeats:a===null||b===null?null:Math.max(0,b-a)};
  }
  const api={build,state,upper,validateCorrection};root.BlazeFlow=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
