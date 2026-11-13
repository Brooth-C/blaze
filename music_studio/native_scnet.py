"""Explicit local Core ML SCNet experiment; current defaults remain available."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

from .stems import Separator, check_cancel

ARCHIVE_SHA = 'd15357c0abc901defb76282178966b0c41cc3e7b9ad34a8a0fd4598b11043c2f'
FILE_HASHES = {
    'scnet_coreml.mlpackage/Manifest.json':'3548c585bccc5fe517d311869652fd2bf22a2c570de89a3e2d032401eb87dac4',
    'scnet_coreml.mlpackage/Data/com.apple.CoreML/weights/weight.bin':'f1079e57c7b56bc6aa95703092f05af711143a89a5a18b9a11e3d0118bb17677',
    'scnet_coreml.mlpackage/Data/com.apple.CoreML/model.mlmodel':'f5860910c1ea0a04f78e70f2153d21e3bee763b17600035cbac42f54d74c91a9',
}
INPUT_SHAPE = [1, 4, 2049, 338]
OUTPUT_SHAPE = [1, 4, 4, 2049, 338]


def verified_package(directory):
    root = Path(directory).resolve(strict=True)
    manifest = json.loads((root / 'manifest.json').read_text())
    if (manifest.get('schema_version') != 1 or manifest.get('archive_sha256') != ARCHIVE_SHA
            or manifest.get('candidate') != 'native-scnet-fp16'
            or manifest.get('files') != FILE_HASHES):
        raise ValueError('Incompatible native SCNet candidate manifest.')
    package = root / 'scnet_coreml.mlpackage'
    if package.is_symlink() or not package.is_dir():
        raise ValueError('Invalid native SCNet package.')
    actual = set()
    for path in package.rglob('*'):
        if path.is_symlink():
            raise ValueError('Model packages must not contain symbolic links.')
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            actual.add(relative)
            expected = manifest['files'].get(relative)
            with path.open('rb') as stream:
                if not expected or hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError('Native SCNet checksum failed.')
    if actual != set(manifest['files']):
        raise ValueError('Native SCNet package is incomplete.')
    return package, manifest


class _Runtime:
    def __init__(self):
        self.records = []
    def finish(self, session):
        session.close()


class _Session:
    def __init__(self, model):
        self.model = model
    def close(self):
        self.model = None


class NativeSCNetSeparator(Separator):
    def __init__(self, model_directory, ffmpeg='ffmpeg'):
        self.directory = Path(model_directory)
        self.ffmpeg = str(ffmpeg)
        self.session = None
        self.runtime = _Runtime()

    def _load(self, event):
        check_cancel(event)
        if sys.platform != 'darwin' or platform.machine().lower() != 'arm64':
            raise ValueError('Native SCNet requires Apple Silicon macOS.')
        package, manifest = verified_package(self.directory)
        try:
            import coremltools as ct
        except ImportError as error:
            raise ValueError('Install the local model-candidate Core ML dependencies first.') from error
        check_cancel(event)
        started = time.perf_counter()
        model = ct.models.MLModel(str(package), compute_units=ct.ComputeUnit.CPU_AND_GPU)
        spec = model.get_spec()
        inputs, outputs = spec.description.input, spec.description.output
        if (len(inputs) != 1 or len(outputs) != 1
                or list(inputs[0].type.multiArrayType.shape) != INPUT_SHAPE
                or list(outputs[0].type.multiArrayType.shape) != OUTPUT_SHAPE):
            raise ValueError('Native SCNet model signature does not match.')
        dtype = inputs[0].type.multiArrayType.dataType
        if dtype not in (65552,65568):
            raise ValueError('Unsupported native SCNet input precision.')
        self.input_dtype = np.float16 if dtype == 65552 else np.float32
        self.input_name, self.output_name = inputs[0].name, outputs[0].name
        self.session = _Session(model)
        self.runtime.records.append({'backend':'native-coreml','precision':'fp16',
                                     'archive_sha256':manifest['archive_sha256'],
                                     'load_seconds':time.perf_counter()-started})
        check_cancel(event)

    def _predict(self, features, event):
        check_cancel(event)
        if list(features.shape) != INPUT_SHAPE or features.dtype != np.float32 or not np.isfinite(features).all():
            raise ValueError('Invalid SCNet spectral input.')
        start = time.perf_counter()
        with np.errstate(over='ignore'):
            value = np.ascontiguousarray(features,dtype=self.input_dtype)
        if not np.isfinite(value).all():
            raise ValueError('SCNet features exceed the candidate precision range.')
        result = self.session.model.predict({self.input_name:value})[self.output_name]
        check_cancel(event)
        if list(result.shape) != OUTPUT_SHAPE or not np.isfinite(result).all():
            raise ValueError('Native SCNet returned invalid audio.')
        self.runtime.records.append({'predict_seconds':time.perf_counter()-start})
        return np.asarray(result, dtype=np.float32)
