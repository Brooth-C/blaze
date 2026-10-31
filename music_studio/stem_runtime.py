"""Bounded ONNX execution for stems; Core ML is an explicit Mac evaluation path.

Keep CPU as the default until packaged macOS26 measurements justify a change.
Registering CoreML is not evidence that every operation executes on the GPU.
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
        self.backend = backend or os.environ.get('BLAZE_STEM_BACKEND', 'cpu')
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

    def session(self, data, options, model_sha):
        if not re.fullmatch(r'[a-f0-9]{64}', model_sha):
            raise ValueError('A verified model hash is required for stem execution.')
        providers = ['CPUExecutionProvider']
        if self.backend == 'coreml':
            # Separate content-addressed directories prevent stale compiled
            # graphs, even when ONNX node names remain unchanged between models.
            settings = {'ort': ort.__version__, 'contract': 1, 'format': 'MLProgram',
                        'units': 'CPUAndGPU', 'static': True, 'subgraphs': True}
            identity = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]
            cache = self.cache / ('v1-' + identity) / model_sha
            cache.mkdir(parents=True, exist_ok=True)
            providers = [('CoreMLExecutionProvider', {
                'ModelFormat': 'MLProgram', 'MLComputeUnits': 'CPUAndGPU',
                'RequireStaticInputShapes': '1', 'ModelCacheDirectory': str(cache),
                'EnableOnSubgraphs': '1',
            }), 'CPUExecutionProvider']
            if self.profile:
                providers[0][1]['ProfileComputePlan'] = '1'
        if self.profile:
            self.profile.mkdir(parents=True, exist_ok=True)
            options.enable_profiling = True
            options.profile_file_prefix = str(self.profile / (model_sha[:12] + '-' + str(time.monotonic_ns())))
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
