/* Browser plugin not available: installed Playwright fallback.
 * Production renderer + real authenticated loopback/media/export. Inference is
 * controlled; distinct stereo WAVs are real. Not model quality or native QA. */
'use strict';
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=process.env.BLAZE_UI_SCREENSHOTS;
if(out)fs.mkdirSync(out,{recursive:true});
let fixture=fs.readFileSync(path.join(__dirname,'Blaze-Mac-Studio-UI-Tests.cjs'),'utf8').match(/const fixture=String.raw`([\s\S]+?)`;/)[1];
fixture=fixture.replace('import math,shutil,signal,tempfile,wave','import math,shutil,signal,tempfile,wave,time');
fixture=fixture.replace('class Controlled:\n','class Controlled:\n        calls=0\n');
fixture=fixture.replace('            paths={}','            Controlled.calls+=1\n            if Controlled.calls>1:\n                progress(.1,"Controlled background separation")\n                for _ in range(30):\n                    if cancel_event.is_set():return {}\n                    time.sleep(.1)\n            paths={}');
fixture=fixture.replace('    server=create_server(studio)',String.raw`
    # Real Studio worker + Store lifecycle; only model inference is controlled.
    import hashlib,threading
    from types import SimpleNamespace
    import music_studio.server as server_module
    bundle=SimpleNamespace(structured=False,metadata={'sha256':'controlled-model'},manifest={'frontend':{'sha256':'controlled-frontend'}})
    server_module.ModelBundle=lambda *_:bundle
    class Recognition:
        def __init__(self,*_):self.cancelled=threading.Event()
        def cancel(self):self.cancelled.set()
        def check(self):
            if self.cancelled.is_set():raise server_module.AnalysisCancelled()
        def analyze(self,source,progress):
            progress('Controlled chord worker')
            for _ in range(15):
                self.check();time.sleep(.1)
            return {'schema_version':1,'duration':64,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                    'key':'C major','tempo_bpm':120,'analysis_seconds':1.5,
                    'model':{'name':'Controlled recognition','sha256':'controlled-model','frontend_sha256':'controlled-frontend'},
                    'beats':[n*.5 for n in range(128)],
                    'chords':[{'start':0,'end':16,'chord':'C:maj'},{'start':16,'end':64,'chord':'A:min'}]}
    server_module.Analyzer=Recognition
    server=create_server(studio)`);
const server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',fixture],{cwd:root,stdio:['ignore','pipe','pipe']});
let stderr='',browser;server.stderr.on('data',d=>stderr+=d);
const start=()=>new Promise((resolve,reject)=>{let s='';const timeout=setTimeout(()=>reject(Error('Live QA startup timed out: '+stderr)),30000);
 server.stdout.on('data',d=>{s+=d;const m=s.match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timeout);resolve(m[0]);}});server.once('exit',code=>{clearTimeout(timeout);reject(Error('QA exited '+code+': '+stderr));});});
