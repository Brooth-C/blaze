/* Mac Studio workspace. Audio stays in the existing persistent media player;
   every region is a waveform of a real local recording or a saved stem. */
(() => {
    'use strict';
    if (document.documentElement.dataset.presentation !== 'mac') return;
    const el = id => document.getElementById(id);
    const panel = el('studio-panel');
    const player = el('media');
    const families = ['vocals', 'drums', 'bass', 'piano', 'guitar', 'strings', 'brass', 'synths', 'other'];
    const labels = {source:'Recording', vocals:'Vocals', drums:'Drums', bass:'Bass', piano:'Piano', guitar:'Guitar', strings:'Strings', brass:'Brass', synths:'Synths', other:'Other', accompaniment:'Accompaniment'};
    const colors = {source:'#8293a2', vocals:'#438ce2', drums:'#42a7b5', bass:'#8e72cf', piano:'#e6a34f', guitar:'#498fd6', strings:'#c6a757', brass:'#9675d3', synths:'#42bbba', other:'#8b98a7', accompaniment:'#8496ac'};
    const paths = {
        source:'M3 12h2l2-7 3 14 3-14 3 14 2-7h3',
        vocals:'M9 4a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0Zm-3 6v1a6 6 0 0 0 12 0v-1M12 17v5m-4 0h8',
        drums:'M3 9c0-4 18-4 18 0s-18 4-18 0Zm0 0v8c0 4 18 4 18 0V9M4 3l8 4m8-4-8 4M6 11v7m6-6v8m6-9v7',
        bass:'m14 8 6-6 2 2-6 6m-2-2-2 2C5 7 1 17 6 21s12-1 9-8l2-3M8 14l3 3m3-9 4 4',
        piano:'M3 8h18v12H3Zm3 0V3h12v5M7 8v12m5-12v12m5-12v12M9 8v7m6-7v7',
        guitar:'m14 8 6-6 2 2-6 6m-2-2-2 2C5 7 1 17 6 21s12-1 9-8l2-3M8 14l3 3m3-9 4 4',
        strings:'m15 3-9 15m14-15L10 21m2-16c-6 0-9 10-5 13s10-3 8-7l-3-6Zm-7 6 10 6',
        brass:'m3 14 14-7 4-5v17l-4-5-14 4Zm5-3V6h3v4m1-3V3h3v4',
        synths:'M2 5h20v14H2Zm4 0v14m4-14v14m4-14v14m4-14v14M8 5v8m4-8v8m4-8v8',
        other:'M3 12h2l2-7 3 14 3-14 3 14 2-7h3',
        library:'M3 4h4v16H3Zm7 0h4v16h-4Zm7 0 4 1-2 15-4-1Z',
        inspector:'M4 4h16v16H4Zm5 0v16m4-11h4m-4 4h4',
        stop:'M6 6h12v12H6Z', rewind:'m11 5-8 7 8 7Zm10 0-8 7 8 7Z',
        next:'m3 5 8 7-8 7Zm10 0 8 7-8 7Z', play:'m8 4 12 8-12 8Z', pause:'M7 4h3v16H7Zm7 0h3v16h-3Z',
        loop:'m5 6 3-3m-3 3 3 3M5 6h12a4 4 0 0 1 4 4v1M19 18l-3-3m3 3-3 3m3-3H7a4 4 0 0 1-4-4v-1',
        back:'m14 5-7 7 7 7', upload:'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
        wave:'M3 12h2l2-7 3 14 3-14 3 14 2-7h3', close:'m6 6 12 12M6 18 18 6',
        volume:'M3 9v6h4l5 4V5L7 9Zm13-1a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14'
    };
    const svg = name => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+(paths[name] || paths.source)+'"/></svg>';
    const button = (id, name, title, extra='') => '<button id="'+id+'" type="button" aria-label="'+title+'" title="'+title+'" '+extra+'>'+svg(name)+'</button>';
    const root = document.createElement('div');
    root.id = 'mac-studio-workspace';
    root.innerHTML = `
      <div id="daw-transport" role="toolbar" aria-label="Studio transport">
        <div class="daw-panel-tools">${button('daw-back','back','Back to Explore')}${button('daw-library-toggle','library','Show library','aria-pressed="true"')}${button('daw-inspector-toggle','inspector','Show inspector','aria-pressed="true"')}</div>
        <div class="daw-transport-buttons">${button('daw-rewind','rewind','Back 10 seconds')}${button('daw-stop','stop','Stop')}${button('daw-play','play','Play')}${button('daw-forward','next','Forward 10 seconds')}${button('daw-loop','loop','Repeat recording','aria-pressed="false"')}</div>
        <div class="daw-display"><div class="daw-musical-position"><strong id="daw-bars">— · —</strong><small>BAR · BEAT</small></div><div><strong id="daw-time">00:00.000</strong><small>TIME</small></div><div><strong id="daw-tempo">—</strong><small>BPM</small></div><div><strong id="daw-meter">—</strong><small>METER</small></div><div><strong id="daw-key">—</strong><small>KEY</small></div></div>
        <div class="daw-session-actions">${button('daw-import','upload','Import recording')}<span id="daw-stems"></span><button id="daw-chords" aria-expanded="false" aria-controls="daw-practice">Chords</button></div>
      </div>
      <div class="daw-body">
        <aside id="daw-library" aria-label="Studio library"><div class="daw-panel-heading">Library</div><label class="daw-library-search"><span aria-hidden="true">⌕</span><input id="daw-search" type="search" placeholder="Search tracks" aria-label="Search session tracks"></label><div id="daw-families"></div><div class="daw-panel-heading daw-recordings-heading">Session tracks</div><div id="daw-recordings"></div><div class="daw-library-foot">On this Mac<span id="daw-track-count">No recording open</span></div></aside>
        <aside id="daw-inspector" aria-label="Track inspector"><div class="daw-panel-heading">Track: <span id="daw-inspector-name">Recording</span></div><div class="daw-instrument-art" id="daw-instrument-art">${svg('source')}<strong id="daw-instrument-name">Recording</strong></div><details open><summary>Region</summary><dl><div><dt>Start</dt><dd>00:00.000</dd></div><div><dt>Length</dt><dd id="daw-region-length">—</dd></div><div><dt>Channels</dt><dd id="daw-region-channels">—</dd></div></dl></details><details open><summary>Track</summary><dl><div><dt>Type</dt><dd>Audio</dd></div><div><dt>Source</dt><dd id="daw-region-source">Local recording</dd></div></dl><a id="daw-save" class="daw-save" hidden>Save WAV</a></details><details open><summary>Playback</summary><label class="daw-control-label">Volume <output id="daw-gain-label">0.0 dB</output><input id="daw-volume" aria-label="Studio volume" type="range" min="0" max="1" step=".01" value="1"></label><label class="daw-control-label">Speed <select id="daw-rate" aria-label="Studio playback speed"><option value=".5">0.5×</option><option value=".75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option></select></label><div class="daw-channel-buttons"><button id="daw-mute" aria-pressed="false" aria-label="Mute playback">M</button><button id="daw-audition" aria-label="Audition selected track">Audition</button></div></details><details open><summary>Analysis</summary><dl><div><dt>Key</dt><dd id="daw-analysis-key">—</dd></div><div><dt>Tempo</dt><dd id="daw-analysis-tempo">—</dd></div></dl><div id="daw-analysis-actions"></div></details><div class="daw-channel-strip"><div class="daw-channel-caption">SELECTED TRACK</div><div class="daw-channel-fader"><span>+6<br><br>0<br><br>−12<br><br>−24<br><br>−∞</span><div class="daw-fader-line"><i id="daw-fader-cap"></i></div><div class="daw-channel-state">${svg('volume')}<span id="daw-audition-state">Stopped</span></div></div></div></aside>
        <div class="daw-main"><section id="daw-arrangement" aria-label="Track arrangement"><div class="daw-arrangement-title"><strong id="daw-session-title">Untitled session</strong><span id="daw-session-caption">Audio tracks</span></div><div class="daw-arrangement-scroll"><div class="daw-arrangement-grid"><div class="daw-track-heading">Tracks <span id="daw-lane-count">0</span></div><div id="daw-ruler" class="daw-ruler"></div><div id="daw-track-list"></div><div id="daw-regions"><div id="daw-arrangement-playhead" class="daw-playhead"></div></div></div></div><div id="daw-empty"><div>${svg('wave')}<h2>Your next session starts here.</h2><p>Open a recording to see its waveform. Split it into stems to work with each instrument.</p><button id="daw-empty-import">Import recording</button></div></div></section>
        <section id="daw-editor" aria-label="Selected track waveform editor"><div class="daw-editor-toolbar"><strong><i id="daw-track-color"></i><span id="daw-editor-title">Recording</span><span class="daw-rendered-label"> · Audio</span></strong><div class="daw-editor-tabs"><button aria-pressed="true">Waveform</button><button id="daw-notation" aria-label="Open chord notation">Chords</button></div><label class="daw-zoom-control">Zoom <span aria-hidden="true">−</span><input id="daw-zoom" aria-label="Waveform zoom" type="range" min="1" max="8" step=".25" value="1"><span aria-hidden="true">+</span></label></div><div id="daw-editor-scroll"><div id="daw-editor-content"><div id="daw-editor-ruler" class="daw-ruler"></div><canvas id="daw-waveform" role="slider" tabindex="0" aria-label="Selected track waveform. Click to seek; shift-drag to select a range." aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"></canvas><div id="daw-wave-selection" hidden></div><div id="daw-editor-playhead" class="daw-playhead"></div></div><p id="daw-wave-empty">Import a recording to begin.</p></div><div class="daw-editor-footer"><span id="daw-format">Local audio</span><span id="daw-selection-readout">No range selected</span></div></section></div>
      </div><div class="daw-status-bar"><span class="daw-status-brand">Blaze Studio</span><span id="daw-message" role="status">Ready</span><span id="daw-local-indicator">On this Mac</span></div>`;
    const practice = document.createElement('section');
    practice.id = 'daw-practice'; practice.hidden = true;
    practice.setAttribute('aria-label', 'Chord practice');
    const practiceHeading = document.createElement('div'); practiceHeading.className = 'daw-practice-heading';
    practiceHeading.innerHTML = '<strong>Chord practice</strong>'+button('daw-practice-close','close','Close chord practice');
    const legacy = [...panel.children];
    practice.append(practiceHeading, ...legacy);
    panel.append(root, practice);
    // Move the real engine controls instead of cloning handlers or players.
    el('daw-stems').append(el('split-stems'));
    el('daw-analysis-actions').append(el('analyze'), el('cancel'));

    let tracks = [], selected = 'source', currentPeaks = null, zoom = 1, filter = 'all';
    let sessionRevision = null, sessionJob = '', signature = '', loading = false;
    let generation = 0, controller = null, waveformReady = false, selection = null;
    let libraryOpen = innerWidth >= 1100, inspectorOpen = innerWidth >= 800;
    let pendingSelection = false, frame = 0, stopped = false;
    const cache = new Map();
    const active = () => !panel.hidden;
    const isModal = () => !!document.querySelector('dialog[open]');
    const elapsed = value => {
        const v = Math.max(0, Number(value) || 0), minutes = Math.floor(v / 60);
        return String(minutes).padStart(2, '0')+':'+String(Math.floor(v % 60)).padStart(2, '0')+'.'+String(Math.floor(v * 1000) % 1000).padStart(3, '0');
    };
    const duration = () => currentPeaks?.duration || (Number.isFinite(player.duration) ? player.duration : 0);
    const title = value => String(value || 'Untitled session').replace(/\.[a-z0-9]{2,5}$/i, '');
    const text = (id, value) => { if (el(id).textContent !== String(value)) el(id).textContent = String(value); };
    const message = value => text('daw-message', value);
    const chosen = () => tracks.find(t => t.id === selected) || tracks[0];
    const setPanels = () => {
        root.classList.toggle('daw-library-hidden', !libraryOpen); root.classList.toggle('daw-inspector-hidden', !inspectorOpen);
        el('daw-library-toggle').setAttribute('aria-pressed', String(libraryOpen));
        el('daw-inspector-toggle').setAttribute('aria-pressed', String(inspectorOpen));
        el('daw-library').inert = !libraryOpen; el('daw-inspector').inert = !inspectorOpen;
        scheduleDraw();
    };
    const doImport = () => window.BlazeMac.action('import');
    el('daw-import').onclick = doImport; el('daw-empty-import').onclick = doImport;
    el('daw-back').onclick = () => window.BlazeMac.navigate('explore');
    el('daw-library-toggle').onclick = () => { libraryOpen = !libraryOpen; setPanels(); };
    el('daw-inspector-toggle').onclick = () => { inspectorOpen = !inspectorOpen; setPanels(); };
    el('daw-play').onclick = () => { if (!pendingSelection) el('play').click(); };
    el('daw-stop').onclick = () => { player.pause(); seek(0); };
    el('daw-rewind').onclick = () => seek(player.currentTime - 10);
    el('daw-forward').onclick = () => seek(player.currentTime + 10);
    el('daw-loop').onclick = () => { player.loop = !player.loop; el('repeat').checked = player.loop; paintTransport(); };
    el('daw-mute').onclick = () => { player.muted = !player.muted; paintTransport(); };
    el('daw-audition').onclick = () => { if (sourceName && !pendingSelection) player.play().catch(failure); };
    el('daw-volume').oninput = event => { player.volume = Number(event.target.value); el('volume').value = String(player.volume); };
    el('daw-rate').onchange = event => { player.playbackRate = Number(event.target.value); el('speed').value = String(player.playbackRate); };
    const showPractice = show => {
        practice.hidden = !show; el('daw-chords').setAttribute('aria-expanded', String(show));
        if (show) { requestAnimationFrame(() => { wave(); diagram(); paintFlow(); }); el('daw-practice-close').focus(); }
        else el('daw-chords').focus();
    };
    el('daw-chords').onclick = () => showPractice(practice.hidden);
    el('daw-notation').onclick = () => showPractice(true);
    el('daw-practice-close').onclick = () => showPractice(false);
    practice.addEventListener('keydown', event => { if (event.key === 'Escape' && !isModal()) { event.preventDefault(); showPractice(false); } });
    el('daw-zoom').oninput = event => { zoom = Number(event.target.value); scheduleDraw(); };

    for (const id of ['all', ...families]) {
        const b = document.createElement('button'); b.dataset.family = id;
        b.innerHTML = svg(id === 'all' ? 'library' : id)+'<span></span><span class="daw-disclosure" aria-hidden="true">›</span>';
        b.querySelector('span').textContent = id === 'all' ? 'All tracks' : labels[id];
        b.setAttribute('aria-pressed', String(id === filter));
        b.onclick = () => { filter = id; renderTracks(); };
        el('daw-families').append(b);
    }
    el('daw-search').oninput = () => renderTracks();

    async function selectTrack(track) {
        if (pendingSelection || busy || importing || selected === track.id || !track.jobId || isModal()) return;
        pendingSelection = true; paintTransport(); message('Opening '+track.label+'…');
        const previousPosition = Number.isFinite(player.currentTime) ? player.currentTime : 0;
        const wasPlaying = !player.paused;
        try {
            window.BlazeDesktop.cancelPreparation();
            await api('/api/stems-select', {jobId:track.jobId, stem:track.id});
            selected = track.id;
            await window.BlazeMac.importCompleted();
            const revision = sourceRevision;
            // Preserve audition position only for this completed selection.
            const resume = () => {
                if (sourceRevision !== revision) return;
                seek(previousPosition);
                if (wasPlaying) player.play().catch(failure);
            };
            if (player.readyState >= 1) resume(); else player.addEventListener('loadedmetadata', resume, {once:true});
            // The selected recording is ready; sibling previews can load in the
            // background without holding the transport disabled.
            signature = ''; void syncSession();
        } catch (error) { message(error.message || 'This track could not be opened.'); }
        finally { pendingSelection = false; paintTransport(); }
    }

    function renderTracks() {
        const search = el('daw-search').value.toLocaleLowerCase();
        for (const b of el('daw-families').children) { b.classList.toggle('selected', b.dataset.family === filter); b.setAttribute('aria-pressed', String(b.dataset.family === filter)); }
        const visible = tracks.filter(t => (filter === 'all' || filter === t.id) && t.label.toLocaleLowerCase().includes(search));
        el('daw-track-list').replaceChildren();
        const head = el('daw-arrangement-playhead'); el('daw-regions').replaceChildren(head);
        el('daw-recordings').replaceChildren();
        for (const track of visible) {
            const row = document.createElement('button'); row.type = 'button'; row.className = 'daw-track'; row.dataset.trackId = track.id;
            row.classList.toggle('selected', track.id === selected); row.setAttribute('aria-pressed', String(track.id === selected));
            row.style.setProperty('--track-color', colors[track.id] || colors.source);
            row.innerHTML = '<span class="daw-track-number"></span>'+svg(track.id)+'<span class="daw-track-label"></span><span class="daw-track-audition" aria-hidden="true">▷</span>';
            row.querySelector('.daw-track-number').textContent = String(tracks.indexOf(track)+1);
            row.querySelector('.daw-track-label').textContent = track.label;
            row.setAttribute('aria-label', 'Select '+track.label+' track');
            row.onclick = () => selectTrack(track); el('daw-track-list').append(row);
            const lane = document.createElement('div'); lane.className = 'daw-lane'; lane.dataset.trackId = track.id;
            lane.style.setProperty('--track-color', colors[track.id] || colors.source);
            const region = document.createElement('button'); region.type = 'button'; region.className = 'daw-region'; region.classList.toggle('selected', track.id === selected);
            region.setAttribute('aria-label', 'Open '+track.label+' waveform');
            const caption = document.createElement('span'); caption.textContent = track.id === 'source' ? title(sourceName) : track.label;
            const canvas = document.createElement('canvas'); canvas.className = 'daw-region-wave'; canvas.setAttribute('aria-hidden','true');
            region.append(caption, canvas); region.onclick = () => selectTrack(track); lane.append(region); el('daw-regions').append(lane);
            const patch = document.createElement('button'); patch.className = 'daw-recording'; patch.classList.toggle('selected', track.id === selected);
            patch.textContent = track.label; patch.onclick = () => selectTrack(track); el('daw-recordings').append(patch);
        }
        text('daw-lane-count', visible.length); text('daw-track-count', tracks.length ? tracks.length+' audio '+(tracks.length===1?'track':'tracks') : 'No recording open');
        el('daw-empty').hidden = !!sourceName;
        el('daw-arrangement').classList.toggle('daw-is-empty', !tracks.length);
        if (tracks.length && !visible.length) message('No tracks match this filter.');
        paintInspector(); scheduleDraw();
    }

    function paintInspector() {
        const track = chosen(), label = track?.label || 'Recording';
        text('daw-inspector-name', label); text('daw-instrument-name', label); text('daw-editor-title', label);
        el('daw-instrument-art').querySelector('svg').outerHTML = svg(track?.id || 'source');
        el('daw-track-color').style.background = colors[track?.id] || colors.source;
        text('daw-region-length', duration() ? elapsed(duration()) : '—');
        text('daw-region-channels', currentPeaks ? 'Stereo' : '—');
        text('daw-region-source', track?.jobId ? 'Separated stem' : 'Local recording');
        el('daw-save').hidden = !track?.jobId;
        if (track?.jobId) {
            el('daw-save').href = '/api/stem-file?jobId='+encodeURIComponent(track.jobId)+'&stem='+encodeURIComponent(track.id)+'&token='+encodeURIComponent(token);
            el('daw-save').download = label+'.wav';
            el('daw-save').setAttribute('aria-label','Save '+label+' WAV');
        } else el('daw-save').removeAttribute('href');
        text('daw-format', currentPeaks ? 'Stereo · Local audio' : 'Local audio');
    }

    function paintTransport() {
        const enabled = !!sourceName && !pendingSelection;
        for (const id of ['daw-play','daw-stop','daw-rewind','daw-forward','daw-loop','daw-audition']) el(id).disabled = !enabled;
        const play = el('daw-play'), state = player.paused ? 'play' : 'pause';
        if (play.dataset.state !== state) { play.innerHTML = svg(state); play.dataset.state = state; }
        play.setAttribute('aria-label', player.paused ? 'Play' : 'Pause');
        play.classList.toggle('playing', !player.paused);
        el('daw-loop').setAttribute('aria-pressed', String(player.loop));
        el('daw-mute').setAttribute('aria-pressed', String(player.muted));
        el('daw-volume').value = String(player.volume); el('daw-rate').value = String(player.playbackRate);
        text('daw-gain-label', player.volume ? (20*Math.log10(player.volume)).toFixed(1)+' dB' : '−∞ dB');
        text('daw-audition-state', player.paused ? 'Stopped' : 'Playing');
        el('daw-fader-cap').style.top = (1-player.volume)*80+'%';
        const bpm = result?.rhythm_correction?.mode === 'grid' ? result.rhythm_correction.bpm : result?.tempo_bpm;
        const position = Number.isFinite(player.currentTime) ? player.currentTime : 0;
        const timing = BlazeFlow.state(flowMap,position);
        const measure = flowMap.measures[timing.measure];
        const meter = measure && !['unknown','lead-in'].includes(measure.kind) ? measure.numerator : null;
        text('daw-tempo', bpm ? Number(bpm).toFixed(bpm%1?1:0) : '—');
        text('daw-meter', meter ? meter+'/'+measure.denominator : '—');
        text('daw-key', result?.key || '—'); text('daw-analysis-key',result?.key||'—'); text('daw-analysis-tempo',bpm?Number(bpm).toFixed(0)+' BPM':'—');
        text('daw-time', elapsed(position));
        text('daw-bars', meter ? (measure.barNumber || timing.measure-(flowMap.barStart||0)+1)+' · '+(timing.beat?timing.beat.index+1:'—') : '— · —');
        const progress = duration() ? Math.max(0,Math.min(1,position/duration())) : 0;
        for (const id of ['daw-arrangement-playhead','daw-editor-playhead']) el(id).style.left = (progress*100)+'%';
        el('daw-waveform').setAttribute('aria-valuenow', String(Math.round(progress*100)));
        el('daw-waveform').setAttribute('aria-valuetext', elapsed(position)+' of '+elapsed(duration()));
        if (!active() || player.paused) { cancelAnimationFrame(frame); frame=0; }
        else if (!frame) frame=requestAnimationFrame(() => { frame=0; paintTransport(); });
    }

    function peakCanvas(canvas, data, color, stereo=false) {
        const r=canvas.getBoundingClientRect(), d=Math.min(devicePixelRatio||1,2);
        canvas.width=Math.max(1,Math.round(r.width*d)); canvas.height=Math.max(1,Math.round(r.height*d));
        const g=canvas.getContext('2d'); g.scale(d,d); const w=r.width,h=r.height;
        if (!w||!h) return;
        g.strokeStyle='#ffffff0c'; g.lineWidth=1;
        const lanes=stereo?2:1;
        for (let channel=0;channel<lanes;channel++) {
            const center=h/lanes*(channel+.5), amplitude=h/lanes*.42;
            g.beginPath();g.moveTo(0,center);g.lineTo(w,center);g.stroke();
            if (stereo) { g.fillStyle='#9ba7af';g.font='10px -apple-system,sans-serif';g.fillText(channel?'R':'L',7,center-4); }
            const bins=data?.peaks?.[channel] || data?.peaks?.[0];
            if (!bins?.length) continue;
            // Peak-normalized display only; playback/export audio is unchanged.
            const maximum=Math.max(...bins.map(pair=>Math.max(Math.abs(pair[0]),Math.abs(pair[1]))));
            const displayGain=maximum>0?Math.min(20,.95/maximum):1;
            g.fillStyle=color; g.globalAlpha=.9;
            const count=Math.max(1,Math.ceil(w));
            for(let x=0;x<count;x++) {
                const first=Math.floor(x/count*bins.length), last=Math.max(first+1,Math.ceil((x+1)/count*bins.length));
                let low=0,high=0;
                for(let i=first;i<last&&i<bins.length;i++){low=Math.min(low,bins[i][0]);high=Math.max(high,bins[i][1]);}
                g.fillRect(x,center-high*amplitude*displayGain,1,Math.max(.6,(high-low)*amplitude*displayGain));
            }
            g.globalAlpha=1;
        }
    }
    let drawFrame=0;
    function scheduleDraw() { cancelAnimationFrame(drawFrame);drawFrame=requestAnimationFrame(draw); }
    function ruler(target, length, detailed=false) {
        target.replaceChildren();
        const width=target.getBoundingClientRect().width;
        const count=Math.max(2,Math.min(33,Math.floor(width/(detailed?100:85))));
        for(let i=0;i<count;i++) {
            const mark=document.createElement('span'); const seconds=length*i/(count-1);
            mark.textContent=time(seconds);
            mark.style.left=(i/(count-1)*100)+'%'; target.append(mark);
        }
    }
    function draw() {
        if (!active()) return;
        const length=duration();
        el('daw-editor-content').style.width=(zoom*100)+'%';
        ruler(el('daw-ruler'),length); ruler(el('daw-editor-ruler'),length,true);
        for(const lane of el('daw-regions').querySelectorAll('.daw-lane')) {
            const t=tracks.find(t=>t.id===lane.dataset.trackId);
            peakCanvas(lane.querySelector('canvas'), t?.waveform, colors[t?.id]||colors.source);
        }
        peakCanvas(el('daw-waveform'),currentPeaks,colors[selected]||colors.source,true);
        el('daw-wave-empty').hidden=!!currentPeaks;
        text('daw-wave-empty',sourceName?(loading?'Reading waveform…':'Waveform unavailable. Playback and analysis remain available.'):'Import a recording to begin.');
        paintRange(); paintTransport();
    }
    function paintRange() {
        const range=el('daw-wave-selection'),length=duration(); range.hidden=!selection||!length;
        if(selection&&length){range.style.left=(selection[0]/length*100)+'%';range.style.width=((selection[1]-selection[0])/length*100)+'%';text('daw-selection-readout','Selection '+elapsed(selection[0])+' – '+elapsed(selection[1]));}
        else text('daw-selection-readout','No range selected');
    }
    const waveform=el('daw-waveform');let pointerStart=null;
    const atPointer=event=>Math.max(0,Math.min(1,(event.clientX-waveform.getBoundingClientRect().left)/waveform.getBoundingClientRect().width))*duration();
    waveform.onpointerdown=event=>{
        if(event.button!==0||!duration()||!sourceName)return;
        waveform.setPointerCapture(event.pointerId);pointerStart=event.shiftKey?atPointer(event):null;
        if(pointerStart===null){selection=null;seek(atPointer(event));paintRange();}
        else{selection=[pointerStart,pointerStart];paintRange();}
    };
    waveform.onpointermove=event=>{if(waveform.hasPointerCapture(event.pointerId)){if(pointerStart===null)seek(atPointer(event));else{const end=atPointer(event);selection=[Math.min(pointerStart,end),Math.max(pointerStart,end)];paintRange();}}};
    waveform.onpointerup=waveform.onpointercancel=event=>{if(waveform.hasPointerCapture(event.pointerId))waveform.releasePointerCapture(event.pointerId);pointerStart=null;};
    waveform.onkeydown=event=>{let target=null;if(event.key==='ArrowLeft')target=player.currentTime-5;if(event.key==='ArrowRight')target=player.currentTime+5;if(event.key==='Home')target=0;if(event.key==='End')target=duration();if(event.key==='Escape'){selection=null;paintRange();}if(target!==null){event.preventDefault();seek(target);}};

    const delay = (milliseconds, signal) => new Promise((resolve,reject)=>{
        const abort=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};
        const timer=setTimeout(()=>{signal?.removeEventListener('abort',abort);resolve();},milliseconds);
        if(signal?.aborted)abort();else signal?.addEventListener('abort',abort,{once:true});
    });
    async function fetchWave(revision, jobId='', stem='', signal, attempt=0) {
        const params=new URLSearchParams({sourceRevision:String(revision)});if(jobId){params.set('jobId',jobId);params.set('stem',stem);}
        const response=await fetch('/api/studio-waveform?'+params,{headers:{'X-Blaze-Token':token},signal});
        const data=await response.json();
        if(response.status===503&&attempt<4){await delay(100*Math.pow(2,attempt),signal);return fetchWave(revision,jobId,stem,signal,attempt+1);}
        if(!response.ok){const error=Error(data.error||'The waveform could not be read.');error.status=response.status;throw error;}return data;
    }
    async function syncSession() {
        if(stopped||!active())return;
        paintTransport();
        const stems=window.BlazeMacStems?.snapshot();
        const next=JSON.stringify([sourceRevision,sourceName,stems?.status,stems?.jobId]);
        if(next===signature)return;
        signature=next;const mine=++generation;controller?.abort();controller=new AbortController();
        const revision=sourceRevision;selection=null;waveformReady=false;
        if(!sourceName||!Number.isSafeInteger(revision)){
            tracks=[];selected='source';currentPeaks=null;sessionJob='';sessionRevision=revision;renderTracks();message('Import a recording to begin.');return;
        }
        const sourceChanged=sessionRevision!==revision;
        sessionRevision=revision;loading=true;
        if(sourceChanged){currentPeaks=null;tracks=[{id:'source',label:title(sourceName),waveform:null}];selected='source';renderTracks();}
        message('Reading local waveform…');
        text('daw-session-title',title(sourceName));
        try{
            const data=await fetchWave(revision,'','',controller.signal);
            if(mine!==generation||revision!==sourceRevision||!active())return;
            currentPeaks=data;waveformReady=true;sessionJob=data.stemJobId||'';
            const rows=sessionJob&&stems?.status==='done'&&stems.jobId===sessionJob&&Array.isArray(stems.stems)?stems.stems.filter(r=>labels[r.id]):[];
            const selectedStem=rows.find(row=>row.filename===sourceName);
            selected=selectedStem?.id||'source';
            tracks=rows.map(row=>({id:row.id,label:labels[row.id],jobId:sessionJob,waveform:cache.get(sessionJob+':'+row.id)||null}));
            if(selected==='source')tracks.unshift({id:'source',label:title(sourceName),waveform:data});
            else tracks.find(t=>t.id===selected).waveform=data;
            for(const key of cache.keys())if(!key.startsWith(sessionJob+':'))cache.delete(key);
            loading=false;renderTracks();message('Ready · '+(selected==='source'?'Recording':labels[selected]));
            text('daw-session-caption',tracks.length>1?'Separated audio tracks':'Audio recording');
            const queue=tracks.filter(t=>t.jobId&&!t.waveform);
            const worker=async()=>{while(queue.length&&mine===generation){const track=queue.shift();try{const peaks=await fetchWave(revision,track.jobId,track.id,controller.signal);if(mine!==generation||revision!==sourceRevision)return;track.waveform=peaks;cache.set(track.jobId+':'+track.id,peaks);scheduleDraw();}catch(error){if(error.name==='AbortError')return;}}};
            await Promise.all([worker(),worker()]);
        }catch(error){if(mine!==generation||error.name==='AbortError')return;loading=false;currentPeaks=null;waveformReady=false;if(error.status===503)signature='';message(error.message||'The waveform could not be read.');scheduleDraw();}
    }
    const resize=new ResizeObserver(scheduleDraw);resize.observe(root);resize.observe(el('daw-editor-scroll'));
    let previousWidth=innerWidth;
    window.addEventListener('resize',()=>{
        if(innerWidth<800&&previousWidth>=800){libraryOpen=false;inspectorOpen=false;setPanels();}
        else if(innerWidth<1100&&previousWidth>=1100){libraryOpen=false;setPanels();}
        previousWidth=innerWidth;
    });
    new MutationObserver(()=>{if(active()){setPanels();syncSession();}else{controller?.abort();signature='';++generation;practice.hidden=true;el('daw-chords').setAttribute('aria-expanded','false');paintTransport();}}).observe(panel,{attributes:true,attributeFilter:['hidden']});
    for(const event of ['timeupdate','play','pause','loadedmetadata','volumechange','ratechange','seeked','ended'])player.addEventListener(event,paintTransport);
    const timer=setInterval(()=>{if(active()){syncSession();paintTransport();}},750);
    window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);controller?.abort();cancelAnimationFrame(frame);resize.disconnect();},{once:true});
    window.BlazeMacStudio={snapshot:()=>({active:active(),selectedTrack:selected,tracks:tracks.map(t=>({id:t.id,label:t.label})),zoom,libraryOpen,inspectorOpen,waveformReady,waveformsReady:tracks.filter(t=>t.waveform).length,sourceRevision:sessionRevision})};
    setPanels();renderTracks();syncSession();
})();
