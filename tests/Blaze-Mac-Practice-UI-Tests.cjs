/* Real authenticated server, WAV playback and process restart. Model inference
 * is controlled; this verifies workflow, not separation quality or native UI.
 * Browser plugin absent. Chromium is needed for actual media compatibility. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),data=fs.mkdtempSync(path.join(os.tmpdir(),'blaze-practice-'));
const fixture=String.raw`
import hashlib,json,math,shutil,signal,sys,threading,time,wave
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import music_studio.server as module
from music_studio.stem_jobs import StemJobs
root=Path(sys.argv[1]);source=root/'Practice song.wav';rate=24000
def render(target,frequency):
    t=np.arange(rate*12)/rate
    audio=np.stack([np.sin(t*2*math.pi*frequency)*.15,np.sin(t*2*math.pi*(frequency+3))*.12],axis=1)
    with wave.open(str(target),'wb') as out:
        out.setparams((2,2,rate,0,'NONE','not compressed'));out.writeframes((audio*32767).astype('<i2').tobytes())
if not source.exists():render(source,330)
def counted(name):
    p=root/(name+'.count');p.write_text(str(int(p.read_text())+1 if p.exists() else 1))
studio=module.Studio(root/'state',shutil.which('ffmpeg') or 'ffmpeg',source if sys.argv[2]=='initial' else None)
studio.presentation='mac'
class Controlled:
    def __init__(self,*_):pass
    def separate(self,source,output_dir,progress,cancel_event):
        counted('separation');progress(.1,'Preparing piano')
        for _ in range(25):
            if cancel_event.is_set():return {}
            time.sleep(.1)
        outputs={}
        for name,hz in [('piano',440),('accompaniment',220)]:
            target=output_dir/(name+'.wav');render(target,hz);outputs[name]=target
        return outputs
studio.stems=StemJobs(studio,separator_factory=Controlled)
bundle=SimpleNamespace(structured=False,metadata={'sha256':'controlled'},manifest={'frontend':{'sha256':'controlled-frontend'}})
module.ModelBundle=lambda *_:bundle
class Recognition:
    def __init__(self,*_):self.cancelled=threading.Event()
    def cancel(self):self.cancelled.set()
    def check(self):
        if self.cancelled.is_set():raise module.AnalysisCancelled()
    def analyze(self,source,progress):
        counted('analysis');progress('Reading chords');time.sleep(.5)
        if studio.name=='Broken analysis.wav':raise ValueError('Controlled analysis failure for recovery QA')
        original=hashlib.sha256(source.read_bytes()).hexdigest()==hashlib.sha256((root/'Practice song.wav').read_bytes()).hexdigest()
        return {'schema_version':1,'duration':12,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'key':'C major' if original else 'F major','tempo_bpm':120,'analysis_seconds':.5,
        'model':{'name':'Controlled','sha256':'controlled','frontend_sha256':'controlled-frontend'},
        'beats':[i*.5 for i in range(24)],'chords':[{'start':0,'end':6,'chord':'C:maj' if original else 'F:maj'},{'start':6,'end':12,'chord':'G:maj'}]}
module.Analyzer=Recognition
server=module.create_server(studio)
def stop(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
print('http://127.0.0.1:'+str(server.server_port),flush=True)
try:server.serve_forever()
except KeyboardInterrupt:pass
finally:server.server_close();studio.close()
`;
let server,browser,logs='',base;
async function start(stage){
 logs='';server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',fixture,data,stage],{cwd:root,stdio:['ignore','pipe','pipe']});
 server.stderr.on('data',d=>logs+=d);
 return new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('Startup timeout: '+logs)),20000);
  server.stdout.on('data',d=>{output+=d;const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
  server.once('exit',c=>{clearTimeout(timer);reject(Error('Server exited '+c+': '+logs));});});
}
async function stop(){if(!server)return;const current=server;server=null;await new Promise(resolve=>{current.once('exit',resolve);current.kill('SIGTERM');});}
async function pageFor(url){const page=await browser.newPage({viewport:{width:1440,height:900}});page.errors=[];page.on('pageerror',e=>page.errors.push(e.stack));await page.goto(url);await page.waitForFunction(()=>window.BlazeMacPractice?.snapshot().visible);return page;}
const count=name=>Number(fs.readFileSync(path.join(data,name+'.count'),'utf8'));
async function snapshot(page){return page.evaluate(()=>window.BlazeMacPractice.snapshot());}
async function assertPitch(page,frequency,label){
 const reply=await page.request.get(await page.locator('#media').evaluate(media=>media.currentSrc));assert.equal(reply.status(),200);
 const wav=path.join(data,label+'.wav');fs.writeFileSync(wav,await reply.body());
 const check=spawnSync(process.env.BLAZE_TEST_PYTHON||'python3',['-c',"import sys,subprocess,numpy as np; raw=subprocess.run(['ffmpeg','-v','error','-i',sys.argv[1],'-ac','1','-ar','44100','-f','f32le','-'],check=True,capture_output=True).stdout; x=np.frombuffer(raw,dtype='<f4'); f=np.fft.rfftfreq(len(x),1/44100)[np.argmax(abs(np.fft.rfft(x)))]; assert abs(f-float(sys.argv[2]))<2,(f,sys.argv[2])",wav,String(frequency)],{encoding:'utf8'});assert.equal(check.status,0,check.stderr);
}
async function mode(page,name){
 const id='practice-'+name;
 await page.waitForFunction(id=>{const b=document.getElementById(id);return b&&!b.disabled&&b.getAttribute('aria-busy')!=='true';},id);
 await page.evaluate(id=>document.getElementById(id).click(),id);
 await page.waitForFunction(name=>window.BlazeMacPractice.snapshot().mode===name&&!window.BlazeMacStudio.viewState().pending&&document.getElementById('practice-'+name).getAttribute('aria-busy')!=='true',name);
}
(async()=>{try{
 base=await start('initial');
 // Obscura is the preferred lightweight rendering check when installed.
 const obscura='/workspace/agent-tools/bin/obscura';
 if(fs.existsSync(obscura)){
  const check=spawnSync(obscura,['fetch',base,'--allow-private-network','--timeout','10','--eval','JSON.stringify({title:document.title,practice:!!document.getElementById("practice-workspace"),play:!!document.getElementById("practice-play")})'],{encoding:'utf8',timeout:20000});
  assert.equal(check.status,0,check.stderr);assert.match(check.stdout,/practice[^,]*true/);console.log('Obscura: practice screen renders.');
 }
 browser=await chromium.launch({args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
 let page=await pageFor(base);await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().waveformReady);
 assert.equal(await page.locator('audio,video').count(),1);
 await page.evaluate(()=>window.BlazeMacStudio.commands.seek(2));await page.locator('#practice-set-a').click();
 await page.evaluate(()=>window.BlazeMacStudio.commands.seek(6));await page.locator('#practice-set-b').click();
 await page.locator('[data-rate=".75"]').click();await page.evaluate(()=>window.BlazeMacStudio.commands.seek(3));
 await page.locator('#practice-play').click();await page.waitForFunction(()=>!document.getElementById('media').paused&&document.getElementById('media').currentTime>.1);
 await page.locator('#practice-piano').click();await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().preparing);
 assert.equal(await page.locator('#practice-play').isEnabled(),true,'Preparation blocked playback');
 assert.equal(await page.locator('#mini-player').isVisible(),false,'Practice has duplicate playback controls');
 await page.evaluate(()=>window.BlazeMac.navigate('explore'));await page.locator('#mini-player').waitFor({state:'visible'});
 assert.equal(await page.locator('#mini-play').isEnabled(),true,'Leaving Practice hid background playback');
 assert.equal(await page.locator('#media').evaluate(media=>media.paused),false,'Browsing interrupted playback');
 await page.evaluate(()=>window.BlazeMac.navigate('studio'));await page.locator('#practice-play').waitFor({state:'visible'});
 await page.waitForFunction(()=>!document.getElementById('mini-player').getBoundingClientRect().height);
 await page.locator('#practice-analyze').click();
 await page.waitForFunction(()=>!window.BlazeMacPractice.snapshot().preparing&&window.BlazeMacPractice.snapshot().mode==='piano'&&!window.BlazeMacStudio.viewState().pending);
 assert.equal(await page.evaluate(()=>window.BlazeMacStudio.viewState().loopStart),2,'Preparation lost the active loop start');
 assert.equal(await page.evaluate(()=>window.BlazeMacStudio.viewState().loopEnd),6,'Preparation lost the active loop end');
 await page.waitForFunction(()=>document.querySelector('#practice-current-chord strong').textContent==='C');
 await page.evaluate(()=>document.getElementById('media').pause());
 await page.evaluate(()=>window.BlazeMacStudio.commands.seek(2));await page.locator('#practice-set-a').click();
 await page.evaluate(()=>window.BlazeMacStudio.commands.seek(6));await page.locator('#practice-set-b').click();
 await page.locator('[data-rate=".75"]').click();
 await page.evaluate(()=>window.BlazeMacStudio.commands.seek(4.5));
 for(const name of ['piano','backing','original','backing']){
  await mode(page,name);const s=await snapshot(page);assert.equal(s.rate,.75);assert(s.pitchPreserved);assert.equal(s.loopStart,2);assert.equal(s.loopEnd,6);assert(s.loopEnabled);assert(Math.abs(s.position-4.5)<.25,JSON.stringify(s));
 }
 assert.equal(await page.locator('#practice-advanced,#logic-preview,#blaze-daw').count(),0);
 const originalPlayback=await page.locator('#media').evaluate(media=>media.currentSrc);
 await page.route('**/api/practice-audio?**',route=>route.fulfill({status:404,body:'controlled missing render'}));
 await page.locator('#practice-pitch-up').click();await page.waitForFunction(()=>!window.BlazeMacPractice.snapshot().pitchBusy&&!!window.BlazeMacPractice.snapshot().error);
 await page.unrouteAll({behavior:'wait'});await page.waitForFunction(url=>document.getElementById('media').currentSrc===url&&document.getElementById('media').readyState>=1,originalPlayback);
 assert.equal((await snapshot(page)).transpose,0,'A failed pitch load changed the displayed key');
 for(let step=1;step<=2;step++){
  await page.locator('#practice-pitch-up').click();
  await page.waitForFunction(step=>{const s=window.BlazeMacPractice.snapshot();return s.transpose===step&&!s.pitchBusy;},step);
 }
 assert.match(await page.evaluate(()=>document.getElementById('media').src),/api\/practice-audio/);
 assert.equal(await page.locator('#practice-current-chord strong').innerText(),'D');
 await assertPitch(page,220*2**(2/12),'pitched-backing');
 await mode(page,'piano');await page.waitForFunction(()=>!window.BlazeMacPractice.snapshot().pitchBusy);await assertPitch(page,440*2**(2/12),'pitched-piano');
 await mode(page,'backing');await page.waitForFunction(()=>!window.BlazeMacPractice.snapshot().pitchBusy);await assertPitch(page,220*2**(2/12),'pitched-backing-again');
 // A failed re-pitch after selecting raw audio must reset the displayed key.
 await page.route('**/api/practice-render',route=>route.request().method()==='POST'?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Controlled render failure'})}):route.continue());
 await mode(page,'piano');await page.waitForFunction(()=>!window.BlazeMacPractice.snapshot().pitchBusy&&window.BlazeMacPractice.snapshot().transpose===0);
 await page.unrouteAll({behavior:'wait'});await assertPitch(page,440,'mode-render-failure-raw-piano');
 assert.equal(await page.locator('#practice-current-chord strong').innerText(),'C');
 await page.locator('#practice-pitch-value').selectOption('2');await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().transpose===2&&!window.BlazeMacPractice.snapshot().pitchBusy);
 await page.route('**/api/practice-audio?**',route=>route.fulfill({status:404,body:'controlled missing mode render'}));
 await mode(page,'backing');await page.waitForFunction(()=>!window.BlazeMacPractice.snapshot().pitchBusy&&window.BlazeMacPractice.snapshot().transpose===0&&document.getElementById('media').readyState>=1);
 await page.unrouteAll({behavior:'wait'});await assertPitch(page,220,'mode-load-failure-raw-backing');
 assert.equal(await page.locator('#practice-current-chord strong').innerText(),'C');
 await page.locator('#practice-pitch-value').selectOption('2');await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().transpose===2&&!window.BlazeMacPractice.snapshot().pitchBusy);
 assert.equal((await snapshot(page)).rate,.75);assert.equal((await snapshot(page)).loopStart,2);assert.equal((await snapshot(page)).loopEnd,6);
 await page.locator('#practice-pitch-value').selectOption('-3');await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().transpose===-3&&!window.BlazeMacPractice.snapshot().pitchBusy);await assertPitch(page,220*2**(-3/12),'pitched-direct-choice');
 await page.locator('#practice-pitch-reset').click();await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().transpose===0&&!window.BlazeMacPractice.snapshot().pitchBusy);
 await page.locator('.practice-download summary').click();
 await page.keyboard.press('Escape');assert.equal(await page.locator('.practice-download').evaluate(menu=>menu.open),false);
 assert(await page.locator('.practice-download summary').evaluate(summary=>summary===document.activeElement),'Escape lost download-menu focus');
 await page.locator('.practice-download summary').click();await page.locator('#practice-title').click();
 assert.equal(await page.locator('.practice-download').evaluate(menu=>menu.open),false,'Outside click did not dismiss downloads');
 await page.locator('.practice-download summary').click();
 for(const kind of ['piano','backing','both']){
  const pending=page.waitForEvent('download');await page.locator('#practice-download-'+kind).click();const download=await pending;
  const output=path.join(data,kind+(kind==='both'?'.zip':'.wav'));await download.saveAs(output);assert.equal(await download.failure(),null);assert(fs.statSync(output).size>44);
  await page.waitForFunction(()=>!window.BlazeMacPractice.snapshot().downloadBusy);
 }
 const zipCheck=spawnSync(process.env.BLAZE_TEST_PYTHON||'python3',['-c',"import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert set(z.namelist())=={'Piano.wav','Backing.wav'}",path.join(data,'both.zip')],{encoding:'utf8'});assert.equal(zipCheck.status,0,zipCheck.stderr);
 await page.locator('.practice-download summary').click();
 // Native DOM clicks have no Playwright auto-wait. Track selection can finish
 // before Practice's metadata cleanup re-enables the next mode button.
 let releaseModeMetadata;const modeMetadata=new Promise(resolve=>{releaseModeMetadata=resolve;});
 await page.route('**/api/practice',async route=>{await modeMetadata;await route.continue();});
 try{
  await page.evaluate(()=>document.getElementById('practice-piano').click());
  await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().mode==='piano'&&!window.BlazeMacStudio.viewState().pending);
  assert(await page.locator('#practice-backing').isDisabled(),'The metadata cleanup gap was not exercised');
  const releaseTimer=setTimeout(releaseModeMetadata,250);
  try{await mode(page,'backing');}finally{clearTimeout(releaseTimer);}
 }finally{releaseModeMetadata();await page.unrouteAll({behavior:'wait'});}
 await page.locator('#practice-analyze').click();await page.waitForFunction(()=>!window.BlazeMacStudio.viewState().analysisBusy&&window.BlazeMacStudio.viewState().practiceGuide?.key==='F major');
 await page.evaluate(()=>document.getElementById('media').dispatchEvent(new Event('timeupdate')));
 assert.equal(await page.locator('#practice-current-chord strong').innerText(),'C','Stem analysis replaced the original song guide');
 await page.evaluate(()=>window.BlazeMacStudio.commands.seek(5.8));await page.locator('#practice-play').click();
 await page.waitForFunction(()=>document.getElementById('media').currentTime<3);
 await page.evaluate(()=>{document.getElementById('media').pause();window.BlazeMacStudio.commands.seek(4.5);});
 for(let step=1;step<=2;step++){await page.locator('#practice-pitch-up').click();await page.waitForFunction(step=>window.BlazeMacPractice.snapshot().transpose===step&&!window.BlazeMacPractice.snapshot().pitchBusy,step);}
 await page.locator('#practice-save').click();await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().sessionId&&!window.BlazeMacPractice.snapshot().saving);
 const saved=(await snapshot(page)).sessionId;assert(saved);
 for(const [width,height]of [[1440,900],[1024,700],[570,540]])for(const colorScheme of ['light','dark']){
  await page.setViewportSize({width,height});await page.emulateMedia({colorScheme});
  const clipped=await page.evaluate(()=>['practice-open','practice-play','practice-speed','practice-find'].filter(id=>{const r=document.getElementById(id).getBoundingClientRect();return r.width<=0||r.left<0||r.right>innerWidth+1||r.top<0||r.bottom>innerHeight+1;}));assert.deepEqual(clipped,[],width+' '+colorScheme);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 }
 await page.setViewportSize({width:1440,height:900});
 assert.equal(await page.locator('#practice-workspace').isVisible(),true);assert.equal(await page.locator('#logic-preview,#blaze-daw').count(),0);
 const evidence=process.env.BLAZE_UI_SCREENSHOTS;if(evidence){fs.mkdirSync(evidence,{recursive:true});await page.evaluate(()=>document.querySelector('.practice-content').scrollTop=0);await page.screenshot({path:path.join(evidence,'practice-working.png')});}
 assert.deepEqual(page.errors,[]);await page.close();await stop();
 assert.equal(count('separation'),1);assert.equal(count('analysis'),2);
 base=await start('restart');page=await pageFor(base);
 assert(await page.locator('#practice-empty').isVisible());
 assert(await page.locator('.practice-entry-actions #practice-open').isVisible());
 assert(await page.locator('.practice-entry-actions #practice-find').isVisible());
 assert.equal(await page.locator('.practice-transport').isVisible(),false,'Empty Practice shows inert playback controls');
 if(evidence){await page.locator('[data-practice-id="'+saved+'"]').waitFor();await page.screenshot({path:path.join(evidence,'practice-choose-song.png')});}
 await page.locator('[data-practice-id="'+saved+'"]').click();
 await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().mode==='backing'&&window.BlazeMacPractice.snapshot().loopEnabled&&window.BlazeMacPractice.snapshot().rate===.75);
 const resumed=await snapshot(page);assert.equal(resumed.loopStart,2);assert.equal(resumed.loopEnd,6);assert(Math.abs(resumed.position-4.5)<.25,JSON.stringify(resumed));
 assert.equal(resumed.transpose,2);await assertPitch(page,220*2**(2/12),'resumed-pitched-backing');
 await page.waitForFunction(()=>document.querySelector('#practice-current-chord strong').textContent==='D');
 // Native Open can select the same registered file without changing its ID.
 const reopened=(await snapshot(page)).recordingId;
 await page.evaluate(async id=>{await api('/api/practice-open',{id,sourceRevision});await window.BlazeMac.importCompleted();},saved);
 await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().transpose===0&&!window.BlazeMacPractice.snapshot().pitchBusy&&document.getElementById('media').readyState>=1);
 assert.equal((await snapshot(page)).recordingId,reopened);
 await assertPitch(page,220,'same-recording-reopened-original-key');
 await page.waitForFunction(()=>document.querySelector('#practice-current-chord strong').textContent==='C');
 await page.locator('#practice-play').click();await page.waitForFunction(()=>!document.getElementById('media').paused);await page.locator('#practice-play').click();
 assert.equal(count('separation'),1,'Resume reran separation');assert.equal(count('analysis'),2,'Resume reran analysis');assert.deepEqual(page.errors,[]);
 const previousRevision=await page.evaluate(()=>sourceRevision);
 let releaseMetadata,metadataHeld=false,holdMetadata=true;
 await page.route('**/api/practice',async route=>{
  if(holdMetadata){holdMetadata=false;metadataHeld=true;await new Promise(resolve=>{releaseMetadata=resolve;});}await route.continue();
 });
 await page.locator('#import').setInputFiles(path.join(data,'Practice song.wav'));
 await page.waitForFunction(previous=>sourceRevision!==previous,previousRevision);
 for(let attempt=0;!metadataHeld&&attempt<100;attempt++)await new Promise(resolve=>setTimeout(resolve,20));
 assert(metadataHeld,'The delayed metadata request did not start');
 await page.locator('#practice-save').click();releaseMetadata();
 await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().savedSessions===2&&!!window.BlazeMacPractice.snapshot().sessionId,null,{timeout:5000});
 await page.unroute('**/api/practice');
 const previousRecording=(await snapshot(page)).recordingId;
 await page.locator('#import').setInputFiles(path.join(data,'Practice song.wav'));
 await page.waitForFunction(previous=>{const s=window.BlazeMacPractice.snapshot();return s.recordingId&&s.recordingId!==previous;},previousRecording);
 await page.locator('#practice-piano').click();await page.waitForFunction(()=>window.BlazeMacPractice.snapshot().preparing);
 await page.locator('#practice-original').click();
 await page.waitForFunction(()=>!window.BlazeMacPractice.snapshot().preparing&&window.BlazeMacPractice.snapshot().pianoJobId);
 assert.equal((await snapshot(page)).mode,'original','Preparation overrode the later Original choice');
 assert.equal(count('separation'),2);assert.deepEqual(page.errors,[]);
 const broken=path.join(data,'Broken analysis.wav');fs.copyFileSync(path.join(data,'Practice song.wav'),broken);await page.locator('#import').setInputFiles(broken);
 await page.waitForFunction(()=>sourceName==='Broken analysis.wav');await page.locator('#practice-analyze').click();
 await page.waitForFunction(()=>document.getElementById('practice-status').textContent.includes('Controlled analysis failure'));
 assert(await page.locator('#practice-status').isVisible(),'An analysis failure was hidden in the retired interface');
 await page.close();console.log('PASS: background preparation, concurrent chords, modes, real looping, speed, layout and saved practice across process restart.');
}catch(e){console.error(e.stack);console.error(logs.slice(-2000));process.exitCode=1;}finally{if(browser)await browser.close();await stop();fs.rmSync(data,{recursive:true,force:true});}})();
