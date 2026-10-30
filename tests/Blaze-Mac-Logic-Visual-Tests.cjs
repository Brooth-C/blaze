/* Appearance-only preview: no audio, analysis, recording or backend operations. */
'use strict';
const assert=require('node:assert/strict'),{spawn}=require('node:child_process'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),output=process.env.BLAZE_UI_SCREENSHOTS;
if(output)fs.mkdirSync(output,{recursive:true});
const fixture="import http.server,functools\nh=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory='music_studio/web'))\nprint('http://127.0.0.1:'+str(h.server_port),flush=True)\nh.serve_forever()";
const server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',fixture],{cwd:root,stdio:['ignore','pipe','pipe']});let browser;
(async()=>{try{
const base=await new Promise((resolve,reject)=>{let s='';const timeout=setTimeout(()=>reject(Error('Preview server timed out')),20000);server.stdout.on('data',d=>{s+=d;const m=s.match(/http:\/\/127.0.0.1:\d+/);if(m){clearTimeout(timeout);resolve(m[0]);}});server.on('exit',()=>reject(Error('Preview server exited')));});
browser=await chromium.launch({args:['--no-sandbox']});const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[],api=[];
page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))api.push(r.url());});
await page.goto(base+'/mac-logic-preview.html');await page.waitForFunction(()=>window.BlazeLogicVisual);
assert.equal(await page.locator('.track-header').count(),9);assert.equal(await page.locator('.track-header.selected .track-name').innerText(),'Piano');
for(const [width,height]of[[1440,900],[1280,800],[1024,700]])for(const colorScheme of ['light','dark']){
 await page.setViewportSize({width,height});await page.emulateMedia({colorScheme});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 const clipped=await page.evaluate(()=>['.control-bar','.workspace-bar','.arrangement','.audio-editor','#editor-wave'].filter(s=>{const r=document.querySelector(s).getBoundingClientRect();return r.left<0||r.right>innerWidth+1||r.top<0||r.bottom>innerHeight+1||r.width<=0||r.height<=0;}));assert.deepEqual(clipped,[],'Clipped preview at '+width+' '+colorScheme);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 const ink=await page.locator('#editor-wave').evaluate(c=>{const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<a.length;i+=4)if(a[i])n++;return n;});assert(ink>1000,'Illustrative waveform missing');
 if(output)await page.screenshot({path:path.join(output,'logic12-'+width+'-'+colorScheme+'.png')});
}
await page.getByRole('option',{name:'Strings',exact:true}).locator('.track-name').click();assert.equal(await page.locator('#editor-track').innerText(),'Strings');
await page.getByRole('button',{name:'Mute Strings',exact:true}).click();assert.equal(await page.getByRole('button',{name:'Mute Strings',exact:true}).getAttribute('aria-pressed'),'true');
await page.locator('[data-menu=view]').click();assert(await page.locator('#appearance-menu').isVisible());await page.keyboard.press('Escape');assert(await page.locator('#appearance-menu').isHidden());
await page.getByRole('button',{name:'Show or hide lower editor'}).click();assert(await page.locator('.audio-editor').isHidden());await page.getByRole('button',{name:'Show or hide lower editor'}).click();assert(await page.locator('.audio-editor').isVisible());
assert.deepEqual(errors,[]);assert.deepEqual(api,[],'Visual preview called a production API');
console.log('Logic visual preview PASS: nine illustrative tracks; light/dark at1440,1280,1024; waveform pixels; fit; visual selection/mute/menu/editor toggles; no engine/API calls. Not a functional DAW or native Mac validation.');
}finally{if(browser)await browser.close();server.kill('SIGTERM');}})().catch(e=>{console.error(e);process.exitCode=1;});
