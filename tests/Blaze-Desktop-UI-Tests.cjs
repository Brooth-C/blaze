/* Real loopback UI regression test. Requires Playwright Chromium and Studio Python deps.
 * BLAZE_TEST_PYTHON=/path/to/python PLAYWRIGHT_MODULE=/path/to/playwright
 * PLAYWRIGHT_CHROMIUM=/path/to/chrome node tests/Blaze-Desktop-UI-Tests.cjs
 */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const screenshots=process.env.BLAZE_UI_SCREENSHOTS;
if(screenshots)fs.mkdirSync(screenshots,{recursive:true});
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..');
const server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',`
import tempfile, wave, shutil, sys, threading, functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from music_studio.server import Studio, create_server
from music_studio.downloads import Downloads
with tempfile.TemporaryDirectory(prefix='blaze-ui-test-') as directory:
    root=Path(directory)
    output=root/'media'; output.mkdir()
    with wave.open(str(output/'Practice.wav'),'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(22050)
        audio.writeframes(b'\\0\\0'*22050*12)
    (output/'Video.webm').write_bytes(b'fixture used for filtering only')
    tools=root/'tools'; tools.mkdir()
    downloader=Path(sys.executable).parent/'yt-dlp'
    if not downloader.is_file():
        downloader=Path(shutil.which('yt-dlp') or '')
    if not downloader.is_file(): raise RuntimeError('Install yt-dlp for the local download UI test.')
    (tools/'yt-dlp').symlink_to(downloader)
    decoder=shutil.which('ffmpeg')
    if not decoder: raise RuntimeError('Install FFmpeg for the local download UI test.')
    (tools/'ffmpeg').symlink_to(decoder)
    class QuietSource(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    fixture=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietSource,directory=str(output)))
    threading.Thread(target=fixture.serve_forever,daemon=True).start()
    studio=Studio(root,decoder)
    studio.downloader=Downloads(root,root/'tools',output)
    server=create_server(studio)
    print('http://127.0.0.1:'+str(server.server_port)+'\\nFIXTURE=http://127.0.0.1:'+str(fixture.server_port)+'/Practice.wav',flush=True)
    try: server.serve_forever()
    finally: fixture.shutdown(); fixture.server_close(); server.server_close(); studio.close()
