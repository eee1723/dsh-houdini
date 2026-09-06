"""Pixel evidence must remain bounded and never become a semantic quality score."""
from pathlib import Path
import struct
import sys
import tempfile
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'houdini/python3.11libs'))
import dsh_hou_helpers as h


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def png(width, height, raw, interlace=0):
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, interlace))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


with tempfile.TemporaryDirectory(prefix='dsh-pixels-') as directory:
    path = Path(directory) / 'sample.png'
    raw = b'\x00' + b'\xff\x00\x00' * 4
    path.write_bytes(png(4, 1, raw))
    w, ht, pixels = h._read_pixels_png(str(path))
    assert (w, ht) == (4, 1) and pixels[0][0] == (255, 0, 0)
    qt = h._read_pixels_qt(str(path))
    assert qt[2][0][0] == pixels[0][0]
    result = h.render_check(str(path))
    assert result['presentation']['needs_review']
    assert result['presentation']['semantic_status'] == 'unverified'
    assert h.render_check(str(path), ref=str(path))['diff_vs_ref']['identical']
    path.write_bytes(png(4, 1, raw * 10000))
    assert h._read_pixels_png(str(path)) is None, 'decompression expansion must be capped at advertised image size'
    path.write_bytes(png(h._MAX_IMAGE_PIXELS + 1, 1, raw))
    assert h._read_pixels_png(str(path)) is None
    path.write_bytes(png(4, 1, raw, interlace=1))
    assert h._read_pixels_png(str(path)) is None, 'fallback does not implement Adam7'
    black = h._image_stats(4, 1, [[(0, 0, 0)] * 4])
    assert black['presentation']['reasons'] == ['no_nonblack_content']

print('bounded image/presentation diagnostics passed')
