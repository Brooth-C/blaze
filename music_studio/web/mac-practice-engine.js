/* Practice state over the existing authenticated server and single media player. */
(() => {
 'use strict';
 if(document.documentElement.dataset.presentation!=='mac')return;
 const player=document.getElementById('media'),host=document.getElementById('studio-panel');
 let peaks=null,tracks=[],selected='source',sessionJob='',sessionTitle='',revision=-1,pending=false,loading=false,controller=null,signature='',generation=0,stopped=false;
 let guide=null,guideIdentity=null;
 const labels={source:'Original',piano:'Piano',accompaniment:'Backing',vocals:'Vocals',drums:'Drums',bass:'Bass',guitar:'Guitar',strings:'Strings',brass:'Brass',synths:'Synths',other:'Other'};
 const duration=()=>Number.isFinite(player.duration)?player.duration:Number(peaks?.duration)||0;
 const title=value=>String(value||'').replace(/\.[a-z0-9]{2,5}$/i,'');
 async function sync(){
  if(stopped||host.hidden)return;
  const stems=window.BlazeMacStems?.snapshot()||{},key=JSON.stringify([sourceRevision,sourceName,stems.status,stems.jobId]);
  if(result&&result!==guideIdentity){guide=result;guideIdentity=result;}
  if(key===signature)return;signature=key;const epoch=++generation;controller?.abort();controller=new AbortController();
  const changed=revision!==sourceRevision;revision=sourceRevision;
  if(changed){peaks=null;tracks=[];selected='source';guide=result||null;guideIdentity=result;sessionTitle=title(sourceName);}
  if(!sourceName||!Number.isSafeInteger(revision))return;
  const expected=revision;loading=true;
  try{
   let response;
   const deadline=performance.now()+90000;
   for(let attempt=0;performance.now()<deadline;attempt++){
    response=await fetch('/api/studio-waveform?sourceRevision='+expected,{headers:{'X-Blaze-Token':token},signal:controller.signal});
    if(response.ok||![409,503].includes(response.status))break;
    await new Promise(resolve=>setTimeout(resolve,Math.min(100*2**Math.min(attempt,4),1000)));if(epoch!==generation)return;
   }
   if(!response.ok)throw Error('Waveform unavailable. Playback is still available.');
   const data=await response.json();if(epoch!==generation||expected!==sourceRevision)return;
   peaks=data;sessionJob=data.stemJobId||'';selected=data.selectedStem||'source';
   const session=stems.sessions?.find(row=>row.jobId===sessionJob);
   sessionTitle=title(session?.sourceName||sourceName);
   tracks=session?[{id:'source',label:'Original',jobId:sessionJob,filename:session.original?.filename},...session.stems.map(row=>({...row,label:labels[row.id]||row.label,jobId:sessionJob}))]:[{id:'source',label:'Original',jobId:null}];
  }catch(failure){if(failure.name!=='AbortError'&&epoch===generation)console.warn('Practice waveform:',failure.message);}
  finally{if(epoch===generation)loading=false;}
 }
 async function select(jobId,stem){
  if(pending||analysisBlocksSelection()||importing)return;
  const session=window.BlazeMacStems?.snapshot().sessions?.find(row=>row.jobId===jobId);
  if(!session||!(stem==='source'||session.stems.some(row=>row.id===stem)))throw Error('Prepare the piano and backing tracks first.');
  if(sessionJob===jobId&&selected===stem)return;
  pending=true;
  const position=Number(player.currentTime)||0,rate=player.playbackRate,playing=!player.paused;
  const range=loopEnd!==null?[loopStart,loopEnd]:null;
  const previousGuide=guide;
  try{
   window.BlazeDesktop.cancelPreparation();await api('/api/stems-select',{jobId,stem,sourceRevision});
   await window.BlazeMac.importCompleted();signature='';await sync();
   if(player.readyState<1)await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>finish(Error('The selected audio did not load.')),15000);
    const ready=()=>finish(),failed=()=>finish(Error('The selected audio could not play.'));
    function finish(error){clearTimeout(timeout);player.removeEventListener('loadedmetadata',ready);player.removeEventListener('error',failed);error?reject(error):resolve();}
    player.addEventListener('loadedmetadata',ready,{once:true});player.addEventListener('error',failed,{once:true});
   });
   selected=stem;sessionJob=jobId;guide=previousGuide||result;
   player.preservesPitch=true;player.playbackRate=rate;if(range){loopStart=range[0];loopEnd=range[1];player.loop=false;updateLoop();}
   player.currentTime=Math.min(position,Math.max(0,duration()-.01));if(playing)await player.play();
  }finally{pending=false;}
 }
 const commands={
  practiceTrack:select,
  import:()=>window.BlazeMac.action('import'),browse:()=>window.BlazeMac.navigate('explore'),
  play:()=>player.paused?player.play():player.pause(),stop:()=>{player.pause();player.currentTime=0;},
  seek:value=>{if(sourceName&&!pending)player.currentTime=Math.max(0,Math.min(duration(),Number(value)||0));},
  rate:value=>{player.preservesPitch=true;player.playbackRate=Math.max(.5,Math.min(1.5,Number(value)||1));},
  volume:value=>{player.volume=Math.max(0,Math.min(1,Number(value)||0));},
  setLoop:(start,end,enabled=true)=>{loopStart=start;loopEnd=end;player.loop=false;if(!enabled){loopStart=loopEnd=null;}updateLoop();},
  clearLoop:()=>{loopStart=loopEnd=null;player.loop=false;updateLoop();},
  analyze:()=>document.getElementById('analyze').click(),cancelAnalysis:()=>document.getElementById('cancel').click()
 };
 const viewState=()=>({tracks,selected,title:sessionTitle,peaks,duration:duration(),loading,pending,enabled:!!sourceName&&!pending,
  loop:loopEnd!==null,loopStart,loopEnd,analysisBusy:busy,analysisTask,
  messageState:document.getElementById('error').hidden?'status':'error',message:document.getElementById('error').textContent,
  practiceGuide:guide||result,practiceChords:guide?.chords||result?.chords||[],chords:result?.chords||[],key:(guide||result)?.key||'—',tempo:(guide||result)?.tempo_bpm});
 const snapshot=()=>({active:!host.hidden,selectedTrack:selected,tracks:tracks.map(row=>({id:row.id,label:row.label})),waveformReady:!!peaks,sourceRevision:revision,sessionTitle,guideReady:!!(guide||result)?.chords?.length});
 window.BlazePracticeEngine={viewState,commands,snapshot};
 // The native presentation adapter consumes this private compatibility name.
 window.BlazeMacStudio=window.BlazePracticeEngine;
 const timer=setInterval(sync,200);void sync();
 window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);controller?.abort();},{once:true});
})();
