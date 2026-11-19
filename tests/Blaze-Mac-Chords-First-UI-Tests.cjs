/* Browser plugin not available. Use Chromium for real authenticated loopback
 * requests, audio playback, and preview-to-final UI behavior. Inference is
 * controlled here; this is a workflow regression, not a model benchmark. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),data=fs.mkdtempSync(path.join(os.tmpdir(),'blaze-chords-first-'));
const fixture=String.raw`
import hashlib,json,math,shutil,signal,sys,threading,time,wave
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import music_studio.server as module
root=Path(sys.argv[1]);source=root/'Practice song.wav';rate=24000
samples=np.arange(rate*30)/rate
audio=(np.sin(samples*2*math.pi*330)*6000).astype('<i2')
with wave.open(str(source),'wb') as out:
    out.setparams((1,2,rate,0,'NONE','not compressed'));out.writeframes(audio.tobytes())
studio=module.Studio(root/'state',shutil.which('ffmpeg') or 'ffmpeg',source)
studio.presentation='mac'
module.ModelBundle=lambda *_:SimpleNamespace(structured=False,metadata={'sha256':'controlled'},manifest={'frontend':{'sha256':'controlled-frontend'}})
class Recognition:
    def __init__(self,*_):self.cancelled=threading.Event()
    def cancel(self):self.cancelled.set()
    def check(self):
        if self.cancelled.is_set():raise module.AnalysisCancelled()
    def analyze(self,source,progress):
        count=root/'analysis.count';count.write_text(str(int(count.read_text())+1 if count.exists() else 1))
        value={'schema_version':1,'engine_version':'overlap1','duration':30,
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'key':'C major','tempo_bpm':None,'analysis_seconds':1.0,
            'model':{'name':'Controlled','sha256':'controlled','frontend_sha256':'controlled-frontend'},
            'beats':[],'chords':[{'start':0,'end':6,'chord':'C:maj'},{'start':6,'end':6.12,'chord':'G:maj'},{'start':6.12,'end':12,'chord':'C:maj'},{'start':12,'end':30,'chord':'G:maj'}]}
        preview=dict(value,analysis_stage='chords',rhythm_status='pending')
        self.chords_ready(preview)
        progress('Finding beats and meter locally · 1 / 1')
        while not (root/'finish-rhythm').exists():
            self.check();time.sleep(.025)
        self.check()
        value.update(tempo_bpm=120,beats=[i*.5 for i in range(60)],chords=[{'start':0,'end':6,'chord':'D:maj'},{'start':6,'end':6.12,'chord':'E:maj'},{'start':6.12,'end':12,'chord':'D:maj'},{'start':12,'end':30,'chord':'G:maj'}])
        return value
module.Analyzer=Recognition
server=module.create_server(studio)
def stop(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
print('http://127.0.0.1:'+str(server.server_port),flush=True)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close();studio.close()
`;
let server,browser,page,stderr='';
async function start(){
 server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',fixture,data],{cwd:root,stdio:['ignore','pipe','pipe']});
 server.stderr.on('data',d=>stderr+=d);
 return new Promise((resolve,reject)=>{let output='';const timeout=setTimeout(()=>reject(Error('Startup timeout: '+stderr)),20000);
  server.stdout.on('data',d=>{output+=d;const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timeout);resolve(match[0]);}});
  server.once('exit',code=>{clearTimeout(timeout);reject(Error('Server exited '+code+': '+stderr));});
 });
}
async function api(route,body){return page.evaluate(async({route,body})=>{
 const token=document.querySelector('meta[name="blaze-token"]').content;
 const response=await fetch(route,{method:body===undefined?'GET':'POST',headers:{'X-Blaze-Token':token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const value=await response.json();if(!response.ok)throw Error(value.error||String(response.status));return value;
},{route,body});}
async function preview(){
 await page.waitForFunction(()=>window.BlazeMacStudio.viewState().analysisBusy&&window.BlazeMacStudio.viewState().analysisTask?.phase==='rhythm'&&document.getElementById('practice-chord-help').textContent==='Chords ready · Finding rhythm…');
 assert.equal(await page.locator('#practice-analyze').textContent(),'Stop rhythm');
 assert.equal((await api('/api/state')).result.rhythm_status,'pending');
}
(async()=>{try{
 const base=await start();browser=await chromium.launch({args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
 page=await browser.newPage({viewport:{width:1440,height:900}});
 const errors=[];page.on('pageerror',error=>errors.push(error.stack));
 await page.goto(base);await page.waitForFunction(()=>window.BlazeMacPractice?.snapshot().visible&&window.BlazeMacStudio.snapshot().waveformReady);
 assert.equal(new URL(page.url()).origin,base);assert.match(await page.title(),/Blaze/);
 await page.locator('#practice-play').click();await page.waitForFunction(()=>!document.getElementById('media').paused);
 await page.locator('#practice-analyze').click();await preview();
 assert.equal(await page.locator('#practice-current-chord strong').textContent(),'C');
 assert.equal(await page.evaluate(()=>window.BlazeMacPractice.snapshot().guideMode),'piano');
 // Piano phrasing holds a tiny passing detection, while Detected retains it.
 await page.evaluate(()=>{document.getElementById('media').pause();window.BlazeMacStudio.commands.seek(6.05);});
 await page.waitForFunction(()=>document.querySelector('#practice-current-chord strong').textContent==='C');
 await page.locator('#practice-guide-detected').click();await page.waitForFunction(()=>document.querySelector('#practice-current-chord strong').textContent==='G');
 await page.locator('#practice-guide-piano').click();await page.waitForFunction(()=>document.querySelector('#practice-current-chord strong').textContent==='C');
 await page.evaluate(()=>window.BlazeMacStudio.commands.seek(11));
 await page.waitForFunction(()=>document.querySelector('#practice-next-chord span').textContent==='Prepare'&&document.querySelector('#practice-next-chord small').textContent==='In 1s');
 assert.equal(await page.locator('#practice-current-chord strong').textContent(),'C','Preparation changed the current chord early');
 await page.evaluate(()=>{window.BlazeMacStudio.commands.rate(.5);window.BlazeMacStudio.commands.seek(10.5);});
 await page.waitForFunction(()=>document.querySelector('#practice-next-chord small').textContent==='In 3s'&&document.querySelector('#practice-next-chord span').textContent==='Up next');
 await page.evaluate(()=>{window.BlazeMacStudio.commands.rate(1);window.BlazeMacStudio.commands.seek(1);document.getElementById('media').play();});
 assert.doesNotMatch(await page.locator('#practice-key-tempo').textContent(),/BPM/,'Preview invented a tempo');
 assert.equal(fs.readdirSync(path.join(data,'state','analyses')).filter(name=>name.endsWith('.json')).length,0,'Incomplete rhythm was cached as final');
 assert.equal(await page.locator('#practice-play').isEnabled(),true);assert.equal(await page.locator('#practice-pitch-up').isEnabled(),true);
 await page.locator('#practice-pitch-up').click();await page.waitForFunction(()=>document.querySelector('#practice-current-chord strong').textContent==='C#');
 assert.equal(await page.locator('#media').evaluate(media=>media.paused),false);
 await page.evaluate(()=>window.BlazeMac.navigate('explore'));await page.locator('#mini-player').waitFor({state:'visible'});
 assert.equal(await page.locator('#media').evaluate(media=>media.paused),false,'Browsing interrupted preview playback');
 await page.evaluate(()=>window.BlazeMac.navigate('studio'));await page.locator('#practice-analyze').waitFor({state:'visible'});
 const playing=await page.locator('#media').evaluate(media=>{
  window.previewMediaReloads=0;media.addEventListener('loadedmetadata',()=>window.previewMediaReloads++);
  return {url:media.currentSrc,position:media.currentTime};
 });
 const evidence=process.env.BLAZE_UI_SCREENSHOT_DIR;
 if(evidence){fs.mkdirSync(evidence,{recursive:true});await page.screenshot({path:path.join(evidence,'chords-ready-rhythm-background.png'),fullPage:false,animations:'disabled'});}
 fs.writeFileSync(path.join(data,'finish-rhythm'),'finish');
 await page.waitForFunction(()=>!window.BlazeMacStudio.viewState().analysisBusy&&document.querySelector('#practice-current-chord strong').textContent==='D#');
 assert.match(await page.locator('#practice-key-tempo').textContent(),/120 BPM/);
 const finished=await page.locator('#media').evaluate(media=>({url:media.currentSrc,position:media.currentTime,paused:media.paused,reloads:window.previewMediaReloads,rate:media.playbackRate}));
 assert.equal(finished.url,playing.url,'Final rhythm replaced the media source');assert.equal(finished.paused,false);assert.equal(finished.reloads,0);
 assert(finished.position>=playing.position,'Final rhythm reset playback');assert.equal(await page.locator('#practice-pitch-value').inputValue(),'1');
 assert.equal((await api('/api/state')).result.analysis_stage,undefined);
 assert.equal(await page.locator('#practice-chord-help').textContent(),'');
 // Final rhythm supplies beat-count preparation, including the loop wrap.
 await page.evaluate(()=>{document.getElementById('media').pause();window.BlazeMacStudio.commands.seek(11.3);});
 await page.waitForFunction(()=>document.querySelector('#practice-next-chord small').textContent==='In 2 beats'&&document.querySelector('#practice-next-chord span').textContent==='Prepare');
 assert.equal(await page.locator('#practice-current-chord strong').textContent(),'D#');
 await page.evaluate(()=>{window.BlazeMacStudio.commands.setLoop(0,13,true);window.BlazeMacStudio.commands.seek(12.5);});
 await page.waitForFunction(()=>document.querySelector('#practice-current-chord strong').textContent==='G#'&&document.querySelector('#practice-next-chord strong').textContent==='D#'&&document.querySelector('#practice-next-chord small').textContent==='In 1 beat');
 if(evidence)await page.screenshot({path:path.join(evidence,'piano-prepare-loop.png'),fullPage:false,animations:'disabled'});
 await page.evaluate(()=>{window.BlazeMacStudio.commands.setLoop(2,13,true);window.BlazeMacStudio.commands.seek(12.5);});
 await page.waitForFunction(()=>window.BlazeMacStudio.viewState().loopStart===2&&document.querySelector('#practice-next-chord strong').textContent==='D#');
 await page.locator('#practice-next-chord').click();
 await page.waitForFunction(()=>Math.abs(document.getElementById('media').currentTime-2)<.1);
 await page.emulateMedia({reducedMotion:'reduce'});
 assert.equal(await page.locator('#practice-next-chord').evaluate(el=>getComputedStyle(el,'::after').display),'none');
 await page.emulateMedia({reducedMotion:'no-preference'});
 await page.evaluate(()=>{window.BlazeMacStudio.commands.clearLoop();window.BlazeMacStudio.commands.seek(1);document.getElementById('media').play();});

 // Stop just the remaining rhythm stage while keeping the early chord guide.
 await api('/api/clear-cache',{});fs.unlinkSync(path.join(data,'finish-rhythm'));
 await page.locator('#practice-analyze').click();await preview();
 await page.locator('#practice-analyze').click();
 await page.waitForFunction(()=>!window.BlazeMacStudio.viewState().analysisBusy&&document.getElementById('practice-chord-help').textContent==='Chords ready · Rhythm stopped');
 assert.equal(await page.locator('#practice-current-chord strong').textContent(),'C#');
 assert.equal(await page.locator('#media').evaluate(media=>media.paused),false);
 assert.equal(fs.readdirSync(path.join(data,'state','analyses')).filter(name=>name.endsWith('.json')).length,0);

 // A task attached to a different selected recording must not label its guide.
 await page.locator('#practice-analyze').click();await preview();
 const other=path.join(data,'Other recording.wav');fs.copyFileSync(path.join(data,'Practice song.wav'),other);
 await page.locator('#import').setInputFiles(other);
 await page.waitForFunction(()=>window.BlazeMacStudio.viewState().analysisBusy&&document.getElementById('practice-title').textContent==='Other recording');
 assert.doesNotMatch(await page.locator('#practice-chord-help').textContent(),/Chords ready|Finding rhythm/);
 assert.equal(await page.locator('#practice-current-chord strong').textContent(),'—','Old preview leaked into a different recording');
 await page.locator('#practice-analyze').click();await page.waitForFunction(()=>!window.BlazeMacStudio.viewState().analysisBusy);
 assert.equal(errors.length,0,errors.join('\n'));console.log('PASS: early chords, background rhythm, piano phrasing/detected, preparation cues, looping, live controls, final refinement, cancellation and source guards.');
}catch(error){console.error(error.stack);if(stderr)console.error(stderr);process.exitCode=1;}
finally{
 await browser?.close();if(server){const child=server;await new Promise(resolve=>{child.once('exit',resolve);child.kill('SIGTERM');});}
 fs.rmSync(data,{recursive:true,force:true});
}})();
