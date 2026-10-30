/* Local stem workflow. The existing media element owns all playback. */
(() => {
    'use strict';
    if (document.documentElement.dataset.presentation !== 'mac') return;
    const byId = id => document.getElementById(id);
    const labels = {vocals: 'Vocals', drums: 'Drums', bass: 'Bass', other: 'Other', piano: 'Piano', guitar: 'Guitar', strings: 'Strings', brass: 'Brass', synths: 'Synths', accompaniment: 'Accompaniment'};
    const button = document.createElement('button');
    button.id = 'split-stems'; button.textContent = 'Split stems'; button.hidden = true;
    byId('analyze').before(button);
    const dialog = document.createElement('dialog');
    dialog.id = 'stems-dialog';
    dialog.setAttribute('aria-labelledby', 'stems-heading');
    dialog.innerHTML = '<div class="stems-heading"><h3 id="stems-heading">Split stems</h3><button id="stems-close" aria-label="Close stem separation">×</button></div>' +
        '<p id="stems-source"></p><p class="stems-description">Nine stems separates guitar, strings, brass and synths too. Five stems keeps them in Other. Processing stays on this Mac; nine stems takes longer.</p>' +
        '<div id="stems-progress-panel" hidden><progress id="stems-progress" max="1" value="0" aria-label="Stem separation progress"></progress></div>' +
        '<p id="stems-message" role="status"></p><p id="stems-error" role="alert" hidden></p><p id="stems-results-heading" hidden></p><div id="stems-results"></div>' +
        '<div class="stems-footer"><button id="stems-folder" hidden>Open folder</button><button id="stems-background" hidden>Run in Background</button><button id="stems-cancel" hidden>Cancel separation</button><button id="stems-piano">Isolate piano</button><button id="stems-five">Five stems</button><button id="stems-start" class="primary">Nine stems</button></div>';
    document.body.append(dialog);
    const taskButton = document.createElement('button');
    taskButton.id = 'stems-task'; taskButton.hidden = true;
    taskButton.setAttribute('aria-label', 'Show background stem separation');
    document.body.append(taskButton);
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
        dialog.querySelector('.stems-description').hidden = running || state.status === 'done';
        button.hidden = state.available !== true;
        button.textContent = running ? 'Stems · ' + Math.round((Number(state.progress) || 0) * 100) + '%' : 'Split Stems';
        button.disabled = submitting || (!running && !sourceName);
        taskButton.hidden = !running && state.status !== 'done';
        taskButton.textContent = running ? 'Separating stems · ' + Math.round((Number(state.progress) || 0) * 100) + '%' : 'Stems ready';
        byId('stems-background').hidden = !running;
        byId('stems-start').disabled = submitting || !sourceName;
        byId('stems-start').hidden = running;
        byId('stems-five').hidden = running;
        byId('stems-five').disabled = submitting || !sourceName;
        byId('stems-piano').hidden = running;
        byId('stems-piano').disabled = submitting || !sourceName;
        byId('stems-cancel').hidden = !running;
        byId('stems-cancel').disabled = submitting;
        byId('stems-progress-panel').hidden = !running;
        byId('stems-progress').value = Math.max(0, Math.min(1, Number(state.progress) || 0));
        byId('stems-source').textContent = running ? 'Processing ' + (state.sourceName || 'your recording') : 'Selected recording: ' + (sourceName || 'Choose a recording in Studio.');
        byId('stems-source').title = byId('stems-source').textContent;
        byId('stems-results-heading').hidden = state.status !== 'done';
        byId('stems-results-heading').textContent = 'Saved stems: ' + (state.sourceName || 'Recording');
        byId('stems-message').textContent = state.message || (state.status === 'done' ? 'Your stems are ready.' : 'Ready to separate this recording.');
        byId('stems-folder').hidden = state.status !== 'done';
        byId('stems-folder').disabled = submitting;
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
    const start = async (mode = 'nine') => {
        if (submitting || !sourceName) return;
        submitting = true; ++mutationEpoch; error(''); render();
        try {
            window.BlazeDesktop.cancelPreparation();
            state = await api('/api/stems-start', {mode}); render();
            dialog.close();
            await refresh();
        } catch (failure) { error(failure.message || 'Stem separation could not start.'); }
        finally { submitting = false; render(); await refreshState(); }
    };
    const open = async () => {
        if (!dialog.open) {
            dialog.dataset.background = String(state.status === 'running');
            if (state.status === 'running') dialog.show(); else dialog.showModal();
        }
        error('');
        await refreshState();

    };
    button.onclick = open;
    taskButton.onclick = open;
    byId('stems-background').onclick = () => dialog.close();
    byId('stems-start').onclick = () => start();
    byId('stems-five').onclick = () => start('five');
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