`],{cwd:root,stdio:['ignore','pipe','pipe']});
let fixtureURL='';
let stderr='';server.stderr.on('data',chunk=>stderr+=chunk);
(async()=>{
    let browser;
    try{
        const base=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(Error('Studio startup timed out: '+stderr)),15000);server.stdout.on('data',chunk=>{output+=chunk;const fixture=output.match(/FIXTURE=(http:\/\/127\.0\.0\.1:\d+\/Practice\.wav)/);if(fixture)fixtureURL=fixture[1];const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});server.once('exit',code=>{clearTimeout(timer);reject(Error('Studio exited '+code+': '+stderr));});});
        browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM||undefined,args:['--no-sandbox']});
        const page=await browser.newPage({viewport:{width:1536,height:1024}}),errors=[];
        page.on('pageerror',error=>errors.push(error.message));
        await page.goto(base);
        await page.waitForFunction(()=>!document.getElementById('download-start').disabled);
        assert.equal(await page.locator('[role=tab][aria-selected=true]').textContent(),'Downloads');
        if(screenshots)await page.screenshot({path:path.join(screenshots,'downloads.png')});
        await page.locator('#download-start').click();
        assert.match(await page.locator('#download-error').textContent(),/Paste a link/);
        await page.locator('[data-mode=video]').click();assert(await page.locator('#video-options').isVisible());assert(!(await page.locator('#audio-options').isVisible()));
        await page.locator('#download-urls').fill('not-a-url');await page.locator('#download-start').click();
        await page.waitForFunction(()=>!document.getElementById('download-start').disabled);
        assert(await page.locator('#download-error').isVisible());
        await page.locator('#tab-library').click();await page.waitForFunction(()=>document.querySelectorAll('#download-files .download-row').length===2);
        if(screenshots)await page.screenshot({path:path.join(screenshots,'library.png')});
        await page.locator('[data-filter=video]').click();assert.equal(await page.locator('.library-row').count(),1);assert.match(await page.locator('.library-row').textContent(),/Video.webm/);
        await page.locator('#library-search').fill('missing');assert.match(await page.locator('#download-files').textContent(),/No matching files/);
        await page.locator('[data-filter=audio]').click();await page.locator('#library-search').fill('practice');
        await page.getByRole('button',{name:'Open Practice.wav in Studio'}).click();
        await page.waitForFunction(()=>Math.abs(document.getElementById('media').duration-12)<.01);
        await page.locator('#play').click();await page.waitForFunction(()=>document.getElementById('media').currentTime>.1);
        await page.locator('#play').click();
        const waveBox=await page.locator('#wave').boundingBox();await page.mouse.click(waveBox.x+waveBox.width*.6,waveBox.y+waveBox.height*.5);
        assert(await page.locator('#media').evaluate(el=>el.currentTime>6));
        await page.mouse.move(waveBox.x+waveBox.width*.2,waveBox.y+waveBox.height*.5);await page.mouse.down();await page.mouse.move(waveBox.x+waveBox.width*.8,waveBox.y+waveBox.height*.5,{steps:6});await page.mouse.up();assert(await page.locator('#media').evaluate(el=>el.currentTime>9),'Live scrubbing did not follow pointer');
        if(screenshots)await page.screenshot({path:path.join(screenshots,'studio.png')});
        await page.locator('#studio-settings').click();assert(await page.locator('#settings-dialog').isVisible());await page.locator('#appearance').selectOption('dark');assert.equal(await page.locator('html').getAttribute('data-appearance'),'dark');if(screenshots)await page.screenshot({path:path.join(screenshots,'settings-dark.png')});await page.evaluate(()=>appearanceSave);await page.reload();await page.waitForFunction(()=>document.documentElement.dataset.appearance==='dark'&&document.getElementById('media').duration===12);await page.locator('#studio-settings').click();assert.equal(await page.locator('#appearance').inputValue(),'dark');await page.locator('#appearance').selectOption('light');await page.evaluate(()=>appearanceSave);await page.locator('#close-settings').click();
        // Synthetic analysis exercises rendered chords; it is not an inference test.
        await page.evaluate(()=>{
            seek(0);
            applyResult({duration:12,key:'C major',tempo_bpm:120,analysis_seconds:0,model:{name:'UI test fixture'},beats:Array.from({length:24},(_,i)=>i*.5),waveform:Array.from({length:100},(_,i)=>.1+Math.abs(Math.sin(i*.7))*.6),chords:[{start:0,end:4,chord:'C:maj'},{start:4,end:8,chord:'G:maj'},{start:8,end:12,chord:'A:min'}]});
            updatePlayback();
        });
        assert.equal(await page.locator('.diagram-card canvas').count(),3);
        assert(await page.locator('.reference-cell').count()>0);
        await page.locator('#up').click();assert.equal(await page.locator('#shift').textContent(),'+1');
        await page.locator('#guitar').click();assert.equal(await page.locator('#instrument').inputValue(),'guitar');
        await page.locator('#piano').click();await page.locator('#reset').click();
        if(screenshots)await page.screenshot({path:path.join(screenshots,'studio-fixture.png')});
        await page.setViewportSize({width:780,height:600});
        assert(await page.locator('#studio-settings').evaluate(el=>el.getBoundingClientRect().bottom<=600));
        assert(await page.locator('.diagram-card canvas').evaluateAll(canvases=>canvases.every(canvas=>canvas.getBoundingClientRect().bottom<=canvas.parentElement.getBoundingClientRect().bottom)),'Clipped keyboard canvas');
        if(screenshots)await page.screenshot({path:path.join(screenshots,'studio-compact.png')});
        await page.setViewportSize({width:1440,height:960});
        const wav=Buffer.alloc(44+22050*2);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(22050,24);wav.writeUInt32LE(44100,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
        await page.locator('#import').setInputFiles({name:'Imported.wav',mimeType:'audio/wav',buffer:wav});
        await page.waitForFunction(()=>document.getElementById('filename').textContent==='Imported.wav'&&Math.abs(document.getElementById('media').duration-1)<.01).catch(async error=>{console.error(await page.evaluate(()=>({name:document.getElementById('filename').textContent,duration:document.getElementById('media').duration,error:document.getElementById('error').textContent})));throw error;});
        await page.reload();await page.waitForFunction(()=>document.getElementById('filename').textContent==='Imported.wav'&&Math.abs(document.getElementById('media').duration-1)<.01);
        for(const [width,height] of [[1536,1024],[1440,960],[780,600],[390,844],[320,740]]){
            await page.setViewportSize({width,height});
            assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Horizontal overflow at ${width}`);
            if(width>760){const bottom=await page.locator('#studio-settings').evaluate(el=>el.getBoundingClientRect().bottom);assert(bottom<=height,`Clipped Studio controls at ${width}x${height}`);}
        }
        await page.setViewportSize({width:390,height:844});
        await page.locator('#tab-downloads').click();if(screenshots)await page.screenshot({path:path.join(screenshots,'downloads-phone.png'),fullPage:true});
        await page.setViewportSize({width:780,height:600});
        await page.locator('#tab-studio').click();
        await page.evaluate(()=>{document.documentElement.style.fontSize='24px';dispatchEvent(new Event('resize'));});
        await page.locator('#studio-settings').scrollIntoViewIfNeeded();assert(await page.locator('#studio-settings').isVisible());
        await page.evaluate(()=>{document.documentElement.style.fontSize='';dispatchEvent(new Event('resize'));});
        await page.keyboard.press('Control+f');assert(await page.locator('#library-panel').isVisible());assert(await page.locator('#library-search').evaluate(el=>el===document.activeElement));
        await page.keyboard.press('Control+l');assert(await page.locator('#download-urls').evaluate(el=>el===document.activeElement));
        await page.locator('#tab-downloads').click();await page.locator('#tab-downloads').focus();await page.keyboard.press('ArrowRight');assert.equal(await page.locator('[role=tab][aria-selected=true]').textContent(),'Library');
        await page.locator('#tab-downloads').click();
        assert(fixtureURL,'Missing local download fixture URL');
        await page.locator('#download-urls').fill(fixtureURL);await page.locator('[data-mode=audio]').click();await page.locator('#download-format').selectOption('wav');
        await page.locator('.download-options summary').click();await page.locator('#download-playlist').check();await page.locator('#download-playlist').uncheck();
        await page.locator('#download-start').click();
        await page.waitForFunction(()=>[...document.querySelectorAll('#download-jobs small')].some(el=>el.textContent==='Complete'),{},{timeout:60000});
        if(screenshots)await page.screenshot({path:path.join(screenshots,'download-complete.png')});
        assert.deepEqual(errors,[]);console.log('Desktop UI PASS: real local download, queue validation, filters/search, selection, playback/seek, import, chord rendering/transposition, settings, keyboard navigation and five viewport sizes plus large text.');
    }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exitCode=1;});
