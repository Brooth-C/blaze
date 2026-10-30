/* Mac chord workspace: presentation of the existing indexed timing model.
 * Playback, recognition, corrections and source ownership stay in Studio. */
(() => {
    'use strict';
    const el = id => document.getElementById(id);
    const root = el('mac-studio-workspace');
    if (!root || document.documentElement.dataset.presentation !== 'mac') return;
    const heading = document.createElement('h1'); heading.className = 'sr-only'; heading.textContent = 'Music Studio'; root.prepend(heading);
    const player = el('media'), main = root.querySelector('.daw-main');
    const harmony = document.createElement('section');
    harmony.id = 'daw-harmony';
    harmony.setAttribute('aria-label', 'Chord timeline');
    harmony.innerHTML = '<div class="harmony-toolbar"><h2>Chords</h2>' +
        '<p class="harmony-context"><span>Now <strong id="harmony-now">—</strong></span><span>Next <strong id="harmony-next">—</strong></span><span id="harmony-countdown"></span></p>' +
        '<div class="harmony-navigation"><button id="harmony-previous" aria-label="Previous chord group" title="Previous chord group">‹</button><span id="harmony-range"></span><button id="harmony-next-group" aria-label="Next chord group" title="Next chord group">›</button>' +
        '<button id="harmony-follow" aria-pressed="true" title="Follow the current playback position">Follow</button><select id="harmony-zoom" aria-label="Chord timeline zoom"><option value="2">2 bars</option><option value="4" selected>4 bars</option><option value="8">8 bars</option></select></div></div>' +
        '<div id="harmony-bars" tabindex="0" aria-label="Chord regions; scroll horizontally to inspect the group"></div>' +
        '<div id="harmony-empty"><p id="harmony-status">Open a recording to analyse its chords.</p><button id="harmony-analyze">Analyse Chords</button></div><p id="harmony-announcement" class="sr-only" role="status" aria-live="polite"></p>';
    main.prepend(harmony);

    const editorToggle = document.createElement('button');
    editorToggle.id = 'daw-editor-toggle'; editorToggle.textContent = 'Editor';
    editorToggle.setAttribute('aria-controls', 'daw-editor');
    editorToggle.setAttribute('aria-expanded', 'true');
    editorToggle.title = 'Show or hide the selected track editor';
    root.querySelector('.daw-workflow-actions').append(editorToggle);
    editorToggle.onclick = () => {
        const hidden = !el('daw-editor').hidden;
        el('daw-editor').hidden = hidden;
        root.classList.toggle('daw-editor-hidden', hidden);
        editorToggle.setAttribute('aria-expanded', String(!hidden));
    };
    el('harmony-analyze').onclick = () => el('analyze').click();

    let first = 0, count = 4, follow = true, lastMap = null, signature = '';
    let regions = [], markers = [], stopped = false, animationFrame = 0;
    let lastPaint = '', paintedMap = null;
    const text = (id, value) => { if (el(id).textContent !== value) el(id).textContent = value; };
    const stamp = value => {
        const s = Math.max(0, Number(value) || 0);
        return Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');
    };
    const label = chord => chord === 'N' ? 'N' : chord === 'X' ? '—' : pretty(chord);
    const spoken = chord => chord === 'N' ? 'No chord' : chord === 'X' ? 'Uncertain chord' : pretty(chord);
    const knownBar = measure => !['unknown', 'lead-in'].includes(measure.kind);
    const setFollow = value => {
        follow = value; signature = '';
        el('harmony-follow').setAttribute('aria-pressed', String(value)); paint();
    };
    const page = direction => {
        follow = false; el('harmony-follow').setAttribute('aria-pressed', 'false');
        const base = flowMap.barStart || 0;
        const last = base + Math.floor(Math.max(0, flowMap.measures.length - 1 - base) / count) * count;
        first = Math.max(base, Math.min(last, first + count * direction));
        signature = ''; paint();
    };
    el('harmony-previous').onclick = () => page(-1);
    el('harmony-next-group').onclick = () => page(1);
    el('harmony-follow').onclick = () => setFollow(!follow);
    el('harmony-zoom').onchange = event => { count = Number(event.target.value); signature = ''; paint(); };

    function build(measures) {
        const restoreFocus = el('harmony-bars').contains(document.activeElement);
        regions = []; markers = [];
        const fragment = document.createDocumentFragment();
        for (const measure of measures) {
            const bar = document.createElement('div'); bar.className = 'harmony-bar';
            const ruler = document.createElement('button'); ruler.className = 'harmony-bar-ruler';
            const caption = knownBar(measure) ? 'Bar ' + (measure.barNumber || measure.index - (flowMap.barStart || 0) + 1) : stamp(measure.start);
            ruler.textContent = caption;
            ruler.title = knownBar(measure) ? caption + ' · ' + (measure.denominator ? measure.numerator + '/' + measure.denominator : measure.numerator + ' detected beats') : 'Meter unconfirmed · ' + stamp(measure.start);
            ruler.setAttribute('aria-label', 'Seek to ' + ruler.title);
            ruler.onclick = () => seek(measure.start);
            const lane = document.createElement('div'); lane.className = 'harmony-region-lane';
            const span = measure.end - measure.start;
            const beats = measure.beats.length ? measure.beats : (Array.isArray(result?.beats) ? result.beats.filter(beat => Number.isFinite(beat) && beat >= measure.start && beat < measure.end) : []);
            for (const beat of beats) {
                const tick = document.createElement('i'); tick.className = 'harmony-beat';
                tick.style.left = ((beat - measure.start) / span * 100) + '%';
                tick.setAttribute('aria-hidden', 'true'); lane.append(tick);
            }
            for (const region of measure.regions) {
                const button = document.createElement('button'); button.className = 'harmony-region';
                button.textContent = label(region.chord);
                button.style.left = ((region.start - measure.start) / span * 100) + '%';
                button.style.width = ((region.end - region.start) / span * 100) + '%';
                button.title = spoken(region.chord) + ' · ' + stamp(region.start) + '–' + stamp(region.end);
                button.setAttribute('aria-label', 'Seek to ' + button.title);
                button.onclick = () => seek(region.start);
                button.oncontextmenu = event => { event.preventDefault(); seek(region.start); el('edit').click(); };
                lane.append(button); regions.push({button, region});
            }
            const marker = document.createElement('i'); marker.className = 'harmony-playhead';
            marker.setAttribute('aria-hidden', 'true'); lane.append(marker);
            markers.push({marker, measure}); bar.append(ruler, lane); fragment.append(bar);
        }
        el('harmony-bars').replaceChildren(fragment);
        el('harmony-bars').style.setProperty('--harmony-count', String(measures.length || count));
        if (restoreFocus) (regions.find(({region}) => player.currentTime >= region.start && player.currentTime < region.end)?.button || el('harmony-bars').querySelector('button'))?.focus({preventScroll: true});
    }

    function paint() {
        if (stopped || el('studio-panel').hidden || document.hidden) return;
        const paintKey = [sourceRevision, player.currentTime, busy, first, count, follow, signature].join(':');
        if (paintKey === lastPaint && paintedMap === flowMap) return;
        lastPaint = paintKey; paintedMap = flowMap;
        const available = !!result && flowMap.measures.length > 0;
        el('harmony-empty').hidden = available; el('harmony-bars').hidden = !available;
        harmony.setAttribute('aria-busy', String(busy));
        el('harmony-analyze').disabled = !sourceName || busy;
        el('harmony-analyze').hidden = !sourceName;
        if (!available) {
            text('harmony-status', busy ? 'Analysing chords… You can keep working.' : sourceName ? 'Analyse this recording to see its chord changes.' : 'Open a recording to analyse its chords.');
            text('harmony-now', '—'); text('harmony-next', '—');
            text('harmony-countdown', ''); text('harmony-range', '');
            text('harmony-announcement', '');
            el('harmony-previous').disabled = el('harmony-next-group').disabled = true;
            signature = ''; lastMap = null; return;
        }
        if (lastMap !== flowMap) { first = 0; signature = ''; lastMap = flowMap; }
        const state = BlazeFlow.state(flowMap, player.currentTime);
        const base = flowMap.barStart || 0;
        if (follow) first = state.measure < base ? 0 : base + Math.floor(Math.max(0, state.measure - base) / count) * count;
        first = Math.min(first, Math.max(0, flowMap.measures.length - 1));
        const measures = flowMap.measures.slice(first, first + count);
        const key = first + ':' + count;
        if (signature !== key) { build(measures); signature = key; }
        const musical = measures.every(knownBar);
        text('harmony-range', musical ? (first - base + 1) + '–' + (first - base + measures.length) : 'Time');
        el('harmony-zoom').setAttribute('aria-label', musical ? 'Chord timeline zoom in bars' : 'Chord timeline zoom in time windows; meter unconfirmed');
        for (const option of el('harmony-zoom').options) { const caption = option.value + (musical ? ' bars' : ' windows'); if (option.textContent !== caption) option.textContent = caption; }
        el('harmony-previous').disabled = first === 0;
        el('harmony-next-group').disabled = first + count >= flowMap.measures.length;
        text('harmony-now', state.chord < 0 ? '—' : label(flowMap.chords[state.chord].chord));
        text('harmony-next', state.next < 0 ? '—' : label(flowMap.chords[state.next].chord));
        text('harmony-countdown', state.next < 0 ? '' : 'in ' + state.seconds.toFixed(1) + 's');
        text('harmony-announcement', state.chord < 0 ? 'No active chord.' : 'Now ' + spoken(flowMap.chords[state.chord].chord) + (state.next < 0 ? '.' : '. Next ' + spoken(flowMap.chords[state.next].chord) + '.'));
        for (const {button, region} of regions) {
            const current = !state.ended && state.time >= region.start && state.time < region.end;
            button.classList.toggle('current', current);
            if (current && !button.hasAttribute('aria-current')) button.setAttribute('aria-current', 'true');
            else if (!current && button.hasAttribute('aria-current')) button.removeAttribute('aria-current');
        }
        for (const {marker, measure} of markers) {
            marker.hidden = state.ended || state.time < measure.start || state.time >= measure.end;
            marker.style.transform = 'translateX(' + Math.max(0, Math.min(1, (state.time - measure.start) / (measure.end - measure.start))) * 100 + '%)';
        }
    }

    // A separator is directly manipulated, not animated; keyboard equivalents
    // and pointer cancellation use the same bounded size setter.
    function separator(parent, id, orientation, read, write, minimum, maximum) {
        const handle = document.createElement('div'); handle.id = id; handle.className = 'daw-panel-resize';
        handle.tabIndex = 0; handle.setAttribute('role', 'separator');
        handle.setAttribute('aria-orientation', orientation);
        handle.setAttribute('aria-label', orientation === 'vertical' ? 'Resize inspector' : 'Resize waveform editor');
        const bound = () => Math.max(minimum, typeof maximum === 'function' ? maximum() : maximum);
        handle.setAttribute('aria-valuemin', String(minimum)); handle.setAttribute('aria-valuemax', String(Math.round(bound())));
        const apply = (value, limit) => { const next = Math.max(minimum, Math.min(limit, value)); write(next); handle.setAttribute('aria-valuenow', String(Math.round(next))); handle.setAttribute('aria-valuemax', String(Math.round(limit))); };
        handle.setAttribute('aria-valuenow', String(Math.max(minimum, Math.round(read()))));
        let drag = null;
        handle.onpointerdown = event => {
            if (event.button !== 0) return;
            event.preventDefault(); handle.focus(); handle.setPointerCapture(event.pointerId);
            drag = {position: orientation === 'vertical' ? event.clientX : event.clientY, size: read(), limit: bound()};
        };
        handle.onpointermove = event => { if (drag) apply(drag.size + (orientation === 'vertical' ? event.clientX - drag.position : drag.position - event.clientY), drag.limit); };
        const release = () => { drag = null; };
        handle.onpointerup = handle.onpointercancel = handle.onlostpointercapture = release;
        window.addEventListener('blur', release);
        handle.onkeydown = event => {
            const increase = orientation === 'vertical' ? 'ArrowRight' : 'ArrowUp';
            const decrease = orientation === 'vertical' ? 'ArrowLeft' : 'ArrowDown';
            if (![increase, decrease, 'Home', 'End'].includes(event.key)) return;
            event.preventDefault(); event.stopPropagation();
            const limit = bound();
            apply(event.key === 'Home' ? minimum : event.key === 'End' ? limit : read() + (event.key === increase ? 8 : -8), limit);
        };
        parent.append(handle);
        const observed = orientation === 'vertical' ? el('daw-inspector') : el('daw-editor');
        const observer = new ResizeObserver(() => {
            const current = read();
            if (current > 0) {
                handle.setAttribute('aria-valuenow', String(Math.round(current)));
                handle.setAttribute('aria-valuemax', String(Math.round(bound())));
            }
        });
        observer.observe(observed);
        window.addEventListener('pagehide', () => { observer.disconnect(); window.removeEventListener('blur', release); }, {once: true});
    }
    separator(root.querySelector('.daw-body'), 'daw-inspector-resize', 'vertical', () => el('daw-inspector').getBoundingClientRect().width,
        value => root.style.setProperty('--inspector-width', value + 'px'), 160, 300);
    separator(el('daw-editor'), 'daw-editor-resize', 'horizontal', () => el('daw-editor').getBoundingClientRect().height,
        value => root.style.setProperty('--studio-editor-size', value + 'px'), 180, () => Math.min(360, main.clientHeight - 224));
    function queueFrame() {
        if (animationFrame || stopped || player.paused || player.ended || document.hidden || el('studio-panel').hidden) return;
        animationFrame = requestAnimationFrame(() => { animationFrame = 0; paint(); queueFrame(); });
    }
    const update = () => { paint(); queueFrame(); };
    const timer = setInterval(update, 150);
    const events = ['timeupdate', 'seeked', 'loadedmetadata', 'play', 'pause'];
    for (const event of events) player.addEventListener(event, update);
    window.addEventListener('pagehide', () => { stopped = true; clearInterval(timer); cancelAnimationFrame(animationFrame); for (const event of events) player.removeEventListener(event, update); }, {once: true});
    window.BlazeMacHarmony = {snapshot: () => ({first, count, follow, available: !!result, editorOpen: !el('daw-editor').hidden}), refresh: paint};
    paint();
})();
