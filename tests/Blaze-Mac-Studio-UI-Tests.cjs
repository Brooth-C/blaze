/* Studio navigation -> real stem selection -> waveform -> playback/export.
 * Browser plugin not available: regular Playwright exercises the authenticated
 * loopback server. Separation is controlled; each output is a real distinct
 * stereo WAV. This suite does not claim model quality or AppKit rendering. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..');
const screenshots=process.env.BLAZE_UI_SCREENSHOTS;
if(screenshots)fs.mkdirSync(screenshots,{recursive:true});
const fixture=String.raw`
import math,shutil,signal,tempfile,wave
from pathlib import Path
import numpy as np
from music_studio.server import Studio,create_server
from music_studio.stem_jobs import StemJobs
from music_studio.mac_app import SmokeCatalogue

with tempfile.TemporaryDirectory(prefix='blaze-studio-workspace-') as directory:
    data=Path(directory)
    rate=48000
    t=np.arange(rate*64,dtype=np.float64)/rate
    names=('vocals','drums','bass','piano','guitar','strings','brass','synths','other')
    def render(path,index):
        phrase=np.maximum(0,np.sin(t*(.9+index*.09)))**2
        pulse=np.exp(-np.mod(t,.5+index*.03)*(2+index*.5))
        signal=(np.sin(2*math.pi*(110+index*37)*t)+.25*np.sin(2*math.pi*(220+index*71)*t))
        signal*=.12*(.12+.7*phrase+.35*pulse)
        samples=np.stack([signal,signal*.8+np.sin(2*math.pi*(120+index*41)*t)*.015],axis=1)
        with wave.open(str(path),'wb') as out:
            out.setparams((2,3,rate,0,'NONE','not compressed'))
            packed=(np.clip(samples,-1,1)*8388607).astype('<i4').view('u1').reshape(-1,4)[:,:3]
            out.writeframes(packed.tobytes())
    # An imported mix can have the same name as one of its generated stems.
    source=data/'Piano.wav'
    render(source,9)
    studio=Studio(data/'state',shutil.which('ffmpeg') or 'ffmpeg',source)
    studio.presentation='mac';studio.discovery=SmokeCatalogue()
    class Controlled:
        def __init__(self,*args):pass
        def separate(self,source,output_dir,progress,cancel_event):
            paths={}
            for i,name in enumerate(names):
                target=output_dir/(name+'.wav');render(target,i);paths[name]=target
            return paths
    studio.stems=StemJobs(studio,separator_factory=Controlled)
    studio.stems.start('nine');studio.stems.worker.join(timeout=20)
    assert studio.stems.snapshot()['status']=='done'
    server=create_server(studio)
    def stop_server(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop_server)
    print('http://127.0.0.1:'+str(server.server_port),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();studio.close()
`;
const server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',fixture],{cwd:root,stdio:['ignore','pipe','pipe']});
let stderr='';server.stderr.on('data',chunk=>stderr+=chunk);
async function start(){return new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Studio QA startup timed out: '+stderr)),30000);
    server.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
    server.once('exit',code=>{clearTimeout(timer);reject(Error('Studio QA server exited '+code+': '+stderr));});
});}
async function shot(page,name){if(screenshots)await page.screenshot({path:path.join(screenshots,'mac-studio-workspace-'+name+'.png'),fullPage:false});}
async function fit(page,ids){
    const invalid=await page.evaluate(ids=>ids.flatMap(id=>{
        // At zoom > 1 the canvas is intentionally wider than its scrollport.
        const element=document.getElementById(id==='daw-waveform'?'daw-editor-scroll':id),r=element?.getBoundingClientRect();
        return r&&r.width>0&&r.height>0&&r.top>=0&&r.left>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1?[]:[{id,rect:r?.toJSON()}];
    }),ids);
    assert.deepEqual(invalid,[],'Studio primary controls clipped');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Studio caused horizontal page scrolling');
    assert(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1),'Studio caused vertical page scrolling');
}
(async()=>{
    let browser,page;
    try{
        const base=await start();
        browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM||undefined,args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
        page=await browser.newPage({viewport:{width:1672,height:941},acceptDownloads:true});
        const errors=[],selections=[];
        let injectedBusy=false,ignoredBusyConsole=0;
        page.on('pageerror',error=>{errors.push(error.stack);console.error(error.stack);});
        page.on('console',message=>{
            const url=message.location().url;
            const staleWaveform=url.includes('/api/studio-waveform?')&&message.text().includes('409 (Conflict)');
            const controlledBusy=url.includes('/api/studio-waveform?')&&/503\b/.test(message.text())&&injectedBusy;
            if(controlledBusy)ignoredBusyConsole++;
            if(message.type()==='error'&&!url.endsWith('/favicon.ico')&&!staleWaveform&&!controlledBusy)errors.push(message.text());
        });
        page.on('request',request=>{if(request.method()==='POST'&&request.url()===base+'/api/stems-select')selections.push(request.postDataJSON());});
        // An old aborted decode can briefly occupy both bounded decoder slots.
        // The first response is controlled; the retry and all peak data are real.
        await page.route('**/api/studio-waveform?*',async route=>{
            if(!injectedBusy){injectedBusy=true;await route.fulfill({status:503,json:{error:'Waveforms are still loading. Try again shortly.'}});}
            else await route.continue();
        });
        await page.goto(base);
        assert.equal(await page.title(),'Blaze');
        assert.equal(new URL(page.url()).origin,base);
        await page.waitForFunction(()=>window.BlazeMacStudio&&sourceName==='Piano.wav');
        const token=await page.locator('meta[name=blaze-token]').getAttribute('content');
        await page.evaluate(()=>{window.testMedia=document.getElementById('media');window.BlazeMac.installNativeChrome({sidebar:true,search:true});window.BlazeMac.navigate('explore');});
        assert.equal(await page.locator('#explore-panel').isVisible(),true);
        await page.evaluate(()=>window.BlazeMac.navigate('studio'));
        await page.locator('#mac-studio-workspace').waitFor({state:'visible'});
        await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().active);
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia),'Studio navigation replaced the shared media element');
        await page.waitForFunction(()=>['vocals','drums','bass','piano','guitar','strings','brass','synths','other'].every(id=>window.BlazeMacStudio.snapshot().tracks.some(track=>track.id===id)));
        await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().waveformReady);
        assert.equal(await page.evaluate(()=>window.BlazeMacStudio.snapshot().selectedTrack),'source','A filename collision relabeled the original mix as a saved stem');
        assert.equal(await page.locator('#daw-save').isVisible(),false,'The original mix advertised a different saved stem');
        await page.waitForFunction(()=>document.getElementById('media').readyState>=1);
        const mixRevision=await page.evaluate(()=>sourceRevision);
        const mixResponse=await page.request.get(await page.locator('#media').evaluate(element=>element.currentSrc));
        assert(mixResponse.ok());const mixBytes=await mixResponse.body();
        await page.locator('[data-track-id="piano"]').first().click();
        await page.waitForFunction(revision=>window.BlazeMacStudio.snapshot().selectedTrack==='piano'&&window.BlazeMacStudio.snapshot().waveformReady&&sourceName==='Piano.wav'&&sourceRevision>revision,mixRevision);
        await page.waitForFunction(()=>document.getElementById('media').readyState>=1);
        await page.waitForFunction(()=>{const state=window.BlazeMacStudio.snapshot();return state.tracks.length>=9&&state.waveformsReady>=state.tracks.length;});
        assert(injectedBusy,'Transient waveform loading response was not exercised');
        assert.equal(selections.at(-1).stem,'piano');
        const pianoResponse=await page.request.get(await page.locator('#media').evaluate(element=>element.currentSrc));
        assert(pianoResponse.ok());const pianoBytes=await pianoResponse.body();
        assert(!pianoBytes.equals(mixBytes),'Selecting Piano.wav kept playing the original mix with the same filename');
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia),'Stem selection replaced the shared media element');
        const pixels=await page.locator('#daw-waveform').evaluate(canvas=>{
            const values=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
            let nontransparent=0;for(let i=3;i<values.length;i+=4)if(values[i])nontransparent++;
            return nontransparent;
        });
        assert(pixels>100,'The detailed waveform did not render actual peak data');
        await fit(page,['daw-transport','daw-play','daw-stop','daw-arrangement','daw-editor','daw-waveform']);
        const geometry=await page.evaluate(()=>Object.fromEntries(['daw-library','daw-inspector','daw-track-list','daw-editor'].map(id=>{const r=document.getElementById(id).getBoundingClientRect();return[id,{left:r.left,top:r.top,width:r.width}];})));
        assert.equal(geometry['daw-library'].width,0,'The main workstation should open with the optional Library closed');
        assert.equal(geometry['daw-inspector'].left,0);assert.equal(geometry['daw-inspector'].width,210);
        assert.equal(geometry['daw-track-list'].left,210);assert.equal(geometry['daw-track-list'].width,310);
        assert(geometry['daw-editor'].top>500&&geometry['daw-editor'].top<660,'Audio editor left the lower workspace');
        assert.equal(await page.locator('#daw-format').textContent(),'48 kHz · 24-bit · Stereo');
        // Controlled chord evidence exercises the reference's note-guide lanes;
        // it is never included as a production session or a model quality claim.
        await page.evaluate(()=>applyResult({duration:64,key:'C major',tempo_bpm:120,analysis_seconds:0,model:{name:'Controlled UI analysis'},beats:Array.from({length:128},(_,i)=>i*.5),chords:Array.from({length:16},(_,i)=>({start:i*4,end:(i+1)*4,chord:['C:maj','A:min','F:maj','G:maj'][i%4]}))}));
        await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().guideReady);
        const ruler=await page.locator('#daw-ruler').boundingBox();
        await page.mouse.move(ruler.x+ruler.width*.25,ruler.y+5);await page.mouse.down();
        await page.mouse.move(ruler.x+ruler.width*.75,ruler.y+5,{steps:8});await page.mouse.up();
        await page.waitForFunction(()=>loopStart===16&&loopEnd===48);
        assert.equal(await page.locator('#daw-ruler .daw-cycle-strip').count(),1);
        assert.equal(await page.locator('#daw-editor-ruler .daw-cycle-strip').count(),0,'Cycle obscured the audio editor ruler');
        const referenceWave=await page.locator('#daw-waveform').boundingBox();
        await page.mouse.click(referenceWave.x+referenceWave.width*.5,referenceWave.y+referenceWave.height*.4);
        await page.waitForFunction(()=>Math.abs(document.getElementById('media').currentTime-32)<1);
        await page.keyboard.down('Shift');
        await page.mouse.move(referenceWave.x+referenceWave.width*.5,referenceWave.y+referenceWave.height*.5);
        await page.mouse.down();
        await page.mouse.move(referenceWave.x+referenceWave.width*.625,referenceWave.y+referenceWave.height*.5,{steps:8});
        await page.mouse.up();await page.keyboard.up('Shift');
        assert.notEqual(await page.locator('#daw-selection-readout').textContent(),'No range selected','Shift-drag did not select an audio range');
        await page.locator('#daw-editor-title').click();
        await page.locator('#daw-zoom').fill('4');await page.locator('#daw-zoom').dispatchEvent('input');
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>{const scroll=document.getElementById('daw-editor-scroll');scroll.scrollLeft=scroll.scrollWidth*26.5/64;resolve();})));
        const gutter=await page.locator('.daw-amplitude-scale').boundingBox(),port=await page.locator('#daw-editor-scroll').boundingBox();
        assert(gutter&&port&&Math.abs(gutter.x+gutter.width-port.x)<1,'Amplitude gutter moved with the waveform scroll');
        assert(await page.locator('#daw-editor-ruler span').evaluateAll(marks=>marks.some(mark=>{const r=mark.getBoundingClientRect(),p=mark.parentElement.getBoundingClientRect();return r.left>=p.left&&r.right<=p.right&&r.top>=p.top&&r.bottom<=p.bottom;})),'Editor ruler labels are clipped');
        await shot(page,'wide');
        await page.emulateMedia({colorScheme:'dark'});await shot(page,'wide-dark');
        await page.emulateMedia({colorScheme:'light'});
        await page.locator('#daw-loop').click();await page.waitForFunction(()=>loopEnd===null);
        await page.locator('#daw-zoom').fill('1');await page.locator('#daw-zoom').dispatchEvent('input');
        await page.evaluate(()=>document.getElementById('daw-editor-scroll').scrollLeft=0);
        await page.locator('#daw-waveform').focus();await page.keyboard.press('Escape');

        await page.evaluate(()=>window.BlazeMac.action('open-player'));
        await page.waitForFunction(()=>document.getElementById('now-dialog').open);
        await fit(page,['mini-play','mac-mini-seek','now-close']);
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia),'Expanded player replaced Studio media');
        await page.evaluate(()=>window.BlazeMac.action('close-player'));
        await page.waitForFunction(()=>!document.getElementById('now-dialog').open);

        // Both transport and waveform seek act on the same real WAV player.
        await page.locator('#daw-play').click();
        await page.waitForFunction(()=>!document.getElementById('media').paused&&document.getElementById('media').currentTime>.1);
        await page.waitForFunction(()=>parseFloat(document.getElementById('daw-master-left').style.width)>0);
        await page.locator('#daw-play').click();
        await page.waitForFunction(()=>document.getElementById('media').paused);
        const wave=await page.locator('#daw-waveform').boundingBox();
        await page.mouse.click(wave.x+wave.width*.4,wave.y+wave.height*.4);
        await page.waitForFunction(()=>{const m=document.getElementById('media');return m.paused&&Math.abs(m.currentTime-m.duration*.4)<1;});
        await page.locator('#daw-zoom').fill('2');
        await page.locator('#daw-zoom').dispatchEvent('input');
        await page.waitForFunction(()=>Number(window.BlazeMacStudio.snapshot().zoom)>1);
        await page.waitForFunction(()=>{const port=document.getElementById('daw-editor-scroll');return port.scrollWidth>port.clientWidth*1.5;});
        await page.locator('#daw-stop').click();
        await page.waitForFunction(()=>document.getElementById('media').paused&&document.getElementById('media').currentTime<.1);
        await page.locator('#daw-volume').fill('0.5');await page.locator('#daw-volume').dispatchEvent('input');
        await page.waitForFunction(()=>document.getElementById('media').volume===.5);
        await page.locator('#daw-mute').click();
        await page.waitForFunction(()=>document.getElementById('media').muted);
        await page.locator('#daw-mute').click();
        await page.waitForFunction(()=>!document.getElementById('media').muted);
        await page.locator('#daw-pan').fill('0.4');await page.locator('#daw-pan').dispatchEvent('input');
        await page.waitForFunction(()=>Math.abs(window.BlazeMacStudio.snapshot().audio.pan-.4)<.001);
        await page.locator('#daw-eq').click();await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().audio.equalizerGain===3);
        await page.locator('#daw-compressor').click();await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().audio.compressionRatio===6);
        await page.locator('#daw-eq').click();await page.locator('#daw-compressor').click();
        await page.locator('#daw-pan').fill('0');await page.locator('#daw-pan').dispatchEvent('input');
        await page.locator('#daw-notation').click();await page.locator('#daw-midi-guide').waitFor({state:'visible'});
        assert.equal(await page.evaluate(()=>window.BlazeMacStudio.snapshot().editorMode),'midi');
        await page.locator('#daw-audio-tab').click();
        await page.locator('#daw-analysis-toggle').click();
        await page.locator('#daw-rate').selectOption('1.25');
        await page.waitForFunction(()=>document.getElementById('media').playbackRate===1.25);
        await page.locator('#daw-rate').selectOption('1');
        await page.locator('#daw-extra-close').click();
        await page.locator('#daw-volume').fill('1');await page.locator('#daw-volume').dispatchEvent('input');

        const before=await page.evaluate(()=>window.BlazeMacStudio.snapshot());
        await page.locator('#daw-library-toggle').click();
        await page.waitForFunction(value=>window.BlazeMacStudio.snapshot().libraryOpen!==value,before.libraryOpen);
        await page.locator('#daw-library-toggle').click();
        await page.locator('#daw-inspector-toggle').click();
        await page.waitForFunction(value=>window.BlazeMacStudio.snapshot().inspectorOpen!==value,before.inspectorOpen);
        await page.locator('#daw-inspector-toggle').click();
        if(!(await page.evaluate(()=>window.BlazeMacStudio.snapshot().libraryOpen)))await page.locator('#daw-library-toggle').click();
        await page.locator('#daw-families [data-family="piano"]').click();
        assert.equal(await page.locator('#daw-families [data-family="piano"]').getAttribute('aria-pressed'),'true');
        assert.equal(await page.locator('#daw-track-list .daw-track').count(),9,'The sound library must not hide arrangement tracks');
        assert.equal(await page.locator('#daw-recordings button:visible').count(),1);
        assert.equal(await page.locator('#daw-recordings button:visible').textContent(),'Piano');
        await page.locator('#daw-search').fill('guitar');
        await page.locator('#daw-families [data-family="all"]').click();
        assert.equal(await page.locator('#daw-recordings button:visible').textContent(),'Guitar');
        await page.locator('#daw-search').fill('');
        assert.equal(await page.locator('#daw-recordings button:visible').count(),9);
        await shot(page,'library');
        assert.equal(await page.locator('#daw-track-list .daw-track').count(),9);
        const download=page.waitForEvent('download');
        await page.locator('#daw-analysis-toggle').click();
        await page.locator('#daw-save').click();
        const file=await download;
        assert.equal(file.suggestedFilename(),'Piano.wav');
        const downloaded=fs.readFileSync(await file.path());
        const real=await page.request.get(base+'/api/stem-file?token='+encodeURIComponent(token)+'&jobId='+encodeURIComponent(selections.at(-1).jobId)+'&stem=piano');
        assert(real.ok());assert.deepEqual(downloaded,await real.body(),'Studio export changed saved audio bytes');
        assert.deepEqual(downloaded,pianoBytes,'Saved stem bytes differ from the actual selected playback source');
        await page.locator('#daw-extra-close').click();

        // A source/stem context change may never multiply player elements.
        await page.evaluate(()=>window.BlazeMac.navigate('explore'));
        assert.equal(await page.locator('#mac-studio-workspace').isVisible(),false);
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia));
        await page.evaluate(()=>window.BlazeMac.navigate('studio'));
        await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().active);
        assert.equal(await page.locator('video').count(),1);
        for(const [width,height] of [[1280,800],[780,625],[569,548]]){
            await page.setViewportSize({width,height});
            await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
            await fit(page,['daw-play','daw-stop','daw-arrangement','daw-editor','daw-waveform']);
            await shot(page,width+'x'+height);
        }
        await page.emulateMedia({reducedMotion:'reduce',colorScheme:'light'});
        await fit(page,['daw-play','daw-stop','daw-waveform']);
        await shot(page,'compact-light-system');
        await page.evaluate(()=>window.BlazeMac.action('open-player'));
        await page.waitForFunction(()=>document.getElementById('now-dialog').open);
        await fit(page,['mini-play','mac-mini-seek','now-close']);
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia),'Compact expanded player replaced Studio media');
        await page.evaluate(()=>window.BlazeMac.action('close-player'));
        await page.waitForFunction(()=>!document.getElementById('now-dialog').open);

        // Keep existing chord-analysis tools available through the practice drawer.
        await page.locator('#daw-chords').click();
        await page.locator('#daw-practice').waitFor({state:'visible'});
        assert.equal(await page.locator('#analyze').count(),1);
        assert.equal(await page.locator('#diagram-strip').count(),1);
        await page.locator('#daw-practice-close').click();

        // Stem switching must preserve keyboard focus and inspector changes,
        // while a later user action takes precedence over async completion.
        await page.setViewportSize({width:1230,height:840});
        if(!(await page.evaluate(()=>window.BlazeMacStudio.snapshot().inspectorOpen)))await page.locator('#daw-inspector-toggle').click();
        const waitForTrack=async id=>page.waitForFunction(id=>{
            const state=window.BlazeMacStudio.snapshot();
            return state.selectedTrack===id&&sourceName===id[0].toUpperCase()+id.slice(1)+'.wav'&&state.sourceRevision===sourceRevision&&state.waveformReady;
        },id);
        const chooseTrack=async id=>{
            await page.locator('.daw-track[data-track-id="'+id+'"] .daw-track-select').focus();
            await page.keyboard.press('Enter');await waitForTrack(id);
        };
        const delaySelection=async(id,key='Enter',inspectPending=()=>{})=>{
            let release,entered;
            const reached=new Promise(resolve=>entered=resolve);
            const handler=async route=>{await new Promise(resolve=>{release=resolve;entered();});await route.continue();};
            await page.route('**/api/stems-select',handler,{times:1});
            try{
                await page.locator('.daw-track[data-track-id="'+id+'"] .daw-track-select').focus();
                await page.keyboard.press(key);
                let timer;
                try{await Promise.race([reached,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Track selection did not reach the controlled request')),10000);})]);}
                finally{clearTimeout(timer);}
                await inspectPending();release();await waitForTrack(id);
            }finally{release?.();await page.unroute('**/api/stems-select',handler);}
        };
        await chooseTrack('piano');
        await page.evaluate(()=>document.getElementById('media').pause());
        assert.equal(await page.locator('.daw-track[role="button"]').count(),0,'Track controls must be siblings of the selection button');
        assert.equal(await page.locator('.daw-track-select button,.daw-track-select input').count(),0);
        if(await page.locator('#media').evaluate(element=>element.muted))await page.locator('#daw-mute').click();
        await page.locator('#daw-mute').click();
        await page.locator('#daw-pan').fill('0.3');await page.locator('#daw-pan').dispatchEvent('input');
        assert.equal(await page.locator('.daw-track[data-track-id="piano"] .daw-row-mute').getAttribute('aria-pressed'),'true');
        assert.equal(await page.locator('.daw-track[data-track-id="piano"] .daw-row-pan input').inputValue(),'0.3');
        await delaySelection('guitar','Space',async()=>{
            assert.equal(await page.locator('.daw-track[data-track-id="guitar"]').getAttribute('aria-busy'),'true');
            assert.equal(await page.locator('#daw-message').getAttribute('data-state'),'loading');
            assert(await page.locator('#daw-message').isVisible(),'Opening a real stem lacked visible feedback');
        });
        await page.waitForFunction(()=>document.activeElement.matches('.daw-track[data-track-id="guitar"] .daw-track-select'));
        assert(await page.locator('#media').evaluate(element=>element.paused),'Space selected a track and also toggled global playback');
        await chooseTrack('piano');
        assert(await page.locator('#media').evaluate(element=>element.muted),'Inspector mute did not survive a stem round trip');
        assert.equal(await page.locator('#daw-pan').inputValue(),'0.3','Inspector pan did not survive a stem round trip');
        await page.locator('#daw-analysis-toggle').click();
        assert.equal(await page.locator('#daw-analysis-toggle').getAttribute('aria-expanded'),'true');
        assert(await page.locator('#daw-rate').evaluate(element=>element===document.activeElement));
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('#daw-analysis-toggle').getAttribute('aria-expanded'),'false');
        assert(await page.locator('#daw-inspector-extra').evaluate(element=>element.hidden));
        assert(await page.locator('#daw-analysis-toggle').evaluate(element=>element===document.activeElement));
        await delaySelection('drums','Enter',async()=>{await page.locator('#daw-zoom').focus();});
        assert(await page.locator('#daw-zoom').evaluate(element=>element===document.activeElement),'Async stem completion stole focus from another control');
        const errorsBeforeFailure=errors.length;
        const expectedFailureConsole=page.waitForEvent('console',{predicate:message=>message.type()==='error'&&message.location().url===base+'/api/stems-select'&&/503\b/.test(message.text())});
        await page.route('**/api/stems-select',route=>route.fulfill({status:503,json:{error:'Controlled stem selection failure.'}}),{times:1});
        await page.locator('.daw-track[data-track-id="bass"] .daw-track-select').focus();await page.keyboard.press('Enter');
        await page.waitForFunction(()=>document.getElementById('daw-message').dataset.state==='error');
        assert.equal(await page.locator('#daw-message').textContent(),'Controlled stem selection failure.');
        const failureMessage=await expectedFailureConsole;
        const expectedErrorIndex=errors.indexOf(failureMessage.text(),errorsBeforeFailure);
        assert(expectedErrorIndex>=errorsBeforeFailure,'The controlled request did not produce its expected console diagnostic');
        errors.splice(expectedErrorIndex,1); // Consume this exact injected API failure only.
        await page.setViewportSize({width:780,height:572});
        assert(await page.locator('#daw-message').isVisible(),'Compact Studio hid the stem selection error');
        await page.setViewportSize({width:1230,height:840});
        if(!(await page.evaluate(()=>window.BlazeMacStudio.snapshot().inspectorOpen)))await page.locator('#daw-inspector-toggle').click();
        await chooseTrack('piano');
        if(await page.locator('#media').evaluate(element=>element.muted))await page.locator('#daw-mute').click();
        await page.locator('#daw-pan').fill('0');await page.locator('#daw-pan').dispatchEvent('input');
        await page.locator('#daw-volume').fill('1');await page.locator('#daw-volume').dispatchEvent('input');
        if(await page.locator('#daw-audition').getAttribute('aria-pressed')==='true')await page.locator('#daw-audition').click();
        await page.evaluate(()=>document.getElementById('media').pause());

        // Unrelated imports must not relabel the previous separation as their own.
        const response=await page.request.post(base+'/api/import',{headers:{'X-Blaze-Token':token,'X-File-Name':'Fresh recording.wav'},data:downloaded});
        assert(response.ok());
        await page.evaluate(()=>refresh());
        await page.waitForFunction(()=>{const state=window.BlazeMacStudio.snapshot();return sourceName==='Fresh recording.wav'&&state.sourceRevision===sourceRevision&&state.waveformReady;});
        assert(!(await page.evaluate(()=>window.BlazeMacStudio.snapshot().tracks)).some(track=>track.id==='piano'),'The previous stem session leaked into the new import');
        // Analysis guides from an ordinary recording must not survive a later
        // import when neither recording belongs to a completed stem job.
        await page.evaluate(()=>applyResult({duration:64,key:'C major',tempo_bpm:120,analysis_seconds:0,model:{name:'Controlled guide'},beats:[],chords:[{start:0,end:64,chord:'C:maj'}]}));
        await page.waitForFunction(()=>window.BlazeMacStudio.snapshot().guideReady);
        const longName='93fd8cfb-4d71-48b1-a9f7-Midnight studio recording with a very long descriptive filename.wav';
        const second=await page.request.post(base+'/api/import',{headers:{'X-Blaze-Token':token,'X-File-Name':longName},data:downloaded});
        assert(second.ok());await page.evaluate(()=>refresh());
        await page.waitForFunction(name=>{const s=window.BlazeMacStudio.snapshot();return sourceName===name&&s.sourceRevision===sourceRevision&&s.waveformReady;},longName);
        assert.equal(await page.evaluate(()=>window.BlazeMacStudio.snapshot().guideReady),false,'The previous recording supplied a stale MIDI guide');
        for(const [width,height] of [[1024,649],[780,572]]){
            await page.setViewportSize({width,height});
            if(!(await page.evaluate(()=>window.BlazeMacStudio.snapshot().inspectorOpen)))await page.locator('#daw-inspector-toggle').click();
            await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
            assert.equal(await page.locator('.daw-instrument-art strong').textContent(),'Recording');
            assert.equal(await page.locator('#daw-editor-title').getAttribute('title'),longName.replace(/\.wav$/,''));
            assert(await page.evaluate(()=>{
                const art=document.querySelector('.daw-instrument-art strong'),toolbar=document.querySelector('.daw-editor-toolbar');
                return art.scrollHeight<=art.clientHeight+1&&toolbar.scrollWidth<=toolbar.clientWidth+1;
            }),'A long recording name overflowed Studio controls');
            await fit(page,['daw-play','daw-stop','daw-editor','daw-waveform']);
            if(width===1024)await fit(page,['daw-channel-mute','daw-channel-solo','daw-master-volume']);
            await shot(page,'long-name-'+width);
        }
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia));
        assert(ignoredBusyConsole<=8,'Waveform requests did not settle after bounded retry');
        assert.deepEqual(errors,[]);
        console.log('Mac Studio UI PASS: navigation opens DAW layout, real authorized nine-stem selection/waveforms/export, shared player playback/seek/stop, waveform zoom, library/inspector toggles, compact primary controls, chord-tools drawer, unrelated import invalidation. Browser plugin absent; controlled separator, no model-quality/native AppKit claim.');
    }catch(error){if(stderr.trim())console.error(stderr);if(page)await shot(page,'failure').catch(()=>{});throw error;}
    finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exitCode=1;});
