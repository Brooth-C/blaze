'use strict';
const assert=require('node:assert/strict');
const Guide=require('../music_studio/web/practice-guide.js');

let checks=0;
function test(name,run){try{run();checks++;}catch(error){error.message=name+': '+error.message;throw error;}}
function event(start,end,chord,extra={}){return {start,end,chord,model_score:.9,edited:false,...extra};}
function spans(rows){return rows.map(({start,end,chord})=>({start,end,chord}));}
function near(actual,expected,message){assert.equal(typeof actual,'number',message);assert(Math.abs(actual-expected)<1e-8,message+': '+actual+' vs '+expected);}
const beats=[0,.5,1,1.5,2,2.5,3,3.5,4];
const options={mode:'piano',beats};

test('Detected guide retains every recognised change and metadata',()=>{
 const source=[event(0,2,'C:maj'),event(2,2.18,'D:min'),event(2.18,4,'C:maj')];
 const before=structuredClone(source),actual=Guide.build(source,{mode:'detected',beats});
 assert.deepEqual(actual,before);assert.notEqual(actual,source);
 actual.forEach((row,i)=>assert.notEqual(row,source[i]));
 actual[0].chord='F:maj';assert.deepEqual(source,before);
});

test('Piano phrasing can hold one chord across a brief unsupported return',()=>{
 const source=[event(0,2,'C:maj'),event(2,2.18,'D:min'),event(2.18,4,'C:maj')];
 const before=structuredClone(source),actual=Guide.build(source,options);
 assert.deepEqual(spans(actual),[{start:0,end:4,chord:'C:maj'}]);
 assert.deepEqual(source,before,'Display simplification mutated final recognition');
});

test('Phrasing threshold follows local tempo and retains longer genuine changes',()=>{
 const source=[event(0,2,'C:maj'),event(2,2.18,'D:min'),event(2.18,4,'C:maj')];
 const fastBeats=Array.from({length:21},(_,i)=>i*.2);
 assert.deepEqual(spans(Guide.build(source,{mode:'piano',beats:fastBeats})),spans(source));
 const sustained=[event(0,2,'C:maj'),event(2,2.6,'D:min'),event(2.6,4,'C:maj')];
 assert.deepEqual(spans(Guide.build(sustained,options)),spans(sustained));
 const shortNeighbours=[event(0,.05,'C:maj'),event(.05,.15,'D:min'),event(.15,.2,'C:maj')];
 assert.deepEqual(spans(Guide.build(shortNeighbours,options)),spans(shortNeighbours));
});

test('Genuine distinct changes and offbeat starts remain at their detected timestamps',()=>{
 const source=[event(0,1.13,'C:maj'),event(1.13,3.07,'G:maj'),event(3.07,4,'D:min')];
 assert.deepEqual(spans(Guide.build(source,options)),spans(source));
 const changing=[event(0,2,'C:maj'),event(2,2.1,'D:min'),event(2.1,4,'G:maj')];
 assert.deepEqual(spans(Guide.build(changing,options)),spans(changing));
});

test('Manual corrections are protected on every side of a return',()=>{
 for(let index=0;index<3;index++){
  const source=[event(0,2,'C:maj'),event(2,2.1,'D:min'),event(2.1,4,'C:maj')];
  source[index].edited=true;
  assert.deepEqual(Guide.build(source,options),source);
 }
});

test('Silence and uncertain recognition remain explicit',()=>{
 for(const chord of ['N','X']){
  const source=[event(0,2,'C:maj'),event(2,2.1,chord),event(2.1,4,'C:maj')];
  assert.deepEqual(Guide.build(source,options),source);
 }
 const silence=[event(0,2,'N'),event(2,2.1,'C:maj'),event(2.1,4,'N')];
 assert.deepEqual(Guide.build(silence,options),silence);
});

test('Phrasing never bridges a gap in the recognised timeline',()=>{
 const sources=[
  [event(0,2,'C:maj'),event(2.05,2.15,'D:min'),event(2.15,4,'C:maj')],
  [event(0,2,'C:maj'),event(2,2.1,'D:min'),event(2.15,4,'C:maj')]
 ];
 for(const source of sources)assert.deepEqual(Guide.build(source,options),source);
});