(async()=>{try{
 const base=await start();browser=await chromium.launch({args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1440,height:900},acceptDownloads:true}),errors=[],selections=[];
 page.on('pageerror',e=>errors.push(e.stack));page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/stems-select')selections.push(r.postDataJSON());});
 page.on('console',m=>{const url=m.location().url;if(m.type()==='error'&&!url.endsWith('/favicon.ico')&&!(url.includes('/api/studio-waveform?')&&/409|503/.test(m.text())))errors.push(m.text());});
 await page.goto(base);await page.waitForFunction(()=>window.BlazeLogicVisual?.scope==='live-session');
 assert.equal(new URL(page.url()).origin,base);assert.equal(await page.title(),'Blaze');
 await page.evaluate(()=>{window.testPlayer=document.getElementById('media');window.BlazeMac.navigate('studio');});
 await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().waveformsReady===10);
 await page.waitForFunction(()=>document.querySelectorAll('#logic-preview .track-header').length===10);
 assert(await page.locator('#mac-studio-workspace').isHidden());
 assert.equal(await page.locator('audio,video').count(),1,'Second media player introduced');
 assert.equal(await page.locator('#logic-preview .track-name').first().innerText(),'Piano','Original name colliding with stem was changed');
 assert(await page.locator('#logic-preview .track-header').last().innerText().then(s=>s.includes('Other')));
 // Apply the real native bridge's capability flags, without claiming AppKit
 // rendering. Native navigation must not hide the nested Studio headers.
 await page.evaluate(()=>window.BlazeMac.installNativeChrome({sidebar:true,search:true,window:true}));
 for(const [width,height]of [[1440,900],[1280,800],[1024,700],[780,560],[570,540]])for(const colorScheme of ['light','dark']){
  await page.setViewportSize({width,height});await page.emulateMedia({colorScheme});await page.waitForTimeout(60);
  const clipped=await page.evaluate(()=>['#logic-preview .control-bar','#logic-preview .workspace-bar','#logic-preview .arrangement','#logic-preview .audio-editor','#editor-wave'].flatMap(s=>{
   const r=document.querySelector(s).getBoundingClientRect();return r.left>=0&&r.top>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1&&r.width>0&&r.height>0?[]:[{s,rect:r.toJSON()}];}));
  assert.deepEqual(clipped,[],'Production layout clipped at '+width+' '+colorScheme);
  const geometry=await page.evaluate(()=>{
   const box=s=>document.querySelector(s).getBoundingClientRect(),bar=box('#logic-preview .control-bar'),context=box('#logic-preview .workspace-bar'),heading=box('#logic-preview .editor-heading'),editorMenu=box('#logic-preview .editor-toolbar');
   const number=box('.position-measure>div'),caption=box('.position-measure>small'),lcd=box('.lcd'),pointer=box('#pointer-tools');
   const left=box('.workspace-bar .menu-group'),view=box('#view-tools'),snap=box('.snap-controls'),zoom=box('.zoom-controls');
   const regionColor=getComputedStyle(document.querySelector('#logic-preview .clip.selected')).backgroundColor.match(/[\d.]+/g).slice(0,3).map(Number);
   return {chrome:getComputedStyle(document.querySelector('#logic-preview .control-bar')).backgroundColor,
    controlOverlap:bar.bottom-context.top,editorOverlap:heading.bottom-editorMenu.top,
    captionOverlap:number.bottom-caption.top,lcdOverflow:caption.bottom-lcd.bottom,
    pointerOffset:Math.abs((box('#pointer-tools').left+box('#pointer-tools').width/2)-innerWidth/2),
    leftToolOverlap:Math.max(left.right,view.width?view.right:0)-pointer.left,
    rightToolOverlap:pointer.right-(snap.width?snap.left:zoom.left),
    selectedKeepsColor:Math.max(...regionColor)-Math.min(...regionColor)>15,
    stereo:[...document.querySelectorAll('#logic-preview .clip canvas')].every(c=>c.dataset.channels==='2')};
  });
  assert.equal(geometry.chrome,colorScheme==='light'?'rgb(166, 166, 166)':'rgb(59, 59, 59)','Native navigation removed the Studio chrome fill');
  assert(geometry.controlOverlap<=1&&geometry.editorOverlap<=1,'A header overlaps the next toolbar');
  const topbar=await page.evaluate(()=>{
   const bar=document.querySelector('#logic-preview .control-bar').getBoundingClientRect();
   const groups=[...document.querySelector('#logic-preview .control-bar').children].map(n=>n.getBoundingClientRect()).filter(r=>r.width&&r.height);
   const controls=[...document.querySelectorAll('#logic-preview .control-bar button,#logic-preview .mix-master')].map(n=>n.getBoundingClientRect()).filter(r=>r.width&&r.height);
   return {overlap:groups.some((r,i)=>i>0&&groups[i-1].right>r.left+.5),
    overflow:controls.some(r=>r.left<bar.left||r.right>bar.right+.5||r.top<bar.top||r.bottom>bar.bottom),
    misaligned:groups.some(r=>Math.abs((r.top+r.bottom-bar.top-bar.bottom)/2)>.5)};
  });
  assert.deepEqual(topbar,{overlap:false,overflow:false,misaligned:false},'Top-bar groups collide, clip or lose their common center at '+width+' '+colorScheme);
  assert(geometry.captionOverlap<=1&&geometry.lcdOverflow<=1,'LCD captions collide with digits or escape the display');
  assert(geometry.pointerOffset<=1,'Pointer tools are displaced from the workspace center');
  assert(geometry.leftToolOverlap<=1&&geometry.rightToolOverlap<=1,'Context controls overlap the centered tools');
  assert(geometry.stereo,'Arrangement lost stereo waveform display');
  assert(geometry.selectedKeepsColor,'Generic selected-button styling erased the audio region color');
  for(const id of ['logic-play','logic-stop','add-track','duplicate-track','logic-chords'])assert(await page.locator('#'+id).isVisible(),'Primary action hidden: '+id+' at '+width);
  assert(await page.getByRole('button',{name:'Back to Explore',exact:true}).isVisible(),'No return to browsing at '+width);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1&&document.documentElement.scrollHeight<=innerHeight+1),'Page overflow');
  if(out)await page.screenshot({path:path.join(out,'logic-live-'+width+'-'+colorScheme+'.png')});
 }
 await page.setViewportSize({width:1440,height:900});
 const editorToggle=page.getByRole('button',{name:'Editors',exact:true});
 assert.equal(await editorToggle.getAttribute('aria-pressed'),'true');
 await editorToggle.click();assert(await page.locator('#logic-editor').isHidden());
 assert.equal(await editorToggle.getAttribute('aria-pressed'),'false');
 await page.getByRole('button',{name:'Show or hide lower editor',exact:true}).click();
 assert(await page.locator('#logic-editor').isVisible());assert.equal(await editorToggle.getAttribute('aria-pressed'),'true');
 // Regrouping the timing controls must retain their real command bindings.
 for(const [label,key]of [['Metronome','metronome'],['Cycle','loop']]){
  const initial=await page.evaluate(k=>window.BlazeMacStudio.viewState()[k],key);
  await page.getByRole('button',{name:label,exact:true}).click();
  assert.equal(await page.evaluate(k=>window.BlazeMacStudio.viewState()[k],key),!initial,label+' lost its command binding');
  await page.getByRole('button',{name:label,exact:true}).click();
  assert.equal(await page.evaluate(k=>window.BlazeMacStudio.viewState()[k],key),initial);
 }
 assert(await page.getByRole('button',{name:'Count-in appearance',exact:true}).isDisabled());
 await page.getByRole('button',{name:'Project tempo, time signature and key',exact:true}).focus();await page.keyboard.press('Enter');
 assert(await page.locator('#daw-project-dialog').isVisible(),'LCD lost keyboard access to project settings');
 await page.keyboard.press('Escape');assert(await page.locator('#daw-project-dialog').isHidden());
 const piano=page.locator('#logic-preview .track-header[data-track-id=piano]');
 await piano.locator('.track-name').click();
 await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().selectedTrack==='piano'&&window.BlazeMacStudio.snapshot().waveformReady);
 await page.waitForFunction(()=>document.getElementById('editor-track').textContent==='Piano'&&document.getElementById('editor-wave').dataset.trackId==='piano'&&document.querySelectorAll('#logic-preview .track-header').length===9);
 assert.equal(selections.at(-1).stem,'piano');
 assert(await page.locator('#media').evaluate(m=>m===window.testPlayer),'Player identity changed');
 const waveHash=()=>page.locator('#editor-wave').evaluate(c=>{const pixels=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let hash=0;for(let n=0;n<pixels.length;n+=37)hash=(hash*31+pixels[n])|0;return hash;});
 const pianoHash=await waveHash();assert.notEqual(pianoHash,0,'No waveform pixels');
 await page.locator('#logic-preview .track-header[data-track-id=strings] .track-name').click();
 await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().selectedTrack==='strings'&&window.BlazeMacStudio.snapshot().waveformReady);
 await page.waitForFunction(()=>document.getElementById('editor-track').textContent==='Strings'&&document.getElementById('editor-wave').dataset.trackId==='strings');
 assert.notEqual(await waveHash(),pianoHash,'Different stems use the same illustrative waveform');
 await page.getByRole('button',{name:'Play',exact:true}).click();await page.waitForFunction(()=>!document.getElementById('media').paused&&document.getElementById('media').currentTime>.1);
 await page.getByRole('button',{name:'Pause',exact:true}).click();
 const ruler=page.locator('#project-ruler');await ruler.click({position:{x:(await ruler.boundingBox()).width*.5,y:8}});
 await page.waitForFunction(()=>Math.abs(document.getElementById('media').currentTime-32)<.2);
 await page.locator('#logic-preview .track-header[data-track-id=strings]').getByRole('button',{name:'Mute Strings',exact:true}).click();
 assert(await page.locator('#media').evaluate(m=>m.muted));
 await page.locator('#logic-preview .track-header[data-track-id=strings]').getByRole('button',{name:'Mute Strings',exact:true}).click();
 await page.getByRole('slider',{name:'Master volume',exact:true}).fill('0.4');await page.getByRole('slider',{name:'Master volume',exact:true}).dispatchEvent('input');
 assert(Math.abs(await page.locator('#media').evaluate(m=>m.volume)-.4)<.01);
 const stringsRow=page.locator('#logic-preview .track-header[data-track-id=strings]');
 const pan=stringsRow.getByRole('slider',{name:'Pan Strings',exact:true});
 const fader=stringsRow.getByRole('slider',{name:'Volume Strings',exact:true});
 await pan.focus();await page.keyboard.press('ArrowRight');
 await page.waitForFunction(()=>Math.abs(window.BlazeMacStudio.snapshot().audio.pan-.01)<.0001);
 assert.match(await pan.getAttribute('aria-valuetext'),/R 1/);
 await pan.click({modifiers:['Alt']});await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().audio.pan===0);
 // Control gestures must not redraw every waveform canvas on every move.
 await page.evaluate(()=>{
  window.controlCanvasCalls=0;const original=HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext=function(...args){if(this.closest('#logic-preview'))++window.controlCanvasCalls;return original.apply(this,args);};
  window.restoreControlCanvas=()=>{HTMLCanvasElement.prototype.getContext=original;};
 });
 async function dragPan(fine){const b=await pan.boundingBox(),x=b.x+b.width/2,y=b.y+b.height/2;
  if(fine)await page.keyboard.down('Shift');await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x,y-30,{steps:6});await page.mouse.up();if(fine)await page.keyboard.up('Shift');}
 await dragPan(false);await page.waitForFunction(()=>Math.abs(window.BlazeMacStudio.snapshot().audio.pan-.2)<.002);
 const angle=await pan.locator('..').evaluate(e=>e.style.getPropertyValue('--pan-angle'));assert(Math.abs(parseFloat(angle)-27)<.2,'Pan indicator is still a horizontal slider');
 await pan.click({modifiers:['Alt']});await dragPan(true);await page.waitForFunction(()=>Math.abs(window.BlazeMacStudio.snapshot().audio.pan-.02)<.002);
 await pan.dblclick();await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().audio.pan===0);
 assert.equal(await page.evaluate(()=>window.controlCanvasCalls),0,'Turning the pan knob repainted arrangement waveforms');
 await page.evaluate(()=>window.restoreControlCanvas());
 // A real channel gain node keeps track faders independent of master volume.
 await fader.fill('0.5');await fader.dispatchEvent('input');
 await page.waitForFunction(()=>Math.abs(window.BlazeMacStudio.snapshot().audio.channelGain-.1)<.002);
 assert.match(await fader.getAttribute('aria-valuetext'),/-20\.0 dB/);
 assert.equal(await page.locator('#media').evaluate(m=>m.volume),.4,'Track fader changed master volume');
 const pianoFader=page.locator('#logic-preview .track-header[data-track-id=piano]').getByRole('slider',{name:'Volume Piano',exact:true});
 await pianoFader.fill('0.6');await pianoFader.dispatchEvent('input');
 assert.equal(await page.evaluate(()=>window.BlazeMacStudio.snapshot().selectedTrack),'strings','Inactive fader switched the playing source');
 assert(Math.abs(await page.evaluate(()=>window.BlazeMacStudio.snapshot().audio.channelGain)-.1)<.002,'Inactive fader changed current gain');
 await page.locator('#logic-preview .track-header[data-track-id=piano] .track-name').click();
 await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().selectedTrack==='piano'&&window.BlazeMacStudio.snapshot().waveformReady&&Math.abs(window.BlazeMacStudio.snapshot().audio.channelGain-Math.pow(10,-12/20))<.002);
 await stringsRow.locator('.track-name').click();
 await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().selectedTrack==='strings'&&window.BlazeMacStudio.snapshot().waveformReady&&Math.abs(window.BlazeMacStudio.snapshot().audio.channelGain-.1)<.002);
 await page.getByRole('button',{name:'Inspector',exact:true}).click();
 const inspectorPan=page.getByRole('slider',{name:'Pan in inspector',exact:true});await inspectorPan.focus();await page.keyboard.press('ArrowRight');
 await page.waitForFunction(()=>Math.abs(window.BlazeMacStudio.snapshot().audio.pan-.01)<.0001);
 const inspectorVolume=page.getByRole('slider',{name:'Track volume in inspector',exact:true});await inspectorVolume.click({modifiers:['Alt']});
 await page.waitForFunction(()=>Math.abs(window.BlazeMacStudio.snapshot().audio.channelGain-1)<.002);
 if(out)await page.screenshot({path:path.join(out,'logic-controls-inspector.png')});await page.keyboard.press('Escape');
 await pan.click({modifiers:['Alt']});
 // Fine fader drag retains the grabbed value and captures outside the control.
 const cap=await stringsRow.locator('.mix-fader-cap').boundingBox();await page.mouse.move(cap.x+cap.width/2,cap.y+cap.height/2);await page.mouse.down();
 assert(Math.abs(Number(await fader.inputValue())-.75)<.001,'Grabbing the fader handle jumped its value');
 await page.keyboard.down('Shift');await page.mouse.move(cap.x+cap.width/2-15,cap.y+cap.height/2,{steps:5});await page.mouse.up();await page.keyboard.up('Shift');
 const fineValue=Number(await fader.inputValue());assert(fineValue<.75&&fineValue>.70,'Fine fader adjustment ignored Shift');
 await fader.click({modifiers:['Alt']});await page.waitForFunction(()=>Math.abs(window.BlazeMacStudio.snapshot().audio.channelGain-1)<.002);
 if(out){await pan.fill('0.35');await pan.dispatchEvent('input');await page.getByRole('button',{name:'Play',exact:true}).click();await page.waitForFunction(()=>parseFloat(window.BlazeMacStudio.viewState().levels[0])>0);
  await page.screenshot({path:path.join(out,'logic-controls-playing.png')});await stringsRow.screenshot({path:path.join(out,'controls-row-playing.png')});await page.getByRole('button',{name:'Pause',exact:true}).click();await pan.click({modifiers:['Alt']});}
 const save=page.getByRole('link',{name:'Save Strings WAV',exact:true});const downloadPromise=page.waitForEvent('download');await save.click();const download=await downloadPromise;
 assert.equal(download.suggestedFilename(),'Strings.wav');const saved=fs.readFileSync(await download.path());assert.equal(saved.subarray(0,4).toString(),'RIFF');assert(saved.length>1000000);
 const original=await page.request.get(download.url());assert.deepEqual(saved,await original.body(),'Saved stem was re-encoded or truncated');
 await page.evaluate(()=>applyResult({duration:64,key:'C major',tempo_bpm:120,analysis_seconds:0,model:{name:'Controlled timing evidence'},beats:Array.from({length:128},(_,i)=>i*.5),chords:[{start:0,end:16,chord:'C:maj'},{start:16,end:64,chord:'A:min'}]}));
 await page.waitForFunction(()=>document.querySelectorAll('#chord-lane button').length===2);
 const geometry=await page.locator('#chord-lane button').first().evaluate(b=>b.getBoundingClientRect().width/b.parentElement.getBoundingClientRect().width);assert(Math.abs(geometry-.25)<.01,'Chords not aligned to recording time');
 await page.locator('#chord-lane button').last().click();await page.waitForFunction(()=>Math.abs(document.getElementById('media').currentTime-16)<.1);
 const editor=page.locator('#editor-wave');await editor.focus();await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>Math.abs(document.getElementById('media').currentTime-21)<.1);
 await page.getByRole('slider',{name:'Waveform zoom',exact:true}).fill('3');await page.getByRole('slider',{name:'Waveform zoom',exact:true}).dispatchEvent('input');
 assert(await page.locator('.live-editor-scroll').evaluate(e=>e.scrollWidth>e.clientWidth*2.9));
 await page.getByRole('button',{name:'Library',exact:true}).click();assert(await page.locator('#logic-session-tools').isVisible());await page.keyboard.press('Escape');
 await page.locator('[data-menu=functions]').first().click();await page.locator('#appearance-menu').getByRole('button',{name:'Chord practice',exact:true}).click();
 assert(await page.locator('#daw-practice').isVisible());await page.locator('#daw-practice-close').click();
 assert.equal(await page.evaluate(()=>document.activeElement.id),'logic-chords','Closing chord practice lost visible keyboard focus');
 await page.evaluate(()=>failure(Error('Controlled decoder failure')));
 await page.waitForFunction(()=>document.getElementById('live-status').textContent==='Controlled decoder failure'&&document.getElementById('live-status').dataset.state==='error');
 await page.evaluate(()=>document.getElementById('error').hidden=true);
 await page.getByRole('button',{name:'Split stems',exact:true}).click();await page.locator('#stems-start').click();
 await page.waitForFunction(()=>window.BlazeMacStems.snapshot().status==='running'&&!document.getElementById('stems-dialog').open);
 await page.getByRole('button',{name:'Analyse chords',exact:true}).click();
 await page.waitForFunction(()=>busy&&window.BlazeMacStems.snapshot().status==='running');
 await page.getByRole('button',{name:'Play',exact:true}).click();await page.waitForFunction(()=>!document.getElementById('media').paused);
 await page.getByRole('button',{name:'Back to Explore',exact:true}).click();assert(await page.locator('#explore-panel').isVisible());
 await page.waitForFunction(()=>!busy&&result?.model?.name==='Controlled recognition');
 await page.waitForFunction(()=>window.BlazeMacStems.snapshot().status==='done',{timeout:20000});
 await page.evaluate(()=>window.BlazeMac.navigate('studio'));await page.waitForFunction(()=>document.querySelectorAll('#logic-preview .track-header').length>=9);
 await page.waitForFunction(()=>{const job=window.BlazeMacStems.snapshot().jobId;return window.BlazeMacStudio.viewState().tracks.some(t=>t.jobId===job);});
 await page.waitForFunction(()=>{const s=window.BlazeMacStudio.snapshot();return s.waveformsReady===s.tracks.length;});
 assert.equal(await page.evaluate(()=>window.BlazeMacStudio.viewState().tracks.find(t=>t.id==='piano')?.gain),1,'A new separation job inherited an unrelated track level');
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('#logic-preview .track-header')).map(n=>n.dataset.trackId).join(',')===window.BlazeMacStudio.snapshot().tracks.map(t=>t.id).join(','));
 await page.evaluate(()=>window.BlazeMacStudio.commands.stop());
 if(out)await page.screenshot({path:path.join(out,'logic-live-connected.png')});
 // A controlled empty backend state must never fall back to the concept song.
 const blank=await browser.newPage({viewport:{width:1024,height:700}});
 blank.on('pageerror',e=>errors.push(e.message));
 await blank.route('**/api/state',route=>route.fulfill({json:{sourceRevision:0,name:'',busy:false,result:null,progress:'Import a recording.'}}));
 await blank.goto(base);await blank.waitForFunction(()=>window.BlazeLogicVisual?.scope==='live-session');
 await blank.evaluate(()=>window.BlazeMac.navigate('studio'));
 await blank.waitForFunction(()=>!document.getElementById('live-empty').hidden);
 assert.equal(await blank.locator('#logic-preview .track-header').count(),0,'Empty project contains demo tracks');
 assert(await blank.locator('#logic-play').isDisabled());
 if(out)await blank.screenshot({path:path.join(out,'logic-live-empty.png')});await blank.close();
 assert.deepEqual(errors,[],'Page errors');
 console.log('Logic live PASS: production Studio, one player, real WAVs/export, rotary pan drag/fine/reset/keyboard, independent track gains/restore, inspector sync, fader grab/fine/reset, no canvas redraw during pan drag, five widths/light/dark, concurrent chord/stem workers and browsing. Controlled inference; native macOS 26/model quality not tested.');
}finally{if(browser)await browser.close();server.kill('SIGTERM');}})().catch(e=>{console.error(e);process.exitCode=1;});
