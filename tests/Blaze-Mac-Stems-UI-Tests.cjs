/* Mac stem sheet workflows use a controlled worker; local WAV playback,
 * authenticated source replacement and downloaded bytes are real. Model
 * inference and native AppKit are covered by separate suites. */
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
import math,struct,tempfile,wave
from pathlib import Path
from music_studio.server import Studio,create_server
from music_studio.mac_app import SmokeCatalogue
with tempfile.TemporaryDirectory(prefix='blaze-stems-ui-') as directory:
    source=Path(directory)/'A local recording.wav'
    with wave.open(str(source),'wb') as out:
        out.setparams((1,2,22050,0,'NONE','not compressed'))
        out.writeframes(b''.join(struct.pack('<h',int(2500*math.sin(i*2*math.pi*220/22050))) for i in range(22050*4)))
    studio=Studio(Path(directory)/'state','ffmpeg',source)
    studio.presentation='mac';studio.discovery=SmokeCatalogue()
    class UIWorker:
        # The download uses the real authenticated server and filesystem. Only
        # separation job state is controlled by the browser fixture below.
        def file(self,job_id,stem):
            if (job_id,stem) not in [('fixture-job-2','vocals'),('fixture-job-3','piano')]:raise ValueError('Unknown fixture stem')
            return source
        def close(self):pass
    studio.stems=UIWorker()
    server=create_server(studio)
    print('http://127.0.0.1:'+str(server.server_port),flush=True)
    try:server.serve_forever()
    finally:server.server_close();studio.close()
