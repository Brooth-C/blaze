"""Real macOS binary, audio/video decoder and local download verification."""
from pathlib import Path
from functools import partial
from http.server import SimpleHTTPRequestHandler
import argparse
import json
import math
import platform
import shutil
import struct
import subprocess
import threading
import time
import wave


def run(*command):
    return subprocess.run([str(c) for c in command], check=True, capture_output=True, text=True, timeout=180)


def fixture(path):
    rate = 22050
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        notes = [(60, 64, 67, 71), (57, 60, 64, 67), (62, 65, 69, 72), (55, 59, 62, 65)]
        for i in range(rate * 12):
            chord = notes[min(3, i // (3 * rate))]
            t = i / rate
            value = sum(math.sin(2 * math.pi * 440 * 2 ** ((note - 69) / 12) * t) for note in chord)
            output.writeframesraw(struct.pack('<h', int(value * 5000)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'x86_64'), required=True)
    args = parser.parse_args()
    app, work = args.app.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    resources = app / 'Contents/Resources'
    # PyInstaller macOS layout preserves the binary/data symlinks in Resources.
    tools = resources / 'bin'
    decoder = tools / 'ffmpeg'
    assert args.arch in run('/usr/bin/lipo', '-archs', app / 'Contents/MacOS/Blaze').stdout
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
    for name in ('ffmpeg', 'ffprobe'):
        version = run(tools / name, '-version').stdout
        assert '--disable-gpl' in version and '--disable-nonfree' in version
    assert run(tools / 'node', '--version').stdout.strip() == 'v22.20.0'
    assert run(tools / 'yt-dlp', '--version').stdout.strip() == '2026.08.19'
    audio = work / 'Advanced-chords.wav'
    fixture(audio)
    for suffix, codec in [('mp3', 'libmp3lame'), ('m4a', 'aac'), ('flac', 'flac'), ('ogg', 'libvorbis'), ('opus', 'libopus')]:
        target = audio.with_suffix('.' + suffix)
        run(decoder, '-y', '-v', 'error', '-i', audio, '-c:a', codec, target)
        run(decoder, '-v', 'error', '-i', target, '-f', 'null', '-')
    video = work / '4K-local.mov'
    run(decoder, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=3840x2160:r=1:d=1',
        '-i', audio, '-c:v', 'png', '-c:a', 'aac', '-shortest', video)
    probe = json.loads(run(tools / 'ffprobe', '-v', 'error', '-show_streams', '-of', 'json', video).stdout)
    assert any(s.get('width') == 3840 and s.get('height') == 2160 for s in probe['streams'])
    run(decoder, '-v', 'error', '-i', video, '-vn', '-f', 'null', '-')
    binary = app / 'Contents/MacOS/Blaze'
    result_path = work / 'package-analysis.json'
    run(binary, audio, '--self-test', result_path)
    result = json.loads(result_path.read_text())
    assert result['chords'] and result_path.with_suffix('.csv').is_file()
    assert 'Ensemble' in str(result['model'])
    # Exercise the real packaged downloader, decoder and output path without
    # relying on a third-party site's uptime, accounts or anti-bot policy.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from music_studio.server import LoopbackHTTPServer
    server = LoopbackHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(work)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        output = work / 'downloaded.wav'
        run(tools / 'yt-dlp', '--no-update', '--no-playlist', '--ffmpeg-location', tools,
            '-x', '--audio-format', 'wav', '-o', output, f'http://127.0.0.1:{server.server_port}/{audio.name}')
        assert output.is_file() and output.stat().st_size > 100
    finally:
        server.shutdown()
        server.server_close()
    receipt_path = work / 'native-ui.json'
    preview = work / 'ui-smoke-data/downloads/blaze-video-fixture.mp4'
    preview.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).parent / 'media/playback-avc-aac.mp4', preview)
    artwork = work / 'ui-smoke-data/discovery-fixtures'
    artwork.mkdir(parents=True, exist_ok=True)
    source_artwork = Path(__file__).resolve().parents[1] / 'android/app/src/main/res/drawable-nodpi'
    for name in ('piano', 'acoustic', 'jazz', 'sunset'):
        shutil.copy2(source_artwork / ('discovery_' + name + '.png'), artwork / (name + '.png'))
    process = subprocess.Popen([str(binary), str(audio), '--ui-smoke', str(receipt_path)])
    try:
        process.wait(timeout=660)
    except subprocess.TimeoutExpired:
        process.kill()
        raise
    receipt = json.loads(receipt_path.read_text())
    print(json.dumps(receipt, indent=2), flush=True)
    if process.returncode != 0:
        log = work / 'ui-smoke-data/desktop.log'
        if log.is_file(): print(log.read_text(encoding='utf-8')[-6000:], flush=True)
    assert process.returncode == 0, receipt
    assert receipt['ok'], receipt
    assert receipt['video']['decoded_pixels'] and receipt['video']['studio_return']
    navigation = receipt['native_navigation']
    expected_material = 'liquid-glass' if int(platform.mac_ver()[0].split('.')[0]) >= 26 else 'system-vibrancy'
    assert navigation['material'] == expected_material, navigation
    assert navigation['installed'] and navigation['web_navigation'] and navigation['roundtrip'], navigation
    assert receipt['mac_design']['sidebar'] and receipt['mac_design']['native_search'], receipt
    assert receipt['mac_design']['compact_player'], receipt
    assert receipt['mac_design']['selection_keeps_browsing'], receipt
    assert receipt['mac_design']['expanded_controls_fit'], receipt
    assert receipt['mac_design']['compact_layout']['controls'], receipt
    assert receipt['layout']['studio_workspace'], receipt
    assert receipt['layout']['names_fit'] and receipt['layout']['editor_toolbar_fits'], receipt
    assert receipt['mac_design']['chord_drawer']['opened'] and receipt['mac_design']['chord_drawer']['keyboards_visible'], receipt
    assert receipt['mac_design']['compact_layout']['studio_workspace'] and receipt['mac_design']['compact_layout']['chord_drawer'], receipt
    assert receipt['mac_design']['studio_waveform']['active'] and receipt['mac_design']['studio_waveform']['waveformReady'], receipt
    assert receipt['stems']['real_model'] and receipt['stems']['native_playback'], receipt
    assert receipt['stems']['count'] == 9, receipt
    assert receipt['stems']['instrument_playback'], receipt
    session = receipt['stems']['studio_workspace']
    assert session['active'] and session['waveformReady'] and session['selectedTrack'] == 'vocals', receipt
    assert len(session['tracks']) == 9, receipt
    assert receipt['piano']['real_model'] and receipt['piano']['native_playback'], receipt
    print(json.dumps({'architecture': args.arch, 'checks': 'native launch, ensemble, edits/exports, 6 audio formats, 4K decode, download, Cocoa playback/seek/layout', 'ui': receipt}, indent=2))
    # Let the remote desktop screenshot finish writing before artifact upload.
    assert receipt_path.with_suffix('.png').stat().st_size > 100
    time.sleep(.1)


if __name__ == '__main__':
    main()
