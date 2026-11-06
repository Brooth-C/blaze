"""Bounded ONNX inference with Core ML GPU delegation on Apple Silicon.

Core ML uses CPUAndGPU for supported graph partitions. Unsupported operations
may remain on CPU; this runtime does not claim that every app task or every
operator executes on the GPU.
"""
import logging
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import time

import onnxruntime as ort

LOG = logging.getLogger(__name__)


class StemRuntime:
    def __init__(self, backend=None, cache=None, profile=None):
        requested = backend if backend is not None else os.environ.get('BLAZE_STEM_BACKEND')
        self.backend = requested or self.default_backend()
        if self.backend not in ('cpu', 'coreml'):
            raise ValueError('Choose cpu or coreml for the stem backend.')
        self.cache = Path(cache) if cache else Path.home() / 'Library/Caches/Blaze/StemCoreML'
        profile = profile or os.environ.get('BLAZE_STEM_PROFILE_DIR')
        self.profile = Path(profile) if profile else None
        self.records = []
        self._pending = {}
        if self.backend == 'coreml':
            if sys.platform != 'darwin' or platform.machine().lower() not in ('arm64', 'aarch64'):
                raise ValueError('Core ML stem evaluation requires an Apple Silicon Mac.')
            version = tuple(int(v) for v in ort.__version__.split('.')[:2])
            if version < (1, 31):
                raise ValueError('Core ML stem evaluation requires the reviewed ONNX Runtime 1.31 or newer.')
            if 'CoreMLExecutionProvider' not in ort.get_available_providers():
                raise ValueError('This ONNX Runtime build does not include Core ML.')

    @staticmethod
    def default_backend():
        if sys.platform == 'darwin' and platform.machine().lower() in ('arm64', 'aarch64'):
            if tuple(int(value) for value in ort.__version__.split('.')[:2]) < (1, 31):
                raise ValueError('Apple Silicon model inference requires the reviewed Core ML runtime 1.31 or newer.')
            if 'CoreMLExecutionProvider' not in ort.get_available_providers():
                raise ValueError('Apple Silicon model inference requires the Core ML GPU execution provider.')
            return 'coreml'
        return 'cpu'

    def session(self, data, options, model_sha, *, free_dimensions=None):
        if not re.fullmatch(r'[a-f0-9]{64}', model_sha):
            raise ValueError('A verified model hash is required for stem execution.')
        dimensions = dict(free_dimensions or {})
        for name, value in dimensions.items():
            if not isinstance(name, str) or not name or type(value) is not int or value <= 0:
                raise ValueError('Model dimension overrides require names and positive integer sizes.')
            options.add_free_dimension_override_by_name(name, value)
        providers = ['CPUExecutionProvider']
        if self.backend == 'coreml':
            # Separate content-addressed directories prevent stale compiled
            # graphs, even when ONNX node names remain unchanged between models.
            settings = {'ort': ort.__version__, 'contract': 3, 'format': 'MLProgram',
                        'units': 'CPUAndGPU', 'static': bool(dimensions), 'subgraphs': True,
                        'free_dimensions': dimensions}
            identity = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]
            cache = self.cache / ('v1-' + identity) / model_sha
            cache.mkdir(parents=True, exist_ok=True)
            providers = [('CoreMLExecutionProvider', {
                'ModelFormat': 'MLProgram', 'MLComputeUnits': 'CPUAndGPU',
                'RequireStaticInputShapes': '1' if dimensions else '0', 'ModelCacheDirectory': str(cache),
                'EnableOnSubgraphs': '1',
            }), 'CPUExecutionProvider']
            if self.profile:
                providers[0][1]['ProfileComputePlan'] = '1'
        if self.profile:
            self.profile.mkdir(parents=True, exist_ok=True)
            options.enable_profiling = True
            options.profile_file_prefix = str(self.profile / (model_sha[:12] + '-' + str(time.monotonic_ns())))
        if self.backend == 'coreml':
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
        start = time.monotonic()
        session = ort.InferenceSession(data, sess_options=options, providers=providers)
        registered = session.get_providers()
        if self.backend == 'coreml' and 'CoreMLExecutionProvider' not in registered:
            if self.profile:
                session.end_profiling()
            raise ValueError('Core ML could not initialize; the requested GPU evaluation did not start.')
        if self.backend == 'coreml':
            # Prevent Python's automatic whole-session EP retry from disguising
            # an initialization/inference failure as successful GPU execution.
            session.disable_fallback()
        self._pending[id(session)] = {
            'model_sha256': model_sha, 'requested_backend': self.backend,
            'registered_providers': registered,
            'free_dimensions': dimensions,
            'session_creation_seconds': time.monotonic() - start,
        }
        return session

    def finish(self, session):
        if session is None:
            return
        record = self._pending.pop(id(session), None)
        if record is None:
            return
        if self.profile:
            try:
                record['profile'] = session.end_profiling()
            except Exception:
                LOG.exception('Could not finish stem execution profile')
        self.records.append(record)
        LOG.info('Stem graph backend=%s registered=%s model=%s', self.backend,
                 record['registered_providers'], record['model_sha256'][:12])
