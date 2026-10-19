'use strict';
function readPalette(){const style=getComputedStyle(document.documentElement);return Object.fromEntries(['text','muted','accent','accent-bright','border','future'].map(name=>[name,style.getPropertyValue('--'+name).trim()]));}
let palette=readPalette();
const $=id=>document.getElementById(id),token=document.querySelector('meta[name="blaze-token"]').content;
const media=$('media'),roots=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
const intervals={maj:[0,4,7],min:[0,3,7],dim:[0,3,6],aug:[0,4,8],'7':[0,4,7,10],maj7:[0,4,7,11],min7:[0,3,7,10],minmaj7:[0,3,7,11],dim7:[0,3,6,9],hdim7:[0,3,6,10],maj6:[0,4,7,9],min6:[0,3,7,9],sus2:[0,2,7],sus4:[0,5,7],'9':[0,4,7,10,2],maj9:[0,4,7,11,2],min9:[0,3,7,10,2],'11':[0,4,7,10,2,5],'13':[0,4,7,10,2,5,9],min11:[0,3,7,10,2,5],min13:[0,3,7,10,2,5,9],maj13:[0,4,7,11,2,5,9],'7sus4':[0,5,7,10]};
const suffix={maj:'',min:'m',min7:'m7',minmaj7:'m(maj7)',maj6:'6',min6:'m6',hdim7:'m7b5',min11:'m11',min13:'m13'};
let flowMap=BlazeFlow.build(null),flowGroup=-1,flowNodes=[],flowFrame=0,lastFlowPaint=0,flowAnnouncement='';
let summaryView=false,loopStart=null,loopEnd=null;
const mediaSession=Date.now().toString(36);
let importing=false,firstStudioState=true,mediaRevision=0;
let result=null,amount=0,current=-1,kind='piano',sourceName='',lastResultId='',busy=false,studioTimer;
const time=value=>{value=Math.max(0,value||0);return `${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}`;};
function pitch(note){const m=/^([A-G])([#b]?)$/.exec(note);if(!m)return -1;return ({C:0,D:2,E:4,F:5,G:7,A:9,B:11}[m[1]]+(m[2]==='#'?1:m[2]==='b'?-1:0)+12)%12;}
function parts(label){if(!label||label==='N'||label==='X')return null;const [rq,bass]=label.split('/'),[root,quality='maj']=rq.split(':');return {root:(pitch(root)+amount+12)%12,quality,bass:bass?(pitch(bass)+amount+12)%12:null};}
function pretty(label){if(label==='N')return 'No chord';if(label==='X')return '—';const p=parts(label);return p?roots[p.root]+(suffix[p.quality]??p.quality)+(p.bass===null?'':'/'+roots[p.bass]):'—';}
async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'X-Blaze-Token':token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(value.error||'Could not complete this action.');return value;}
function failure(error){$('error').hidden=false;$('error').textContent=error.message||String(error);}
function seek(value){if(Number.isFinite(media.duration))media.currentTime=Math.max(0,Math.min(media.duration,value));updatePlayback();}
function seekChord(event){if(event)seek(Math.min(event.end-.001,event.start+Math.min(.025,(event.end-event.start)/2)));}
function indexAt(value){if(!result)return -1;let low=0,high=result.chords.length-1;while(low<=high){const mid=(low+high)>>1,e=result.chords[mid];if(value<e.start)high=mid-1;else if(value>=e.end)low=mid+1;else return mid;}return -1;}
function cards(){const container=$('chord-cards');container.replaceChildren();const upcoming=flowMap.nextKnown[current]??-1;const indexes=result&&current>=0?[flowMap.previousKnown[current]??-1,current,upcoming,upcoming>=0?flowMap.nextKnown[upcoming]:-1]:[-1,-1,-1,-1];indexes.forEach((index,i)=>{const b=document.createElement('button');b.className='chord'+(i===1?' active':'');const e=result&&index>=0?result.chords[index]:null;const label=document.createElement('span');label.textContent=e?pretty(e.chord):'—';const hint=document.createElement('small');hint.textContent=['PREVIOUS','NOW','NEXT','AFTER'][i];b.append(label,hint);b.disabled=!e;if(e){b.title=`${time(e.start)}${e.edited?' · corrected locally':''}`;b.onclick=()=>seekChord(e);}container.append(b);});}
function canvas(id){const c=$(id),r=c.getBoundingClientRect(),d=devicePixelRatio||1,w=Math.max(1,Math.round(r.width*d)),h=Math.max(1,Math.round(r.height*d));if(c.width!==w)c.width=w;if(c.height!==h)c.height=h;const g=c.getContext('2d');g.setTransform(d,0,0,d,0,0);g.clearRect(0,0,r.width,r.height);return {c,g,w:r.width,h:r.height};}
function wave(){const {g,w,h}=canvas('wave');if(!result?.waveform?.length){const duration=media.duration;if(sourceName&&Number.isFinite(duration)){const position=Math.max(0,Math.min(1,media.currentTime/duration));g.fillStyle=palette.border;g.fillRect(0,h/2-2,w,4);g.fillStyle=palette['accent-bright'];g.fillRect(0,h/2-2,w*position,4);$('wave').setAttribute('aria-valuenow',String(Math.round(position*100)));$('wave').setAttribute('aria-valuetext',time(media.currentTime)+' of '+time(duration));}return;}const values=result.waveform,position=Math.max(0,Math.min(1,media.currentTime/result.duration));const count=Math.min(values.length,Math.max(1,Math.floor(w/9))),max=Math.max(.02,...values);for(let i=0;i<count;i++){const a=Math.floor(i*values.length/count),b=Math.max(a+1,Math.floor((i+1)*values.length/count));let peak=0;for(let n=a;n<b;n++)peak=Math.max(peak,values[n]);const height=Math.max(4,peak/max*(h-8)),x=(i+.5)*w/count;g.fillStyle=x/w<=position?palette['accent-bright']:palette.future;g.beginPath();g.roundRect(x-3,h/2-height/2,6,height,3);g.fill();}g.strokeStyle=palette.accent;g.lineWidth=2;g.beginPath();g.moveTo(position*w,5);g.lineTo(position*w,h-5);g.stroke();$('wave').setAttribute('aria-valuenow',String(Math.round(position*100)));$('wave').setAttribute('aria-valuetext',time(media.currentTime)+' of '+time(result.duration));}
function chordNotes(e=result?.chords[current]){const p=e?parts(e.chord):null;if(!p)return [];const notes=(intervals[p.quality]||[]).map(n=>(n+p.root)%12);if(p.bass!==null&&!notes.includes(p.bass))notes.push(p.bass);return notes;}
function fingering(notes,root){if(notes.length>6)return null;const tuning=[4,9,2,7,11,4],target=new Set(notes);let best=null,cost=Infinity;for(let base=0;base<=9;base++){const choices=tuning.map(note=>[-1,...Array.from({length:5},(_,n)=>base+n).filter(f=>target.has((note+f)%12))]);function visit(i,frets){if(i===6){const sounding=frets.map((f,n)=>f<0?-1:(tuning[n]+f)%12).filter(n=>n>=0);if(sounding.length<3||!notes.every(n=>sounding.includes(n)))return;const positive=frets.filter(f=>f>0);if(positive.length&&Math.max(...positive)-Math.min(...positive)>4)return;const score=positive.reduce((a,b)=>a+b,0)+frets.filter(f=>f<0).length*3+(sounding[0]===root?0:4);if(score<cost){cost=score;best=frets.slice();}return;}for(const value of choices[i])visit(i+1,[...frets,value]);}visit(0,[]);}return best;}
function drawDiagram(id,e){const {g,w,h}=canvas(id);const p=e?parts(e.chord):null,notes=chordNotes(e);$('diagram-label').textContent=e?pretty(e.chord):'—';$('diagram-note').textContent='';if(!p||!notes.length)return;g.font='12px system-ui';g.textAlign='center';if(kind==='piano'){const whites=[5,7,9,11,12,14,16,17,19,21,23],blacks=[6,8,10,13,15,18,20,22],gaps=[1,2,3,5,6,8,9,10],kw=(w-12)/whites.length,top=5,bottom=h-30;const extensions={'9':[0,4,7,10,14],maj9:[0,4,7,11,14],min9:[0,3,7,10,14],'11':[0,4,7,10,14,17],'13':[0,4,7,10,14,17,21],min11:[0,3,7,10,14,17],min13:[0,3,7,10,14,17,21],maj13:[0,4,7,11,14,17,21],'7sus4':[0,5,7,10]};const positions=new Set((extensions[p.quality]||intervals[p.quality]||[]).map(n=>{let v=(p.root<5?p.root+12:p.root)+n;while(v<5)v+=12;while(v>=24)v-=12;return v;}));if(p.bass!==null&&!notes.slice(0,-1).includes(p.bass))positions.add(p.bass<5?p.bass+12:p.bass);whites.forEach((note,i)=>{const x=6+i*kw;g.fillStyle='#eeeeee';g.fillRect(x,top,kw-1,bottom-top);if(positions.has(note)){g.fillStyle=palette['accent-bright'];g.beginPath();g.arc(x+kw/2,bottom-16,Math.min(8,kw*.29),0,Math.PI*2);g.fill();}});blacks.forEach((note,i)=>{const x=6+gaps[i]*kw-.32*kw;g.fillStyle='#090f14';g.fillRect(x,top,.64*kw,(bottom-top)*.6);if(positions.has(note)){g.fillStyle=palette['accent-bright'];g.beginPath();g.arc(x+.32*kw,top+(bottom-top)*.48,Math.min(6,kw*.23),0,Math.PI*2);g.fill();}});g.fillStyle=palette.muted;g.fillText(notes.map(n=>roots[n]).join('   '),w/2,h-6);$('diagram-note').textContent='Suggested piano voicing · each marked key is played once.';}else{const frets=fingering(notes,p.root);if(!frets){$('diagram-note').textContent='No compact guitar shape found for this voicing. Use the piano notes.';return;}const positive=frets.filter(f=>f>0),start=positive.length&&Math.max(...positive)>4?Math.min(...positive):1,dx=Math.min(40,(w-80)/5),left=(w-5*dx)/2,top=30,dy=(h-55)/4;g.strokeStyle=palette.muted;g.lineWidth=1;for(let i=0;i<=4;i++){g.beginPath();g.moveTo(left,top+i*dy);g.lineTo(left+5*dx,top+i*dy);g.stroke();}frets.forEach((f,i)=>{const x=left+i*dx;g.beginPath();g.moveTo(x,top);g.lineTo(x,top+4*dy);g.stroke();g.fillStyle=palette.text;g.fillText(f<0?'×':f===0?'○':String(f),x,top-10);if(f>0){g.fillStyle=palette['accent-bright'];g.beginPath();g.arc(x,top+(f-start+.5)*dy,5,0,Math.PI*2);g.fill();}});g.fillStyle=palette.muted;g.fillText(String(start),left-20,top+dy/2);$('diagram-note').textContent='E–A–D–G–B–e standard tuning. Fret numbers shown above; × means mute. Suggested voicing, not a detected guitar fingering.';}}
function timeline(){const list=$('timeline-rows');list.replaceChildren();if(!result)return;const limit=Math.min(1000,result.chords.length);for(let i=0;i<limit;i++){const e=result.chords[i];if(e.chord==='X')continue;const b=document.createElement('button');b.className='timeline-chord';const label=document.createElement('b');label.textContent=pretty(e.chord);const t=document.createElement('span');t.textContent=`${time(e.start)} – ${time(e.end)}${e.edited?' · edited':''}`;b.append(label,t);b.onclick=()=>seekChord(e);list.append(b);}if(limit<result.chords.length){const info=document.createElement('p');info.textContent='Showing the first 1,000 segments. Export includes the complete timeline.';list.append(info);}}
function updatePlayback(){$('previous').setAttribute('aria-label',result?'Previous chord':'Back 10 seconds');$('next').setAttribute('aria-label',result?'Next chord':'Forward 10 seconds');if(loopEnd!==null&&media.currentTime>=loopEnd&&!media.paused)media.currentTime=loopStart;const index=indexAt(media.currentTime);if(index!==current){current=index;cards();diagram();}if($('position').textContent!==time(media.currentTime))$('position').textContent=time(media.currentTime);const playState=media.paused?'play':'pause';if($('play').dataset.state!==playState){$('play').dataset.state=playState;$('play').innerHTML=icon(playState);}$('play').setAttribute('aria-label',media.paused?'Play':'Pause');wave();paintFlow();}
function applyResult(value){result=value;flowMap=BlazeFlow.build(result,result?.rhythm_correction);flowGroup=-1;populateRhythm();current=indexAt(media.currentTime);$('empty-wave').hidden=!!result||!!sourceName;$('key').textContent=(result?.key||'—');$('bpm').textContent=result?.rhythm_correction?.mode==='grid'?result.rhythm_correction.bpm+' (manual)':(result?.tempo_bpm?String(result.tempo_bpm):'—');$('duration').textContent=time(result?.duration||media.duration);$('edit').disabled=!result;$('export-json').disabled=!result;$('export-csv').disabled=!result;$('model-info').textContent=result?`${result.model.name} · ${result.analysis_seconds}s analysis · N: no chord · results and corrections saved locally`:'Ready for local music analysis.';cards();wave();diagram();timeline();songDetails();paintFlow();}
async function refresh(){clearTimeout(studioTimer);try{const state=await api('/api/state');if(firstStudioState){firstStudioState=false;if(state.name)showSection('studio');}busy=state.busy;$('status').textContent=state.progress;$('cancel').hidden=!busy;$('analyze').disabled=busy||analysisRequested||!state.name;$('import').disabled=busy||importing;if(state.name!==sourceName){sourceName=state.name;if(!state.result&&result)applyResult(null);$('empty-wave').hidden=!!sourceName;$('error').hidden=true;$('filename').textContent=sourceName||'Your music, on your device';media.pause();media.src='/media?token='+encodeURIComponent(token)+'&revision='+mediaSession+'-'+(++mediaRevision);media.classList.toggle('audio-only',!/\.(mp4|webm|mkv|mov|m4v)$/i.test(sourceName));media.controls=!media.classList.contains('audio-only');media.load();loopStart=loopEnd=null;updateLoop();$('preview-title').textContent=media.classList.contains('audio-only')?'Audio':'Video Preview';$('audio-preview').hidden=!media.classList.contains('audio-only');$('audio-preview').textContent='♫ Local audio · '+sourceName;}const identity=state.result?JSON.stringify([state.result.analysis_id,state.result.analysis_seconds,state.result.chords.filter(e=>e.edited),state.result.rhythm_correction]):'';if(identity!==lastResultId){lastResultId=identity;applyResult(state.result);}if(!state.name)media.classList.add('audio-only');if(state.error)failure(Error(state.error));}catch(error){failure(error);}studioTimer=setTimeout(refresh,750);}
async function importFile(file){if(!file||busy||importing)return;try{importing=true;$('import').disabled=true;$('error').hidden=true;$('status').textContent='Reading your file into the local workspace…';media.pause();media.removeAttribute('src');media.load();const response=await fetch('/api/import',{method:'POST',headers:{'X-Blaze-Token':token,'X-File-Name':encodeURIComponent(file.name)},body:file});const answer=await response.json();if(!response.ok)throw Error(answer.error);sourceName='';lastResultId='';applyResult(null);await refresh();}catch(error){failure(error);}finally{importing=false;$('import').value='';$('import').disabled=busy;}}
$('import').onchange=event=>importFile(event.target.files[0]);
let analysisRequested=false;
$('analyze').onclick=async()=>{if(busy||analysisRequested||!sourceName)return;analysisRequested=true;$('analyze').disabled=true;try{$('error').hidden=true;await api('/api/analyze',{model:$('model').value});await refresh();}catch(error){failure(error);}finally{analysisRequested=false;$('analyze').disabled=busy||!sourceName;}};
$('cancel').onclick=()=>api('/api/cancel',{}).catch(failure);
$('play').onclick=()=>{if(!sourceName)return;$('error').hidden=true;return media.paused?media.play().catch(failure):media.pause();};
$('previous').onclick=()=>{if(!result)return seek(media.currentTime-10);const index=Math.max(0,current-(current>=0&&media.currentTime-result.chords[current].start<.3?1:0));seekChord(result.chords[index]);};
$('next').onclick=()=>result?seekChord(result.chords[Math.min(result.chords.length-1,current+1)]):seek(media.currentTime+10);
$('repeat').onchange=()=>{media.loop=$('repeat').checked;};
$('speed').onchange=()=>{media.playbackRate=Number($('speed').value);media.preservesPitch=true;};
media.ontimeupdate=updatePlayback;media.onplay=()=>{updatePlayback();startFlow();};media.onpause=()=>{stopFlow();updatePlayback();};media.onseeking=updatePlayback;media.onseeked=updatePlayback;media.onratechange=updatePlayback;media.onended=()=>{stopFlow();if(loopEnd!==null){seek(loopStart);media.play().catch(failure);}else updatePlayback();};media.onloadedmetadata=()=>{$('duration').textContent=time(result?.duration||media.duration);updatePlayback();};
media.onwaiting=()=>{stopFlow();updatePlayback();};media.onplaying=()=>{updatePlayback();startFlow();};
media.onerror=()=>{if(!sourceName)return;stopFlow();failure(Error('This browser cannot play the selected format. Chord analysis can still read supported audio/video through the local decoder.'));};
let scrubbing=false;
function scrubAt(event){const duration=result?.duration||media.duration;if(!Number.isFinite(duration)||!sourceName)return;const rect=$('wave').getBoundingClientRect();if(rect.width)seek((event.clientX-rect.left)/rect.width*duration);}
$('wave').onpointerdown=event=>{if(event.button!==0||!sourceName||!Number.isFinite(media.duration))return;scrubbing=true;$('wave').setPointerCapture(event.pointerId);scrubAt(event);};
$('wave').onpointermove=event=>{if(scrubbing)scrubAt(event);};
$('wave').onpointerup=event=>{if(!scrubbing)return;scrubAt(event);scrubbing=false;if($('wave').hasPointerCapture(event.pointerId))$('wave').releasePointerCapture(event.pointerId);};
$('wave').onpointercancel=$('wave').onlostpointercapture=()=>{scrubbing=false;};
$('wave').onkeydown=event=>{let t=null;if(event.key==='ArrowLeft')t=media.currentTime-5;if(event.key==='ArrowRight')t=media.currentTime+5;if(event.key==='Home')t=0;if(event.key==='End')t=media.duration;if(t!==null){event.preventDefault();seek(t);}};
function shift(delta){amount=Math.max(-12,Math.min(12,amount+delta));$('shift').textContent=amount>0?'+'+amount:String(amount);cards();diagram();timeline();songDetails();flowGroup=-1;paintFlow();}
$('down').onclick=()=>shift(-1);$('up').onclick=()=>shift(1);$('reset').onclick=()=>{amount=0;shift(0);};
$('piano').onclick=()=>{kind='piano';$('instrument').value='piano';$('piano').classList.add('selected');$('guitar').classList.remove('selected');$('piano').setAttribute('aria-pressed','true');$('guitar').setAttribute('aria-pressed','false');diagram();};$('guitar').onclick=()=>{kind='guitar';$('instrument').value='guitar';$('guitar').classList.add('selected');$('piano').classList.remove('selected');$('guitar').setAttribute('aria-pressed','true');$('piano').setAttribute('aria-pressed','false');diagram();};
for(const type of ['json','csv'])$('export-'+type).onclick=()=>{const link=document.createElement('a');link.href=`/api/export?format=${type}&transpose=${amount}&token=${encodeURIComponent(token)}`;link.download=`Blaze-chords.${type}`;link.click();};
$('edit').onclick=()=>{if(!result||current<0)return;$('edited-chord').value=result.chords[current].chord;$('edit-error').textContent='';$('edit-dialog').showModal();};
$('save-edit').onclick=async event=>{event.preventDefault();try{await api('/api/edit',{index:current,chord:$('edited-chord').value});lastResultId='';$('edit-dialog').close();}catch(error){$('edit-error').textContent=error.message;}};
$('clear-cache').onclick=()=>api('/api/clear-cache',{}).then(()=>{$('status').textContent='Analysis cache cleared. Saved corrections are kept.';}).catch(failure);
window.onresize=()=>{document.body.classList.toggle('large-type',parseFloat(getComputedStyle(document.documentElement).fontSize)>18);syncSidePanel();wave();diagram();paintFlow();};document.addEventListener('visibilitychange',()=>{if(document.hidden)media.pause();});cards();refresh();

function showSection(section){
    if(typeof section==='boolean')section=section?'studio':'downloads';
    document.body.classList.toggle('studio-active',section==='studio');
    for(const name of ['downloads','library','studio']){
        $(name+'-panel').hidden=name!==section;
        const tab=$('tab-'+name);tab.classList.toggle('selected',name===section);
        tab.setAttribute('aria-selected',String(name===section));tab.tabIndex=name===section?0:-1;
    }
    $('section-label').textContent='On your device';
    if(section!=='studio'){media.pause();stopFlow();}
    requestAnimationFrame(()=>{wave();diagram();paintFlow();});
}
for(const name of ['downloads','library','studio'])$('tab-'+name).onclick=()=>showSection(name);
document.querySelector('.app-tabs').addEventListener('keydown',event=>{
    const tabs=[...document.querySelectorAll('[role="tab"]')];
    let index=tabs.indexOf(document.activeElement);
    if(index<0)return;
    if(event.key==='ArrowRight'||event.key==='ArrowDown')index=(index+1)%tabs.length;
    else if(event.key==='ArrowLeft'||event.key==='ArrowUp')index=(index+tabs.length-1)%tabs.length;
    else if(event.key==='Home')index=0;else if(event.key==='End')index=tabs.length-1;else return;
    event.preventDefault();tabs[index].click();tabs[index].focus();
});
$('download-mode').onchange=()=>{const video=$('download-mode').value==='video';$('audio-options').hidden=video;$('video-options').hidden=!video;for(const button of document.querySelectorAll('[data-mode]')){const selected=button.dataset.mode===$('download-mode').value;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));}};
function downloadError(error){$('download-error').textContent=error.message;$('download-error').hidden=false;}
let submittingDownload=false,downloadsBusy=false;
$('download-start').onclick=async()=>{
    if(submittingDownload||downloadsBusy)return;
    const urls=$('download-urls').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
    if(!urls.length){downloadError(Error('Paste a link to start downloading.'));$('download-urls').focus();return;}
    submittingDownload=true;$('download-start').disabled=true;$('download-start').textContent='Adding…';
    try{$('download-error').hidden=true;await api('/api/download-start',{urls,mode:$('download-mode').value,format:$('download-format').value,resolution:$('download-resolution').value,playlist:$('download-playlist').checked});await refreshDownloads();}
    catch(error){downloadError(error);}finally{submittingDownload=false;$('download-start').disabled=downloadsBusy;$('download-start').innerHTML=icon('downloads')+'Download';}
};
$('download-stop').onclick=()=>api('/api/download-cancel',{}).catch(downloadError);
$('download-folder').onclick=()=>api('/api/download-folder',{}).catch(downloadError);
$('library-folder').onclick=()=>api('/api/download-folder',{}).catch(error=>{$('library-error').hidden=false;$('library-error').textContent=error.message;});
let downloadsSignature='',downloadTimer,libraryFiles=[],libraryFilter='all',librarySignature=null;
const isVideo=file=>/\.(mp4|mkv|webm|mov|m4v)$/i.test(file.name);
function emptyState(target,title,description,action){
    const box=document.createElement('div');box.className='empty-state';
    const heading=document.createElement('h3');heading.textContent=title;
    const hint=document.createElement('p');hint.textContent=description;box.innerHTML=icon(action?'file':'downloads');box.append(heading,hint);
    if(action){const button=document.createElement('button');button.className='primary';button.textContent='Go to Downloads';button.onclick=()=>showSection('downloads');box.append(button);}
    target.append(box);
}
function renderLibrary(){
    const query=$('library-search').value.trim().toLocaleLowerCase();
    const files=libraryFiles.filter(file=>(libraryFilter==='all'||isVideo(file)===(libraryFilter==='video'))&&file.name.toLocaleLowerCase().includes(query));
    const target=$('download-files');target.replaceChildren();
    $('library-count').textContent=`${files.length} ${files.length===1?'file':'files'}${libraryFiles.length>=200?' · showing the latest 200':''}`;
    if(!files.length){emptyState(target,libraryFiles.length?'No matching files':'Your collection starts here',libraryFiles.length?'Try another search or media type.':'Save a link in Downloads to begin.',!libraryFiles.length);return;}
    for(const file of files){
        const row=document.createElement('div');row.className='download-row library-row';
        const label=document.createElement('span');label.textContent=file.name;label.title=file.id;
        const type=document.createElement('small');type.className='file-type';type.textContent=isVideo(file)?'Video':'Audio';
        const open=document.createElement('button');open.textContent='Open in Studio';open.setAttribute('aria-label','Open '+file.name+' in Studio');
        open.onclick=async()=>{open.disabled=true;$('library-error').hidden=true;try{await api('/api/download-select',{id:file.id});sourceName='';lastResultId='';applyResult(null);showSection('studio');await refresh();}catch(error){$('library-error').hidden=false;$('library-error').textContent=error.message;}finally{open.disabled=false;}};
        const mark=document.createElement('div');mark.className='file-mark';mark.innerHTML=icon(isVideo(file)?'video':'file');row.append(mark,label,type,open);target.append(row);
    }
}
$('library-search').oninput=renderLibrary;
for(const button of document.querySelectorAll('[data-filter]'))button.onclick=()=>{
    libraryFilter=button.dataset.filter;
    for(const other of document.querySelectorAll('[data-filter]')){const active=other===button;other.classList.toggle('selected',active);other.setAttribute('aria-pressed',String(active));}
    renderLibrary();
};
async function refreshDownloads(){
    clearTimeout(downloadTimer);
    try{
        const state=await api('/api/downloads');
        downloadsBusy=!!state.busy;$('download-start').disabled=downloadsBusy||submittingDownload||!!state.unavailable;
        $('download-stop').hidden=!state.busy;
        $('download-output').textContent=state.unavailable?'Downloading is available in the complete Blaze app.':'Saved to '+state.output;
        $('library-folder').disabled=$('download-folder').disabled=!!state.unavailable;
        const signature=JSON.stringify(state);if(signature===downloadsSignature)return;downloadsSignature=signature;
        const filesSignature=JSON.stringify(state.files||[]);if(filesSignature!==librarySignature){librarySignature=filesSignature;libraryFiles=state.files||[];renderLibrary();}const target=$('download-jobs');target.replaceChildren();
        if(!state.jobs?.length)emptyState(target,'Ready when you are','Add a link above. Your downloads will appear here.');
        for(const job of state.jobs||[]){
            const row=document.createElement('div');row.className='download-row';
            const label=document.createElement('span');label.textContent=job.title||job.url;
            const detail=document.createElement('small');detail.textContent=job.status==='failed'?(job.error||'Download failed'):job.status==='done'?'Complete':job.status==='cancelled'?'Cancelled':`${job.phase||job.status} · ${Math.round(job.progress||0)}% ${job.speed||''}`;
            label.append(detail);row.dataset.status=job.status;
            if(job.status==='downloading'){const progress=document.createElement('progress');progress.max=100;progress.value=job.progress||0;progress.setAttribute('aria-label','Download progress');label.append(progress);}
            row.append(label);target.append(row);
        }
    }catch(error){downloadError(error);}finally{downloadTimer=setTimeout(refreshDownloads,1500);}
}
showSection('downloads');refreshDownloads();

