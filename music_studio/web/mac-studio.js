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
    const regionColors={source:['#3a6a94','#315c86'],vocals:['#246da6','#2268a2'],drums:['#1b7277','#207c83'],bass:['#69409f','#664296'],piano:['#c9a42b','#a88a21'],guitar:['#2b7447','#2f7e50'],strings:['#9eaa2b','#7c8621'],brass:['#84406a','#914a78'],synths:['#22657e','#25718c'],other:['#53677f','#566a80']};
    const paths = {
        source:'M3 12h2l2-7 3 14 3-14 3 14 2-7h3',
        vocals:'M9 4a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0Zm-3 6v1a6 6 0 0 0 12 0v-1M12 17v5m-4 0h8',
        drums:'M3 9c0-4 18-4 18 0s-18 4-18 0Zm0 0v8c0 4 18 4 18 0V9M4 3l8 4m8-4-8 4M6 11v7m6-6v8m6-9v7',
        bass:'m14 8 6-6 2 2-6 6m-2-2-2 2C5 7 1 17 6 21s12-1 9-8l2-3M8 14l3 3m3-9 4 4',
        piano:'M3 12h18v4H3Zm2 4v6m14-6v6M6 12V7L18 2l2 1v9M6 7h14M6 12v4m3-4v4m3-4v4m3-4v4m3-4v4',
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
        volume:'M3 9v6h4l5 4V5L7 9Zm13-1a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14',
        previous:'M5 4v16m14-16L7 12l12 8Z', record:'M12 5a7 7 0 1 0 0 14 7 7 0 1 0 0-14Z',
        undo:'m9 4-6 5 6 5M3 9h11a6 6 0 1 1 0 12',redo:'m15 4 6 5-6 5m6-5H10a6 6 0 1 0 0 12',
        metronome:'m8 3-5 18h18L16 3ZM8 16l9-9M7 3h10',search:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6',
        plus:'M12 4v16M4 12h16',chords:'M3 5h18v14H3Zm4 0v14m4-10h7m-7 4h7',
        eq:'M3 12h2l3-5 4 10 4-10 3 5h2',compressor:'M3 5h7v14H3Zm11 0h7v14h-7M7 8v8m10-8v8',
        pointer:'m5 3 3 17 4-6 7-2Z',scissors:'M6 13a4 4 0 1 0 0 8 4 4 0 1 0 0-8Zm12 0a4 4 0 1 0 0 8 4 4 0 1 0 0-8ZM4 2l14 14M20 2 6 16',
        fade:'M3 20V4h18M3 20C5 8 12 6 21 4',automation:'M3 18h5l6-12h7M7 16v4m6-16v4'
    };
    const svg = name => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+(paths[name] || paths.source)+'"/></svg>';
    const instrumentIcon=name=>{const index=families.indexOf(name);return index<0?svg(name):'<span class="daw-instrument-icon daw-instrument-'+name+'" aria-hidden="true"></span>';};
    const button = (id, name, title, extra='') => '<button id="'+id+'" type="button" aria-label="'+title+'" title="'+title+'" '+extra+'>'+svg(name)+'</button>';
    const root = document.createElement('div');
    root.id = 'mac-studio-workspace';
    root.dataset.design = 'logic';
    root.innerHTML = `
      <div class="daw-window-bar"><div class="daw-window-lights" aria-hidden="true"><i></i><i></i><i></i></div><span id="daw-window-title">Untitled — Blaze</span></div>
      <div id="daw-transport" role="toolbar" aria-label="Studio transport">
        <div class="daw-panel-tools">${button('daw-library-toggle','library','Show library','aria-pressed="true"')}<span class="daw-button-caption">Library</span>${button('daw-inspector-toggle','inspector','Show inspector','aria-pressed="true"')}<span class="daw-button-caption">Inspector</span><div class="daw-history">${button('daw-undo','undo','Undo Studio setting')}${button('daw-redo','redo','Redo Studio setting')}</div></div>
        <div class="daw-transport-buttons">${button('daw-start','previous','Go to beginning')}${button('daw-rewind','rewind','Back 10 seconds')}${button('daw-stop','stop','Stop')}${button('daw-play','play','Play')}${button('daw-record','record','Recording is not available in this build','disabled')}${button('daw-loop','loop','Repeat recording','aria-pressed="false"')}</div>
        <div class="daw-display"><div class="daw-musical-position"><strong id="daw-bars">1&nbsp; 1</strong><small>BAR&nbsp;&nbsp; BEAT</small></div><div><strong id="daw-time">00:00.000</strong><small>TIME</small></div><button id="daw-tempo-control" title="Project tempo"><strong id="daw-tempo">120</strong><small>BPM</small></button><button id="daw-meter-control" title="Project time signature"><strong id="daw-meter">4/4</strong><small>SIGNATURE</small></button><button id="daw-key-control" title="Project key"><strong id="daw-key">—</strong><small>KEY</small></button></div>
        <div class="daw-click-controls">${button('daw-metronome','metronome','Metronome','aria-pressed="false"')}<button id="daw-count-in" aria-label="Count in requires recording" disabled>123</button></div>
        <div class="daw-master"><div class="daw-master-meters" aria-label="Output level"><i><span id="daw-master-left"></span></i><i><span id="daw-master-right"></span></i></div><input id="daw-master-volume" type="range" min="0" max="1" step=".01" value="1" aria-label="Master volume">${svg('volume')}</div>
      </div>
      <div class="daw-body">
        <aside id="daw-library" aria-label="Studio library"><div class="daw-panel-heading">Library</div><label class="daw-library-search">${svg('search')}<input id="daw-search" type="search" placeholder="Search tracks" aria-label="Search session tracks"></label><div id="daw-families"></div><div id="daw-patches" hidden></div><div class="daw-library-foot">${button('daw-back','back','Back to Explore')}<span id="daw-track-count"></span></div><div class="daw-recordings-heading">Session tracks</div><div id="daw-recordings" role="group" aria-label="Session tracks"></div></aside>
        <aside id="daw-inspector" aria-label="Track inspector"><div class="daw-panel-heading">▾ &nbsp; Track: <span id="daw-inspector-name">Recording</span></div><div class="daw-instrument-art" id="daw-instrument-art"><img src="/studio-grand.png" alt="Grand piano" hidden>${svg('source')}<strong id="daw-instrument-name">Recording</strong></div>
          <details open><summary>Region</summary><dl><div><dt>Gain</dt><dd id="daw-gain-label">0.0 dB</dd></div><div><dt>Transpose</dt><dd id="daw-region-transpose">0</dd></div><div><dt>Flex</dt><dd>Off</dd></div></dl></details>
          <details open><summary>Track</summary><dl><div><dt>Icon</dt><dd id="daw-track-icon">${svg('piano')}</dd></div><div><dt>Name</dt><dd id="daw-track-name">Recording</dd></div><div><dt>Color</dt><dd><input id="daw-color" type="color" value="#e68f32" aria-label="Track color"></dd></div><div><dt>Track Mode</dt><dd class="daw-mini-track-controls"><button id="daw-mute" aria-pressed="false" aria-label="Mute playback">M</button><button id="daw-audition" aria-pressed="false" aria-label="Audition selected track">S</button><button class="daw-arm" aria-label="Record arm unavailable" disabled>●</button></dd></div></dl></details>
          <details open><summary>Instrument</summary><button class="daw-instrument-slot" disabled title="Instrument patches are not available in this build">♧ &nbsp; Studio Grand</button></details>
          <details open><summary>Audio FX</summary><button id="daw-eq" class="daw-effect-slot" aria-pressed="false">${svg('eq')}<span>Channel EQ</span></button><button id="daw-compressor" class="daw-effect-slot" aria-pressed="false">${svg('compressor')}<span>Compressor</span></button><div class="daw-effects-plus"><button id="daw-analysis-toggle" title="Analysis and playback options" aria-label="Open analysis and playback options">+</button></div></details>
          <div class="daw-sends"><span>⌄ &nbsp; Sends</span><span>♧ &nbsp; Bus 1 &nbsp; +</span></div>
          <div class="daw-channel-strip"><div class="daw-channel-main"><div class="daw-pan"><span id="daw-channel-name">Recording</span><label class="daw-pan-knob"><input id="daw-pan" type="range" min="-1" max="1" step=".01" value="0" aria-label="Track pan"><i id="daw-pan-pointer"></i></label><div><output id="daw-pan-label">0.0</output><span>R0</span></div></div><div class="daw-channel-fader"><input id="daw-volume" aria-label="Studio volume" type="range" min="0" max="1" step=".01" value="1"><i id="daw-fader-cap" hidden></i></div><div class="daw-channel-scale"><span>+6</span><span>0</span><span>−12</span><span>−24</span><span>−36</span><span>−60</span></div><div class="daw-level-pair"><i><span id="daw-level-left"></span></i><i><span id="daw-level-right"></span></i></div></div><div class="daw-channel-buttons"><button id="daw-channel-mute" aria-label="Mute selected track" aria-pressed="false">M</button><button id="daw-channel-solo" aria-label="Solo selected track" aria-pressed="false">S</button><button class="daw-arm" aria-label="Record arm unavailable" disabled>●</button></div></div>
          <div id="daw-inspector-extra" hidden><div><strong>Playback & analysis</strong><button id="daw-extra-close" aria-label="Close playback options">×</button></div><label>Speed <select id="daw-rate" aria-label="Studio playback speed"><option value=".5">0.5×</option><option value=".75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option></select></label><dl><div><dt>Length</dt><dd id="daw-region-length">—</dd></div><div><dt>Channels</dt><dd id="daw-region-channels">—</dd></div><div><dt>Source</dt><dd id="daw-region-source">Local recording</dd></div><div><dt>Detected key</dt><dd id="daw-analysis-key">—</dd></div><div><dt>Detected tempo</dt><dd id="daw-analysis-tempo">—</dd></div></dl><div id="daw-analysis-actions"></div><a id="daw-save" class="daw-save" hidden>Save WAV</a><span id="daw-audition-state" hidden>Stopped</span></div></aside>
        <div class="daw-main"><section id="daw-arrangement" aria-label="Track arrangement"><div class="daw-arrangement-title" hidden><strong id="daw-session-title">Untitled session</strong><span id="daw-session-caption">Audio tracks</span></div><div class="daw-arrangement-scroll"><div class="daw-arrangement-grid"><div class="daw-track-heading"><div class="daw-session-actions">${button('daw-import','plus','Import recording')}<span id="daw-stems"></span><button id="daw-chords" aria-expanded="false" aria-controls="daw-practice" title="Chord practice">${svg('chords')}</button></div><span id="daw-lane-count" hidden>0</span></div><div id="daw-ruler" class="daw-ruler"></div><div id="daw-track-list"></div><div id="daw-regions"><div id="daw-arrangement-playhead" class="daw-playhead"></div></div></div></div><div id="daw-empty"><div>${svg('wave')}<h2>Your next session starts here.</h2><p>Open a recording to see its waveform. Split it into stems to work with each instrument.</p><button id="daw-empty-import">Import recording</button></div></div></section>
        <section id="daw-editor" aria-label="Selected track waveform editor"><div class="daw-editor-toolbar"><strong><i id="daw-track-color"></i><span id="daw-editor-title">Recording</span><span class="daw-rendered-label"> · Rendered audio</span></strong><div class="daw-editor-tabs"><button id="daw-audio-tab" aria-pressed="true">Waveform</button><button id="daw-notation" aria-pressed="false" title="Notes inferred from chord analysis, not a MIDI recording">Chord Guide</button></div><div class="daw-edit-tools">${button('daw-pointer-tool','pointer','Seek tool','aria-pressed="true"')}${button('daw-range-tool','scissors','Range selection tool','aria-pressed="false"')}${button('daw-fade-tool','fade','Fade editing is not available in this build','disabled')}${button('daw-automation-tool','automation','Automation is not available in this build','disabled')}</div><label class="daw-snap-label">Snap: <select id="daw-snap" aria-label="Selection snap"><option value="beat">Beat</option><option value="off">Off</option></select></label><label class="daw-zoom-control">Zoom: <span aria-hidden="true">−</span><input id="daw-zoom" aria-label="Waveform zoom" type="range" min="1" max="8" step=".25" value="1"><span aria-hidden="true">+</span></label></div><div id="daw-editor-scroll"><div id="daw-editor-content"><div id="daw-editor-ruler" class="daw-ruler"></div><div class="daw-amplitude-scale" aria-hidden="true"><span>1.0<br>0.5<br>0<br>−0.5<br>−1.0</span><span>1.0<br>0.5<br>0<br>−0.5<br>−1.0</span></div><canvas id="daw-waveform" role="slider" tabindex="0" aria-label="Selected track waveform. Click to seek; shift-drag to select a range." aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"></canvas><canvas id="daw-midi-guide" aria-label="Chord-derived MIDI guide" hidden></canvas><div id="daw-wave-selection" hidden><i></i><i></i></div><div id="daw-editor-playhead" class="daw-playhead"></div></div><p id="daw-wave-empty">Import a recording to begin.</p></div><div class="daw-editor-scrollbar"><button id="daw-scroll-back" aria-label="Scroll waveform left">◂</button><input id="daw-scroll" aria-label="Waveform horizontal position" type="range" min="0" max="1000" value="0"><button id="daw-scroll-forward" aria-label="Scroll waveform right">▸</button></div><div class="daw-editor-footer"><span id="daw-format">Local audio</span><span id="daw-message" role="status">Ready</span><span id="daw-selection-readout">No range selected</span></div></section></div>
      </div>`;
    const practice = document.createElement('section');
    practice.id = 'daw-practice'; practice.hidden = true;
    practice.setAttribute('aria-label', 'Chord practice');
    const practiceHeading = document.createElement('div'); practiceHeading.className = 'daw-practice-heading';
    practiceHeading.innerHTML = '<strong>Chord practice</strong>'+button('daw-practice-close','close','Close chord practice');
    const legacy = [...panel.children];
    practice.append(practiceHeading, ...legacy);
    panel.append(root, practice);
    // The amplitude gutter belongs to the editor viewport, not its scrollable
    // audio content. It stays visible at every horizontal zoom/scroll position.
    const surface=document.createElement('div');surface.className='daw-editor-surface';
    const editorScroll=el('daw-editor-scroll'),scale=root.querySelector('.daw-amplitude-scale');
    editorScroll.before(surface);surface.append(scale,editorScroll);
    const regionHeading=document.createElement('div');regionHeading.id='daw-editor-region';
    regionHeading.setAttribute('aria-hidden','true');el('daw-editor-ruler').after(regionHeading);
    for(const [channel,axis] of [...root.querySelectorAll('.daw-amplitude-scale>span')].entries()){axis.replaceChildren();const name=document.createElement('b');name.textContent=channel?'R':'L';axis.append(name);['100','0','−100'].forEach((label,index)=>{const mark=document.createElement('i');mark.textContent=label;mark.style.top=(8+index*42)+'%';axis.append(mark);});}
    // Move the real engine controls instead of cloning handlers or players.
    el('daw-stems').append(el('split-stems'));
    el('daw-analysis-actions').append(el('analyze'), el('cancel'));
    el('analyze').textContent='Analyse Chords';
    el('cancel').textContent='Cancel Analysis';
    const workflow = document.createElement('div');
    workflow.id='daw-workflow'; workflow.setAttribute('role','toolbar');
    workflow.setAttribute('aria-label','Studio workflow');
    const browse=el('daw-back'); browse.append(document.createTextNode(' Browse'));
    const projectName=document.createElement('strong'); projectName.id='daw-workflow-title';
    projectName.textContent='Recording';
    const actions=document.createElement('div'); actions.className='daw-workflow-actions';
    const chords=el('daw-chords'); chords.append(document.createTextNode(' Chord Tools'));
    actions.append(el('daw-stems'),el('daw-analysis-actions'),chords,el('daw-save'));
    workflow.append(browse,projectName,actions); root.querySelector('.daw-body').prepend(workflow);
    el('daw-chords').setAttribute('aria-label','Open chord practice');

    let editorPixelWidth=0, arrangementPixelWidth=0;
    let tracks = [], selected = 'source', currentPeaks = null, zoom = 1;
    let sessionRevision = null, sessionJob = '', signature = '', loading = false;
    let generation = 0, controller = null, waveformReady = false, selection = null;
    let libraryOpen = false, inspectorOpen = innerWidth >= 800;
    let libraryUserChoice=false,inspectorUserChoice=false;
    let pendingSelection = false, pendingTrack = '', frame = 0, stopped = false;
    let deferredTrackFocus = null;
    let editorMode='audio', rangeTool=false, solo=false, projectTempo=120, projectNumerator=4, projectDenominator=4, projectKey='—';
    let manualProject=false, guide=null, guideJob='', metronome=false, lastClickBeat=-1;
    let audioGraph=null;
    const history=[],future=[];
    const mutedTracks=new Set(),trackPans=new Map();
    let sessionTitle='Untitled',libraryFamily='all',lastGuide=null;
    const cache = new Map();
    const active = () => !panel.hidden;
    const isModal = () => !!document.querySelector('dialog[open]:not(#stems-dialog[data-background=true])');
    const elapsed = value => {
        const v = Math.max(0, Number(value) || 0), minutes = Math.floor(v / 60);
        return String(minutes).padStart(2, '0')+':'+String(Math.floor(v % 60)).padStart(2, '0')+'.'+String(Math.floor(v * 1000) % 1000).padStart(3, '0');
    };
    const duration = () => currentPeaks?.duration || (Number.isFinite(player.duration) ? player.duration : 0);
    const title = value => String(value || 'Untitled session').replace(/\.[a-z0-9]{2,5}$/i, '');
    const text = (id, value) => { if (el(id).textContent !== String(value)) el(id).textContent = String(value); };
    const message = (value, state='status') => {
        const status=el('daw-message');
        text('daw-message',value);
        status.hidden=/^Ready\b/.test(value);
        status.dataset.state=state;
        status.setAttribute('aria-busy',String(state==='loading'));
    };
    const chosen = () => tracks.find(t => t.id === selected) || tracks[0];
    const remember = () => { history.push({volume:player.volume,pan:Number(el('daw-pan').value),zoom,muted:player.muted});if(history.length>50)history.shift();future.length=0; };
    const restoreSetting = value => { player.volume=value.volume;setTrackMuted(selected,value.muted);zoom=value.zoom;el('daw-zoom').value=String(zoom);setTrackPan(selected,value.pan);paintTransport();scheduleDraw(); };
    const setting = () => ({volume:player.volume,pan:Number(el('daw-pan').value),zoom,muted:player.muted});
    el('daw-undo').onclick=()=>{if(history.length){future.push(setting());restoreSetting(history.pop());}};
    el('daw-redo').onclick=()=>{if(future.length){history.push(setting());restoreSetting(future.pop());}};
    function ensureAudio() {
        if(!audioGraph){
            const Context=window.AudioContext||window.webkitAudioContext;
            if(!Context)return null;
            try{
                const context=new Context(),source=context.createMediaElementSource(player),eq=context.createBiquadFilter(),compressor=context.createDynamicsCompressor(),pan=context.createStereoPanner(),split=context.createChannelSplitter(2);
                eq.type='peaking';eq.frequency.value=1200;eq.Q.value=.7;eq.gain.value=0;compressor.ratio.value=1;
                source.connect(eq).connect(compressor).connect(pan);pan.connect(context.destination);pan.connect(split);
                const meters=[context.createAnalyser(),context.createAnalyser()];
                for(let i=0;i<2;i++){meters[i].fftSize=256;split.connect(meters[i],i);}
                audioGraph={context,eq,compressor,pan,meters,samples:new Uint8Array(256)};
            }catch(error){message('Audio controls could not be opened: '+error.message,'error');return null;}
        }
        audioGraph.context.resume().catch(()=>{});return audioGraph;
    }
    function paintMeters(position) {
        const levels=[0,0];
        if(audioGraph&&!player.paused&&!player.muted){for(let ch=0;ch<2;ch++){audioGraph.meters[ch].getByteTimeDomainData(audioGraph.samples);let power=0;for(const value of audioGraph.samples)power+=Math.pow((value-128)/128,2);levels[ch]=Math.max(0,Math.min(1,(20*Math.log10(Math.sqrt(power/256)||1e-4)+60)/60));}}
        for(let i=0;i<2;i++){el(i?'daw-master-right':'daw-master-left').style.width=(levels[i]*100)+'%';el(i?'daw-level-right':'daw-level-left').style.height=(levels[i]*100)+'%';}
        for(const row of el('daw-track-list').children){const meter=row.querySelector('.daw-track-meter i');if(meter)meter.style.width=(row.dataset.trackId===selected?Math.max(...levels)*100:0)+'%';}
    }
    const setPanels = () => {
        root.classList.toggle('daw-library-hidden', !libraryOpen); root.classList.toggle('daw-inspector-hidden', !inspectorOpen);
        el('daw-library-toggle').setAttribute('aria-pressed', String(libraryOpen));
        el('daw-inspector-toggle').setAttribute('aria-pressed', String(inspectorOpen));
        el('daw-library').inert = !libraryOpen; el('daw-inspector').inert = !inspectorOpen;
        scheduleDraw();
    };
    function setTrackMuted(id, muted) {
        if(muted)mutedTracks.add(id);else mutedTracks.delete(id);
        if(id===selected)player.muted=muted;
        const row=[...el('daw-track-list').children].find(item=>item.dataset.trackId===id);
        row?.querySelector('.daw-row-mute').setAttribute('aria-pressed',String(muted));
        paintTransport();
    }
    function setTrackPan(id, value) {
        const pan=Math.max(-1,Math.min(1,Number(value)||0));
        trackPans.set(id,pan);
        const row=[...el('daw-track-list').children].find(item=>item.dataset.trackId===id);
        const input=row?.querySelector('.daw-row-pan input');
        if(input){input.value=String(pan);input.nextElementSibling.style.transform='rotate('+(pan*120)+'deg)';}
        if(id===selected){el('daw-pan').value=String(pan);const graph=ensureAudio();if(graph)graph.pan.pan.value=pan;}
        paintTransport();
    }
    const doImport = () => window.BlazeMac.action('import');
    el('daw-import').onclick = doImport; el('daw-empty-import').onclick = doImport;
    el('daw-back').onclick = () => window.BlazeMac.navigate('explore');
    el('daw-library-toggle').onclick = () => {libraryUserChoice=true;libraryOpen = !libraryOpen;setPanels();};
    el('daw-inspector-toggle').onclick = () => {inspectorUserChoice=true;inspectorOpen = !inspectorOpen;setPanels();};
    el('daw-play').onclick = () => { if (!pendingSelection){ensureAudio();el('play').click();} };
    el('daw-start').onclick=()=>seek(0);
    el('daw-stop').onclick = () => { player.pause(); seek(0); };
    el('daw-rewind').onclick = () => seek(player.currentTime - 10);
    el('daw-loop').onclick = () => {
        if(player.loop||loopEnd!==null){player.loop=false;loopStart=loopEnd=null;}
        else if(selection&&selection[1]>selection[0]){[loopStart,loopEnd]=selection;player.loop=false;}
        else player.loop=true;
        el('repeat').checked=player.loop;updateLoop();scheduleDraw();paintTransport();
    };
    el('daw-mute').onclick = () => {remember();setTrackMuted(selected,!player.muted);};
    el('daw-channel-mute').onclick=()=>el('daw-mute').click();
    el('daw-audition').onclick = () => {solo=!solo;if(sourceName&&!pendingSelection){ensureAudio();player.play().catch(failure);}paintTransport();};
    el('daw-channel-solo').onclick=()=>el('daw-audition').click();
    for(const id of ['daw-volume','daw-master-volume']){el(id).addEventListener('pointerdown',remember);el(id).oninput=event=>{player.volume=Number(event.target.value);el('volume').value=String(player.volume);paintTransport();};}
    el('daw-pan').addEventListener('pointerdown',remember);
    el('daw-pan').oninput=event=>setTrackPan(selected,event.target.value);
    el('daw-eq').onclick=()=>{const graph=ensureAudio();if(!graph)return;const enabled=el('daw-eq').getAttribute('aria-pressed')!=='true';graph.eq.gain.value=enabled?3:0;el('daw-eq').setAttribute('aria-pressed',String(enabled));};
    el('daw-compressor').onclick=()=>{const graph=ensureAudio();if(!graph)return;const enabled=el('daw-compressor').getAttribute('aria-pressed')!=='true';graph.compressor.ratio.value=enabled?6:1;graph.compressor.threshold.value=-20;el('daw-compressor').setAttribute('aria-pressed',String(enabled));};
    const optionsButton=el('daw-analysis-toggle'),optionsPanel=el('daw-inspector-extra');
    optionsButton.setAttribute('aria-controls',optionsPanel.id);
    optionsButton.setAttribute('aria-expanded','false');
    optionsPanel.setAttribute('role','region');optionsPanel.setAttribute('aria-label','Playback and analysis options');
    const showOptions=show=>{
        optionsPanel.hidden=!show;optionsButton.setAttribute('aria-expanded',String(show));
        if(show)el('daw-rate').focus();else optionsButton.focus();
    };
    optionsButton.onclick=()=>showOptions(optionsPanel.hidden);
    el('daw-extra-close').onclick=()=>showOptions(false);
    optionsPanel.addEventListener('keydown',event=>{if(event.key==='Escape'&&!isModal()){event.preventDefault();event.stopPropagation();showOptions(false);}});
    el('daw-color').oninput=event=>{const color=event.target.value;colors[selected]=color;regionColors[selected]=['color-mix(in srgb,'+color+',#102030 55%)','color-mix(in srgb,'+color+',#101820 75%)'];renderTracks();};
    el('daw-pointer-tool').onclick=()=>{rangeTool=false;el('daw-pointer-tool').setAttribute('aria-pressed','true');el('daw-range-tool').setAttribute('aria-pressed','false');};
    el('daw-range-tool').onclick=()=>{rangeTool=true;el('daw-pointer-tool').setAttribute('aria-pressed','false');el('daw-range-tool').setAttribute('aria-pressed','true');};
    el('daw-metronome').onclick=()=>{ensureAudio();metronome=!metronome;lastClickBeat=-1;el('daw-metronome').setAttribute('aria-pressed',String(metronome));};
    el('daw-rate').onchange = event => { player.playbackRate = Number(event.target.value); el('speed').value = String(player.playbackRate); };
    const showPractice = show => {
        practice.hidden = !show; el('daw-chords').setAttribute('aria-expanded', String(show));
        if (show) { requestAnimationFrame(() => { wave(); diagram(); paintFlow(); }); el('daw-practice-close').focus(); }
        else el('daw-chords').focus();
    };
    el('daw-chords').onclick = () => showPractice(practice.hidden);
    el('daw-notation').onclick = () => {editorMode='midi';el('daw-audio-tab').setAttribute('aria-pressed','false');el('daw-notation').setAttribute('aria-pressed','true');scheduleDraw();};
    el('daw-audio-tab').onclick=()=>{editorMode='audio';el('daw-audio-tab').setAttribute('aria-pressed','true');el('daw-notation').setAttribute('aria-pressed','false');scheduleDraw();};
    el('daw-practice-close').onclick = () => showPractice(false);
    practice.addEventListener('keydown', event => { if (event.key === 'Escape' && !isModal()) { event.preventDefault(); showPractice(false); } });
    el('daw-zoom').oninput = event => { zoom = Number(event.target.value); scheduleDraw(); };
    el('daw-scroll').oninput=event=>{const port=el('daw-editor-scroll');port.scrollLeft=Number(event.target.value)/1000*(port.scrollWidth-port.clientWidth);};
    el('daw-scroll-back').onclick=()=>{el('daw-editor-scroll').scrollLeft-=el('daw-editor-scroll').clientWidth*.25;};
    el('daw-scroll-forward').onclick=()=>{el('daw-editor-scroll').scrollLeft+=el('daw-editor-scroll').clientWidth*.25;};
    el('daw-editor-scroll').addEventListener('scroll',()=>{const port=el('daw-editor-scroll');el('daw-scroll').value=String(port.scrollWidth>port.clientWidth?port.scrollLeft/(port.scrollWidth-port.clientWidth)*1000:0);});

    for (const [id,caption,kind] of [['all','All tracks','library'],['vocals','Vocals','vocals'],['piano','Piano','piano'],['synths','Synthesizers','synths'],['guitar','Guitars','guitar'],['bass','Bass','bass'],['drums','Drums','drums'],['strings','Strings','strings'],['brass','Brass','brass']]) {
        const b = document.createElement('button'); b.dataset.family = id;
        b.innerHTML = instrumentIcon(kind)+'<span class="daw-family-caption"></span><span class="daw-disclosure" aria-hidden="true">›</span>';
        b.querySelector('.daw-family-caption').textContent = caption;
        b.setAttribute('aria-pressed', String(id === libraryFamily));
        b.onclick = () => {libraryFamily=id;renderTracks();};
        el('daw-families').append(b);
    }
    el('daw-search').oninput = () => renderTracks();

    const projectDialog=document.createElement('dialog');projectDialog.id='daw-project-dialog';
    projectDialog.innerHTML='<form method="dialog"><h3>Project timing</h3><label>Tempo <input id="daw-project-bpm" type="number" min="20" max="300" value="120" step=".1" required></label><label>Time signature <select id="daw-project-num"><option>2</option><option>3</option><option selected>4</option><option>5</option><option>6</option><option>7</option><option>9</option><option>12</option></select> / <select id="daw-project-den"><option>2</option><option selected>4</option><option>8</option><option>16</option></select></label><label>Key <select id="daw-project-key"></select></label><p>Project grid settings. Original audio stays unchanged.</p><div class="actions"><button value="cancel">Cancel</button><button id="daw-project-save" value="save">Apply</button></div></form>';
    document.body.append(projectDialog);
    for(const name of roots)for(const quality of ['major','minor']){const option=document.createElement('option');option.textContent=name+' '+quality;el('daw-project-key').append(option);}
    for(const id of ['daw-tempo-control','daw-meter-control','daw-key-control'])el(id).onclick=()=>{el('daw-project-bpm').value=String(projectTempo);el('daw-project-num').value=String(projectNumerator);el('daw-project-den').value=String(projectDenominator);el('daw-project-key').value=projectKey==='—'?'C major':projectKey;projectDialog.showModal();};
    el('daw-project-save').onclick=()=>{const tempo=Number(el('daw-project-bpm').value);if(tempo<20||tempo>300)return;projectTempo=tempo;projectNumerator=Number(el('daw-project-num').value);projectDenominator=Number(el('daw-project-den').value);projectKey=el('daw-project-key').value;manualProject=true;scheduleDraw();};

    function paintTrackPending() {
        for(const row of el('daw-track-list').children){
            const pending=pendingSelection&&row.dataset.trackId===pendingTrack;
            row.setAttribute('aria-busy',String(pending));row.classList.toggle('loading',pending);
        }
    }
    async function selectTrack(track) {
        if (pendingSelection || busy || importing || selected === track.id || !track.jobId || isModal()) return;
        pendingSelection = true;pendingTrack=track.id;paintTrackPending();paintTransport();message('Opening '+track.label+'…','loading');
        const previousPosition = Number.isFinite(player.currentTime) ? player.currentTime : 0;
        const wasPlaying = !player.paused;
        try {
            window.BlazeDesktop.cancelPreparation();
            await api('/api/stems-select', {jobId:track.jobId, stem:track.id});
            selected = track.id;
            await window.BlazeMac.importCompleted();
            player.muted=mutedTracks.has(track.id);el('daw-pan').value=String(trackPans.get(track.id)||0);
            if(audioGraph)audioGraph.pan.pan.value=Number(el('daw-pan').value);
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
        } catch (error) { message(error.message || 'This track could not be opened.','error'); }
        finally { pendingSelection = false;pendingTrack='';paintTrackPending();paintTransport(); }
    }

    // A stem selection briefly replaces the current source row before the saved
    // track list returns. Retain focus only when this renderer removed it; a
    // subsequent user action outside the rows abandons that intent.
    document.addEventListener('focusin',event=>{
        if(deferredTrackFocus&&!event.target.closest?.('#daw-track-list,#daw-regions'))deferredTrackFocus=null;
    });
    document.addEventListener('pointerdown',event=>{
        if(deferredTrackFocus&&!event.target.closest?.('#daw-track-list,#daw-regions'))deferredTrackFocus=null;
    },true);
    function rememberTrackFocus() {
        const focused=document.activeElement;
        const area=el('daw-track-list').contains(focused)?'track':el('daw-regions').contains(focused)?'region':null;
        if(!area){if(focused!==document.body)deferredTrackFocus=null;return;}
        const owner=focused.closest('[data-track-id]');
        if(!owner)return;
        const track=tracks.find(item=>item.id===owner.dataset.trackId);
        const control=area==='region'?'.daw-region':focused.matches('.daw-row-mute')?'.daw-row-mute':focused.matches('.daw-row-solo')?'.daw-row-solo':focused.matches('.daw-row-pan input')?'.daw-row-pan input':'.daw-track-select';
        deferredTrackFocus={id:owner.dataset.trackId,jobId:track?.jobId||sessionJob,area,control};
    }
    function restoreTrackFocus() {
        if(!deferredTrackFocus||document.activeElement!==document.body)return;
        const intent=deferredTrackFocus;
        const track=tracks.find(item=>item.id===intent.id&&(!intent.jobId||item.jobId===intent.jobId));
        if(!track)return;
        const container=el(intent.area==='region'?'daw-regions':'daw-track-list');
        const owner=[...container.children].find(item=>item.dataset.trackId===intent.id);
        const target=owner?.querySelector(intent.control);
        if(target){target.focus({preventScroll:true});deferredTrackFocus=null;}
    }
    function renderTracks() {
        rememberTrackFocus();
        const search = el('daw-search').value.toLocaleLowerCase();
        for (const b of el('daw-families').children) { b.classList.toggle('selected', b.dataset.family === libraryFamily); b.setAttribute('aria-pressed', String(b.dataset.family === libraryFamily)); }
        const visible = tracks;
        for(const patch of el('daw-patches').children){patch.hidden=!!search&&!patch.textContent.toLocaleLowerCase().includes(search);patch.title='Instrument patches are not available in this build';}
        el('daw-track-list').replaceChildren();
        const head = el('daw-arrangement-playhead'); el('daw-regions').replaceChildren(head);
        el('daw-recordings').replaceChildren();
        for (const track of visible) {
            const row = document.createElement('div');row.setAttribute('role','group');row.className = 'daw-track'; row.dataset.trackId = track.id;
            row.classList.toggle('selected', track.id === selected);
            row.style.setProperty('--track-color', colors[track.id] || colors.source);
            row.innerHTML = '<button type="button" class="daw-track-select" aria-pressed="'+(track.id===selected)+'"><span class="daw-track-number"></span>'+instrumentIcon(track.id)+'<span class="daw-track-label"></span></button><div class="daw-row-controls"><button class="daw-row-mute" aria-label="Mute track" aria-pressed="'+mutedTracks.has(track.id)+'">M</button><button class="daw-row-solo" aria-label="Solo track" aria-pressed="'+(solo&&selected===track.id)+'">S</button><button class="daw-arm" aria-label="Recording unavailable" disabled>●</button><span class="daw-track-meter" title="Source level at playhead"><i></i></span><label class="daw-row-pan"><input type="range" min="-1" max="1" step=".01" value="'+(trackPans.get(track.id)||0)+'" aria-label="Pan track"><i></i></label></div>';
            row.querySelector('.daw-row-mute').setAttribute('aria-label','Mute '+track.label);
            row.querySelector('.daw-row-solo').setAttribute('aria-label','Solo '+track.label);
            row.querySelector('input').setAttribute('aria-label','Pan '+track.label);
            row.querySelector('.daw-track-number').textContent = String(tracks.indexOf(track)+1);
            row.querySelector('.daw-track-label').textContent = track.label;
            row.setAttribute('aria-label',track.label+' track');
            const selectButton=row.querySelector('.daw-track-select');
            selectButton.setAttribute('aria-label','Select '+track.label+' track');selectButton.title=track.label;
            selectButton.onclick=()=>selectTrack(track);
            row.onclick=event=>{if(event.target===row)selectTrack(track);};
            row.querySelector('.daw-row-mute').onclick=event=>{event.stopPropagation();setTrackMuted(track.id,!mutedTracks.has(track.id));};
            row.querySelector('.daw-row-solo').onclick=async event=>{event.stopPropagation();if(pendingSelection||busy||importing||isModal())return;const alreadySolo=solo&&selected===track.id;await selectTrack(track);if(selected!==track.id||pendingSelection)return;solo=!alreadySolo;if(solo){ensureAudio();player.play().catch(failure);}renderTracks();paintTransport();};
            const panInput=row.querySelector('input');panInput.onclick=event=>event.stopPropagation();panInput.oninput=event=>setTrackPan(track.id,event.target.value);
            panInput.nextElementSibling.style.transform='rotate('+((trackPans.get(track.id)||0)*120)+'deg)';
            el('daw-track-list').append(row);
            const lane = document.createElement('div'); lane.className = 'daw-lane'; lane.dataset.trackId = track.id;
            lane.style.setProperty('--track-color', colors[track.id] || colors.source);
            lane.style.setProperty('--region-header',(regionColors[track.id]||regionColors.source)[0]);
            lane.style.setProperty('--region-bg',(regionColors[track.id]||regionColors.source)[1]);
            lane.style.setProperty('--region-ink',['piano','strings'].includes(track.id)?'#171b1f':'#f2f5f7');
            const region = document.createElement('button'); region.type = 'button'; region.className = 'daw-region'; region.classList.toggle('selected', track.id === selected);
            region.setAttribute('aria-label', 'Open '+track.label+' waveform');
            const caption = document.createElement('span'); caption.textContent = track.id === 'source' ? title(sourceName) : track.label;
            const canvas = document.createElement('canvas'); canvas.className = 'daw-region-wave'; canvas.setAttribute('aria-hidden','true');
            region.append(caption, canvas); region.onclick = () => selectTrack(track); lane.append(region); el('daw-regions').append(lane);
            const patch = document.createElement('button'); patch.className = 'daw-recording'; patch.classList.toggle('selected', track.id === selected);
            patch.textContent = track.label;patch.hidden=(!!search&&!track.label.toLocaleLowerCase().includes(search))||(libraryFamily!=='all'&&track.id!==libraryFamily);patch.onclick = () => selectTrack(track); el('daw-recordings').append(patch);
        }
        text('daw-lane-count', visible.length); text('daw-track-count', tracks.length ? tracks.length+' audio '+(tracks.length===1?'track':'tracks') : 'No recording open');
        el('daw-empty').hidden = !!sourceName;
        el('daw-arrangement').classList.toggle('daw-is-empty', !tracks.length);
        paintInspector();paintTrackPending();restoreTrackFocus();scheduleDraw();
    }

    function paintInspector() {
        const track = chosen(), label = track?.label || 'Recording';
        text('daw-inspector-name', label);text('daw-instrument-name',track?.id==='source'?'Recording':label);text('daw-editor-title',label);
        el('daw-inspector-name').title=label;el('daw-editor-title').title=label;
        text('daw-track-name',label);text('daw-channel-name',label);text('daw-region-transpose',amount||0);
        el('daw-instrument-art').querySelector('svg').outerHTML = svg(track?.id || 'source');
        el('daw-instrument-art').querySelector('img').hidden=track?.id!=='piano';
        el('daw-instrument-art').querySelector('svg').toggleAttribute('hidden',track?.id==='piano');
        el('daw-track-icon').innerHTML=instrumentIcon(track?.id||'source');
        el('daw-color').value=colors[track?.id]||colors.source;
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
        const rate=currentPeaks?.sourceSampleRate,bits=currentPeaks?.sourceBits;
        text('daw-format',rate&&bits?(rate/1000)+' kHz · '+bits+'-bit'+(currentPeaks.sourceEncoding==='float'?' float':'')+' · '+(currentPeaks.sourceChannels===1?'Mono':'Stereo'):currentPeaks?'Stereo · Local audio':'Local audio');
    }

    function paintTransport() {
        const enabled = !!sourceName && !pendingSelection;
        for (const id of ['daw-play','daw-stop','daw-rewind','daw-loop','daw-audition','daw-mute','daw-channel-mute','daw-channel-solo','daw-pan']) el(id).disabled = !enabled;
        const play = el('daw-play'), state = player.paused ? 'play' : 'pause';
        if (play.dataset.state !== state) { play.innerHTML = svg(state); play.dataset.state = state; }
        play.setAttribute('aria-label', player.paused ? 'Play' : 'Pause');
        play.classList.toggle('playing', !player.paused);
        el('daw-loop').setAttribute('aria-pressed', String(player.loop||loopEnd!==null));
        el('daw-mute').setAttribute('aria-pressed', String(player.muted));el('daw-channel-mute').setAttribute('aria-pressed',String(player.muted));
        el('daw-audition').setAttribute('aria-pressed',String(solo));el('daw-channel-solo').setAttribute('aria-pressed',String(solo));
        el('daw-volume').value = String(player.volume);el('daw-master-volume').value=String(player.volume);el('daw-rate').value = String(player.playbackRate);
        const pan=Number(el('daw-pan').value);text('daw-pan-label',pan===0?'0.0':(pan<0?'L':'R')+Math.round(Math.abs(pan)*100));el('daw-pan-pointer').style.transform='rotate('+(pan*120)+'deg)';
        el('daw-undo').disabled=!history.length;el('daw-redo').disabled=!future.length;
        text('daw-gain-label', player.volume ? (20*Math.log10(player.volume)).toFixed(1)+' dB' : '−∞ dB');
        text('daw-audition-state', player.paused ? 'Stopped' : 'Playing');
        el('daw-fader-cap').style.top = (1-player.volume)*80+'%';
        const bpm = result?.rhythm_correction?.mode === 'grid' ? result.rhythm_correction.bpm : result?.tempo_bpm;
        const position = Number.isFinite(player.currentTime) ? player.currentTime : 0;
        const timing = BlazeFlow.state(flowMap,position);
        const measure = flowMap.measures[timing.measure];
        const meter = measure && !['unknown','lead-in'].includes(measure.kind) ? measure.numerator : null;
        if(!manualProject&&bpm)projectTempo=bpm;
        if(!manualProject&&meter){projectNumerator=meter;projectDenominator=measure.denominator;}
        if(!manualProject&&result?.key)projectKey=result.key;
        text('daw-tempo',Number(projectTempo).toFixed(projectTempo%1?1:0));
        text('daw-meter',projectNumerator+'/'+projectDenominator);
        text('daw-key',projectKey);text('daw-analysis-key',result?.key||'—'); text('daw-analysis-tempo',bpm?Number(bpm).toFixed(0)+' BPM':'—');
        text('daw-time', elapsed(position));
        const quarter=position*projectTempo/60,beat=quarter/(4/projectDenominator);
        text('daw-bars',(Math.floor(beat/projectNumerator)+1)+'  '+(Math.floor(beat)%projectNumerator+1));
        const progress = duration() ? Math.max(0,Math.min(1,position/duration())) : 0;
        el('daw-arrangement-playhead').style.transform='translateX('+(progress*arrangementPixelWidth)+'px)';
        el('daw-editor-playhead').style.transform='translateX('+(progress*editorPixelWidth)+'px)';
        paintMeters(position);
        if(metronome&&audioGraph&&!player.paused){const beatIndex=Math.floor(quarter);if(beatIndex!==lastClickBeat){lastClickBeat=beatIndex;const oscillator=audioGraph.context.createOscillator(),gain=audioGraph.context.createGain(),now=audioGraph.context.currentTime;oscillator.frequency.value=beatIndex%projectNumerator===0?1500:1000;gain.gain.setValueAtTime(.04,now);gain.gain.exponentialRampToValueAtTime(.0001,now+.035);oscillator.connect(gain).connect(audioGraph.context.destination);oscillator.start(now);oscillator.stop(now+.04);}}
        el('daw-waveform').setAttribute('aria-valuenow', String(Math.round(progress*100)));
        el('daw-waveform').setAttribute('aria-valuetext', elapsed(position)+' of '+elapsed(duration()));
        el('daw-midi-guide').setAttribute('aria-valuenow',String(Math.round(progress*100)));
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
    function drawNotes(canvas,data,color,low=48,high=84) {
        const r=canvas.getBoundingClientRect(),d=Math.min(devicePixelRatio||1,2);canvas.width=Math.max(1,Math.round(r.width*d));canvas.height=Math.max(1,Math.round(r.height*d));
        const g=canvas.getContext('2d');g.scale(d,d);g.clearRect(0,0,r.width,r.height);const length=duration();if(!length||!data?.chords)return;
        g.fillStyle=color;
        for(const event of data.chords){const chord=parts(event.chord);if(!chord)continue;const notes=intervals[chord.quality]||intervals.maj;for(const interval of notes){const note=60+chord.root+interval;if(note<low||note>high)continue;const x=event.start/length*r.width,width=Math.max(2,(event.end-event.start)/length*r.width-2),y=(high-note)/(high-low)*Math.max(1,r.height-12)+8;g.fillRect(x,y,width,Math.max(2,Math.min(5,r.height/(high-low)*.72)));}}
    }
    let drawFrame=0;
    function scheduleDraw() { cancelAnimationFrame(drawFrame);drawFrame=requestAnimationFrame(draw); }
    function ruler(target, length, detailed=false) {
        target.replaceChildren();
        const width=target.getBoundingClientRect().width;
        const secondsPerBar=60/projectTempo*(4/projectDenominator)*projectNumerator;
        target.style.setProperty('--bar-pixels',(length?secondsPerBar/length*width:100)+'px');
        target.style.setProperty('--beat-pixels',(length?secondsPerBar/projectNumerator/length*width:25)+'px');
        const total=Math.max(1,length/secondsPerBar),step=2**Math.ceil(Math.log2(Math.max(1,total/Math.max(2,width/(detailed?110:100)))));
        for(let bar=0;bar<=total+.0001;bar+=step) {
            const mark=document.createElement('span');
            mark.textContent=String(bar+1);
            mark.style.left=(bar/total*100)+'%';target.append(mark);
        }
        const cycle=!detailed&&(player.loop||loopEnd!==null);
        target.classList.toggle('daw-has-cycle',cycle);
        if(cycle&&length){const start=loopEnd!==null?loopStart:0,end=loopEnd!==null?loopEnd:length,strip=document.createElement('i');strip.className='daw-cycle-strip';strip.style.left=(start/length*100)+'%';strip.style.width=((end-start)/length*100)+'%';strip.textContent=String(Math.floor(start/secondsPerBar)+1);target.append(strip);}
    }
    function draw() {
        if (!active()) return;
        const length=duration();
        el('daw-editor-content').style.width=(zoom*100)+'%';
        el('daw-scroll').disabled=zoom<=1;
        el('daw-scroll').style.setProperty('--scroll-thumb',Math.max(12,el('daw-editor-scroll').clientWidth/zoom-36)+'px');
        editorPixelWidth=el('daw-editor-content').clientWidth;arrangementPixelWidth=el('daw-regions').clientWidth;
        ruler(el('daw-ruler'),length); ruler(el('daw-editor-ruler'),length,true);
        for(const lane of el('daw-regions').querySelectorAll('.daw-lane')) {
            const t=tracks.find(t=>t.id===lane.dataset.trackId);
            const canvas=lane.querySelector('canvas');
            peakCanvas(canvas,t?.waveform,'#c7e5fc');
        }
        el('daw-waveform').hidden=editorMode!=='audio';el('daw-midi-guide').hidden=editorMode!=='midi';
        if(editorMode==='audio')peakCanvas(el('daw-waveform'),currentPeaks,'#c5dff7',true);
        else drawNotes(el('daw-midi-guide'),guide,colors[selected]||colors.piano);
        el('daw-wave-empty').hidden=editorMode==='audio'?!!currentPeaks:!!guide?.chords?.length;
        text('daw-wave-empty',editorMode==='midi'?'Analyze chords to view a MIDI guide.':sourceName?(loading?'Reading waveform…':'Waveform unavailable. Playback and analysis remain available.'):'Import a recording to begin.');
        root.style.setProperty('--bar-grid',(length?60/projectTempo*(4/projectDenominator)*projectNumerator/length*100:12.5)+'%');
        text('daw-editor-region',chosen()?.id==='source'?title(sourceName):chosen()?.label||'Audio');
        paintRange(); paintTransport();
    }
    function paintRange() {
        const range=el('daw-wave-selection'),length=duration(); range.hidden=!selection||!length;
        if(selection&&length){const width=el('daw-editor-content').clientWidth;range.style.left=(selection[0]/length*width)+'px';range.style.width=((selection[1]-selection[0])/length*width)+'px';text('daw-selection-readout','Selection  '+elapsed(selection[0])+' – '+elapsed(selection[1])+'  |  '+((selection[1]-selection[0]).toFixed(3))+' s');}
        else text('daw-selection-readout','No range selected');
    }
    const waveform=el('daw-waveform');let pointerStart=null;
    const cycleRuler=el('daw-ruler');let cycleStart=null;
    const rulerTime=event=>{const r=cycleRuler.getBoundingClientRect(),seconds=60/projectTempo*(4/projectDenominator);return Math.max(0,Math.min(duration(),Math.round((event.clientX-r.left)/r.width*duration()/seconds)*seconds));};
    cycleRuler.onpointerdown=event=>{if(event.button!==0||!duration())return;cycleStart=rulerTime(event);cycleRuler.setPointerCapture(event.pointerId);};
    cycleRuler.onpointermove=event=>{if(cycleStart===null||!cycleRuler.hasPointerCapture(event.pointerId))return;const end=rulerTime(event);loopStart=Math.min(cycleStart,end);loopEnd=Math.max(cycleStart,end);player.loop=false;updateLoop();scheduleDraw();};
    cycleRuler.onpointerup=cycleRuler.onpointercancel=event=>{if(cycleRuler.hasPointerCapture(event.pointerId))cycleRuler.releasePointerCapture(event.pointerId);cycleStart=null;if(loopEnd!==null&&loopEnd-loopStart<.05)loopStart=loopEnd=null;updateLoop();scheduleDraw();};
    const atPointer=event=>Math.max(0,Math.min(1,(event.clientX-waveform.getBoundingClientRect().left)/waveform.getBoundingClientRect().width))*duration();
    waveform.onpointerdown=event=>{
        if(event.button!==0||!duration()||!sourceName)return;
        waveform.setPointerCapture(event.pointerId);pointerStart=event.shiftKey||rangeTool?atPointer(event):null;
        if(pointerStart===null){selection=null;seek(atPointer(event));paintRange();}
        else{selection=[pointerStart,pointerStart];paintRange();}
    };
    waveform.onpointermove=event=>{if(waveform.hasPointerCapture(event.pointerId)){if(pointerStart===null)seek(atPointer(event));else{let end=atPointer(event);if(el('daw-snap').value==='beat'){const spacing=60/projectTempo*(4/projectDenominator);end=Math.round(end/spacing)*spacing;}selection=[Math.min(pointerStart,end),Math.max(pointerStart,end)];paintRange();}}};
    waveform.onpointerup=waveform.onpointercancel=event=>{if(waveform.hasPointerCapture(event.pointerId))waveform.releasePointerCapture(event.pointerId);pointerStart=null;};
    waveform.onkeydown=event=>{let target=null;if(event.key==='ArrowLeft')target=player.currentTime-5;if(event.key==='ArrowRight')target=player.currentTime+5;if(event.key==='Home')target=0;if(event.key==='End')target=duration();if(event.key==='Escape'){selection=null;paintRange();}if(target!==null){event.preventDefault();seek(target);}};
    const midiGuide=el('daw-midi-guide');midiGuide.tabIndex=0;midiGuide.setAttribute('role','slider');midiGuide.setAttribute('aria-valuemin','0');midiGuide.setAttribute('aria-valuemax','100');
    midiGuide.onclick=event=>{const r=midiGuide.getBoundingClientRect();if(duration())seek((event.clientX-r.left)/r.width*duration());};midiGuide.onkeydown=waveform.onkeydown;

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
        if(result&&result!==lastGuide){lastGuide=result;guide=result;guideJob=sessionJob;scheduleDraw();}
        paintTransport();
        const stems=window.BlazeMacStems?.snapshot();
        const next=JSON.stringify([sourceRevision,sourceName,stems?.status,stems?.jobId]);
        if(next===signature)return;
        signature=next;const mine=++generation;controller?.abort();controller=new AbortController();
        const revision=sourceRevision;selection=null;waveformReady=false;
        if(!sourceName||!Number.isSafeInteger(revision)){
            tracks=[];selected='source';currentPeaks=null;guide=lastGuide=null;guideJob='';sessionJob='';sessionRevision=revision;renderTracks();message('Import a recording to begin.');return;
        }
        const sourceChanged=sessionRevision!==revision;
        const previousGuide=guide&&sessionJob?{jobId:sessionJob,data:guide}:null;
        sessionRevision=revision;loading=true;
        if(sourceChanged){currentPeaks=null;guide=null;lastGuide=null;tracks=[{id:'source',label:title(sourceName),waveform:null}];selected='source';renderTracks();}
        message('Reading local waveform…','loading');
        text('daw-session-title',title(sourceName));
        try{
            const data=await fetchWave(revision,'','',controller.signal);
            if(mine!==generation||revision!==sourceRevision||!active())return;
            currentPeaks=data;waveformReady=true;const nextJob=data.stemJobId||'';
            if(sourceChanged){
                guide=result||(nextJob&&previousGuide?.jobId===nextJob?previousGuide.data:null);
                lastGuide=result||null;guideJob=nextJob;
            }
            if(nextJob!==sessionJob||!sessionTitle||sessionTitle==='Untitled'){if(result){guide=result;guideJob=nextJob;}else if(guideJob!==nextJob){guide=null;lastGuide=null;}if(!nextJob||!sessionJob)sessionTitle=title(stems?.sourceName||sourceName);}
            sessionJob=nextJob;
            if(!sessionJob)sessionTitle=title(sourceName);
            text('daw-window-title',sessionTitle+' — Blaze');text('daw-workflow-title',sessionTitle);
            const rows=sessionJob&&stems?.status==='done'&&stems.jobId===sessionJob&&Array.isArray(stems.stems)?stems.stems.filter(r=>labels[r.id]):[];
            // Display names can collide (an original mix may be Piano.wav).
            // The server identifies the selected saved file from its source path.
            const selectedStem=rows.find(row=>row.id===data.selectedStem);
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
        }catch(error){if(mine!==generation||error.name==='AbortError')return;loading=false;currentPeaks=null;waveformReady=false;if(error.status===503)signature='';message(error.message||'The waveform could not be read.','error');scheduleDraw();}
    }
    const resize=new ResizeObserver(scheduleDraw);resize.observe(root);resize.observe(el('daw-editor-scroll'));
    let previousWidth=innerWidth;
    window.addEventListener('resize',()=>{
        if(innerWidth<800&&previousWidth>=800){libraryOpen=false;inspectorOpen=false;setPanels();}
        else if(innerWidth<1100&&previousWidth>=1100){libraryOpen=false;setPanels();}
        if(innerWidth>=800&&previousWidth<800&&!inspectorUserChoice){inspectorOpen=true;setPanels();}
        previousWidth=innerWidth;
    });
    new MutationObserver(()=>{if(active()){setPanels();syncSession();}else{controller?.abort();signature='';++generation;practice.hidden=true;el('daw-chords').setAttribute('aria-expanded','false');paintTransport();}}).observe(panel,{attributes:true,attributeFilter:['hidden']});
    for(const event of ['timeupdate','play','pause','loadedmetadata','volumechange','ratechange','seeked','ended'])player.addEventListener(event,paintTransport);
    const timer=setInterval(()=>{if(active()){syncSession();paintTransport();}},750);
    window.addEventListener('blaze-mac-media-changed',()=>{signature='';void syncSession();});
    window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);controller?.abort();cancelAnimationFrame(frame);resize.disconnect();},{once:true});
    window.BlazeMacStudio={snapshot:()=>({active:active(),selectedTrack:selected,tracks:tracks.map(t=>({id:t.id,label:t.label})),zoom,libraryOpen,inspectorOpen,waveformReady,waveformsReady:tracks.filter(t=>t.waveform).length,sourceRevision:sessionRevision,sessionTitle,editorMode,guideReady:!!guide?.chords?.length,projectTempo,projectNumerator,projectDenominator,audio:audioGraph?{pan:audioGraph.pan.pan.value,equalizerGain:audioGraph.eq.gain.value,compressionRatio:audioGraph.compressor.ratio.value}:null})};
    setPanels();renderTracks();syncSession();
})();
