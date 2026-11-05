"""Select the piano inference backend without disguising GPU failures."""
import os
import platform
import sys


def selected_piano_backend():
    """Use fused Metal for Apple Silicon by default; allow an explicit CPU opt-out."""
    requested = os.environ.get('BLAZE_PIANO_BACKEND')
    if requested is not None:
        if requested not in ('mlx', 'onnx'):
            raise ValueError('Choose mlx or onnx for the piano backend.')
        return requested
    if sys.platform == 'darwin' and platform.machine().lower() in ('arm64', 'aarch64'):
        return 'mlx'
    return 'onnx'