function populateRhythm(){const c=result?.rhythm_correction;$('rhythm-mode').value=c?.mode||'auto';$('rhythm-bpm').value=c?.bpm||result?.tempo_bpm||120;$('rhythm-num').value=c?.numerator||4;$('rhythm-den').value=c?.denominator||4;$('rhythm-offset').value=c?.offset||0;$('rhythm-compound').checked=!!c?.compound;}
function rhythmInputs(){return {mode:$('rhythm-mode').value,bpm:Number($('rhythm-bpm').value),numerator:Number($('rhythm-num').value),denominator:Number($('rhythm-den').value),offset:Number($('rhythm-offset').value),compound:$('rhythm-compound').checked,changes:result?.rhythm_correction?.changes||[]};}
async function saveRhythm(c){if(c?.mode==='auto')c=null;try{if(!result)throw Error('Analyse a recording first.');if(c){BlazeFlow.validateCorrection(c);BlazeFlow.build(result,c);}await api('/api/rhythm',{correction:c});lastResultId='';$('rhythm-message').textContent=c?'Rhythm correction saved locally. Detected beat timestamps remain preserved.':'Automatic rhythm restored.';await refresh();}catch(error){$('rhythm-message').textContent=error.message;}}
$('rhythm-align').onclick=()=>{$('rhythm-offset').value=media.currentTime.toFixed(3);};$('rhythm-save').onclick=()=>saveRhythm(rhythmInputs());$('rhythm-reset').onclick=()=>saveRhythm(null);
$('rhythm-change').onclick=()=>{const selected=rhythmInputs(),c=result?.rhythm_correction?JSON.parse(JSON.stringify(result.rhythm_correction)):null;if(!c||c.mode==='unknown')return $('rhythm-message').textContent='Save the initial meter and rhythm grid first.';const t=Number(media.currentTime.toFixed(3));c.changes=[...(c.changes||[]).filter(e=>Math.abs(e.time-t)>.001),{time:t,numerator:selected.numerator,denominator:selected.denominator,compound:selected.compound}].sort((a,b)=>a.time-b.time);saveRhythm(c);};
function renderTimelineCells(node){
 const list=$('bar-flow'),first=Math.max(0,Math.floor(list.scrollLeft/node.cellWidth)-8),last=Math.min(node.layout.rows.length,first+Math.ceil(list.clientWidth/node.cellWidth)+20);
 if(first===node.visibleFirst&&last===node.visibleLast)return;
 node.visibleFirst=first;node.visibleLast=last;node.cells.replaceChildren();
 for(let i=first;i<last;i++){
  const cell=node.layout.rows[i],button=document.createElement('button');
  button.className='reference-cell';button.style.left=i*node.cellWidth+'px';button.style.width=node.cellWidth+'px';button.dataset.cell=i;
  const names=cell.labels.map(e=>pretty(e.chord));
  for(let k=0;k<cell.labels.length;k++){
   const event=cell.labels[k],label=document.createElement('span');label.className='reference-label';label.textContent=pretty(event.chord);label.dataset.time=event.time;
   const left=cell.labels.length>1?8:Math.min(event.offset*node.cellWidth,20);label.style.left=left+'px';
   label.style.top=cell.labels.length>1?(14+k*26)+'px':'50%';
   label.style.fontSize=cell.labels.length>1?'22px':Math.max(22,Math.min(38,(node.cellWidth-left-10)/(label.textContent.length*.58)))+'px';button.append(label);
  }
  button.title=(names.length?names.join(' → ')+' · ':'')+time(cell.start)+' — '+time(cell.end);
  button.setAttribute('aria-label','Seek to '+time(cell.start)+(names.length?' · '+names.join(', '):''));
  button.onclick=ev=>{const r=button.getBoundingClientRect();seek(BlazeFlow.cellTime(node.layout,i+(ev.detail?Math.max(0,Math.min(1,(ev.clientX-r.left)/r.width)):0)));};
  button.oncontextmenu=ev=>{ev.preventDefault();seek(cell.start);$('edit').click();};node.cells.append(button);
 }
}
function paintFlow(){
 const state=BlazeFlow.state(flowMap,media.currentTime),list=$('bar-flow');
 if(!result){list.replaceChildren();$('flow-status').textContent='Import a recording and analyse its chords.';return;}
 if(flowGroup!==0){
  flowGroup=0;list.classList.add('reference-timeline');list.replaceChildren();
  const layout=BlazeFlow.cells(flowMap,result.beats),cellWidth=100,rail=document.createElement('div'),cells=document.createElement('div');
  rail.className='reference-rail';rail.style.width=Math.max(cellWidth,layout.rows.length*cellWidth)+'px';cells.className='reference-cells';rail.append(cells);
  const track=document.createElement('div');track.className='reference-progress';track.tabIndex=0;track.setAttribute('role','slider');track.setAttribute('aria-label','Seek through chord timeline');track.setAttribute('aria-valuemin','0');track.setAttribute('aria-valuemax','100');
  const fill=document.createElement('div');fill.className='reference-fill';track.append(fill);rail.append(track);
  track.onclick=ev=>{const r=rail.getBoundingClientRect();seek(BlazeFlow.cellTime(layout,(ev.clientX-r.left)/cellWidth));};
  track.onkeydown=ev=>{let t=null;if(ev.key==='Home')t=0;if(ev.key==='End')t=result.duration;if(ev.key==='ArrowLeft')t=media.currentTime-.25;if(ev.key==='ArrowRight')t=media.currentTime+.25;if(t!==null){ev.preventDefault();seek(t);}};
  for(const bar of BlazeFlow.markers(flowMap,result.beats).bars){const line=document.createElement('div');line.className='reference-bar';line.style.left=BlazeFlow.cellPosition(layout,bar.time)*cellWidth+'px';line.title=bar.label;rail.append(line);}
  const head=document.createElement('div');head.className='reference-head';rail.append(head);list.append(rail);
  const node={layout,cellWidth,rail,cells,track,fill,head,visibleFirst:-1,visibleLast:-1,lastTime:null};flowNodes=[node];
  list.onscroll=()=>{renderTimelineCells(node);highlightTimelineCell(node,media.currentTime);};list.scrollLeft=0;
 }
 const node=flowNodes[0],x=BlazeFlow.cellPosition(node.layout,state.time)*node.cellWidth;
 node.head.style.left=x+'px';node.fill.style.width=x+'px';node.track.setAttribute('aria-valuenow',String(Math.round(state.time/result.duration*100)));node.track.setAttribute('aria-valuetext',time(state.time));
 if(node.lastTime!==state.time){list.scrollLeft=Math.max(0,x-list.clientWidth*.25);node.lastTime=state.time;}
 renderTimelineCells(node);highlightTimelineCell(node,state.time);
 const m=flowMap.measures[state.measure];
 $('flow-status').textContent=state.ended?'End of recording':m.kind==='automatic'?`Bar ${m.barNumber} · ${m.numerator} beats · automatic`:m.kind==='unknown'?(result.rhythm_model?'Beat spacing detected · meter not resolved here':node.layout.timed?'Time cells · meter unconfirmed':'Beat spacing · meter unconfirmed'):m.kind==='lead-in'?'Before first downbeat':`Bar ${state.measure-(flowMap.barStart||0)+1} · ${m.numerator}/${m.denominator}`;
 $('meter').textContent=m.kind==='automatic'?m.numerator+' beats/bar':m.kind==='unknown'||m.kind==='lead-in'?'Unknown':m.numerator+'/'+m.denominator;
 $('flow-beat').textContent=state.beat?`Beat ${state.beat.index+1} / ${state.beat.total}`:time(state.time);
 $('flow-countdown').textContent=state.next<0?'No further change':`in ${state.seconds.toFixed(1)}s`;
 const announcement=JSON.stringify([state.chord,state.measure,state.ended]);if(announcement!==flowAnnouncement){flowAnnouncement=announcement;$('flow-announcement').textContent=$('now-label').textContent+', '+$('flow-status').textContent;}
}
function highlightTimelineCell(node,time){const active=time>=node.layout.duration?-1:Math.floor(BlazeFlow.cellPosition(node.layout,time));for(const cell of node.cells.children)cell.classList.toggle('active',Number(cell.dataset.cell)===active);}
function stopFlow(){if(flowFrame)cancelAnimationFrame(flowFrame);flowFrame=0;}
function startFlow(){stopFlow();let lastPosition=-1;function frame(timestamp){if(media.paused||media.ended||document.hidden||$('studio-panel').hidden){flowFrame=0;return;}const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;if(media.currentTime!==lastPosition&&(!reduced||timestamp-lastFlowPaint>=100)){updatePlayback();lastFlowPaint=timestamp;lastPosition=media.currentTime;}flowFrame=requestAnimationFrame(frame);}flowFrame=requestAnimationFrame(frame);}

