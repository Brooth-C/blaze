/* Real local player/server, controlled musical evidence. This is not a model
 * accuracy, native AppKit, VoiceOver or physical-device performance test. */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const fixture = fs.readFileSync(path.join(__dirname, 'Blaze-Mac-Studio-UI-Tests.cjs'), 'utf8').match(/const fixture=String.raw`([\s\S]+?)`;/)[1];
const server = spawn(process.env.BLAZE_TEST_PYTHON || 'python3', ['-u', '-c', fixture], {cwd:root, stdio:['ignore','pipe','pipe']});
let stderr = ''; server.stderr.on('data', data => stderr += data);
const output = process.env.BLAZE_UI_SCREENSHOTS;
if (output) fs.mkdirSync(output, {recursive:true});
const start = () => new Promise((resolve, reject) => {
    let text = ''; const timer = setTimeout(() => reject(Error(stderr || 'Harmony QA startup timed out')), 30000);
    server.stdout.on('data', chunk => {text += chunk; const match = text.match(/http:\/\/127\.0\.0\.1:\d+/); if (match) {clearTimeout(timer); resolve(match[0]);}});
    server.once('exit', code => {clearTimeout(timer); reject(Error('QA server exited ' + code + ': ' + stderr));});
});
const shot = async (page, name) => {if (output) await page.screenshot({path:path.join(output, 'mac-harmony-' + name + '.png')});};
const settle = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
(async () => {
    let browser, page;
    try {
        const base = await start();
        browser = await chromium.launch({headless:true,args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
        page = await browser.newPage({viewport:{width:1440,height:900}});
        const errors = []; page.on('pageerror', error => errors.push(error.message));
        await page.goto(base);
        await page.waitForFunction(() => window.BlazeMacHarmony && window.BlazeMacStudio);
        await page.evaluate(() => window.BlazeDesktop.selectSection('studio'));
        await page.waitForFunction(() => window.BlazeMacStudio.snapshot().waveformReady);
        assert(await page.locator('#harmony-empty').isVisible());
        assert.match(await page.locator('#harmony-status').innerText(), /Analyse this recording/);
        await shot(page, 'empty');
        await page.evaluate(() => {
            window.harmonyTestPlayer = document.getElementById('media');
            window.harmonyTestResult = {
                duration:64,key:'C major',tempo_bpm:120,analysis_seconds:0,model:{name:'Controlled timing evidence'},
                beats:Array.from({length:128}, (_,i) => i*.5),
                meter:{confidence:.9,bars:Array.from({length:32}, (_,i) => ({start:i*2,end:(i+1)*2,beats_per_bar:4,beats:[i*2,i*2+.5,i*2+1,i*2+1.5]}))},
                chords:[{start:0,end:.5,chord:'C:maj'},{start:.5,end:2,chord:'A:min'},
                    ...Array.from({length:31},(_,i) => ({start:(i+1)*2,end:(i+2)*2,chord:['F:maj','G:maj','C:maj','N','X','D:min'][i%6]}))]
            };
            applyResult(window.harmonyTestResult); window.BlazeMacHarmony.refresh();
        });
        await page.locator('.harmony-bar-ruler').first().waitFor();
        await page.waitForFunction(() => document.getElementById('daw-meter').textContent==='4 beats');
        assert(!/null|NaN|Infinity/.test(await page.locator('#daw-transport').innerText()),'Automatic meter corrupted the transport');
        assert.equal(await page.locator('.harmony-bar').count(),4);
        assert.equal(await page.locator('.harmony-bar-ruler').first().innerText(),'Bar 1');
        const proportions = await page.locator('.harmony-bar').first().evaluate(bar => {
            const lane=bar.querySelector('.harmony-region-lane').getBoundingClientRect();
            return [...bar.querySelectorAll('.harmony-region')].map(button => button.getBoundingClientRect().width/lane.width);
        });
        assert.equal(proportions.length,2,'Chord changes became separate bars');
        assert(Math.abs(proportions[0]-.25)<.01 && Math.abs(proportions[1]-.75)<.01,'Regions ignore musical duration');
        await shot(page,'subdivisions');
        await page.locator('.harmony-bar').first().getByRole('button',{name:/Seek to Am/}).click();
        await page.waitForFunction(() => Math.abs(document.getElementById('media').currentTime-.5)<.05 && document.getElementById('harmony-now').textContent==='Am');
        assert.equal(await page.locator('#harmony-next').innerText(),'F');
        assert.equal(await page.locator('.harmony-region[aria-current=true]').innerText(),'Am');
        await page.locator('#harmony-next-group').click();
        assert.equal(await page.locator('.harmony-bar-ruler').first().innerText(),'Bar 5');
        await page.locator('.harmony-bar-ruler').first().focus(); await page.keyboard.press('Enter');
        await page.waitForFunction(() => Math.abs(document.getElementById('media').currentTime-8)<.05);
        await page.locator('#harmony-follow').click();
        await page.evaluate(() => seek(20));
        await page.waitForFunction(() => document.querySelector('.harmony-bar-ruler').textContent==='Bar 9');
        await page.waitForFunction(() => /11\s+1/.test(document.getElementById('daw-bars').textContent));
        assert.match(await page.locator('#daw-bars').innerText(),/11\s+1/,'Transport lost its musical position for an automatic meter');

        const inspectorWidth = await page.locator('#daw-inspector').evaluate(element => element.getBoundingClientRect().width);
        await page.locator('#daw-inspector-resize').focus(); await page.keyboard.press('ArrowRight'); await settle(page);
        assert.equal(await page.locator('#daw-inspector').evaluate(element => element.getBoundingClientRect().width),inspectorWidth+8);
        await page.keyboard.press('ArrowLeft');
        const editorHeight = await page.locator('#daw-editor').evaluate(element => element.getBoundingClientRect().height);
        await page.locator('#daw-editor-resize').focus(); await page.keyboard.press('ArrowUp'); await settle(page);
        assert(Math.abs(await page.locator('#daw-editor').evaluate(element => element.getBoundingClientRect().height)-editorHeight-8)<1);
        await page.keyboard.press('ArrowDown');
        await page.locator('#daw-editor-toggle').click(); assert(await page.locator('#daw-editor').isHidden());
        assert.equal(await page.locator('#daw-editor-toggle').getAttribute('aria-expanded'),'false');
        await page.locator('#daw-editor-toggle').click(); await settle(page);
        assert(await page.locator('#daw-waveform').isVisible());
        await page.waitForFunction(() => window.BlazeMacStudio.snapshot().waveformsReady===window.BlazeMacStudio.snapshot().tracks.length);

        for (const [width,height] of [[1440,900],[1024,649],[780,572],[569,548]]) {
            await page.setViewportSize({width,height}); await settle(page);
            const clipped = await page.evaluate(() => ['daw-harmony','daw-arrangement','daw-editor','daw-play','daw-editor-toggle','daw-waveform'].filter(id => {
                const r=document.getElementById(id).getBoundingClientRect(); return !r.width || r.height<8 || r.left<0 || r.top<0 || r.right>innerWidth+1 || r.bottom>innerHeight+1;
            }));
            assert.deepEqual(clipped,[],'Primary workspace clipped at '+width);
            assert(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth+1));
            await shot(page,width+'-light');
            await page.evaluate(() => applyAppearance('dark')); await settle(page); await shot(page,width+'-dark');
            await page.evaluate(() => applyAppearance('light'));
        }
        await page.locator('#harmony-zoom').selectOption('8');
        await page.waitForFunction(() => document.querySelectorAll('.harmony-bar').length===8);
        assert(await page.locator('#harmony-bars').evaluate(element => element.scrollWidth>element.clientWidth));
        await page.locator('#harmony-bars').evaluate(element => {element.scrollLeft=element.scrollWidth;});
        assert(await page.locator('#harmony-bars').evaluate(element => element.scrollLeft>0));
        await page.setViewportSize({width:1440,height:900});
        await page.evaluate(() => {seek(0);document.getElementById('daw-play').click();});
        await page.waitForFunction(() => !document.getElementById('media').paused && document.getElementById('media').currentTime>.1);
        const performanceSample = await page.evaluate(() => new Promise(resolve => {
            const intervals=[],tasks=[];let previous=null;
            const start=performance.now();
            const observer=new PerformanceObserver(list => tasks.push(...list.getEntries().map(entry => entry.duration)));
            observer.observe({type:'longtask',buffered:false});
            function sample(now) {
                if(previous!==null)intervals.push(now-previous);previous=now;
                if(now-start<5000){requestAnimationFrame(sample);return;}
                observer.disconnect();intervals.sort((a,b)=>a-b);
                resolve({scope:'Five-second Chromium local-WAV playback sample; not physical-device FPS or native audio profiling',
                    frames:intervals.length,medianFrameIntervalMs:intervals[Math.floor(intervals.length*.5)],
                    p95FrameIntervalMs:intervals[Math.floor(intervals.length*.95)],longTasks:tasks.length,
                    maxLongTaskMs:Math.max(0,...tasks),playerAdvanced:document.getElementById('media').currentTime>4});
            }
            requestAnimationFrame(sample);
        }));
        assert(performanceSample.playerAdvanced,'The real player stopped during the UI sample');
        if(output)fs.writeFileSync(path.join(output,'performance.json'),JSON.stringify(performanceSample,null,2));
        await page.locator('#daw-play').click();
        await page.evaluate(() => {const value={...window.harmonyTestResult};delete value.meter;applyResult(value);window.BlazeMacHarmony.refresh();});
        assert(!/Bar/.test(await page.locator('.harmony-bar-ruler').first().innerText()),'Uncertain meter was advertised as measured bars');
        assert.match(await page.locator('#harmony-zoom option:checked').innerText(),/windows/);
        assert(await page.locator('.harmony-bar').first().locator('.harmony-beat').count()>0,'Uncertain meter hid the detected beat spacing');
        assert(await page.locator('#media').evaluate(element => element===window.harmonyTestPlayer),'Chord navigation replaced the player');
        assert.deepEqual(errors,[]);
        console.log('Mac harmony UI PASS: real player seek, four measured bars, unequal chord subdivisions, current/next, group navigation/follow, zoom/scroll, uncertain meter, keyboard panel resizing/collapse, four viewports in light/dark. Controlled analysis; no native/perceptual performance claim.');
    } catch (error) {if(page)await shot(page,'failure').catch(()=>{});throw error;}
    finally {if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(error => {console.error(error);process.exitCode=1;});