test('Cue changes exactly at the real chord boundary and supports backwards seeks',()=>{
 const source=[event(0,2,'C:maj'),event(2,4,'G:maj'),event(4,6,'D:min')];
 assert.equal(Guide.cue(source,1.999,{beats}).current.chord,'C:maj');
 assert.equal(Guide.cue(source,2,{beats}).current.chord,'G:maj');
 assert.equal(Guide.cue(source,4,{beats}).current.chord,'D:min');
 assert.equal(Guide.cue(source,.25,{beats}).current.chord,'C:maj');
 assert.equal(Guide.cue(source,6,{beats}).current,null);
});

test('Before music starts a cue targets the actual first event',()=>{
 const source=[event(2,4,'C:maj'),event(4,6,'G:maj')];
 const cue=Guide.cue(source,1,{beats});
 assert.equal(cue.current,null);assert.equal(cue.next.chord,'C:maj');
 near(cue.nextAt,2,'First chord start');near(cue.remainingSeconds,1,'Intro countdown');
});

test('Cue uses actual variable beat positions rather than a global BPM',()=>{
 const source=[event(0,2,'C:maj'),event(2,4,'G:maj')];
 const variable=[0,.5,1.25,2,3,4];
 const cue=Guide.cue(source,.875,{beats:variable});
 near(cue.nextAt,2,'Detected next chord boundary');
 near(cue.remainingBeats,1.5,'Variable beat countdown');
 const later=Guide.cue(source,1.625,{beats:variable});
 near(later.remainingBeats,.5,'Half of a changing beat');
 assert(later.prepareProgress>=cue.prepareProgress,'Preparation cue moved backwards');
});

test('Playback rate changes seconds until a chord without altering its musical beat count',()=>{
 const source=[event(0,2,'C:maj'),event(2,4,'G:maj')];
 const slow=Guide.cue(source,1,{beats,rate:.5}),fast=Guide.cue(source,1,{beats,rate:2});
 near(slow.remainingSeconds,2,'Half-speed real seconds');near(fast.remainingSeconds,.5,'Double-speed real seconds');
 near(slow.remainingBeats,2,'Half-speed musical beats');near(fast.remainingBeats,2,'Double-speed musical beats');
});

test('Missing beat analysis uses seconds and keeps the original next chord time',()=>{
 const source=[event(0,2.13,'C:maj'),event(2.13,4,'G:maj')];
 const cue=Guide.cue(source,1.13,{beats:[],rate:1});
 near(cue.nextAt,2.13,'Unsnapped boundary');near(cue.remainingSeconds,1,'Seconds fallback');
 assert.equal(cue.remainingBeats,null);
});

test('Active loop cues the chord at loop start when the next change is beyond the seam',()=>{
 const source=[event(0,2,'C:maj'),event(2,4,'G:maj'),event(4,6,'D:min')];
 const cue=Guide.cue(source,3.5,{beats,loopEnabled:true,loopStart:1,loopEnd:3.75,rate:.5});
 assert.equal(cue.current.chord,'G:maj');assert.equal(cue.next.chord,'C:maj');
 assert.equal(cue.looping,true);near(cue.nextAt,3.75,'Loop seam');
 near(cue.remainingSeconds,.5,'Rate-adjusted loop seam countdown');
 const beforeChange=Guide.cue(source,1.5,{beats,loopEnabled:true,loopStart:1,loopEnd:3.75});
 assert.equal(beforeChange.next.chord,'G:maj');near(beforeChange.nextAt,2,'Earlier real transition wins');
});

test('Disabled loops do not affect the next actual change',()=>{
 const source=[event(0,2,'C:maj'),event(2,4,'G:maj'),event(4,6,'D:min')];
 const cue=Guide.cue(source,3.5,{beats,loopEnabled:false,loopStart:1,loopEnd:3.75});
 assert.equal(cue.next.chord,'D:min');near(cue.nextAt,4,'Disabled seam ignored');
 assert.equal(cue.looping,false);
});

test('Empty and finished guides have no preparation cue',()=>{
 for(const cue of [Guide.cue([],0,{beats}),Guide.cue([event(0,2,'C:maj')],2,{beats})]){
  assert.equal(cue.current,null);assert.equal(cue.next,null);assert.equal(cue.preparing,false);
  assert.equal(cue.prepareProgress,0);
 }
 assert.deepEqual(Guide.build([],{mode:'piano',beats}),[]);
});

