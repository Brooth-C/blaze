/* Approved Studio layout over the existing local session/player. This adapter
 * owns no audio element, jobs, tokens, file paths or inference requests. */
(() => {
 'use strict';
 const engine=window.BlazeMacStudio,template=document.getElementById('logic-live-template');
 if(!engine||!template)return;
 const panel=document.getElementById('studio-panel'),legacy=document.getElementById('mac-studio-workspace');
 const root=template.content.firstElementChild.cloneNode(true);
 root.classList.add('logic-live');root.setAttribute('aria-label','Music Studio');
 panel.prepend(root);legacy.hidden=true;legacy.inert=true;
 window.BlazeLogicHost=engine;
 window.BlazeLogicLiveMount=({svg,button})=>{
  const $=id=>root.querySelector('#'+id),cmd=engine.commands;
  let state=engine.viewState(),disposed=false,frame=0,timer=0,zoom=1,rangeTool=false,actionError='';
  let lastPeaks=null,lastTracks='',lastChords=null,lastChordDuration=-1,lastRuler='',lastEditorWidth=0;
  const rows=new Map(),pendingActions=new Set();
  const text=(node,value)=>{if(node.textContent!==String(value))node.textContent=String(value);};
  const bind=(node,action)=>{node.onclick=async()=>{if(pendingActions.has(node))return;pendingActions.add(node);actionError='';
   try{await action();}catch(error){actionError=error.message||'This action could not be completed.';}
   finally{pendingActions.delete(node);update();}};};
  const status=$('visual-time');status.id='live-status';status.setAttribute('role','status');
  root.querySelector('.arrangement').setAttribute('aria-label','Track arrangement');
  root.querySelector('.audio-editor').setAttribute('aria-label','Selected track waveform editor');
  root.querySelector('.output-meter').setAttribute('aria-label','Output level');
  root.querySelector('footer').lastElementChild.id='live-selection-readout';
  const meters=[...root.querySelectorAll('.output-meter i')];
  const master=document.createElement('input');master.type='range';master.min='0';master.max='1';master.step='.01';
  master.setAttribute('aria-label','Master volume');master.className='live-master';
  master.oninput=()=>{cmd.volume(master.value);update();};root.querySelector('.output-section').append(master);
  const toolbar=$('track-headers');toolbar.setAttribute('role','listbox');toolbar.setAttribute('aria-label','Session tracks');
  const transport=[...$('transport').children];
  transport[1].id='logic-play';transport[0].id='logic-stop';
  root.querySelector('.arrangement').id='logic-arrangement';root.querySelector('.audio-editor').id='logic-editor';
  bind(transport[0],cmd.stop);bind(transport[1],cmd.play);bind(transport[5],cmd.loop);
  for(const i of [2,3,4])unsupported(transport[i]);
  const navigation=$('navigation-tools');bind(navigation.children[0],()=>showPanel('library'));bind(navigation.children[1],()=>showPanel('inspector'));
  for(const node of [...navigation.children].slice(2))unsupported(node);
  for(const node of $('workspace-tools').children)unsupported(node);
  bind($('workspace-tools').lastChild,toggleEditor);$('workspace-tools').lastChild.disabled=false;
  for(const node of $('browser-tools').children)unsupported(node);
  const browse=button('browser','Back to Explore');bind(browse,cmd.browse);$('browser-tools').lastChild.replaceWith(browse);
  const timing=[...$('timing-tools').children];for(const node of timing)unsupported(node);
  timing.at(-1).disabled=false;timing.at(-1).title='Metronome';timing.at(-1).setAttribute('aria-label','Metronome');bind(timing.at(-1),cmd.metronome);
  for(const node of $('view-tools').children)unsupported(node);$('view-tools').children[1].disabled=false;
  for(const node of $('editor-tools').children)unsupported(node);
  for(const node of $('display-tools').children)unsupported(node);
  $('pointer-tools').children[0].onclick=()=>setTool(false);$('pointer-tools').children[1].onclick=()=>setTool(true);
  $('pointer-tools').children[1].title='Select a time range';$('pointer-tools').children[1].setAttribute('aria-label','Time range tool');
  for(const node of $('editor-heading-tools').children)unsupported(node);
  const snap=root.querySelector('[aria-label="Visual snap setting"]');snap.setAttribute('aria-label','Selection snap');
  const drag=root.querySelector('[aria-label="Visual drag setting"]');drag.disabled=true;drag.title='Region editing is not available';
  const importButton=$('add-track');importButton.setAttribute('aria-label','Import recording');importButton.title='Import recording';bind(importButton,cmd.import);
  const stems=$('duplicate-track');stems.textContent='Split';stems.setAttribute('aria-label','Split stems');stems.title='Split stems';bind(stems,cmd.stems);
  const analyze=document.createElement('button');analyze.id='logic-chords';analyze.textContent='Chords';analyze.setAttribute('aria-label','Analyse chords');
  bind(analyze,()=>state.analysisBusy?cmd.cancelAnalysis():cmd.analyze());stems.after(analyze);
  const save=document.createElement('a');save.className='live-save';save.textContent='Save WAV';save.hidden=true;analyze.after(save);
  bind($('show-editor'),toggleEditor);
  bind(root.querySelector('.lcd'),cmd.project);root.querySelector('.lcd').tabIndex=0;root.querySelector('.lcd').setAttribute('role','button');
  root.querySelector('.lcd').setAttribute('aria-label','Project tempo, time signature and key');
  root.querySelector('.lcd').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();cmd.project();}};
  const time=document.createElement('span');time.id='live-position';root.querySelector('footer').insertBefore(time,status);
  const empty=document.createElement('div');empty.id='live-empty';empty.innerHTML='<p>Open a recording to begin.</p>';
  const open=document.createElement('button');open.textContent='Import recording';bind(open,cmd.import);empty.append(open);$('regions').append(empty);
  // The amplitude scale stays fixed while the waveform and its ruler zoom.
  const scroll=document.createElement('div');scroll.className='live-editor-scroll';
  const editorArea=root.querySelector('.editor-wave-area');editorArea.before(scroll);scroll.append(editorArea);
  const canvas=$('editor-wave');canvas.setAttribute('role','slider');canvas.tabIndex=0;
  canvas.setAttribute('aria-label','Selected track waveform. Click to seek; shift-drag to select a range.');
  canvas.setAttribute('aria-valuemin','0');canvas.setAttribute('aria-valuemax','100');
  const editorEmpty=document.createElement('span');editorEmpty.className='live-editor-empty';root.querySelector('.wave-surface').append(editorEmpty);
  let pointerStart=null;
  const at=e=>Math.max(0,Math.min(state.duration,(e.clientX-canvas.getBoundingClientRect().left)/canvas.getBoundingClientRect().width*state.duration));
  canvas.onpointerdown=e=>{if(e.button!==0||!state.enabled||!state.duration)return;canvas.setPointerCapture(e.pointerId);
   pointerStart=e.shiftKey||rangeTool?at(e):null;if(pointerStart===null)cmd.seek(at(e));else cmd.range(pointerStart,pointerStart);update();};
  canvas.onpointermove=e=>{if(!canvas.hasPointerCapture(e.pointerId))return;let value=at(e);
   if(pointerStart===null)cmd.seek(value);else{const spacing=snap.value==='Bar'?60/state.tempo*4/state.denominator*state.numerator:snap.value==='Beat'?60/state.tempo*4/state.denominator:0;
    if(spacing)value=Math.round(value/spacing)*spacing;cmd.range(pointerStart,value);}update();};
  canvas.onpointerup=canvas.onpointercancel=e=>{if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);pointerStart=null;};
  canvas.onkeydown=e=>{const steps={ArrowLeft:state.position-5,ArrowRight:state.position+5,Home:0,End:state.duration};
   if(Object.hasOwn(steps,e.key)){e.preventDefault();cmd.seek(steps[e.key]);update();}};
  $('project-ruler').onclick=e=>{if(!state.enabled)return;const r=e.currentTarget.getBoundingClientRect();cmd.seek((e.clientX-r.left)/r.width*state.duration);update();};
  const height=root.querySelector('[aria-label="Track visual height"]');height.setAttribute('aria-label','Track height');
  height.oninput=()=>{root.style.setProperty('--row-height',height.value+'px');redraw();};
  const arrangementZoom=root.querySelector('[aria-label="Timeline visual zoom"]');arrangementZoom.disabled=true;arrangementZoom.title='Arrangement fits the whole recording';
  const editorZoom=root.querySelector('[aria-label="Editor visual zoom"]');editorZoom.setAttribute('aria-label','Waveform zoom');editorZoom.value='1';
  editorZoom.oninput=()=>{zoom=Number(editorZoom.value);editorArea.style.width=(zoom*100)+'%';redraw();};
  toolbar.onscroll=()=>{$('regions').scrollTop=toolbar.scrollTop;};$('regions').onscroll=()=>{toolbar.scrollTop=$('regions').scrollTop;};
  const menu=$('appearance-menu');
  const menus={edit:[['Undo Studio setting',cmd.undo],['Redo Studio setting',cmd.redo],['Back 10 seconds',()=>cmd.seek(state.position-10)],['Forward 10 seconds',()=>cmd.seek(state.position+10)]],
   functions:[['Import recording',cmd.import],['Split stems',cmd.stems],['Analyse chords',cmd.analyze],['Chord practice',cmd.practice]],
   view:[['Library',()=>showPanel('library')],['Inspector',()=>showPanel('inspector')],['Audio Editor',toggleEditor],['Back to Explore',cmd.browse]]};
  for(const b of root.querySelectorAll('[data-menu]'))b.onclick=()=>{menu.replaceChildren();for(const [label,action]of menus[b.dataset.menu.replace('editor-','')]){
   const item=document.createElement('button');item.textContent=label;bind(item,()=>{menu.hidden=true;return action();});menu.append(item);}
   const rect=b.getBoundingClientRect();menu.style.left=rect.left+'px';menu.style.top=(rect.bottom+4)+'px';menu.hidden=false;};
  const dismiss=e=>{if(e.type==='keydown'?e.key==='Escape':!e.target.closest?.('[data-menu],#appearance-menu'))menu.hidden=true;};
  document.addEventListener('keydown',dismiss);document.addEventListener('pointerdown',dismiss);
  const tools=document.createElement('dialog');tools.id='logic-session-tools';tools.setAttribute('aria-labelledby','logic-tools-heading');
  tools.innerHTML='<header><strong id="logic-tools-heading"></strong><button aria-label="Close session panel">×</button></header><div class="logic-tools-body"></div>';
  const close=tools.querySelector('button');close.onclick=()=>tools.close();document.body.append(tools);
  let toolsMode='',toolsIdentity='';
  function showPanel(mode){toolsMode=mode;toolsIdentity='';renderPanel();if(!tools.open)tools.showModal();}
  function renderPanel(){
   if(!toolsMode)return;const key=JSON.stringify([toolsMode,state.selected,state.tracks.map(t=>[t.id,t.label])]);if(key===toolsIdentity)return;toolsIdentity=key;
   text(tools.querySelector('strong'),toolsMode==='library'?'Session tracks':'Track inspector');const body=tools.querySelector('.logic-tools-body');body.replaceChildren();
   if(toolsMode==='library'){
    if(!state.tracks.length){const p=document.createElement('p');p.textContent='No recording open.';body.append(p);}
    for(const track of state.tracks){const b=document.createElement('button');b.textContent=track.label;b.setAttribute('aria-pressed',String(track.id===state.selected));bind(b,()=>cmd.select(track.id));body.append(b);}return;
   }
   const name=document.createElement('p');name.textContent=state.tracks.find(t=>t.id===state.selected)?.label||'Recording';body.append(name);
   for(const [label,min,max,step,value,action]of[['Volume',0,1,.01,state.volume,cmd.volume],['Pan',-1,1,.01,state.tracks.find(t=>t.id===state.selected)?.pan||0,v=>cmd.pan(state.selected,v)],['Speed',.5,1.5,.25,state.rate,cmd.rate]]){
    const field=document.createElement('label'),input=document.createElement('input');field.textContent=label;input.type='range';Object.assign(input,{min:String(min),max:String(max),step:String(step),value:String(value)});input.setAttribute('aria-label',label);input.oninput=()=>{action(Number(input.value));update();};field.append(input);body.append(field);
   }
   for(const [label,action]of[['Channel EQ',cmd.eq],['Compressor',cmd.compressor],['Project timing',cmd.project],['Chord practice',cmd.practice]]){
    const b=document.createElement('button');b.textContent=label;bind(b,()=>{tools.close();return action();});body.append(b);
   }
  }
  function unsupported(node){node.disabled=true;node.title=(node.getAttribute('aria-label')||node.title||'Control')+' — not available';}
  function toggleEditor(){const hidden=root.classList.toggle('editor-hidden');$('show-editor').setAttribute('aria-pressed',String(!hidden));redraw();}
  function setTool(range){rangeTool=range;for(const [i,node]of [...$('pointer-tools').children].entries())node.setAttribute('aria-pressed',String(range?i===1:i===0));}
  function stamp(seconds){const n=Math.max(0,Number(seconds)||0);return String(Math.floor(n/60)).padStart(2,'0')+':'+String(Math.floor(n%60)).padStart(2,'0')+'.'+String(Math.floor(n*1000)%1000).padStart(3,'0');}
  function renderRows(){
   const key=JSON.stringify([state.revision,state.selected,state.pending,state.tracks.map(t=>[t.id,t.jobId,t.label,t.muted,t.pan,!!t.waveform])]);if(key===lastTracks)return;lastTracks=key;
   const ids=new Set(state.tracks.map(t=>t.id));for(const [id,row]of rows)if(!ids.has(id)){row.header.remove();row.lane.remove();rows.delete(id);}
   state.tracks.forEach((track,index)=>{
    let row=rows.get(track.id);
    if(!row){
     const header=document.createElement('div');header.className='track-header';header.tabIndex=0;header.setAttribute('role','option');header.dataset.trackId=track.id;
     header.innerHTML='<span class="track-number"></span><span class="instrument"></span><div class="track-info"><span class="track-name"></span><div class="track-controls"></div></div>';
     header.querySelector('.instrument').innerHTML=svg(({vocals:'vocal',synths:'synth',source:'wave',other:'wave'})[track.id]||track.id);
     const controls=header.querySelector('.track-controls');
     for(const [letter,label,action]of [['M','Mute',()=>cmd.mute(track.id)],['S','Audition',()=>cmd.solo(track.id)],['R','Record-enable',null],['I','Input-monitoring',null]]){
      const b=document.createElement('button');b.textContent=letter;b.setAttribute('aria-label',label+' '+track.label);b.onclick=async e=>{e.stopPropagation();if(action){await action();update();}};if(!action)unsupported(b);controls.append(b);
     }
     const meter=document.createElement('span');meter.className='track-level';meter.innerHTML='<i></i>';controls.append(meter);
     const pan=document.createElement('input');pan.className='live-pan';pan.type='range';pan.min='-1';pan.max='1';pan.step='.01';pan.setAttribute('aria-label','Pan '+track.label);pan.onclick=e=>e.stopPropagation();pan.oninput=()=>{cmd.pan(track.id,Number(pan.value));update();};controls.append(pan);
     header.onclick=e=>{if(!e.target.closest('button,input'))void cmd.select(track.id).then(update);};
     header.onkeydown=e=>{if(e.target===header&&(e.key==='Enter'||e.key===' ')){e.preventDefault();void cmd.select(track.id).then(update);}};
     const lane=document.createElement('div');lane.className='region-row';
     const clip=document.createElement('button');clip.className='clip';clip.setAttribute('aria-label','Open '+track.label+' waveform');clip.innerHTML='<span class="clip-name"></span><canvas></canvas>';
     bind(clip,()=>cmd.select(track.id));lane.append(clip);toolbar.append(header);$('regions').append(lane);
     row={header,lane,clip,canvas:clip.querySelector('canvas'),waveform:null};rows.set(track.id,row);
    }
    // Reconcile order as well as identity when a new completed job inserts its
    // original recording above the saved stems. Leave stable focused rows alone.
    if(toolbar.children[index]!==row.header)toolbar.insertBefore(row.header,toolbar.children[index]||null);
    const before=$('regions').querySelectorAll('.region-row')[index];
    if(before!==row.lane)$('regions').insertBefore(row.lane,before||null);
    const tone='var(--region-'+track.id+', '+track.region+')';
    row.header.style.setProperty('--track-color',tone);row.lane.style.setProperty('--region-color',tone);
    row.header.classList.toggle('selected',track.id===state.selected);row.header.setAttribute('aria-selected',String(track.id===state.selected));row.header.setAttribute('aria-busy',String(state.pending&&track.id===state.pendingTrack));
    row.header.setAttribute('aria-label',track.label);text(row.header.querySelector('.track-number'),index+1);text(row.header.querySelector('.track-name'),track.label);
    row.header.querySelector('button').setAttribute('aria-pressed',String(track.muted));row.header.querySelectorAll('button')[1].setAttribute('aria-pressed',String(state.solo&&track.id===state.selected));
    row.header.querySelector('input').value=String(track.pan);row.clip.classList.toggle('selected',track.id===state.selected);text(row.clip.querySelector('.clip-name'),track.label);
    row.clip.style.left='0';row.clip.style.width='100%';row.waveform=track.waveform;
   });
   empty.hidden=state.tracks.length>0;redraw();renderPanel();
  }
  function waveform(target,data,stereo=false){
   const r=target.getBoundingClientRect();if(!r.width||!r.height)return;const d=Math.min(devicePixelRatio||1,2);target.width=Math.round(r.width*d);target.height=Math.round(r.height*d);
   const g=target.getContext('2d');g.scale(d,d);const channels=stereo?2:1,style=getComputedStyle(root);
   const bar=60/state.tempo*4/state.denominator*state.numerator;
   const barPixels=state.duration?bar/state.duration*r.width:0;
   if(barPixels>0){let spacing=barPixels/state.numerator;while(spacing<18)spacing*=2;
    g.strokeStyle=style.getPropertyValue('--wave-grid');g.lineWidth=1;
    for(let x=spacing;x<r.width;x+=spacing){g.beginPath();g.moveTo(Math.round(x)+.5,0);g.lineTo(Math.round(x)+.5,r.height);g.stroke();}}
   g.fillStyle=style.getPropertyValue('--wave-ink');
   // Keep the stereo relationship: one display gain for both channels.
   let maximum=0;for(const bins of data?.peaks||[])for(const pair of bins)maximum=Math.max(maximum,Math.abs(pair[0]),Math.abs(pair[1]));
   const gain=maximum?Math.min(8,.88/maximum):1;
   target.dataset.channels=String(channels);
   for(let ch=0;ch<channels;ch++){const center=r.height/channels*(ch+.5),amplitude=r.height/channels*.42;
    g.strokeStyle='#bddcf044';g.beginPath();g.moveTo(0,center);g.lineTo(r.width,center);g.stroke();
    const bins=data?.peaks?.[ch]||data?.peaks?.[0];if(!bins?.length)continue;
    for(let x=0;x<r.width;x++){const first=Math.floor(x/r.width*bins.length),last=Math.min(bins.length,Math.max(first+1,Math.ceil((x+1)/r.width*bins.length)));let low=0,high=0;
     for(let n=first;n<last;n++){low=Math.min(low,bins[n][0]);high=Math.max(high,bins[n][1]);}g.fillRect(x,center-high*amplitude*gain,1,Math.max(.5,(high-low)*amplitude*gain));}
   }
  }
  function ruler(id){const target=$(id);target.replaceChildren();const bar=60/state.tempo*4/state.denominator*state.numerator;
   const count=Math.max(1,state.duration/bar),width=target.clientWidth;const step=2**Math.ceil(Math.log2(Math.max(1,count/Math.max(2,width/85))));
   target.style.setProperty('--beat-grid-px',(width/count/state.numerator)+'px');
   for(let n=0;n<count;n+=step){const span=document.createElement('span');span.textContent=String(n+1);span.style.left=(n/count*100)+'%';target.append(span);}}
  function redraw(){if(!state.active)return;for(const row of rows.values())waveform(row.canvas,row.waveform,true);waveform(canvas,state.peaks,true);
   const bar=60/state.tempo*4/state.denominator*state.numerator;
   $('regions').style.setProperty('--bar-grid-px',(state.duration?bar/state.duration*$('regions').clientWidth:100)+'px');
   ruler('project-ruler');ruler('editor-ruler');paintPosition();}
  function paintPosition(){
   const ratio=state.duration?Math.max(0,Math.min(1,state.position/state.duration)):0;
   for(const id of ['project-playhead','editor-playhead'])$(id).style.left=(ratio*100)+'%';
   const beats=state.position*state.tempo/60/(4/state.denominator),bar=Math.floor(beats/state.numerator)+1;
   text($('position-bar'),bar);text($('position-padding'),bar<10?'00':bar<100?'0':'');
   text($('position-beat'),Math.floor(beats)%state.numerator+1);
   text(time,stamp(state.position));canvas.setAttribute('aria-valuenow',String(Math.round(ratio*100)));canvas.setAttribute('aria-valuetext',stamp(state.position)+' of '+stamp(state.duration));
   for(const [i,meter]of meters.entries())meter.style.width=state.levels[i];
   for(const [id,row]of rows)row.header.style.setProperty('--level',id===state.selected?state.levels[0]:'0%');
   const range=$('wave-selection');range.hidden=!state.selection||!state.duration;
   if(state.selection&&state.duration){range.style.left=(state.selection[0]/state.duration*100)+'%';range.style.width=((state.selection[1]-state.selection[0])/state.duration*100)+'%';}
   text($('live-selection-readout'),state.selection?'Selection '+state.selection.map(stamp).join(' – '):'No range selected');
  }
  function update(){
   if(disposed)return;state=engine.viewState();if(!state.active){cancelAnimationFrame(frame);frame=0;return;}
   renderRows();const selected=state.tracks.find(t=>t.id===state.selected);text($('editor-track'),selected?.label||'Recording');text($('editor-caption'),selected?.label||'Recording');
   text(root.querySelector('.tempo b'),Number(state.tempo).toFixed(state.tempo%1?1:0));text(root.querySelector('.signature b'),state.numerator+'/'+state.denominator);text(root.querySelector('.signature span'),state.key.replace(' major','maj').replace(' minor','min'));
   text(root.querySelector('footer').firstElementChild,state.format);text(status,actionError||state.message);status.dataset.state=actionError?'error':state.messageState;
   text(editorEmpty,!state.peaks?(state.loading||state.pending?'Reading waveform…':state.tracks.length?'Waveform unavailable. Playback remains available.':'Import a recording to begin.'):'');
   const stemsState=window.BlazeMacStems?.snapshot();text(stems,stemsState?.status==='running'?'Split '+Math.round((stemsState.progress||0)*100)+'%':stemsState?.status==='failed'?'Retry split':'Split');stems.disabled=stemsState?.available!==true;
   analyze.disabled=!state.enabled&&!state.analysisBusy;text(analyze,state.analysisBusy?'Cancel':'Chords');analyze.setAttribute('aria-label',state.analysisBusy?'Cancel chord analysis':'Analyse chords');
   for(const i of [0,1,5])transport[i].disabled=!state.enabled;
   const playState=state.paused?'play':'pause';if(transport[1].dataset.state!==playState){transport[1].innerHTML=svg(playState);transport[1].dataset.state=playState;transport[1].setAttribute('aria-label',state.paused?'Play':'Pause');}
   transport[5].setAttribute('aria-pressed',String(state.loop));timing.at(-1).setAttribute('aria-pressed',String(state.metronome));master.value=String(state.volume);
   save.hidden=!state.save;if(state.save){save.href=state.save.href;save.download=state.save.name;save.setAttribute('aria-label','Save '+(selected?.label||'track')+' WAV');}else save.removeAttribute('href');
   if(state.chords!==lastChords||state.duration!==lastChordDuration){lastChords=state.chords;lastChordDuration=state.duration;$('chord-lane').replaceChildren();for(const chord of state.chords||[]){const node=document.createElement('button');node.textContent=chord.chord;
    node.style.left=(chord.start/(state.duration||1)*100)+'%';node.style.width=((chord.end-chord.start)/(state.duration||1)*100)+'%';node.title=chord.chord+' · '+stamp(chord.start);bind(node,()=>cmd.seek(chord.start));$('chord-lane').append(node);}}
   const rulerKey=[state.duration,state.tempo,state.numerator,state.denominator].join(':');if(rulerKey!==lastRuler){lastRuler=rulerKey;redraw();}
   const width=canvas.clientWidth;if(state.peaks!==lastPeaks||width!==lastEditorWidth){lastPeaks=state.peaks;lastEditorWidth=width;waveform(canvas,state.peaks,true);canvas.dataset.trackId=state.peaks?state.selected:'';}
   paintPosition();if(!state.paused&&!frame)frame=requestAnimationFrame(()=>{frame=0;update();});
  }
  const observer=new ResizeObserver(()=>{state=engine.viewState();redraw();});observer.observe(root);
  const player=document.getElementById('media');const events=['play','pause','timeupdate','seeked','loadedmetadata','volumechange','ratechange'];for(const event of events)player.addEventListener(event,update);
  const activeObserver=new MutationObserver(update);activeObserver.observe(panel,{attributes:true,attributeFilter:['hidden']});
  timer=setInterval(update,200);update();
  window.addEventListener('pagehide',()=>{disposed=true;clearInterval(timer);cancelAnimationFrame(frame);observer.disconnect();activeObserver.disconnect();tools.remove();
   for(const event of events)player.removeEventListener(event,update);document.removeEventListener('keydown',dismiss);document.removeEventListener('pointerdown',dismiss);},{once:true});
  window.BlazeLogicVisual={scope:'live-session',snapshot:()=>({tracks:state.tracks.map(t=>t.id),selected:state.selected,position:state.position,duration:state.duration,zoom}),redraw};
 };
})();