function diagram(){const next=flowMap.nextKnown[current]??-1;const ids=summaryView&&result?[...new Map(result.chords.map((e,i)=>[e.chord,i]).filter(([chord])=>chord!=='X')).values()]:[current,next,next>=0?flowMap.nextKnown[next]:-1];const strip=$('diagram-strip');strip.replaceChildren();strip.classList.toggle('summary-strip',summaryView);for(let k=0;k<ids.length;k++){const e=result?.chords[ids[k]],card=document.createElement('article');card.className='diagram-card'+(k===0&&!summaryView?' current':'');const tag=document.createElement('small');tag.textContent=summaryView?'CHORD':['NOW','NEXT','AFTER'][k];const label=document.createElement('h2');label.textContent=e?pretty(e.chord):'—';const c=document.createElement('canvas');c.id='diagram-'+k;c.setAttribute('aria-label',(e?pretty(e.chord):'No chord')+' '+kind+' diagram');card.append(tag,label,c);strip.append(card);if(e)drawDiagram(c.id,e);}const e=result?.chords[current];$('now-label').textContent=e?pretty(e.chord):'—';$('next-label').textContent=result?.chords[next]?pretty(result.chords[next].chord):'—';}
function songDetails(){const target=$('unique-chords');target.replaceChildren();if(!result)return;for(const e of [...new Map(result.chords.filter(e=>e.chord!=='X').map(e=>[e.chord,e])).values()]){const b=document.createElement('button');b.textContent=pretty(e.chord);b.onclick=()=>seekChord(e);target.append(b);}}
function updateLoop(){$('loop').textContent=loopStart===null?'Loop A–B':loopEnd===null?'Set loop end':'Clear loop';$('loop').classList.toggle('selected',loopStart!==null);$('loop').setAttribute('aria-pressed',String(loopStart!==null));$('loop-status').textContent=loopStart===null?'':loopEnd===null?'Loop start '+time(loopStart)+'. Seek to the end and click Set loop end.':'Loop '+time(loopStart)+' — '+time(loopEnd);}
$('loop').onclick=()=>{if(!Number.isFinite(media.duration))return;if(loopStart===null){loopStart=media.currentTime;media.loop=false;$('repeat').checked=false;}else if(loopEnd===null){if(media.currentTime<=loopStart+.1){$('loop-status').textContent='Seek after the loop start first.';return;}loopEnd=media.currentTime;seek(loopStart);}else loopStart=loopEnd=null;updateLoop();};
$('volume').oninput=()=>media.volume=Number($('volume').value);
$('instrument').onchange=()=>{$( $('instrument').value).click();};
$('animated').onclick=()=>{summaryView=false;$('animated').classList.add('selected');$('summary-view').classList.remove('selected');$('animated').setAttribute('aria-pressed','true');$('summary-view').setAttribute('aria-pressed','false');diagram();};
$('summary-view').onclick=()=>{summaryView=true;$('summary-view').classList.add('selected');$('animated').classList.remove('selected');$('summary-view').setAttribute('aria-pressed','true');$('animated').setAttribute('aria-pressed','false');diagram();};
$('fullscreen').onclick=async()=>{try{const answer=await api('/api/fullscreen',{});if(answer.native)return;if(document.fullscreenElement)await document.exitFullscreen();else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();}catch(error){failure(error);}};
$('repeat').addEventListener('change',()=>{if($('repeat').checked){loopStart=loopEnd=null;updateLoop();}});

