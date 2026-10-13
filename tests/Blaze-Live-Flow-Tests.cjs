const assert=require('node:assert/strict');
const Flow=require('../music_studio/web/flow.js');
const chords=[{start:0,end:2,chord:'C:maj'},{start:2,end:3,chord:'G:maj'},{start:3,end:4,chord:'D:maj'},{start:4,end:6,chord:'A:min'},{start:6,end:8,chord:'F:maj7'},{start:8,end:10,chord:'C:maj'},{start:10,end:12,chord:'C:maj'}];
const result={duration:12,chords,beats:Array.from({length:24},(_,i)=>i*.5)};
const correction={mode:'grid',bpm:120,numerator:4,denominator:4,offset:0};
const map=Flow.build(result,correction);
assert.equal(map.measures.length,6);assert.equal(map.measures[1].regions.length,2);assert.equal(map.measures[1].regions[0].end-map.measures[1].regions[0].start,1);
assert.equal(Flow.state(map,0).chord,0);assert.equal(Flow.state(map,2).chord,1);assert.equal(Flow.state(map,3).chord,2);assert.equal(Flow.state(map,8).group,1);assert.equal(Flow.state(map,7.999).group,0);
assert.equal(Flow.state(map,1).progress,.5);assert.equal(Flow.state(map,2.5).beat.index,1);assert.equal(Flow.state(map,1).remainingBeats,2);
assert.equal(Flow.state(map,10).next,-1);assert.equal(Flow.state(map,12).chord,-1);assert.equal(Flow.state(map,12).progress,1);assert.equal(Flow.state(map,12).ended,true);
// Paused/speed/loop state always comes from the supplied media clock, never elapsed wall time.
assert.deepEqual(Flow.state(map,3.2),Flow.state(map,3.2));assert.equal(Flow.state(map,0).group,0);
const variable={...result,beats:[0,.5,1.1,1.6,2.3,3.1,3.9,4.8,5.8,6.9,8.1,9.4,10.8]};
const v=Flow.build(variable,{...correction,mode:'beats'});assert.equal(v.measures[0].end,2.3);assert.equal(v.measures[1].end,5.8);assert.equal(Flow.state(v,2.3).measure,1);
const three=Flow.build(result,{...correction,numerator:3});assert.equal(three.measures[0].end,1.5);assert.equal(Flow.state(three,1).beat.total,3);
const compound=Flow.build(result,{...correction,numerator:6,denominator:8,compound:true});assert.equal(compound.measures[0].end,1.5);assert.equal(compound.measures[0].beats.length,2);
const changed=Flow.build(result,{...correction,changes:[{time:4,numerator:3,denominator:4}]});assert.equal(changed.measures[2].numerator,3);assert.equal(changed.measures[2].end,5.5);
const lead=Flow.build(result,{...correction,offset:1});assert.equal(lead.barStart,1);assert.equal(Flow.state(lead,9).group,1);
const unknown=Flow.build(result);assert.equal(unknown.measures[0].numerator,null);assert.equal(Flow.state(unknown,1).beat,null);
assert.doesNotThrow(()=>Flow.state(Flow.build(null),0));assert.throws(()=>Flow.build(result,{...correction,bpm:0}));assert.throws(()=>Flow.build({...result,beats:[]},{...correction,mode:'beats'}));
const short=Flow.build({...result,duration:1,chords:[{start:0,end:1,chord:'X'}]},correction);assert.equal(short.measures.length,1);assert.equal(short.measures[0].end,1);
console.log('Live flow: boundaries, split bars, countdown, grouping, variable beats, compound/change meters, lead-in, final timestamp and unknown timing PASS');

// Unknown meter cannot manufacture four-second or four-beat bars.
const unknownMarkers=Flow.markers(unknown,[.13,.64,1.23,1.76]);
assert.deepEqual(unknownMarkers.bars,[]);
assert.deepEqual(unknownMarkers.ticks.map(t=>t.time),[.13,.64,1.23,1.76]);
assert.ok(unknownMarkers.ticks.every(t=>!t.downbeat));
const confirmedMarkers=Flow.markers(map,result.beats);
assert.deepEqual(confirmedMarkers.bars.map(t=>t.time),[0,2,4,6,8,10]);
assert.deepEqual(Flow.markers(v,variable.beats).bars.slice(0,3).map(t=>t.time),[0,2.3,5.8]);
console.log('Markers: no invented bars, exact measured beats, confirmed and variable-tempo bars PASS');
