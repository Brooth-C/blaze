/* Explore workflow against the real authenticated loopback server and media element.
 * Metadata and preparation are deterministic injected test doubles; local WAV
 * decoding is real. This test establishes no live YouTube availability claim.
 * Same Playwright/Python environment variables as Blaze-Desktop-UI-Tests.cjs.
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
import math, shutil, struct, subprocess, tempfile, time, uuid, wave
from pathlib import Path
from music_studio.server import Studio, create_server

def item(identity, title, kind='song'):
    url = 'https://www.youtube.com/watch?v=' + identity
    if kind == 'playlist': url = 'https://www.youtube.com/playlist?list=' + identity
    if kind == 'artist': url = 'https://www.youtube.com/channel/' + identity
    return {'id': identity, 'kind': kind, 'title': title, 'creator': 'Fixture Artist',
            'url': url, 'thumbnail': '/api/discovery-image?id=fixture',
            'durationMs': 30000, 'localJobId': ''}

HOME = [item('aaaaaaaaaaa', 'Morning Session'),
        item('bbbbbbbbbbb', 'Evening Video', 'video'),
        item('PLfixture123', 'Acoustic Collection', 'playlist')]

class FixtureDiscovery:
    def __init__(self, audio, video):
        self.audio = audio
        self.video = video
        self.jobs = {}
        self.failures = 0
        self.heard = [HOME[0]]

    def request(self, body):
        action = body.get('action')
        query = body.get('query', '')
        identity = uuid.uuid4().hex
        delay = 1.2 if query == 'slow' else .06
        results = HOME
        error = None
        if action == 'search':
            results = [item('ccccccccccc', query + ' result'), item('ddddddddddd', query + ' video', 'video')]
            if body.get('filter') == 'videos': results = results[1:]
            if query == 'empty': results = []
            if query == 'broken' and self.failures == 0:
                self.failures += 1
                error = 'Fixture metadata could not load. Try again.'
            if query == 'prepare slow': results = [item('eeeeeeeeeee', 'Slow preparation')]
        elif action == 'browse':
            results = [item('fffffffffff', 'Collection Song')]
        self.jobs[identity] = {'ready': time.monotonic() + delay, 'items': results,
                               'error': error, 'cancelled': False}
        return {'requestId': identity}

    def status(self, identity):
        job = self.jobs[identity]
        if job['cancelled']: return {'status': 'cancelled'}
        if time.monotonic() < job['ready']:
            return {'status': 'pending', 'progress': 'Preparing local test media…'}
        if job.get('error'): return {'status': 'failed', 'error': job['error']}
        if 'item' in job: return {'status': 'ready', 'item': job['item']}
        return {'status': 'ready', 'items': job['items']}

    def cancel(self, identity):
        if identity in self.jobs: self.jobs[identity]['cancelled'] = True

    def prepare(self, body):
        selected = body['item']
        identity = uuid.uuid4().hex
        self.jobs[identity] = {'ready': time.monotonic() + (2 if selected['id'] == 'eeeeeeeeeee' else .1),
                               'item': selected, 'cancelled': False}
        return {'requestId': identity}

    def select(self, identity):
        if self.status(identity)['status'] != 'ready': raise ValueError('Media is not prepared.')
        selected = self.jobs[identity]['item']
        return (self.video if selected['kind'] == 'video' else self.audio), selected

    def history(self): return self.heard
    def listened(self, body): self.heard = [body['item']]
    def reset(self): self.heard = []
    def image(self, identity):
        return (Path('android/app/src/main/res/drawable-nodpi/discovery_sunset.png').read_bytes(), 'image/png')
    def close(self): pass

with tempfile.TemporaryDirectory(prefix='blaze-discovery-ui-') as directory:
    audio = Path(directory) / 'Local Playback.wav'
    with wave.open(str(audio), 'wb') as output:
        output.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
        for i in range(22050 * 30):
            output.writeframesraw(struct.pack('<h', int(2500 * math.sin(i * 2 * math.pi * 220 / 22050))))
    video = audio.with_suffix('.mp4')
    decoder = shutil.which('ffmpeg')
    if not decoder: raise RuntimeError('Install FFmpeg for the real local video fixture.')
    subprocess.run([decoder, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10',
                    '-i', str(audio), '-t', '10', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(video)],
                   check=True, timeout=30)
    studio = Studio(directory, 'ffmpeg')
    studio.discovery = FixtureDiscovery(audio, video)
    server = create_server(studio)
    print('http://127.0.0.1:' + str(server.server_port), flush=True)
    try: server.serve_forever()
    finally: server.server_close(); studio.close()
`;
const server=spawn(process.env.BLAZE_TEST_PYTHON||'python3',['-u','-c',fixture],{cwd:root,stdio:['ignore','pipe','pipe']});
let stderr='';server.stderr.on('data',chunk=>stderr+=chunk);
async function start(){return new Promise((resolve,reject)=>{
    let output='';const timer=setTimeout(()=>reject(Error('Studio startup timed out: '+stderr)),20000);
    server.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
    server.once('exit',code=>{clearTimeout(timer);reject(Error('Studio exited '+code+': '+stderr));});
});}
async function shot(page,name){if(screenshots)await page.screenshot({path:path.join(screenshots,name+'.png'),fullPage:false});}
(async()=>{
    let browser,page;
    try{
        const base=await start();
        browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM||undefined,args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
        page=await browser.newPage({viewport:{width:1440,height:960}});
        const errors=[],requests=[];
        page.on('pageerror',error=>errors.push(error.message));
        page.on('console',message=>{if(message.type()==='error'&&!message.location().url.endsWith('/favicon.ico'))errors.push(message.text()+' '+message.location().url);});
        page.on('request',request=>{if(request.method()==='POST'&&request.url().startsWith(base+'/api/')){try{requests.push({path:new URL(request.url()).pathname,body:request.postDataJSON()});}catch{ /* Non-JSON imports are outside this flow. */ }}});
        await page.goto(base);
        assert.equal(await page.title(),'Blaze');
        assert.equal(new URL(page.url()).origin,base);
        await page.locator('.discovery-card').first().waitFor();
        assert.match(await page.locator('[role=tab][aria-selected=true]').textContent(),/Explore/);
        assert.match(await page.locator('#explore-results').textContent(),/Morning Session/);
        assert.equal(await page.locator('video').count(),1);
        await page.waitForFunction(()=>[...document.querySelectorAll('.discovery-card img')].some(el=>el.complete&&el.naturalWidth>0));
        await shot(page,'explore-desktop');

        const field=page.locator('#explore-search');
        await page.evaluate(()=>{window.testSearchField=document.getElementById('explore-search');window.testMedia=document.getElementById('media');});
        await field.pressSequentially('acoustic',{delay:25});
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('acoustic result'));
        assert.equal(requests.filter(r=>r.path==='/api/discovery'&&r.body.action==='search'&&r.body.query==='acoustic').length,1,'Typing should submit one debounced query');
        assert(await field.evaluate(el=>el===window.testSearchField&&el===document.activeElement&&el.selectionStart===8),'Results replaced or blurred the search input');
        await shot(page,'search-desktop');

        const slowRequest=page.waitForRequest(r=>r.url()===base+'/api/discovery'&&r.method()==='POST'&&r.postDataJSON()?.query==='slow');
        await field.fill('slow');
        // Wait until the slow request is actually submitted, then supersede it.
        await slowRequest;
        await field.fill('fresh');
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('fresh result'));
        await page.waitForTimeout(1400);
        assert(!((await page.locator('#explore-results').textContent()).includes('slow result')),'A cancelled response replaced current results');
        assert(requests.some(r=>r.path==='/api/discovery-cancel'),'Superseded searches should cancel backend work');

        await field.fill('broken');
        await page.locator('#explore-retry').waitFor({state:'visible'});
        assert.match(await page.locator('#explore-status').textContent(),/could not load/i);
        await page.locator('#explore-retry').click();
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('broken result'));
        await field.fill('empty');
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('Nothing here yet'));
        assert.equal(await page.locator('.discovery-card').count(),0);

        await field.fill('prepare slow');
        await page.getByRole('button',{name:/Slow preparation/}).first().click();
        await page.locator('#prepare-cancel').waitFor({state:'visible'});
        await page.locator('#prepare-cancel').click();
        await page.waitForTimeout(2300);
        assert.equal(await page.locator('#media').getAttribute('src'),null,'Cancelled preparation selected media');

        await page.locator('#explore-home').click();
        await page.locator('.discovery-card[data-kind=playlist] .discovery-primary').click();
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('Collection Song'));
        assert(requests.some(r=>r.path==='/api/discovery'&&r.body.action==='browse'),'Playlist should browse rather than attempt playback');
        await page.locator('.discovery-primary').first().click();
        await page.waitForFunction(()=>{const m=document.getElementById('media');return Number.isFinite(m.duration)&&m.duration>29&&!m.paused&&m.currentTime>.1;});
        await page.locator('#now-close').click();
        await page.locator('#tab-downloads').click();
        await page.locator('#tab-library').click();
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia&&!el.paused&&el.currentTime>.1),'Navigation replaced or paused the shared player');
        await page.locator('#mini-open').click();
        await page.locator('#now-dialog').waitFor({state:'visible'});
        await shot(page,'now-playing-desktop');
        await page.locator('#now-play').click();
        await page.waitForFunction(()=>document.getElementById('media').paused);
        await page.locator('#now-seek').fill('400');
        await page.locator('#now-seek').dispatchEvent('input');
        await page.locator('#now-seek').dispatchEvent('change');
        assert(await page.locator('#media').evaluate(el=>el.currentTime>11&&el.currentTime<13),'Now Playing scrubber did not seek');
        const source=await page.locator('#media').getAttribute('src');
        await page.locator('#now-studio').click();
        await page.locator('#studio-panel').waitFor({state:'visible'});
        assert.equal(await page.locator('#media').getAttribute('src'),source,'Opening Studio reopened media');
        assert(await page.locator('#media').evaluate(el=>el===window.testMedia&&el.paused&&el.currentTime>0),'Studio lost the paused player state');
        await shot(page,'studio-from-explore');
        await page.locator('#tab-explore').click();
        await page.locator('#mini-open').click();
        await page.locator('#now-download').click();
        await page.locator('#downloads-panel').waitFor({state:'visible'});
        assert.match(await page.locator('#download-urls').inputValue(),/youtube\.com\/watch\?v=fffffffffff/,'Download handoff lost the selected canonical link');

        await page.locator('#tab-explore').click();
        await page.locator('#explore-home').click();
        await page.locator('#explore-reset').click();
        await page.waitForFunction(()=>document.getElementById('app-announcement').textContent.includes('Listening history reset'));
        const history=await page.evaluate(async()=>{
            const token=document.querySelector('meta[name="blaze-token"]').content;
            const response=await fetch('/api/discovery-history',{headers:{'X-Blaze-Token':token}});
            return response.json();
        });
        assert.deepEqual(history.items,[],'Reset did not clear the local profile');
        assert(requests.some(r=>r.path==='/api/discovery-reset'));
        await field.fill('landscape');
        await page.locator('[data-discovery-filter=videos]').click();
        await page.waitForFunction(()=>document.getElementById('explore-results').textContent.includes('landscape video'));
        assert.equal(await page.locator('.discovery-card[data-kind=song]').count(),0);
        assert(requests.some(r=>r.path==='/api/discovery'&&r.body.filter==='videos'&&r.body.query==='landscape'));
        await page.locator('.discovery-card[data-kind=video] .discovery-primary').click();
        await page.waitForFunction(()=>{const m=document.getElementById('media');return m.videoWidth===320&&m.videoHeight===180&&!m.paused&&m.currentTime>.1;});
        assert(await page.locator('#now-video-slot #media').isVisible(),'The video result was presented as audio');
        assert(await page.locator('#media').evaluate(el=>{
            const canvas=document.createElement('canvas');canvas.width=32;canvas.height=18;
            const context=canvas.getContext('2d');context.drawImage(el,0,0,32,18);
            return context.getImageData(0,0,32,18).data.some((value,index)=>index%4!==3&&value>100);
        }),'Decoded video frame is blank');
        await shot(page,'video-now-playing');
        await page.locator('#now-play').click();
        await page.waitForFunction(()=>document.getElementById('media').paused);
        const videoPosition=await page.locator('#media').evaluate(el=>el.currentTime);
        await page.locator('#now-studio').click();
        assert(await page.locator('.preview-panel #media').isVisible(),'Video did not return to the Studio preview');
        assert(await page.locator('#media').evaluate((el,position)=>el===window.testMedia&&el.paused&&Math.abs(el.currentTime-position)<.15,videoPosition),'Moving video into Studio lost the paused frame position');
        await page.locator('#tab-explore').click();
        for(const [width,height] of [[780,600],[390,844]]){
            await page.setViewportSize({width,height});
            assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Horizontal overflow at ${width}`);
            assert(await page.locator('#explore-search').isVisible());
            await shot(page,'explore-'+width);
        }
        await page.emulateMedia({reducedMotion:'reduce',colorScheme:'dark'});
        await page.setViewportSize({width:1440,height:960});
        await shot(page,'explore-dark-reduced-motion');
        assert.deepEqual(errors,[]);
        console.log('Desktop discovery UI PASS: real loopback/media decoding; controlled recommendations/thumbnails; debounce/focus; stale cancellation; error/retry/empty; browse; prepare cancellation; one player across navigation/Now Playing/Studio; seek; download handoff; filters; responsive/dark/reduced-motion rendering. Live YouTube not exercised.');
    }catch(error){
        if(stderr.trim())console.error(stderr);
        if(page&&screenshots){await shot(page,'discovery-failure').catch(()=>{});console.error(await page.locator('#explore-status').textContent().catch(()=>''));}
        throw error;
    }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exitCode=1;});
