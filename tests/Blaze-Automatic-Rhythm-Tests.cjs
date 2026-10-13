const assert=require('node:assert/strict'),Flow=require('../music_studio/web/flow.js');
const data={duration:12,beats:Array.from({length:24},(_,i)=>i*.5),chords:[{start:0,end:12,chord:'C:maj'}],meter:{confidence:1,bars:[
 {start:1,end:3,beats:[1,1.5,2,2.5],beats_per_bar:4},
 {start:3,end:5,beats:[3,3.5,4,4.5],beats_per_bar:4},
 {start:6,end:7.5,beats:[6,6.5,7],beats_per_bar:3}
]}};
const auto=Flow.build(data);
assert.equal(auto.kind,'auto');
assert.equal(Flow.state(auto,.5).beat,null);
assert.equal(Flow.state(auto,2).beat.index,2);
assert.equal(Flow.state(auto,5.5).beat,null);
assert.equal(Flow.state(auto,6.5).beat.total,3);
assert.equal(auto.measures.find(m=>m.start===6).barNumber,3);
assert.deepEqual(Flow.markers(auto,data.beats).bars.map(b=>b.time),[1,3,6]);
assert.equal(Flow.cells(auto,data.beats).rows.length,24);
const disabled=Flow.build(data,{mode:'unknown',numerator:4,denominator:4,offset:0});
assert.equal(disabled.kind,'unknown');assert.deepEqual(Flow.markers(disabled,data.beats).bars,[]);
const manual=Flow.build(data,{mode:'grid',numerator:3,denominator:4,offset:0,bpm:120});
assert.equal(manual.kind,'grid');assert.equal(manual.measures[0].end,1.5);
assert.equal(Flow.build({...data,meter:undefined}).kind,'unknown');
console.log('Automatic rhythm: measured downbeats, unresolved gaps, variable pulse counts, manual override and backward compatibility PASS');

assert.equal(Flow.build({...data,meter:{...data.meter,confidence:.21}}).kind,"unknown");

const countdown=Flow.build({...data,chords:[{start:0,end:7.5,chord:"C:maj"},{start:7.5,end:12,chord:"G:maj"}]});
assert.equal(Flow.state(countdown,5.5).remainingBeats,4);
assert.equal(Flow.build({...data,meter:{...data.meter,confidence:"1"}}).kind,"unknown");
