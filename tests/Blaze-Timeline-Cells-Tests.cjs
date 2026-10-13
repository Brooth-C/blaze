const assert=require('node:assert/strict');
const Flow=require('../music_studio/web/flow.js');
const result={duration:4,beats:[0,.5,1.1,1.6,2.3,3.1],chords:[
 {start:0,end:.2,chord:'X'}, {start:.2,end:.4,chord:'C:maj'},
 {start:.4,end:1.6,chord:'G:7'}, {start:1.6,end:2,chord:'X'},
 {start:2,end:2.8,chord:'A:min7'}, {start:2.8,end:4,chord:'N'}
]};
const before=JSON.stringify(result),layout=Flow.cells(Flow.build(result),result.beats);
const labels=layout.rows.flatMap(cell=>cell.labels);
assert.deepEqual(labels.map(e=>[e.chord,e.time]),[['C:maj',.2],['G:7',.4],['A:min7',2]]);
assert.ok(labels.every(e=>!['X','N'].includes(e.chord)));
assert.equal(layout.rows[2].labels.length,0); // held G7 is a blank continuation
assert.equal(JSON.stringify(result),before); // display does not rewrite analysis
for(const t of [0,.13,.2,.4,.5,1.05,1.6,2,3.7,4]){
 assert.ok(Math.abs(Flow.cellTime(layout,Flow.cellPosition(layout,t))-t)<1e-8);
}
const sparse={duration:40,beats:[0,.5],chords:[
 {start:0,end:10,chord:'C:maj'}, {start:10,end:20,chord:'A:min'},
 {start:20,end:30,chord:'F:maj'}, {start:30,end:40,chord:'G:maj'}
]};
const filled=Flow.cells(Flow.build(sparse),sparse.beats);
assert.deepEqual(filled.rows.flatMap(c=>c.labels.map(l=>l.chord)),['C:maj','A:min','F:maj','G:maj']);
assert.ok(filled.rows.every(c=>c.end-c.start<=2.5));
const fallback=Flow.cells(Flow.build({...sparse,beats:[]}),[]);
assert.equal(fallback.timed,true);assert.equal(fallback.rows.length,40);
assert.equal(Flow.cellTime(fallback,40),40);
assert.equal(Flow.cells(Flow.build(null),[]).rows.length,0);
console.log('Timeline cells: exact known onsets, blank uncertainty/continuations, sparse beats, variable-time seek and unchanged analysis PASS');