test('Frozen final recognition can be used for either display without writes',()=>{
 const source=Object.freeze([Object.freeze(event(0,2,'C:maj')),Object.freeze(event(2,2.1,'D:min')),Object.freeze(event(2.1,4,'C:maj'))]);
 const frozenBeats=Object.freeze(beats.slice());
 assert.equal(Guide.build(source,{mode:'piano',beats:frozenBeats}).length,1);
 assert.deepEqual(Guide.build(source,{mode:'detected',beats:frozenBeats}),source);
 assert.equal(Guide.cue(source,1,{beats:frozenBeats}).current.chord,'C:maj');
});

test('Unknown and silent events remain the current state without hiding the next real chord',()=>{
 for(const chord of ['N','X']){
  const source=[event(0,1,'C:maj'),event(1,3,chord),event(3,4,'G:maj')];
  const cue=Guide.cue(source,2,{beats});
  assert.equal(cue.current.chord,chord);assert.equal(cue.next.chord,'G:maj');
  near(cue.nextAt,3,'Known chord beyond silent or uncertain region');
 }
});

test('Loop-start gaps are counted through the seam without moving the next chord',()=>{
 const source=[event(0,1,'C:maj'),event(1,2,'N'),event(2,4,'G:maj')];
 const cue=Guide.cue(source,3.25,{beats,loopEnabled:true,loopStart:1.5,loopEnd:3.5});
 assert.equal(cue.current.chord,'G:maj');assert.equal(cue.next.chord,'G:maj');
 assert.equal(cue.looping,true);near(cue.nextAt,4,'Unwrapped return time including loop-start silence');
 near(cue.remainingSeconds,.75,'Seam plus silent lead-in');near(cue.remainingBeats,1.5,'Beats on both sides of seam');
});

test('Loop cues use variable beats and exact seeks never retain a stale loop countdown',()=>{
 const source=[event(0,2,'C:maj'),event(2,4,'G:maj'),event(4,6,'D:min')];
 const variable=[0,.5,1.25,2,3,4,5,6];
 const options={beats:variable,loopEnabled:true,loopStart:1.25,loopEnd:3.5,rate:.5};
 const nearSeam=Guide.cue(source,3.25,options);
 near(nearSeam.remainingBeats,.25,'Variable beat at loop seam');near(nearSeam.remainingSeconds,.5,'Slow playback at seam');
 const atStart=Guide.cue(source,1.25,options);
 assert.equal(atStart.current.chord,'C:maj');assert.equal(atStart.next.chord,'G:maj');near(atStart.nextAt,2,'Seek to loop start');
 const atEnd=Guide.cue(source,3.5,options);
 assert.equal(atEnd.looping,false);near(atEnd.nextAt,4,'Exact end is no longer inside loop');
 const outside=Guide.cue(source,4.5,options);
 assert.equal(outside.current.chord,'D:min');assert.equal(outside.next,null);assert.equal(outside.looping,false);
});

test('Outside measured beat coverage the cue uses seconds instead of inventing beats',()=>{
 const source=[event(1,2,'C:maj'),event(2,4,'G:maj'),event(4,6,'D:min')];
 const intro=Guide.cue(source,.5,{beats:[1,1.5,2,2.5,3,3.5,4]});
 assert.equal(intro.remainingBeats,null);near(intro.remainingSeconds,.5,'Unmeasured intro seconds');
 const outro=Guide.cue(source,3.5,{beats:[1,1.5,2,2.5,3]});
 assert.equal(outro.remainingBeats,null);near(outro.remainingSeconds,.5,'Unmeasured outro seconds');
 const seam=Guide.cue(source,3.25,{beats:[2,2.5,3,3.5],loopEnabled:true,loopStart:1.25,loopEnd:3.5});
 assert.equal(seam.remainingBeats,null);near(seam.remainingSeconds,.25,'Loop start outside measured beats');
});

console.log('Practice guide: '+checks+' checks PASS (immutable recognition, conservative piano phrasing, exact timing, variable beats, rate and loop cues).');
