"""Create deterministic stereo music-like audio for whole-worker comparisons."""
import argparse
from pathlib import Path
import wave
import numpy as np


def create(output, seconds=150):
    rate = 44100
    rng = np.random.default_rng(1811)
    chords = [(130.8128, 164.8138, 195.9977), (174.6141, 220., 261.6256),
              (195.9977, 246.9417, 293.6648), (110., 130.8128, 164.8138)]
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), 'wb') as stream:
        stream.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        for second in range(seconds):
            t = np.arange(rate) / rate + second
            frequencies = chords[(second // 10) % len(chords)]
            attack = np.exp(-5 * (t % .5))
            signal = sum(np.sin(t * 2 * np.pi * frequency) * .08 for frequency in frequencies)
            signal *= .45 + .55 * attack
            signal += rng.normal(0, .004, rate) * np.exp(-60 * (t % .5))
            stereo = np.stack((signal, signal * .92), axis=1)
            if second % 37 == 19:
                stereo[:] = 0
            stream.writeframes((stereo * 32767).astype('<i2').tobytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=150)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error('Choose a fixture duration between 1 and 600 seconds.')
    create(args.output, args.seconds)


if __name__ == '__main__':
    main()
