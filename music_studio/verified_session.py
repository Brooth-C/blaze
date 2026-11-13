"""Checksum-verified assets with inference sessions opened only when needed."""
import hashlib
from pathlib import Path


class VerifiedSession:
    def __init__(self, directory, metadata, runtime, options, maximum_bytes):
        name = metadata['file']
        if Path(name).name != name:
            raise ValueError('Model asset paths must remain inside the bundle.')
        self.path = Path(directory) / name
        self.sha256 = metadata['sha256']
        self.maximum_bytes = maximum_bytes
        self.runtime, self.options = runtime, options
        self.session = None
        # Validate even on result-cache hits, without holding model bytes in RAM.
        self._verify()

    def _verify(self):
        if not self.path.is_file() or self.path.stat().st_size > self.maximum_bytes:
            raise ValueError('Recognition model file is missing or too large.')
        with self.path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != self.sha256:
                raise ValueError('Recognition model verification failed.')

    def run(self, *args, **kwargs):
        if self.session is None:
            with self.path.open('rb') as stream:
                data = stream.read(self.maximum_bytes + 1)
            # Revalidate the exact bytes used, including replacement since lookup.
            if len(data) > self.maximum_bytes or hashlib.sha256(data).hexdigest() != self.sha256:
                raise ValueError('Recognition model verification failed.')
            self.session = self.runtime.session(data, self.options, self.sha256)
        return self.session.run(*args, **kwargs)

    def close(self):
        self.runtime.finish(self.session)
        self.session = None
