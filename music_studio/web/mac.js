/* Mac presentation adapter. AppKit owns navigation; the existing media element
   and Studio engine remain the only playback and analysis implementation. */
(() => {
    'use strict';
    if (document.documentElement.dataset.presentation !== 'mac') return;

    const byId = id => document.getElementById(id);
    const sections = new Set(['explore', 'downloads', 'library', 'studio']);
    const player = byId('mini-player');
    const now = byId('now-dialog');
    const video = byId('media');
    const sidebar = document.querySelector('.song-sidebar');
    let focusSearchRequest = 0;
    let importRequest = 0;
    let nativeChromeInstalled = false;
    let scrubbing = false;
    let lastSource = '';

    const text = (element, value) => {
        if (element.textContent !== value) element.textContent = value;
    };
    const bounded = (value, length = 200) => String(value || '').slice(0, length);
    const currentSection = () => window.BlazeDesktop.activeSection();
    const modalOpen = () => !!document.querySelector('dialog[open]:not(#now-dialog)');
    const hasMedia = () => !!sourceName;
    const duration = () => Number.isFinite(video.duration) ? video.duration : 0;
    const position = () => Number.isFinite(video.currentTime) ? video.currentTime : 0;
    const redraw = () => requestAnimationFrame(() => {
        if (currentSection() === 'studio') { wave(); diagram(); paintFlow(); }
    });

    // Existing controls are moved, never recreated. Their engine handlers stay
    // attached, and the media element stays inside its original preview panel.
    const practice = document.createElement('details');
    practice.id = 'mac-practice';
    practice.className = 'mac-practice';
    const practiceSummary = document.createElement('summary');
    practiceSummary.textContent = 'Practice controls';
    practice.append(practiceSummary, document.querySelector('.practice-toolbar'));
    document.querySelector('.song-top').after(practice);

    const inspector = document.createElement('details');
    inspector.id = 'mac-inspector';
    inspector.className = 'mac-inspector';
    const inspectorSummary = document.createElement('summary');
    inspectorSummary.textContent = 'Song details';
    inspector.append(inspectorSummary, sidebar);
    document.querySelector('.studio-heading').append(inspector);
    for (const disclosure of [practice, inspector]) disclosure.addEventListener('toggle', redraw);

    const previous = document.createElement('button');
    previous.id = 'mac-mini-previous';
    previous.className = 'transport-icon mac-mini-previous';
    previous.setAttribute('aria-label', 'Back 10 seconds');
    previous.innerHTML = icon('previous');
    previous.onclick = () => { if (hasMedia()) seek(position() - 10); };
    const transport = document.createElement('div');
    transport.className = 'mac-mini-transport';
    transport.setAttribute('role', 'group');
    transport.setAttribute('aria-label', 'Playback controls');
    transport.append(previous, byId('mini-play'), byId('mini-next'));
    player.append(transport);

    const timeline = document.createElement('div');
    timeline.className = 'mac-mini-timeline';
    const slider = document.createElement('input');
    slider.id = 'mac-mini-seek';
    slider.className = 'mac-mini-seek';
    slider.type = 'range';
    slider.min = '0'; slider.max = '1000'; slider.step = '1'; slider.value = '0';
    slider.setAttribute('aria-label', 'Playback position');
    const times = document.createElement('div');
    times.className = 'mac-mini-times';
    const elapsed = document.createElement('span');
    elapsed.id = 'mac-mini-position';
    const total = document.createElement('span');
    total.id = 'mac-mini-duration';
    times.append(elapsed, total);
    timeline.append(slider, times);
    player.append(timeline);

    const volumeLabel = document.createElement('label');
    volumeLabel.className = 'mac-mini-volume';
    volumeLabel.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4Z"/><path d="M16 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
    const volume = document.createElement('input');
    volume.id = 'mac-mini-volume';
    volume.type = 'range'; volume.min = '0'; volume.max = '1'; volume.step = '.01';
    volume.value = String(video.volume);
    volume.setAttribute('aria-label', 'Player volume');
    volumeLabel.append(volume);
    player.append(volumeLabel);
    volume.addEventListener('input', () => {
        video.volume = Math.max(0, Math.min(1, Number(volume.value)));
        byId('volume').value = volume.value;
    });
    video.addEventListener('volumechange', () => { volume.value = String(video.volume); });

    const paintTimeline = () => {
        const length = duration();
        const value = scrubbing ? Number(slider.value) / 1000 * length : position();
        if (!scrubbing) slider.value = String(length ? value / length * 1000 : 0);
        slider.disabled = !length;
        slider.setAttribute('aria-valuetext', time(value) + ' of ' + time(length));
        text(elapsed, time(value)); text(total, time(length));
    };
    slider.addEventListener('input', () => { scrubbing = true; paintTimeline(); });
    slider.addEventListener('change', () => {
        const target = Number(slider.value) / 1000 * duration();
        scrubbing = false;
        if (duration()) seek(target);
        paintTimeline();
    });
    const cancelScrub = () => { scrubbing = false; paintTimeline(); };
    slider.addEventListener('pointercancel', cancelScrub);
    slider.addEventListener('blur', cancelScrub);

    const closePlayer = () => window.BlazeDesktop.closePlayer();
    const beginImport = () => {
        if (modalOpen() || busy || importing) return false;
        window.BlazeDesktop.cancelPreparation();
        closePlayer();
        return true;
    };
    const requestImport = () => {
        if (!beginImport()) return false;
        if (document.body.dataset.nativeSidebar === 'true') ++importRequest;
        else { navigate('studio'); byId('import').click(); }
        return true;
    };
    const navigate = name => {
        if (!sections.has(name) || modalOpen()) return false;
        closePlayer();
        window.BlazeDesktop.selectSection(name);
        return true;
    };
    const search = (query, commit = false) => {
        if (typeof query !== 'string' || modalOpen()) return false;
        const input = byId('explore-search');
        navigate('explore');
        input.value = query.slice(0, 200);
        if (commit === true) byId('explore-form').dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
        else input.dispatchEvent(new Event('input', {bubbles: true}));
        return true;
    };

    window.BlazeMac = {
        keepBrowsing: true,
        displayTitle(value) {
            return value === sourceName ? value.replace(/\.(mp3|m4a|aac|flac|wav|ogg|opus|mp4|m4v|mov|webm|mkv)$/i, '') : value;
        },
        installNativeChrome(capabilities) {
            if (!capabilities || typeof capabilities !== 'object') return false;
            let changed = !nativeChromeInstalled;
            if (capabilities.sidebar === true) {
                changed ||= document.body.dataset.nativeSidebar !== 'true';
                document.body.dataset.nativeSidebar = 'true';
                document.body.dataset.nativeNavigation = 'true';
            }
            if (capabilities.search === true) {
                changed ||= document.body.dataset.nativeSearch !== 'true';
                document.body.dataset.nativeSearch = 'true';
            }
            if (capabilities.window === true) document.body.dataset.nativeWindow = 'true';
            nativeChromeInstalled = true;
            if (changed) redraw();
            return true;
        },
        snapshot() {
            return {
                section: currentSection(),
                studioWorkspace: !!window.BlazeMacStudio?.snapshot().active,
                studioTitle: window.BlazeMacStudio?.snapshot().sessionTitle || '',
                appearance: document.documentElement.dataset.appearance || 'system',
                query: bounded(byId('explore-search').value),
                hasMedia: hasMedia(), modal: modalOpen(),
                title: bounded(byId('mini-title').textContent),
                creator: bounded(byId('mini-creator').textContent),
                paused: video.paused, position: position(), duration: duration(),
                busy: !!(busy || importing), nativeChromeInstalled, focusSearchRequest, importRequest
            };
        },
        navigate, search, beginImport,
        action(name) {
            if (typeof name !== 'string' || modalOpen()) return false;
            switch (name) {
            case 'import': return requestImport();
            case 'settings': byId('app-settings').click(); return true;
            case 'play': if (!hasMedia()) return false; byId('mini-play').click(); return true;
            case 'previous': if (!hasMedia()) return false; previous.click(); return true;
            case 'next': if (!hasMedia()) return false; byId('mini-next').click(); return true;
            case 'open-player': if (!hasMedia()) return false; window.BlazeDesktop.openPlayer(); return true;
            case 'close-player': closePlayer(); return true;
            default: return false;
            }
        },
        async importCompleted() {
            window.BlazeDesktop.cancelPreparation();
            closePlayer();
            window.BlazeDesktop.selectSection('studio');
            await refresh();
            this.playerChanged();
            return true;
        },
        syncInspector() {
            byId('studio-details').hidden = true;
            if (sidebar.parentElement !== inspector) inspector.append(sidebar);
        },
        sectionChanged(name) {
            if (now.open) closePlayer();
            if (name === 'studio' && hasMedia() && !video.classList.contains('audio-only')) inspector.open = true;
            this.syncInspector();
        },
        presentPlayer(dialog) {
            inspector.open = false;
            document.body.classList.add('mac-player-expanded');
            dialog.show();
            redraw();
        },
        playerClosed() {
            const wasExpanded = document.body.classList.contains('mac-player-expanded');
            document.body.classList.remove('mac-player-expanded');
            if (wasExpanded && currentSection() === 'studio' && !video.classList.contains('audio-only')) inspector.open = true;
            if (wasExpanded) redraw();
        },
        playerChanged() {
            const loaded = hasMedia();
            player.hidden = false;
            for (const button of [byId('mini-open'), byId('mini-play'), byId('mini-next'), previous]) button.disabled = !loaded;
            if (!loaded) text(byId('mini-creator'), 'Choose music in Explore or open a file');
            if (lastSource !== sourceName) {
                lastSource = sourceName;
                scrubbing = false;
                text(byId('filename'), loaded ? this.displayTitle(sourceName) : 'Choose a song to begin');
                if (currentSection() === 'studio' && loaded && !video.classList.contains('audio-only')) inspector.open = true;
            }
            paintTimeline();
        }
    };

    // Native menus normally handle these. This fallback also works when the
    // content is focused or AppKit chrome could not be installed.
    document.addEventListener('keydown', event => {
        if (event.isComposing || event.altKey) return;
        const editing = event.target.closest?.('input,textarea,select,button,a,summary,[contenteditable=true]');
        const key = event.key.toLowerCase();
        let handled = false;
        if (event.metaKey && !event.shiftKey && !modalOpen()) {
            if (key === 'f') {
                if (document.body.dataset.nativeSearch === 'true') ++focusSearchRequest;
                else { navigate('explore'); byId('explore-search').focus(); byId('explore-search').select(); }
                handled = true;
            } else if (key === 'o') { requestImport(); handled = true; }
            else if (key === ',') { window.BlazeMac.action('settings'); handled = true; }
        } else if (event.key === ' ' && !event.metaKey && !event.ctrlKey && !editing && !modalOpen() && hasMedia()) {
            window.BlazeMac.action('play'); handled = true;
        } else if (event.key === 'Escape' && now.open && !modalOpen()) {
            closePlayer(); byId('mini-open').focus(); handled = true;
        }
        if (handled) { event.preventDefault(); event.stopImmediatePropagation(); }
    }, true);

    // Clicking elsewhere dismisses the inspector without blocking the action.
    document.addEventListener('pointerdown', event => {
        if (inspector.open && !inspector.contains(event.target)) inspector.open = false;
    });
    window.BlazeMac.syncInspector();
    window.BlazeDesktop.updatePlayer();
})();
