/* One-model stem workflow. The existing media element owns all playback. */
(() => {
    'use strict';
    if (document.documentElement.dataset.presentation !== 'mac') return;
    const byId = id => document.getElementById(id);
    const labels = {vocals: 'Vocals', drums: 'Drums', bass: 'Bass', other: 'Other', piano: 'Piano', accompaniment: 'Accompaniment'};
    const button = document.createElement('button');
    button.id = 'split-stems'; button.textContent = 'Split stems'; button.hidden = true;
    byId('analyze').before(button);
    const dialog = document.createElement('dialog');
    dialog.id = 'stems-dialog';
    dialog.setAttribute('aria-labelledby', 'stems-heading');
    dialog.innerHTML = '<div class="stems-heading"><h3 id="stems-heading">Split stems</h3><button id="stems-close" aria-label="Close stem separation">×</button></div>' +
        '<p id="stems-source"></p><p class="stems-description">Split four stems or isolate the piano. Processed on this Mac.</p>' +
        '<div id="stems-progress-panel" hidden><progress id="stems-progress" max="1" value="0" aria-label="Stem separation progress"></progress></div>' +
        '<p id="stems-message" role="status"></p><p id="stems-error" role="alert" hidden></p><div id="stems-results"></div>' +
        '<div class="stems-footer"><button id="stems-folder" hidden>Open folder</button><button id="stems-cancel" hidden>Cancel separation</button><button id="stems-piano">Isolate piano</button><button id="stems-start" class="primary">Split four stems</button></div>';
    document.body.append(dialog);
    let state = {available: false, status: 'idle', stems: []};
    let requestInFlight = false, submitting = false, stopped = false, mutationEpoch = 0;
    let lastResults = '', timer, actionError = '';
    const paintError = () => {
        const message = actionError || state.error || '';
        byId('stems-error').textContent = String(message);
        byId('stems-error').hidden = !message;
    };
    const error = message => {
        actionError = message;
        paintError();
    };
    const render = () => {
        const running = state.status === 'running';
        button.hidden = state.available !== true;
        button.textContent = running ? 'Splitting…' : 'Split stems';
        button.disabled = submitting || (!running && (!sourceName || busy));
        byId('stems-start').disabled = submitting || busy || !sourceName;
        byId('stems-start').hidden = running;
        byId('stems-piano').hidden = running;
        byId('stems-piano').disabled = submitting || busy || !sourceName;
        byId('stems-cancel').hidden = !running;
        byId('stems-cancel').disabled = submitting;
        byId('stems-progress-panel').hidden = !running;
        byId('stems-progress').value = Math.max(0, Math.min(1, Number(state.progress) || 0));
        byId('stems-source').textContent = state.sourceName || sourceName || 'Choose a recording in Studio.';
        byId('stems-message').textContent = state.message || (state.status === 'done' ? 'Your stems are ready.' : 'Ready to separate this recording.');
        byId('stems-folder').hidden = state.status !== 'done';
        byId('stems-folder').disabled = submitting || busy;
        paintError();
        const rows = state.status === 'done' && Array.isArray(state.stems) ? state.stems.filter(row => labels[row.id]) : [];
        const identity = JSON.stringify([state.jobId, rows]);
        if (identity !== lastResults) {
            lastResults = identity;
            byId('stems-results').replaceChildren();
            for (const row of rows) {
                const container = document.createElement('div'); container.className = 'stem-result';
                const label = document.createElement('strong'); label.textContent = labels[row.id];
                const open = document.createElement('button'); open.textContent = 'Open in Studio';
                open.setAttribute('aria-label', 'Open ' + labels[row.id] + ' in Studio');
                open.onclick = async () => {
                    if (submitting || busy) return;
                    submitting = true; render(); error('');
                    try {
                        window.BlazeDesktop.cancelPreparation();
                        await api('/api/stems-select', {jobId: state.jobId, stem: row.id});
                        await window.BlazeMac.importCompleted();
                        dialog.close();
                    } catch (failure) { error(failure.message || 'This stem could not be opened.'); }
                    finally { submitting = false; render(); }
                };
                const save = document.createElement('a'); save.className = 'button stem-save'; save.textContent = 'Save WAV';
                save.setAttribute('aria-label', 'Save ' + labels[row.id] + ' WAV');
                save.href = '/api/stem-file?jobId=' + encodeURIComponent(state.jobId) + '&stem=' + encodeURIComponent(row.id) + '&token=' + encodeURIComponent(token);
                save.download = row.filename || row.id + '.wav';
                container.append(label, open, save); byId('stems-results').append(container);
            }
        }
        for (const open of byId('stems-results').querySelectorAll('button')) open.disabled = submitting || busy;
    };
    const refreshState = async () => {
        if (stopped || requestInFlight) return;
        requestInFlight = true;
        const epoch = mutationEpoch;
        try {
            const value = await api('/api/stems');
            if (epoch === mutationEpoch && value && typeof value === 'object') {
                const settled = state.status === 'running' && value.status !== 'running';
                state = value;
                if (settled) await refresh();
                render();
            }
        } catch (failure) {
            if (dialog.open) error(failure.message || 'Stem separation could not be checked.');
        } finally { requestInFlight = false; }
    };
    const start = async (mode = 'stems') => {
        if (submitting || busy || !sourceName) return;
        submitting = true; ++mutationEpoch; error(''); render();
        try {
            window.BlazeDesktop.cancelPreparation();
            state = await api('/api/stems-start', {mode}); render();
            await refresh();
        } catch (failure) { error(failure.message || 'Stem separation could not start.'); }
        finally { submitting = false; render(); await refreshState(); }
    };
    const open = async () => {
        if (!dialog.open) dialog.showModal();
        error('');
        await refreshState();

    };
    button.onclick = open;
    byId('stems-start').onclick = () => start();
    byId('stems-piano').onclick = () => start('piano');
    byId('stems-close').onclick = () => dialog.close();
    dialog.addEventListener('close', () => button.focus());
    byId('stems-cancel').onclick = async () => {
        if (submitting) return;
        submitting = true; ++mutationEpoch; error(''); render();
        try { state = await api('/api/stems-cancel', {}); await refresh(); }
        catch (failure) { error(failure.message || 'Separation could not be cancelled.'); }
        finally { submitting = false; render(); await refreshState(); }
    };
    byId('stems-folder').onclick = async () => {
        error('');
        try { await api('/api/stems-folder', {jobId: state.jobId}); }
        catch (failure) { error(failure.message || 'The stem folder could not be opened.'); }
    };
    window.BlazeMacStems = {open, refresh: refreshState, snapshot: () => ({...state})};
    const tick = async () => {
        if (stopped) return;
        render();
        if (dialog.open || state.status === 'running') await refreshState();
        timer = setTimeout(tick, 600);
    };
    window.addEventListener('pagehide', () => { stopped = true; clearTimeout(timer); });
    refreshState().finally(tick);
})();
