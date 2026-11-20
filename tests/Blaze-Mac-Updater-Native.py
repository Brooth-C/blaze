"""Real Sparkle -> PyObjC delegate/block ABI check, on macOS 26 only."""
import argparse
import ctypes
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(framework):
    if sys.platform != 'darwin' or platform.mac_ver()[0].split('.')[0] != '26':
        raise RuntimeError('Native updater validation requires macOS 26.')
    import objc
    from music_studio.mac_updates import delegate_class, RelaunchGate
    framework = framework.resolve()
    objc.loadBundle('Sparkle', {}, bundle_path=str(framework))
    gate = RelaunchGate()
    delegate = delegate_class().alloc().init()
    delegate.owner = SimpleNamespace(gate=gate, receipt={})
    with tempfile.TemporaryDirectory(prefix='blaze-updater-abi-') as folder:
        folder = Path(folder)
        source = folder / 'sender.m'
        source.write_text('''#import <Sparkle/Sparkle.h>
static int completed = 0;
int BlazeSend(id<SPUUpdaterDelegate> target) {
 return [target updater:nil shouldPostponeRelaunchForUpdate:nil untilInvokingBlock:^{ completed++; }];
}
int BlazeCompleted(void) { return completed; }
''')
        binary = folder / 'sender.dylib'
        subprocess.run(['clang', '-dynamiclib', '-fblocks', '-fobjc-arc', '-framework', 'Foundation',
                        '-F', str(framework.parent), '-framework', 'Sparkle',
                        '-Wl,-rpath,' + str(framework.parent), str(source), '-o', str(binary)], check=True)
        native = ctypes.CDLL(str(binary))
        native.BlazeSend.argtypes = [ctypes.c_void_p]
        native.BlazeSend.restype = ctypes.c_int
        native.BlazeCompleted.restype = ctypes.c_int
        assert native.BlazeSend(objc.pyobjc_id(delegate)) == 1
        assert native.BlazeCompleted() == 0
        assert gate.finish(False) is False
        assert gate.finish(True) is True
        assert native.BlazeCompleted() == 1
        assert gate.finish(True) is False
        assert native.BlazeCompleted() == 1
    print('PASS: real Sparkle protocol BOOL, retained native install block, idle deferral, exactly-once relaunch.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--framework', type=Path, required=True)
    main(parser.parse_args().framework)
