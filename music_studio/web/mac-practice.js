/* Piano-first practice over the existing player, analysis and separation engines. */
(() => {
 'use strict';
 const engine=window.BlazeMacStudio;
 if(document.documentElement.dataset.presentation!=='mac'||!engine||window.BlazeLogicVisual?.scope!=='live-session')return;
 const host=document.getElementById('studio-panel'),studio=document.getElementById('logic-preview'),player=document.getElementById('media'),cmd=engine.commands;
 const root=document.createElement('section');root.id='practice-workspace';root.setAttribute('aria-label','Song practice');
 root.innerHTML=`
  <header class="practice-header"><div class="practice-song"><h1 id="practice-title">Practice</h1><p id="practice-song-detail">Open a song and learn it one passage at a time.</p></div><div class="practice-header-actions"><button id="practice-open">Open song</button><button id="practice-find">Find a song</button><button id="practice-advanced" class="practice-quiet">Advanced Studio</button></div></header>
  <div class="practice-content">
   <section id="practice-empty" class="practice-empty"><h2>Choose a song to begin.</h2><p>Hear its piano, slow down a difficult passage, then play along with the backing.</p></section>
   <div id="practice-song-controls" hidden>
    <div class="practice-listening"><div class="practice-mode" role="group" aria-label="Listening mode"><button id="practice-original" aria-pressed="true">Original</button><button id="practice-piano" aria-pressed="false">Piano</button><button id="practice-backing" aria-pressed="false">Backing</button></div><p id="practice-preparation" role="status"></p><button id="practice-preparation-details" class="practice-quiet" hidden>Preparation details</button></div>
    <section class="practice-passage" aria-label="Song passage"><div class="practice-wave-heading"><span id="practice-mode-label">Original recording</span><span id="practice-wave-status"></span></div><div id="practice-wave-area" class="practice-wave-area"><canvas id="practice-wave" role="slider" tabindex="0" aria-label="Song waveform. Click to seek; shift-drag to loop a passage." aria-valuemin="0" aria-valuemax="100"></canvas><div id="practice-loop-range" class="practice-loop-range" hidden></div><div id="practice-playhead" class="practice-playhead" aria-hidden="true"></div><span id="practice-wave-empty">Reading waveform…</span></div><div class="practice-wave-times"><span>0:00</span><span id="practice-song-duration">0:00</span></div>
     <div class="practice-loop-tools"><div class="practice-loop-points"><button id="practice-set-a">Set A <span id="practice-a-value">—</span></button><button id="practice-set-b">Set B <span id="practice-b-value">—</span></button></div><button id="practice-loop-toggle" aria-pressed="false">Loop passage</button><button id="practice-clear-loop" class="practice-quiet">Clear</button><span id="practice-loop-hint">Set A and B, or shift-drag on the waveform.</span></div>
    </section>
    <section class="practice-chords" aria-labelledby="practice-chords-heading"><div class="practice-section-heading"><h2 id="practice-chords-heading">Chord guide</h2><span id="practice-key-tempo"></span><button id="practice-analyze" class="practice-quiet">Analyse chords</button></div><p id="practice-chord-help">Analyse this song to follow its chords while you play.</p><div class="practice-chord-pair"><button id="practice-current-chord" class="practice-chord"><span>Current</span><strong aria-live="polite">—</strong><small>Not analysed</small></button><button id="practice-next-chord" class="practice-chord"><span>Up next</span><strong>—</strong><small>Not analysed</small></button></div></section>
   </div>
   <section class="practice-saved" aria-labelledby="practice-saved-heading"><div class="practice-section-heading"><h2 id="practice-saved-heading">Saved practices</h2><button id="practice-save" class="practice-quiet" disabled>Save practice</button></div><p id="practice-save-status" role="status">Save a song to remember your passage, speed and listening mode.</p><div id="practice-sessions" role="group" aria-label="Saved practices"></div></section>
  </div>
  <footer class="practice-transport" aria-label="Practice playback"><div class="practice-speed"><label for="practice-speed">Speed <output id="practice-speed-value">1×</output></label><input id="practice-speed" type="range" min=".5" max="1.25" step=".05" value="1"><div class="practice-speed-presets"><button data-rate=".5">0.5×</button><button data-rate=".75">0.75×</button><button data-rate="1" aria-pressed="true">1×</button></div></div><div class="practice-play-controls"><button id="practice-back" class="practice-icon" aria-label="Back five seconds"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5v14M19 5 7 12l12 7Z"/></svg></button><button id="practice-play" class="practice-play" aria-label="Play song"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 4 12 8-12 8Z"/></svg></button><button id="practice-forward" class="practice-icon" aria-label="Forward five seconds"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 5v14M5 5l12 7-12 7Z"/></svg></button><output id="practice-position">0:00 / 0:00</output></div><div class="practice-volume"><label for="practice-volume">Volume</label><input id="practice-volume" type="range" min="0" max="1" step=".01" value="1"></div><p id="practice-status" role="status"></p></footer>`;
 host.prepend(root);
 const $=id=>root.querySelector('#practice-'+id),text=(node,value)=>{value=String(value??'');if(node.textContent!==value)node.textContent=value;};
 let studioVisible=null;
 let playFrame=0,pendingRestore=null;
 let active=true,stopped=false,state=engine.viewState(),meta={sessions:[],current:null,pianoJobId:null,recordingId:null,sourceRevision:-1,guide:null};
 let metadataBusy=false,metadataAgain=false,metadataSerial=0,actionEpoch=0,modeBusy=false,queuedMode=null,pendingMode=null,restoring=false;
 let message='',error='',saveMessage='',saving=false,saveTimer=0,saveAgain=false,lastSaveAt=0,lastSavedFingerprint='',lastControlsFingerprint='',lastKey=null,lastMetaTrigger='';
 let a=null,b=null,previewRange=null,pointer=null,peaksIdentity=null,lastCanvasWidth=0,lastGuide=null,events=[],knownEvents=[],currentChord=null,nextChord=null,rowsIdentity='';
 const stamp=value=>{value=Math.max(0,Number(value)||0);return Math.floor(value/60)+':'+String(Math.floor(value%60)).padStart(2,'0');};
 const precise=value=>value===null?'—':stamp(value)+(Math.abs(value-Math.round(value))>.02?'.'+Math.floor(value%1*10):'');
 const hasSong=()=>!!sourceName;
 const currentJob=()=>state.tracks.find(t=>t.id===state.selected)?.jobId||state.tracks.find(t=>t.id==='source')?.jobId||null;
 const actualMode=()=>currentJob()===meta.pianoJobId&&state.selected==='piano'?'piano':currentJob()===meta.pianoJobId&&state.selected==='accompaniment'?'backing':'original';
 const settings=()=>({position:Math.max(0,Number(player.currentTime)||0),rate:player.playbackRate||1,loopStart:a,loopEnd:b,loopEnabled:!!(state.loop&&a!==null&&b!==null),mode:actualMode()});
 const fingerprint=value=>JSON.stringify([value.rate,value.loopStart,value.loopEnd,value.loopEnabled,value.mode]);
 function report(failure){error=failure?.message||String(failure);update();}
 const run=action=>async()=>{error='';try{await action();}catch(failure){report(failure);}finally{update();}};
 function visibility(){document.body.classList.toggle('practice-workspace-active',active&&!host.hidden);root.hidden=!active;studio.hidden=active;if(studioVisible!==!active){studioVisible=!active;window.BlazeLogicVisual?.setVisible?.(!active);}returnButton.hidden=active;if(!active||host.hidden){cancelAnimationFrame(playFrame);playFrame=0;}}
 function showPractice(){active=true;visibility();void refreshMetadata();update();}
 function showStudio(){active=false;visibility();window.BlazeLogicVisual?.redraw();}
 const returnButton=document.createElement('button');returnButton.className='practice-return';returnButton.textContent='Practice';returnButton.setAttribute('aria-label','Return to Practice');returnButton.onclick=showPractice;studio.querySelector('footer').append(returnButton);
 $('advanced').onclick=showStudio;$('open').onclick=run(()=>cmd.import());$('find').onclick=run(()=>cmd.browse());
 $('play').onclick=run(()=>cmd.play());$('back').onclick=run(()=>cmd.seek((Number(player.currentTime)||0)-5));$('forward').onclick=run(()=>cmd.seek((Number(player.currentTime)||0)+5));
 const keepPitch=()=>{player.preservesPitch=true;if('webkitPreservesPitch'in player)player.webkitPreservesPitch=true;if('mozPreservesPitch'in player)player.mozPreservesPitch=true;};
 $('speed').oninput=()=>{keepPitch();cmd.rate(Number($('speed').value));changed();update();};
 for(const button of root.querySelectorAll('[data-rate]'))button.onclick=()=>{keepPitch();cmd.rate(Number(button.dataset.rate));changed();update();};
 $('volume').oninput=()=>{cmd.volume(Number($('volume').value));update();};
 function applyLoop(enabled=true){if(a===null||b===null||b-a<.05)return;cmd.setLoop(a,b,enabled);changed();update();}
 $('set-a').onclick=()=>{a=Math.max(0,Number(player.currentTime)||0);if(b!==null&&b<=a)b=null;if(b!==null)applyLoop(state.loop);else cmd.clearLoop();changed();update();};
 $('set-b').onclick=()=>{const end=Number(player.currentTime)||0;if(a===null)a=0;if(end<=a+.05){error='Set B after A.';update();return;}b=end;applyLoop(true);};
 $('loop-toggle').onclick=()=>applyLoop(!state.loop);
 $('clear-loop').onclick=()=>{a=b=null;cmd.clearLoop();changed();update();};
 $('analyze').onclick=run(()=>state.analysisBusy?cmd.cancelAnalysis():cmd.analyze());
 $('preparation-details').onclick=run(()=>window.BlazeMacStems.open());
 function changed(){if(restoring||!hasSong())return;lastControlsFingerprint=fingerprint(settings());scheduleSave();}
 function scheduleSave(delay=750,reset=true){if(!reset&&saveTimer)return;clearTimeout(saveTimer);if(!meta.current?.id||!meta.recordingId||restoring)return;saveTimer=setTimeout(()=>{saveTimer=0;void save(false);},delay);}
 async function save(explicit){
  if(!hasSong()||restoring)return;
  if(saving){saveAgain=true;return;}
  const revision=sourceRevision;if(meta.sourceRevision!==revision){await refreshMetadata();if(sourceRevision!==revision||meta.sourceRevision!==revision)return;}const key=meta.recordingId;
  saving=true;saveAgain=false;saveMessage='Saving practice…';error='';update();
  try{
   const value=settings(),answer=await api('/api/practice-save',{sourceRevision:revision,...(meta.current?.id?{sessionId:meta.current.id}:{}),...value});
   if(key===meta.recordingId&&revision===sourceRevision){meta=answer;lastSavedFingerprint=fingerprint(value);lastControlsFingerprint=lastSavedFingerprint;lastSaveAt=performance.now();saveMessage='Saved on this Mac';}
   else{saveMessage='Practice saved';await refreshMetadata();}
  }catch(failure){if(explicit||key===meta.recordingId)report(failure);saveMessage='Practice could not be saved.';}
  finally{saving=false;update();if(saveAgain&&meta.recordingId===key)scheduleSave();}
 }
 $('save').onclick=()=>void save(true);
 async function refreshMetadata(){
  if(stopped)return;
  if(metadataBusy){metadataAgain=true;return;}
  metadataBusy=true;const serial=++metadataSerial;
  try{
   const answer=await api('/api/practice');if(serial!==metadataSerial||stopped)return;
   if(Number.isSafeInteger(sourceRevision)&&answer.sourceRevision!==sourceRevision){metadataAgain=true;return;}
   const changedSong=lastKey!==null&&answer.recordingId!==lastKey;
   meta=answer;
   if(changedSong&&!restoring){++actionEpoch;pendingMode=null;queuedMode=null;a=b=null;saveMessage='';error='';clearTimeout(saveTimer);lastSavedFingerprint='';lastControlsFingerprint='';}
   if(lastKey!==answer.recordingId){lastKey=answer.recordingId;lastControlsFingerprint=fingerprint(settings());}
   if(pendingMode&&pendingMode.recordingId!==meta.recordingId)pendingMode=null;
   if(active)update();
  }catch(failure){if(active)report(failure);}
  finally{metadataBusy=false;if(metadataAgain){metadataAgain=false;setTimeout(()=>void refreshMetadata(),120);}}
 }
 async function chooseMode(mode){
  const intent=++actionEpoch;error='';
  if(modeBusy){queuedMode=mode;return;}
  if(!hasSong())return;
  if(meta.sourceRevision!==sourceRevision)await refreshMetadata();
  if(intent!==actionEpoch||meta.sourceRevision!==sourceRevision)return;
  const key=meta.recordingId,pair=meta.pianoJobId;
  if(mode==='original')pendingMode=null;
  if(mode!=='original'&&!pair){
   const task=window.BlazeMacStems.snapshot();
   if(task.status==='running'){
    if(pendingMode?.recordingId===key){pendingMode.mode=mode;update();return;}
    error='Another preparation is running. You can keep practising this song.';update();return;
   }
   modeBusy=true;pendingMode={mode,recordingId:key,jobId:null};update();
   try{
    const job=currentJob();if(state.selected!=='source'&&job)await cmd.practiceTrack(job,'source');
    if(intent!==actionEpoch||meta.recordingId!==key)return;
    const started=await window.BlazeMacStems.start('piano');
    if(intent===actionEpoch&&pendingMode?.recordingId===key){if(['running','done'].includes(started.status)&&started.mode==='piano')pendingMode.jobId=started.jobId;else if(started.status==='failed')throw Error(started.error||'Piano preparation could not start.');}
    await refreshMetadata();
   }catch(failure){if(intent===actionEpoch){pendingMode=null;report(failure);}}
   finally{modeBusy=false;update();runQueued();}
   return;
  }
  const job=pair||currentJob();if(!job){update();return;}
  const stem={original:'source',piano:'piano',backing:'accompaniment'}[mode];
  if(currentJob()===job&&state.selected===stem){update();return;}
  modeBusy=true;update();
  try{await cmd.practiceTrack(job,stem);if(intent===actionEpoch&&meta.recordingId===key){pendingMode=null;await refreshMetadata();changed();}}
  catch(failure){if(intent===actionEpoch)report(failure);}
  finally{modeBusy=false;update();runQueued();}
 }
 function runQueued(){if(queuedMode){const next=queuedMode;queuedMode=null;void chooseMode(next);}}
 for(const mode of ['original','piano','backing'])$(mode).onclick=()=>void chooseMode(mode);
 async function openSaved(id){
  const intent=++actionEpoch,revision=sourceRevision;cancelRestore();pendingMode=null;restoring=true;let awaitingMetadata=false;error='';clearTimeout(saveTimer);message='Opening saved practice…';update();
  try{
   const answer=await api('/api/practice-open',{id,sourceRevision:revision});if(intent!==actionEpoch)return;
   const expected=answer.sourceRevision;await window.BlazeMac.importCompleted();if(intent!==actionEpoch||sourceRevision!==expected)return;
   meta=answer;lastKey=answer.recordingId;const value=answer.settings||answer.opened.settings;
   const ready=()=>{
    if(pendingRestore?.handler===ready)pendingRestore=null;
    if(intent!==actionEpoch||sourceRevision!==expected){restoring=false;return;}
    keepPitch();cmd.rate(value.rate);a=value.loopStart;b=value.loopEnd;
    if(a!==null&&b!==null)cmd.setLoop(a,b,value.loopEnabled);else cmd.clearLoop();
    cmd.seek(value.position);restoring=false;lastControlsFingerprint=fingerprint(settings());lastSavedFingerprint=lastControlsFingerprint;lastSaveAt=performance.now();message=answer.notice||'';update();
   };
   if(player.readyState>=1)ready();else{awaitingMetadata=true;pendingRestore={revision:expected,handler:ready};player.addEventListener('loadedmetadata',ready,{once:true});}
   saveMessage='Saved practice opened';
  }catch(failure){if(intent===actionEpoch)report(failure);}
  finally{if(!awaitingMetadata)restoring=false;update();}
 }
 function cancelRestore(){if(pendingRestore){player.removeEventListener('loadedmetadata',pendingRestore.handler);pendingRestore=null;restoring=false;}}
 function renderSessions(){
  const rows=meta.sessions||[],identity=JSON.stringify(rows.map(row=>[row.id,row.title,row.available,row.updatedAt]));if(identity===rowsIdentity)return;rowsIdentity=identity;$('sessions').replaceChildren();
  if(!rows.length){const empty=document.createElement('p');empty.className='practice-no-saved';empty.textContent='Your saved songs will appear here.';$('sessions').append(empty);return;}
  for(const row of rows){const button=document.createElement('button');button.className='practice-saved-row';button.dataset.practiceId=row.id;button.setAttribute('aria-label','Resume '+row.title);button.disabled=row.available===false;
   const name=document.createElement('strong');name.textContent=row.title;const details=document.createElement('span'),value=row.settings;
   details.textContent=row.available===false?'Recording unavailable':[(value.rate||1)+'×',value.loopEnabled&&value.loopStart!==null?'Loop '+stamp(value.loopStart)+'–'+stamp(value.loopEnd):'From '+stamp(value.position),({original:'Original',piano:'Piano',backing:'Backing'})[value.mode]||'Original'].join(' · ');
   button.append(name,details);button.onclick=()=>void openSaved(row.id);$('sessions').append(button);}
 }
 function chordLabel(chord){if(!chord||chord==='X')return 'Uncertain';if(chord==='N')return 'No chord';const [main,bass]=chord.split('/'),[note,quality='maj']=main.split(':'),suffix={maj:'',min:'m',min7:'m7',minmaj7:'m(maj7)',maj6:'6',min6:'m6',hdim7:'m7♭5'};return note+(suffix[quality]??quality)+(bass?'/'+bass:'');}
 function after(values,position){let left=0,right=values.length;while(left<right){const mid=(left+right)>>>1;if(values[mid].start<=position)left=mid+1;else right=mid;}return left;}
 function renderChords(){
  const recordingGuide=meta.sourceRevision===sourceRevision?meta.guide:null;
  const guide=recordingGuide||state.practiceGuide;const candidate=recordingGuide?.chords?.length?recordingGuide.chords:state.practiceChords?.length?state.practiceChords:state.chords||[];
  if(candidate!==lastGuide){lastGuide=candidate;events=candidate;knownEvents=events.filter(event=>event.chord!=='N'&&event.chord!=='X');}
  const position=Number(player.currentTime)||0,index=after(events,position)-1;
  currentChord=index>=0&&events[index].end>position?events[index]:null;nextChord=knownEvents[after(knownEvents,position)]||null;
  for(const [id,event]of [['current-chord',currentChord],['next-chord',nextChord]]){const button=$(id);text(button.querySelector('strong'),event?chordLabel(event.chord):'—');text(button.querySelector('small'),event?stamp(event.start)+'–'+stamp(event.end):events.length?'No chord here':'Not analysed');button.disabled=!event;button.onclick=event?()=>cmd.seek(event.start):null;}
  const key=guide?.key||state.key,tempo=guide?.tempo_bpm||guide?.tempo||state.tempo;const details=events.length?[key&&key!=='—'?key:'',tempo?Math.round(tempo)+' BPM':''].filter(Boolean).join(' · '):'';text($('key-tempo'),details);
  text($('chord-help'),state.analysisBusy?'Analysing '+(state.analysisTask?.sourceName||'your recording')+'…':events.length?'A listening guide, with uncertain sections marked.':'Analyse this song to follow its chords while you play.');
  text($('analyze'),state.analysisBusy?'Cancel analysis':events.length?'Analyse again':'Analyse chords');$('analyze').disabled=!hasSong();
 }
 function drawWave(){
  const canvas=$('wave'),width=canvas.clientWidth,height=canvas.clientHeight,dpr=devicePixelRatio||1,data=state.peaks;
  if(data===peaksIdentity&&width===lastCanvasWidth&&canvas.height===Math.round(height*dpr))return;peaksIdentity=data;lastCanvasWidth=width;canvas.width=Math.max(1,Math.round(width*dpr));canvas.height=Math.max(1,Math.round(height*dpr));
  const context=canvas.getContext('2d');context.setTransform(dpr,0,0,dpr,0,0);context.clearRect(0,0,width,height);if(!data?.peaks?.length)return;
  const style=getComputedStyle(root);context.fillStyle=style.getPropertyValue('--practice-wave-ink').trim();const channels=data.peaks.length>1?data.peaks:[data.peaks[0]],gap=channels.length>1?12:0,band=(height-gap)/channels.length;
  channels.forEach((samples,channel)=>{const middle=channel*(band+gap)+band/2,scale=(band-16)/2;for(let x=0;x<width;x++){const from=Math.floor(x*samples.length/width),to=Math.max(from+1,Math.floor((x+1)*samples.length/width));let low=0,high=0;for(let i=from;i<Math.min(to,samples.length);i++){low=Math.min(low,Number(samples[i][0])||0);high=Math.max(high,Number(samples[i][1])||0);}context.fillRect(x,middle-Math.min(1,high)*scale,1,Math.max(1,(Math.min(1,high)-Math.max(-1,low))*scale));}});
 }
 const at=event=>{const bounds=$('wave').getBoundingClientRect();return Math.max(0,Math.min(state.duration,(event.clientX-bounds.left)/Math.max(1,bounds.width)*state.duration));};
 $('wave').onpointerdown=event=>{if(event.button!==0||!state.enabled||restoring||!state.duration)return;event.preventDefault();$('wave').focus();$('wave').setPointerCapture(event.pointerId);pointer={start:at(event),loop:event.shiftKey};if(pointer.loop)previewRange=[pointer.start,pointer.start];else cmd.seek(pointer.start);update();};
 $('wave').onpointermove=event=>{if(!pointer||!$('wave').hasPointerCapture(event.pointerId))return;const position=at(event);if(pointer.loop)previewRange=[Math.min(pointer.start,position),Math.max(pointer.start,position)];else cmd.seek(position);update();};
 const finishWave=event=>{if(!pointer)return;if(pointer.loop&&previewRange&&previewRange[1]-previewRange[0]>=.05){[a,b]=previewRange;applyLoop(true);}previewRange=null;pointer=null;if($('wave').hasPointerCapture(event.pointerId))$('wave').releasePointerCapture(event.pointerId);update();};
 $('wave').onpointerup=finishWave;$('wave').onpointercancel=event=>{previewRange=null;pointer=null;if($('wave').hasPointerCapture(event.pointerId))$('wave').releasePointerCapture(event.pointerId);update();};
 $('wave').onkeydown=event=>{const position=Number(player.currentTime)||0,steps={ArrowLeft:position-5,ArrowRight:position+5,Home:0,End:state.duration};if(Object.hasOwn(steps,event.key)){event.preventDefault();cmd.seek(steps[event.key]);update();}};
 function update(){
  if(stopped)return;if(pendingRestore&&pendingRestore.revision!==sourceRevision)cancelRestore();state=engine.viewState();visibility();if(!active||host.hidden)return;
  const song=hasSong(),mode=actualMode(),task=window.BlazeMacStems?.snapshot()||{};
  text($('title'),song?(state.title&&!/^Untitled/.test(state.title)?state.title:sourceName):'Practice');$('title').title=$('title').textContent;text($('song-detail'),song?'Piano practice · '+(mode==='original'?'Original recording':mode==='piano'?'Piano only':'Backing without piano'):'Open a song and learn it one passage at a time.');
  $('empty').hidden=song;$('song-controls').hidden=!song;
  for(const value of ['original','piano','backing']){$(value).setAttribute('aria-pressed',String(mode===value));$(value).disabled=!song||restoring||(modeBusy&&value!=='original');$(value).setAttribute('aria-busy',String(modeBusy||pendingMode?.mode===value));}
  const isPreparing=task.status==='running';text($('preparation'),isPreparing?'Preparing '+(task.sourceName||'your recording')+' · '+Math.round((task.progress||0)*100)+'%. You can keep listening.':meta.pianoJobId?'Piano and backing are ready.':song?'Choose Piano or Backing to prepare this song on your Mac.':'');$('preparation-details').hidden=!isPreparing&&task.status!=='failed';
  text($('mode-label'),mode==='original'?'Original recording':mode==='piano'?'Piano only':'Backing without piano');text($('wave-status'),state.loading||state.pending?'Loading waveform…':'');$('wave-empty').hidden=!!state.peaks;text($('wave-empty'),state.loading||state.pending?'Reading waveform…':'Waveform unavailable. Playback is still available.');
  const position=Number(player.currentTime)||0,length=state.duration||0;text($('song-duration'),stamp(length));text($('position'),stamp(position)+' / '+stamp(length));$('playhead').style.left=(length?position/length*100:0)+'%';
  $('wave').setAttribute('aria-valuenow',String(Math.round(length?position/length*100:0)));$('wave').setAttribute('aria-valuetext',stamp(position)+' of '+stamp(length));
  if(state.loopStart!==null&&state.loopStart!==undefined&&state.loopEnd!==null&&state.loopEnd!==undefined){a=state.loopStart;b=state.loopEnd;}
  const range=previewRange||(a!==null&&b!==null?[a,b]:null);$('loop-range').hidden=!range||!length;if(range&&length){$('loop-range').style.left=(range[0]/length*100)+'%';$('loop-range').style.width=((range[1]-range[0])/length*100)+'%';$('loop-range').classList.toggle('enabled',!!state.loop);}
  text($('a-value'),precise(a));text($('b-value'),precise(b));$('set-a').disabled=!state.enabled||restoring;$('set-b').disabled=!state.enabled||restoring;$('loop-toggle').disabled=!state.enabled||restoring||a===null||b===null;$('clear-loop').disabled=a===null&&b===null;$('loop-toggle').setAttribute('aria-pressed',String(!!state.loop&&a!==null&&b!==null));
  const playing=!player.paused;$('play').setAttribute('aria-label',playing?'Pause song':'Play song');if($('play').dataset.playing!==String(playing)){$('play').dataset.playing=String(playing);$('play').innerHTML=playing?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4h4v16H7ZM15 4h4v16h-4Z"/></svg>':'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 4 12 8-12 8Z"/></svg>';}
  for(const id of ['play','back','forward','speed','volume'])$(id).disabled=!state.enabled||restoring;
  if(document.activeElement!==$('speed'))$('speed').value=String(player.playbackRate||1);text($('speed-value'),Number((player.playbackRate||1).toFixed(2))+'×');for(const preset of root.querySelectorAll('[data-rate]'))preset.setAttribute('aria-pressed',String(Math.abs(Number(preset.dataset.rate)-player.playbackRate)<.001));
  if(document.activeElement!==$('volume'))$('volume').value=String(player.volume);
  $('save').disabled=!song||saving||restoring;text($('save'),saving?'Saving…':meta.current?.id?'Save changes':'Save practice');text($('save-status'),saveMessage||'Save a song to remember your passage, speed and listening mode.');
  text($('status'),error||message||(!song?'':state.messageState==='error'?state.message:''));$('status').dataset.error=String(!!error||state.messageState==='error');
  drawWave();renderChords();renderSessions();if(player.paused){cancelAnimationFrame(playFrame);playFrame=0;}else animatePlayback();
  const trigger=JSON.stringify([sourceRevision,task.status,task.jobId,state.analysisBusy]);if(trigger!==lastMetaTrigger){lastMetaTrigger=trigger;void refreshMetadata();}
  if(pendingMode&&meta.pianoJobId===pendingMode.jobId&&meta.recordingId===pendingMode.recordingId&&!modeBusy&&!state.pending){const desired=pendingMode.mode;pendingMode=null;void chooseMode(desired);}
  if(pendingMode&&['failed','cancelled'].includes(task.status)&&task.jobId===pendingMode.jobId){error=task.error||'Piano preparation was cancelled.';pendingMode=null;}
  const value=settings(),controls=fingerprint(value);if(meta.current?.id&&!restoring&&meta.sourceRevision===sourceRevision){if(lastControlsFingerprint&&controls!==lastControlsFingerprint){lastControlsFingerprint=controls;scheduleSave();}if(!player.paused&&performance.now()-lastSaveAt>8000&&!saving)scheduleSave(300,false);}
 }
 function paintPlayback(){const length=state.duration||0,position=Number(player.currentTime)||0;const percentage=length?Math.max(0,Math.min(100,position/length*100)):0;$('playhead').style.left=percentage+'%';text($('position'),stamp(position)+' / '+stamp(length));}
 function animatePlayback(){if(playFrame||stopped||!active||host.hidden||player.paused)return;playFrame=requestAnimationFrame(()=>{playFrame=0;if(stopped||!active||host.hidden||player.paused)return;paintPlayback();animatePlayback();});}
 const mediaEvents=['play','pause','timeupdate','loadedmetadata','seeked','ratechange','volumechange','ended'];for(const event of mediaEvents)player.addEventListener(event,update);
 const saveOnPause=()=>{if(meta.current?.id&&!restoring)scheduleSave(300,false);};player.addEventListener('pause',saveOnPause);player.addEventListener('seeked',saveOnPause);window.addEventListener('blaze-mac-media-changed',update);
 const resize=new ResizeObserver(()=>{peaksIdentity=null;update();});resize.observe(root);
 const observer=new MutationObserver(()=>{visibility();if(!host.hidden&&active){void refreshMetadata();update();}});observer.observe(host,{attributes:true,attributeFilter:['hidden']});
 const timer=setInterval(update,200);keepPitch();showPractice();
 for(const [id,label]of [['tab-studio','Practice'],['now-studio','Practise']]){const node=document.getElementById(id);if(node)node.textContent=label;}
 window.BlazeMac.navigate('studio');
 window.BlazeMacPractice={showPractice,showStudio,refresh:refreshMetadata,snapshot:()=>({visible:active&&!host.hidden,mode:actualMode(),requestedMode:pendingMode?.mode||null,recordingId:meta.recordingId,sessionId:meta.current?.id||null,pianoJobId:meta.pianoJobId,preparing:window.BlazeMacStems?.snapshot().status==='running',loopStart:a,loopEnd:b,loopEnabled:!!(state.loop&&a!==null&&b!==null),rate:player.playbackRate,pitchPreserved:player.preservesPitch,position:Number(player.currentTime)||0,savedSessions:meta.sessions?.length||0,saving,error})};
 window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);clearTimeout(saveTimer);cancelAnimationFrame(playFrame);cancelRestore();resize.disconnect();observer.disconnect();for(const event of mediaEvents)player.removeEventListener(event,update);player.removeEventListener('pause',saveOnPause);player.removeEventListener('seeked',saveOnPause);window.removeEventListener('blaze-mac-media-changed',update);},{once:true});
})();