diagram();

$('studio-settings').onclick=()=>$('settings-dialog').showModal();
$('close-settings').onclick=()=>$('settings-dialog').close();
for(const section of $('settings-dialog').querySelectorAll('details'))section.addEventListener('toggle',()=>{if(section.open)for(const other of $('settings-dialog').querySelectorAll('details'))if(other!==section)other.open=false;});

const studioSidebar=document.querySelector('.song-sidebar');
function syncSidePanel(){const compact=innerWidth<=1000;$('studio-details').hidden=!compact;const target=compact?$('preview-content'):document.querySelector('.workspace');if(studioSidebar.parentElement!==target)target.append(studioSidebar);}
$('studio-details').onclick=()=>$('preview-dialog').showModal();
$('close-preview').onclick=()=>$('preview-dialog').close();
syncSidePanel();

function icon(name){
    const paths={file:'<path d="M6 3h8l4 4v14H6zM14 3v5h4M10 13h4m-4 4h4"/>',video:'<rect x="3" y="6" width="12" height="12" rx="2"/><path d="m15 10 6-3v10l-6-3"/>',upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>',fullscreen:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',play:'<path d="m9 5 11 7-11 7z" fill="currentColor" stroke="none"/>',pause:'<path d="M9 5v14M16 5v14" stroke-width="4"/>',previous:'<path d="M6 5v14m13-14L8 12l11 7z"/>',next:'<path d="M18 5v14M5 5l11 7-11 7z"/>',downloads:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',library:'<path d="M9 18V5l11-2v13M9 5v5l11-2"/><ellipse cx="6" cy="18" rx="3" ry="2"/><ellipse cx="17" cy="16" rx="3" ry="2"/>',studio:'<path d="M4 10v4m5-10v16m6-13v10m5-7v4"/>',folder:'<path d="M3 7V5h6l2 2h10v13H3z"/>'};
    return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+paths[name]+'</svg>';
}
for(const name of ['downloads','library','studio'])$('tab-'+name).insertAdjacentHTML('afterbegin',icon(name));
for(const name of ['previous','next'])$(name).innerHTML=icon(name);
$('play').innerHTML=icon('play');
for(const name of ['download-folder','library-folder'])$(name).insertAdjacentHTML('afterbegin',icon('folder'));
$('download-start').insertAdjacentHTML('afterbegin',icon('downloads'));

// Appearance is explicit and follows system changes without animating the whole canvas.
function applyAppearance(value){
    document.body.classList.toggle('large-type',parseFloat(getComputedStyle(document.documentElement).fontSize)>18);
    const choice=['light','dark'].includes(value)?value:'system';
    document.documentElement.dataset.appearance=choice;$('appearance').value=choice;
    palette=readPalette();wave();diagram();paintFlow();
}
applyAppearance(document.documentElement.dataset.appearance);
let appearanceSave=Promise.resolve();
$('appearance').onchange=()=>{const choice=$('appearance').value;applyAppearance(choice);$('appearance-message').textContent='';appearanceSave=appearanceSave.then(()=>api('/api/appearance',{appearance:choice})).catch(()=>{$('appearance-message').textContent='This appearance could not be saved. Try again.';});};
const systemAppearance=matchMedia('(prefers-color-scheme: dark)');
const refreshAppearance=()=>{if(document.documentElement.dataset.appearance==='system')applyAppearance('system');};
if(systemAppearance.addEventListener)systemAppearance.addEventListener('change',refreshAppearance);else systemAppearance.addListener(refreshAppearance);
$('app-settings').onclick=()=>$('settings-dialog').showModal();
for(const button of document.querySelectorAll('[data-mode]'))button.onclick=()=>{$('download-mode').value=button.dataset.mode;$('download-mode').onchange();};
$('download-mode').onchange();
$('fullscreen').innerHTML=icon('fullscreen');
document.querySelector('label[for="import"]').insertAdjacentHTML('afterbegin',icon('upload'));
$('analyze').insertAdjacentHTML('afterbegin',icon('studio'));
for(const button of document.querySelectorAll('[data-mode]'))button.insertAdjacentHTML('afterbegin',icon(button.dataset.mode==='audio'?'library':'video'));
// Keyboard shortcuts preserve normal editing and control activation.
document.addEventListener('keydown',event=>{
    if(event.isComposing||event.altKey||document.querySelector('dialog[open]'))return;
    const key=event.key.toLowerCase(),command=event.ctrlKey||event.metaKey;
    if(command&&key==='l'){event.preventDefault();showSection('downloads');$('download-urls').focus();}
    else if(command&&key==='f'){event.preventDefault();showSection('library');$('library-search').focus();}
    else if(command&&key==='o'){event.preventDefault();showSection('studio');if(!busy&&!importing)$('import').click();}
    else if(!command&&event.code==='Space'&&!$('studio-panel').hidden&&!event.target.closest('button,input,textarea,select,summary,a,[contenteditable]')&&!document.querySelector('dialog[open]')){event.preventDefault();$('play').click();}
});
$('studio-panel').addEventListener('dragover',event=>{if([...event.dataTransfer.types].includes('Files')){event.preventDefault();event.dataTransfer.dropEffect=busy||importing?'none':'copy';}});
$('studio-panel').addEventListener('drop',event=>{if(!event.dataTransfer.files.length)return;event.preventDefault();if(busy||importing)return;importFile(event.dataTransfer.files[0]);});
// A URL failure is cleared when the user begins correcting it.
$('download-urls').addEventListener('input',()=>{$('download-error').hidden=true;});
