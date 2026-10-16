"""Encode the selected transparent artwork as a multi-resolution Windows icon."""
from pathlib import Path
import os
import sys

runtime_bin = Path(sys.prefix).parent / 'bin'
runtime_dlls = os.add_dll_directory(str(runtime_bin)) if os.name == 'nt' and runtime_bin.is_dir() else None
from PIL import Image

root = Path(__file__).resolve().parents[1]
source = Image.open(root / 'assets/dsh-houdini.png').convert('RGBA')
if source.width != source.height or source.getextrema()[3][0] != 0:
    raise ValueError('Taskbar artwork must be square with a transparent background')
source.save(root / 'assets/dsh-houdini.ico', sizes=[(size, size) for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
print('Encoded DSH-Houdini Windows icon at 16–256 pixels')
