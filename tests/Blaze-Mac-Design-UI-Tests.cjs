/* Mac content QA against the authenticated loopback server and real media.
 * Browser plugin not available: regular Playwright is used. Native AppKit
 * geometry is represented by the WKWebView detail viewport, not simulated as
 * proof of Cocoa rendering. Catalogue data is controlled; no live YouTube.
 */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..');
const screenshots=process.env.BLAZE_UI_SCREENSHOTS;
if(screenshots)fs.mkdirSync(screenshots,{recursive:true});
const fixture=String.raw`
import math, shutil, struct, subprocess, tempfile, wave
from pathlib import Path
from music_studio.server import Studio, create_server
from music_studio.downloads import Downloads
from music_studio.mac_smoke import MacSmokeCatalogue

with tempfile.TemporaryDirectory(prefix='blaze-mac-content-') as directory:
    data=Path(directory)
    artwork=data/'discovery-fixtures'
    artwork.mkdir()
    for name in ('piano','acoustic','jazz','sunset'):
        shutil.copy2(Path('android/app/src/main/res/drawable-nodpi')/('discovery_'+name+'.png'), artwork/(name+'.png'))
    output=data/'downloads'
    output.mkdir()
    audio=output/'Golden Hour.wav'
    with wave.open(str(audio),'wb') as target:
        target.setparams((1,2,22050,0,'NONE','not compressed'))
        target.writeframes(b''.join(struct.pack('<h',int(2500*math.sin(i*2*math.pi*220/22050))) for i in range(22050*30)))
    video=output/'Live Session.webm'
    decoder=shutil.which('ffmpeg')
    if not decoder: raise RuntimeError('Install FFmpeg for real video decoding QA.')
    # Chromium's CI build omits AVC; native Cocoa package tests cover AVC/AAC.
    subprocess.run([decoder,'-y','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=10',
                    '-i',str(audio),'-t','10','-c:v','libvpx','-deadline','realtime',
                    '-cpu-used','8','-pix_fmt','yuv420p','-c:a','libopus',str(video)],check=True,timeout=30)
    studio=Studio(data,decoder)
    studio.presentation='mac'
    studio.discovery=MacSmokeCatalogue(data,audio,video)
    studio.downloader=Downloads(data,data/'tools',output)
    server=create_server(studio)
    print('http://127.0.0.1:'+str(server.server_port),flush=True)
    try: server.serve_forever()
    finally: server.server_close();studio.close()
`;
const server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',fixture],{cwd:root,stdio:['ignore','pipe','pipe']});
let stderr='';server.stderr.on('data',chunk=>stderr+=chunk);
async function start(){return new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Mac content startup timed out: '+stderr)),20000);
    server.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
    server.once('exit',code=>{clearTimeout(timer);reject(Error('Studio exited '+code+': '+stderr));});
});}
async function shot(page,name){if(screenshots)await page.screenshot({path:path.join(screenshots,'mac-'+name+'.png'),fullPage:false});}
async function fit(page,ids,message){
    const invalid=await page.evaluate(ids=>ids.flatMap(id=>{
        const element=document.getElementById(id),r=element?.getBoundingClientRect();
        return r&&r.width>0&&r.height>0&&r.top>=0&&r.left>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1?[]:[{id,rect:r?.toJSON()}];
    }),ids);
    assert.deepEqual(invalid,[],message);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mac detail has horizontal overflow');
}
async function voicingsFit(page){
    const layout=await page.locator('#diagram-strip').evaluate(strip=>{
        const r=strip.getBoundingClientRect(),top=r.top+strip.clientTop,bottom=top+strip.clientHeight;
        const cards=[...strip.querySelectorAll('.diagram-card')];
        const note=document.getElementById('diagram-note').getBoundingClientRect();
        const actions=document.querySelector('.play-workspace .actions').getBoundingClientRect();
        return {count:cards.length,stripHeight:strip.clientHeight,scrollHeight:strip.scrollHeight,
            noteFits:note.height>0&&note.top>=r.bottom-1&&note.bottom<=actions.top+1,
            cards:cards.map(card=>{const c=card.getBoundingClientRect();return {
                insideStrip:c.top>=top-1&&c.bottom<=bottom+1,
                contentFits:card.scrollHeight<=card.clientHeight+1,
                height:c.height,top:c.top,bottom:c.bottom};})};
    });
    assert.equal(layout.count,3,'Standard voicing view should show three cards');
    assert(layout.scrollHeight<=layout.stripHeight+1,'Standard voicings require vertical scrolling: '+JSON.stringify(layout));
    assert(layout.cards.every(card=>card.insideStrip&&card.contentFits),'A voicing card border or content is clipped: '+JSON.stringify(layout));
    assert(layout.noteFits,'The voicing note overlaps the strip or footer actions: '+JSON.stringify(layout));
}
(async()=>{
    let browser,page;
    try{
        const base=await start();
        browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM||undefined,args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
        page=await browser.newPage({viewport:{width:1230,height:840}});
        const errors=[],selections=[];
        page.on('pageerror',error=>errors.push(error.stack));
        page.on('console',message=>{if(message.type()==='error'&&!message.location().url.endsWith('/favicon.ico'))errors.push(message.text());});
        page.on('request',request=>{if(request.method()==='POST'&&request.url()===base+'/api/discovery-select')selections.push(request.postDataJSON());});
        await page.goto(base);
        assert.equal(await page.title(),'Blaze');
        assert.equal(new URL(page.url()).origin,base);
        assert.equal(await page.locator('html').getAttribute('data-presentation'),'mac');
        await page.waitForFunction(()=>!!window.BlazeMac);
        await page.evaluate(()=>window.BlazeMac.installNativeChrome({sidebar:true,search:true}));
        await page.waitForFunction(()=>document.body.dataset.nativeSidebar==='true');
        await page.locator('.discovery-featured').first().waitFor();
        assert.equal(await page.locator('.discovery-featured').count(),3);
        assert.equal(await page.locator('.discovery-featured img').count(),3,'Featured artwork failed to load');
        assert.equal(await page.locator('.discovery-card img').count(),6,'Catalogue artwork failed to load');
        await page.waitForFunction(()=>[...document.querySelectorAll('.discovery-card img')].every(image=>image.complete&&image.naturalWidth>0));
        await page.locator('.discovery-card img').evaluateAll(images=>Promise.all(images.map(image=>image.decode())));
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        assert(await page.locator('.discovery-featured').evaluateAll(cards=>cards.every(card=>{
            const r=card.getBoundingClientRect(),art=card.querySelector('.discovery-art').getBoundingClientRect();
            return art.width>=r.width-2&&art.height>=r.height-2;
        })),'Featured artwork must cover the card rather than appear as a small thumbnail');
        assert.equal(await page.locator('video').count(),1);
        assert.equal(await page.locator('header').isVisible(),false);
        await shot(page,'explore-wide');

        await page.evaluate(()=>{window.testMedia=document.getElementById('media');window.BlazeMac.search('acoustic');});
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('acoustic acoustic session'));
        await page.locator('.discovery-primary').first().click();
        await page.waitForFunction(()=>{const m=document.getElementById('media');return !m.paused&&m.currentTime>.1&&m.duration>29;});
        assert.equal(await page.locator('#now-dialog').evaluate(el=>el.open),false,'Mac selection interrupted browsing');
        assert.equal(await page.locator('#explore-panel').isVisible(),true);
        await page.locator('#mini-play').click();
        await page.waitForFunction(()=>document.getElementById('media').paused);
        await fit(page,['mini-open','mini-play','mac-mini-seek'],'Wide compact transport clipped');
        // Queue changes update the already-open detail surface as well as the
        // persistent transport, without replacing the shared media element.
        await page.evaluate(()=>window.BlazeMac.action('open-player'));
        await page.locator('#now-dialog').waitFor({state:'visible'});
        await page.locator('#mini-next').click();
        await page.waitForFunction(()=>{const m=document.getElementById('media');return m.videoWidth===320&&!m.paused&&m.currentTime>.1;});
        assert(await page.locator('#now-video-slot #media').isVisible(),'Queued video was hidden in the Studio preview');
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia),'Queue transition replaced the player');
        assert(await page.locator('#media').evaluate(el=>{
            const c=document.createElement('canvas');c.width=32;c.height=18;const g=c.getContext('2d');g.drawImage(el,0,0,32,18);
            return g.getImageData(0,0,32,18).data.some((value,index)=>index%4!==3&&value>100);
        }),'Queued video did not draw a decoded frame');
        await shot(page,'queue-video-wide');
        await page.locator('.discovery-primary').first().click();
        await page.waitForFunction(()=>{const m=document.getElementById('media');return m.classList.contains('audio-only')&&m.duration>29&&!m.paused;});
        assert.equal(await page.locator('#now-dialog').evaluate(el=>el.open),true);
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia&&el.parentElement.classList.contains('preview-panel')),'Audio transition did not restore the shared media to its preview owner');
        assert(await page.locator('#now-artwork').isVisible(),'Video-to-audio transition did not restore artwork');
        // Exercise the real ended event, which uses the same queue handoff.
        await page.evaluate(()=>{document.getElementById('media').currentTime=29.95;});
        await page.waitForFunction(()=>{const m=document.getElementById('media');return m.videoWidth===320&&!m.paused&&m.currentTime>.1;});
        assert(await page.locator('#now-video-slot #media').isVisible(),'Automatic queue advance hid the video');
        assert.equal(await page.locator('#now-dialog').evaluate(el=>el.open),true);
        await page.evaluate(()=>window.BlazeMac.action('close-player'));
        await page.locator('.discovery-primary').first().click();
        await page.waitForFunction(()=>{const m=document.getElementById('media');return m.classList.contains('audio-only')&&m.duration>29&&!m.paused;});
        assert.equal(await page.locator('#now-dialog').evaluate(el=>el.open),false,'Closed player reopened during a queue selection');
        await page.locator('#mini-play').click();
        await page.waitForFunction(()=>document.getElementById('media').paused);
        await page.locator('#mac-mini-seek').fill('400');
        await page.locator('#mac-mini-seek').dispatchEvent('input');
        await page.locator('#mac-mini-seek').dispatchEvent('change');
        await page.waitForFunction(()=>{const m=document.getElementById('media');return m.paused&&m.currentTime>11&&m.currentTime<13;});
        await shot(page,'search-wide');

        // Desktop navigation preserves the same player and paused clock.
        for(const section of ['downloads','library','studio']){
            await page.evaluate(section=>window.BlazeMac.navigate(section),section);
            assert(await page.locator('#media').evaluate(el=>el===window.testMedia&&el.paused&&el.currentTime>11));
            await fit(page,['mini-open','mini-play','mac-mini-seek'],'Navigation hid the compact player');
        }
        // This synthetic result tests notation/layout, not model inference.
        await page.evaluate(()=>{
            seek(0);
            applyResult({duration:30,key:'C major',tempo_bpm:120,analysis_seconds:0,model:{name:'Mac UI fixture'},
                beats:Array.from({length:60},(_,i)=>i*.5),waveform:Array.from({length:100},(_,i)=>.1+Math.abs(Math.sin(i*.7))*.6),
                chords:[{start:0,end:10,chord:'C:maj'},{start:10,end:20,chord:'G:maj'},{start:20,end:30,chord:'A:min'}]});
        });
        await page.locator('.diagram-card canvas').first().waitFor();
        await fit(page,['bar-flow','diagram-strip','analyze','mini-play'],'Wide Studio controls clipped');
        await shot(page,'studio-wide');
        // Model the 15 px timeline gutter seen with classic native scrollbars.
        // Chromium may paint an overlay; reserve any missing space as padding.
        await page.evaluate(()=>{
            const flow=document.getElementById('bar-flow'),style=getComputedStyle(flow);
            const borders=parseFloat(style.borderTopWidth)+parseFloat(style.borderBottomWidth);
            const gutter=flow.offsetHeight-flow.clientHeight-borders;
            flow.style.paddingBottom=(parseFloat(style.paddingBottom)+Math.max(0,15-gutter))+'px';
            dispatchEvent(new Event('resize'));
        });
        for(const [width,height] of [[570,540],[569,548]]){
            await page.setViewportSize({width,height});
            await fit(page,['bar-flow','diagram-strip','analyze','mini-play'],'Compact Studio controls clipped');
            assert(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1),'Compact Studio requires page scrolling');
            assert(await page.locator('.diagram-card canvas').evaluateAll(elements=>elements.every(el=>{const r=el.getBoundingClientRect();return r.height>=65&&r.top>=0&&r.bottom<=innerHeight;})),'Compact voicing keyboards clipped');
            await voicingsFit(page);
            await shot(page,'studio-compact-'+width+'x'+height);
        }
        await shot(page,'studio-compact');

        await page.evaluate(()=>window.BlazeMac.action('settings'));
        await page.locator('#settings-dialog').waitFor({state:'visible'});
        // Native navigation must not change the workspace behind a modal sheet.
        await page.evaluate(()=>window.BlazeMac.navigate('downloads'));
        assert.equal(await page.locator('#studio-panel').isVisible(),true);
        await page.locator('#appearance').selectOption('dark');
        await page.evaluate(()=>appearanceSave);
        assert.equal(await page.locator('html').getAttribute('data-appearance'),'dark');
        await page.locator('#close-settings').click();
        await page.emulateMedia({reducedMotion:'reduce',colorScheme:'dark'});
        await shot(page,'studio-compact-dark');

        // Native file selection must invalidate an in-flight discovery result.
        // The fixture deliberately completes that reply after cancellation.
        await page.evaluate(async()=>{window.nativeChoiceBytes=await(await fetch(document.getElementById('media').currentSrc)).arrayBuffer();});
        await page.evaluate(()=>window.BlazeMac.search('slow handoff'));
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('slow handoff acoustic session'));
        const preparation=page.waitForResponse(response=>response.url()===base+'/api/discovery-prepare'&&response.request().method()==='POST');
        await page.locator('.discovery-primary').first().click();
        const pending=(await (await preparation).json()).requestId;
        const lateReply=page.waitForResponse(response=>response.url()===base+'/api/discovery?id='+encodeURIComponent(pending));
        await page.evaluate(async()=>{
            if(!window.BlazeMac.beginImport())throw Error('Native file handoff was refused');
            const response=await fetch('/api/import',{method:'POST',headers:{
                'X-Blaze-Token':document.querySelector('meta[name="blaze-token"]').content,
                'X-File-Name':encodeURIComponent('Native Choice.wav')},body:window.nativeChoiceBytes});
            if(!response.ok)throw Error('The selected local media could not be imported');
            await window.BlazeMac.importCompleted();
        });
        await lateReply;
        await page.evaluate(()=>refresh());
        assert(await page.evaluate(()=>sourceName==='Native Choice.wav'&&document.getElementById('media')===window.testMedia),'Late preparation replaced the native file choice');
        assert(!selections.some(value=>value.requestId===pending),'A cancelled discovery generation selected stale media');

        await page.evaluate(()=>window.BlazeMac.search('landscape'));
        await page.locator('[data-discovery-filter=videos]').click();
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('landscape live session'));
        await page.locator('.discovery-card[data-kind=video] .discovery-primary').click();
        await page.waitForFunction(()=>{const m=document.getElementById('media');return m.videoWidth===320&&m.videoHeight===180&&!m.paused&&m.currentTime>.1;});
        assert.equal(await page.locator('#now-dialog').evaluate(el=>el.open),false);
        await page.locator('#mini-play').click();
        await page.evaluate(()=>window.BlazeMac.action('open-player'));
        await page.locator('#now-dialog').waitFor({state:'visible'});
        assert.equal(await page.locator('#now-dialog').evaluate(el=>el.matches(':modal')),false,'Mac detail became a blocking modal');
        await fit(page,['now-close','now-studio','mini-play','mac-mini-seek'],'Compact expanded video controls clipped');
        assert(await page.locator('#media').evaluate(el=>{
            const c=document.createElement('canvas');c.width=32;c.height=18;const g=c.getContext('2d');g.drawImage(el,0,0,32,18);
            return g.getImageData(0,0,32,18).data.some((value,index)=>index%4!==3&&value>100);
        }),'Decoded video frame blank');
        await shot(page,'video-compact-dark');
        const position=await page.locator('#media').evaluate(el=>el.currentTime);
        await page.locator('#now-studio').click();
        assert(await page.locator('#media').evaluate((el,position)=>el===window.testMedia&&el.paused&&Math.abs(el.currentTime-position)<.1,position),'Studio lost the paused video');

        await page.evaluate(()=>window.BlazeMac.search(''));
        await page.waitForFunction(()=>document.querySelectorAll('.discovery-featured').length===3);
        await shot(page,'explore-compact-dark');
        await page.emulateMedia({reducedMotion:'no-preference',colorScheme:'light'});
        await page.evaluate(()=>window.BlazeMac.action('settings'));
        await page.locator('#appearance').selectOption('light');await page.evaluate(()=>appearanceSave);await page.locator('#close-settings').click();
        await page.setViewportSize({width:1230,height:840});
        await page.evaluate(()=>window.BlazeMac.action('open-player'));
        await fit(page,['now-close','now-studio','mini-play','mac-mini-seek'],'Wide detail player controls clipped');
        await shot(page,'video-wide');
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('#now-dialog').evaluate(el=>el.open),false);
        assert(await page.locator('#mini-open').evaluate(el=>el===document.activeElement),'Closing playback detail lost keyboard focus');
        const focusRequest=await page.evaluate(()=>window.BlazeMac.snapshot().focusSearchRequest);
        await page.keyboard.press('Meta+f');
        assert.equal(await page.evaluate(()=>window.BlazeMac.snapshot().focusSearchRequest),focusRequest+1,'Command-F did not request native search focus');
        await page.keyboard.press('Meta+,');
        await page.locator('#settings-dialog').waitFor({state:'visible'});
        await page.locator('#close-settings').click();
        assert.deepEqual(errors,[]);
        console.log('Mac content UI PASS: controlled artwork, native bridge search/navigation, real WAV and VP8/Opus decode, selection keeps browsing, one persistent player, seek, Studio notation,570x540 detail fit, modal navigation guard, late preparation cannot replace native import, nonmodal expanded video, keyboard focus/shortcuts, light/dark/reduced motion, no console errors. AppKit/native glass and live YouTube require separate checks.');
    }catch(error){
        if(stderr.trim())console.error(stderr);
        if(page&&screenshots)await shot(page,'failure').catch(()=>{});
        throw error;
    }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exitCode=1;});