`;
const server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',fixture],{cwd:root,stdio:['ignore','pipe','pipe']});
let stderr='';server.stderr.on('data',chunk=>stderr+=chunk);
async function start(){return new Promise((resolve,reject)=>{
    let text='';const timer=setTimeout(()=>reject(Error('Stem UI server startup timed out: '+stderr)),20000);
    server.stdout.on('data',chunk=>{text+=chunk;const match=text.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
    server.once('exit',code=>{clearTimeout(timer);reject(Error('Stem UI server exited '+code+': '+stderr));});
});}
async function shot(page,name){if(screenshots)await page.screenshot({path:path.join(screenshots,'mac-stems-'+name+'.png')});}
async function layout(page){
    const clipped=await page.evaluate(()=>['stems-heading','stems-close','stems-source','stems-message',
        ...[...document.querySelectorAll('#stems-dialog button:not([hidden]),#stems-dialog a')].map(el=>el.id).filter(Boolean)]
        .filter(id=>{const r=document.getElementById(id).getBoundingClientRect();return r.width<=0||r.height<=0||r.top<0||r.bottom>innerHeight+1||r.left<0||r.right>innerWidth+1;}));
    assert.deepEqual(clipped,[],'Stem sheet controls clipped');
    assert(await page.locator('#stems-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Stem sheet has horizontal overflow');
}
(async()=>{
    let browser,page;
    try{
        const base=await start();
        browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM||undefined,args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
        page=await browser.newPage({viewport:{width:569,height:548},acceptDownloads:true});
        const errors=[],actions=[];
        page.on('pageerror',error=>errors.push(error.stack));
        let job={available:true,status:'idle',progress:0,message:'Ready',stems:[]};
        let polls=0,starts=0,folderOpened=false,token='',wav;
        await page.route('**/api/state',async route=>{
            const response=await route.fetch();const value=await response.json();
            if(job.status==='running'){value.busy=true;value.progress='Separating stems…';}
            await route.fulfill({response,json:value});
        });
        await page.route('**/api/stems',async route=>{
            if(job.status==='running'&&starts>1&&++polls>=3){job={...job,status:'done',progress:1,message:'Tracks ready.',
                stems:(job.mode==='piano'?['piano','accompaniment']:['vocals','drums','bass','piano','other']).map(id=>({id,label:id,filename:id+'.wav'}))};}
            await route.fulfill({json:job});
        });
        await page.route('**/api/stems-start',async route=>{
            const mode=route.request().postDataJSON().mode;assert(['five','piano'].includes(mode));actions.push('start');++starts;polls=0;
            job={available:true,mode,status:'running',progress:.2,message:'Separating this recording…',jobId:'fixture-job-'+starts,
                sourceRevision:starts,sourceName:'A local recording.wav',stems:[]};
            await route.fulfill({json:job});
        });
        await page.route('**/api/stems-cancel',async route=>{
            actions.push('cancel');job={...job,status:'cancelled',message:'Separation cancelled.',progress:0};
            await route.fulfill({json:job});
        });
        await page.route('**/api/stems-folder',async route=>{
            assert.equal(route.request().postDataJSON().jobId,job.jobId);folderOpened=true;
            await route.fulfill({json:{ok:true}});
        });
        await page.route('**/api/stems-select',async route=>{
            const selected=route.request().postDataJSON();assert.equal(selected.jobId,job.jobId);assert(['vocals','piano'].includes(selected.stem));
            const response=await page.request.post(base+'/api/import',{headers:{'X-Blaze-Token':token,'X-File-Name':selected.stem==='piano'?'Piano.wav':'Vocals.wav'},data:wav});
            assert(response.ok());actions.push('select');await route.fulfill({json:{ok:true}});
        });
        await page.goto(base);
        await page.waitForFunction(()=>window.BlazeMacStems&&sourceName==='A local recording.wav');
        token=await page.locator('meta[name=blaze-token]').getAttribute('content');
        const audio=await page.request.get(base+'/media?token='+encodeURIComponent(token));assert(audio.ok());wav=await audio.body();
        await page.evaluate(()=>{window.testMedia=document.getElementById('media');window.BlazeMac.installNativeChrome({sidebar:true,search:true});});
        await page.locator('#split-stems').waitFor({state:'visible'});
        await page.locator('#split-stems').click();
        await page.locator('#stems-start').click();
        await page.locator('#stems-cancel').waitFor({state:'visible'});
        await layout(page);await shot(page,'running');
        await page.locator('#stems-close').click();
        assert.equal(job.status,'running','Closing the sheet cancelled the job');
        await page.locator('#split-stems').click();
        await page.locator('#stems-cancel').click();
        await page.waitForFunction(()=>window.BlazeMacStems.snapshot().status==='cancelled');
        assert.deepEqual(actions,['start','cancel']);
        await page.locator('#stems-start').click();
        await page.locator('.stem-result').first().waitFor();
        assert.equal(await page.locator('.stem-result').count(),5);
        await page.locator('#stems-folder').click();assert(folderOpened);
        await layout(page);await shot(page,'complete');
        for(const [width,height] of [[570,540],[813,632]]){
            await page.setViewportSize({width,height});await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
            await layout(page);
        }
        const download=page.waitForEvent('download');await page.getByRole('link',{name:'Save Vocals WAV',exact:true}).click();
        const file=await download;assert.equal(file.suggestedFilename(),'Vocals.wav');
        const downloadUrl=new URL(file.url());assert.equal(downloadUrl.searchParams.get('token'),token);
        assert.equal(downloadUrl.searchParams.get('jobId'),job.jobId);assert.equal(downloadUrl.searchParams.get('stem'),'vocals');
        assert.deepEqual(fs.readFileSync(await file.path()),wav,'Downloaded WAV bytes changed');
        await page.getByRole('button',{name:'Open Vocals in Studio',exact:true}).click();
        await page.waitForFunction(()=>!document.getElementById('stems-dialog').open&&sourceName==='Vocals.wav');
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia),'Opening a stem created a second player');
        assert.equal(await page.locator('#studio-panel').isVisible(),true);
        await page.locator('#mini-play').click();
        await page.waitForFunction(()=>{const m=document.getElementById('media');return !m.paused&&m.currentTime>.1;});
        assert.deepEqual(actions,['start','cancel','start','select']);
        await page.locator('#mini-play').click();
        await page.setViewportSize({width:569,height:548});
        await page.emulateMedia({reducedMotion:'reduce',colorScheme:'dark'});
        await page.evaluate(async()=>{applyAppearance('dark');await window.BlazeMacStems.open();});
        await layout(page);await shot(page,'complete-dark');
        await page.keyboard.press('Escape');
        // The dialog closes before its queued close event restores focus.
        await page.waitForFunction(()=>!document.getElementById('stems-dialog').open&&document.activeElement.id==='split-stems');
        assert.equal(await page.locator('#stems-dialog').evaluate(el=>el.open),false);
        assert.equal(await page.evaluate(()=>document.activeElement.id),'split-stems','Closing the sheet lost keyboard focus');
        await page.locator('#split-stems').click();
        await page.locator('#stems-piano').click();
        await page.waitForFunction(()=>window.BlazeMacStems.snapshot().mode==='piano'&&window.BlazeMacStems.snapshot().status==='done');
        await page.getByRole('button',{name:'Open Piano in Studio',exact:true}).waitFor();
        assert.equal(await page.locator('.stem-result').count(),2);
        await layout(page);await shot(page,'piano');
        const pianoDownload=page.waitForEvent('download');
        await page.getByRole('link',{name:'Save Piano WAV',exact:true}).click();
        const pianoFile=await pianoDownload;assert.equal(pianoFile.suggestedFilename(),'Piano.wav');
        assert.deepEqual(fs.readFileSync(await pianoFile.path()),wav);
        await page.getByRole('button',{name:'Open Piano in Studio',exact:true}).click();
        await page.waitForFunction(()=>sourceName==='Piano.wav'&&!document.getElementById('stems-dialog').open);
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia));
        assert.deepEqual(errors,[]);
        console.log('Mac stems UI PASS: start/progress, close and reopen without cancellation, explicit cancel/retry, five separate outputs, token-bound WAV export, folder action, same-player Studio handoff and real WAV playback, compact sheet geometry. Controlled separation worker; no model quality or native AppKit claim.');
    }catch(error){if(stderr.trim())console.error(stderr);if(page)await shot(page,'failure').catch(()=>{});throw error;}
    finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exitCode=1;});
