"""Real, fully local audio/video decoder checks using production Java code."""
from pathlib import Path
import math
import os
import struct
import subprocess
import tempfile
import wave
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path(os.environ['JAVA_HOME']) / 'bin'
SDK = Path(os.environ['ANDROID_HOME'])
ANDROID = SDK / 'platforms/android-36/android.jar'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def run(command):
    return subprocess.run([str(x) for x in command], check=True, capture_output=True)


with tempfile.TemporaryDirectory(prefix='blaze-chords-') as directory:
    folder = Path(directory)
    classes = folder / 'classes'
    classes.mkdir()
    sources = ROOT / 'android/app/src/main/java/com/brooth/blaze'
    run([JAVA / 'javac', '-cp', ANDROID, '-d', classes, sources / 'ChordEngine.java',
         sources / 'ChordAnalyzer.java', ROOT / 'tests/java/com/brooth/blaze/ChordWavTest.java'])
    audio = folder / 'triads.wav'
    with wave.open(str(audio), 'wb') as output:
        output.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
        for section, root in enumerate((0, 9, 7)):
            block = bytearray()
            for i in range(44100 * 3):
                value = 0
                for interval in (0, 3 if section == 1 else 4, 7):
                    frequency = 440 * 2 ** ((48 + root + interval - 69) / 12)
                    for harmonic in range(1, 5):
                        value += .12 / harmonic ** 2 * math.sin(2 * math.pi * frequency * harmonic * i / 44100)
                sample = round(value * 32767)
                block.extend(struct.pack('<hh', sample, sample))
            output.writeframes(block)
    # Lossy audio, video soundtrack, and delayed audio relative to video.
    mp3, video, delayed = (folder / name for name in ('triads.mp3', 'triads.mp4', 'delayed.mkv'))
    run([FFMPEG, '-y', '-i', audio, '-c:a', 'libmp3lame', mp3])
    fixture = ROOT / 'android/app/src/androidTest/assets/fixture-video.mp4'
    run([FFMPEG, '-y', '-i', fixture, '-i', audio, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', video])
    run([FFMPEG, '-y', '-i', fixture, '-itsoffset', '2', '-i', audio, '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy', delayed])
    for index, source in enumerate((audio, mp3, video, delayed)):
        decoded = folder / f'decoded-{index}.wav'
        # Match the shipped analyser's command and pipe-mode WAV header.
        command = [FFMPEG, '-nostdin', '-hide_banner', '-loglevel', 'error',
                   '-protocol_whitelist', 'file,pipe', '-threads', '2', '-i', source,
                   '-map', '0:a:0', '-vn', '-sn', '-dn', '-af', 'aresample=async=1:first_pts=0',
                   '-ac', '1', '-ar', '11025', '-c:a', 'pcm_s16le', '-f', 'wav', 'pipe:1']
        with decoded.open('wb') as output:
            subprocess.run([str(x) for x in command], stdout=output, stderr=subprocess.PIPE, check=True)
        result = run([JAVA / 'java', '-cp', os.pathsep.join((str(classes), str(ANDROID))),
                      'com.brooth.blaze.ChordWavTest', decoded, '2000' if source == delayed else '0'])
        print(source.name + ': ' + result.stdout.decode().strip())
    # The first two header bytes cannot stand in for a readable audio file.
    broken = folder / 'broken.wav'
    broken.write_bytes(b'RI')
    failure = subprocess.run([str(JAVA / 'java'), '-cp', os.pathsep.join((str(classes), str(ANDROID))),
                              'com.brooth.blaze.ChordWavTest', str(broken)], capture_output=True)
    assert failure.returncode != 0
