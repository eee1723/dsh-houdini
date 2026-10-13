"""Houdini image pixels. Executed on the Bridge owning thread."""
from __future__ import annotations

import math
import os
import struct
import zlib


_MAX_IMAGE_PIXELS = 16 * 1024 * 1024


_MAX_IMAGE_FILE_BYTES = 64 * 1024 * 1024


class _QtPixelRows:
    """Retain the decoded image, not millions of Python RGB tuple objects."""
    def __init__(self, image):
        self.image = image

    def __getitem__(self, y):
        image = self.image
        class Row:
            def __getitem__(self, x):
                color = image.pixelColor(x, y)
                return (color.red(), color.green(), color.blue())
        return Row()


class _BytePixelRows:
    def __init__(self, rows, channels):
        self.rows, self.channels = rows, channels

    def __getitem__(self, y):
        data, channels = self.rows[y], self.channels
        class Row:
            def __getitem__(self, x):
                offset = x * channels
                return (data[offset],) * 3 if channels == 1 else tuple(data[offset:offset + 3])
        return Row()


def _read_pixels_qt(path: str):
    """QImage 读像素（Houdini GUI/hython 均带 PySide6）；失败返回 None。"""
    try:
        from PySide6.QtGui import QImage, QImageReader
        reader = QImageReader(path)
        size = reader.size()
        if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > _MAX_IMAGE_PIXELS:
            return None
        img = reader.read()
        if img.isNull():
            return None
        img = img.convertToFormat(QImage.Format.Format_RGB888)
        w, h = img.width(), img.height()
        return w, h, _QtPixelRows(img)
    except Exception:
        return None


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _read_pixels_png(path: str):
    """纯标准库 PNG 解码（8-bit grey/RGB/RGBA，无交错）——hython 无 GUI 时的
    fallback。返回 (w, h, pixels)；不支持的格式返回 None。"""
    try:
        with open(path, "rb") as source:
            data = source.read(_MAX_IMAGE_FILE_BYTES + 1)
        if len(data) > _MAX_IMAGE_FILE_BYTES:
            return None
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        pos = 8
        idat = []
        w = h = bitd = colort = None
        while pos < len(data):
            ln = struct.unpack(">I", data[pos:pos+4])[0]
            if pos + 12 + ln > len(data):
                return None
            typ = data[pos+4:pos+8]
            chunk = data[pos+8:pos+8+ln]
            if typ == b"IHDR":
                if len(chunk) != 13 or chunk[10:] != b'\x00\x00\x00':
                    return None  # nonstandard compression/filtering or Adam7
                w, h, bitd, colort = struct.unpack(">IIBB", chunk[:10])
                if w <= 0 or h <= 0 or w * h > _MAX_IMAGE_PIXELS:
                    return None
            elif typ == b"IDAT":
                idat.append(chunk)
            elif typ == b"IEND":
                break
            pos += 12 + ln
        if bitd != 8 or colort not in (0, 2, 6):
            return None
        channels = {0: 1, 2: 3, 6: 4}[colort]
        stride = w * channels
        expected = h * (stride + 1)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(b''.join(idat), expected + 1)
        if len(raw) != expected or not decoder.eof or decoder.unconsumed_tail:
            return None
        pixels = []
        prev = bytearray(stride)
        off = 0
        for _y in range(h):
            filt = raw[off]
            if filt > 4:
                return None
            line = bytearray(raw[off+1:off+1+stride])
            off += 1 + stride
            for i in range(stride):
                a = line[i-channels] if i >= channels else 0
                b = prev[i]
                c = prev[i-channels] if i >= channels else 0
                if filt == 1:
                    line[i] = (line[i] + a) & 0xFF
                elif filt == 2:
                    line[i] = (line[i] + b) & 0xFF
                elif filt == 3:
                    line[i] = (line[i] + (a + b) // 2) & 0xFF
                elif filt == 4:
                    line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
            pixels.append(bytes(line))
            prev = line
        return w, h, _BytePixelRows(pixels, channels)
    except Exception:
        return None


def _read_pixels(path: str):
    return _read_pixels_qt(path) or _read_pixels_png(path)


def _image_stats(w: int, h: int, pixels, max_samples: int = 512) -> dict:
    """从像素矩阵算客观指标（大图先按网格抽样，上限 max_samples 边长）。"""
    step = max(1, int(max(w, h) / max_samples) + 1)
    lumas = []
    rs = gs = bs = nb = 0
    bbox = None
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = pixels[y][x]
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            lumas.append(luma)
            if luma > 8:  # 非黑
                nb += 1
                rs += r; gs += g; bs += b
                if bbox is None:
                    bbox = [x, y, x, y]
                else:
                    bbox[0] = min(bbox[0], x); bbox[1] = min(bbox[1], y)
                    bbox[2] = max(bbox[2], x); bbox[3] = max(bbox[3], y)
    total = len(lumas) or 1
    risk_reasons = []
    if bbox is None:
        risk_reasons.append('no_nonblack_content')
    bbox_coverage = (100 * (bbox[2] - bbox[0] + step) * (bbox[3] - bbox[1] + step) / (w * h)) if bbox else 0
    if bbox and (bbox[0] <= step or bbox[1] <= step or w - 1 - bbox[2] <= step or h - 1 - bbox[3] <= step):
        risk_reasons.append('nonblack_content_at_image_edge')
    if bbox and bbox_coverage < 10:
        risk_reasons.append('small_nonblack_bbox')
    return {
        "mean_luma": round(sum(lumas) / total, 2),
        "max_luma": round(max(lumas), 2) if lumas else 0,
        "nonblack_pct": round(nb * 100.0 / total, 2),
        "dominant": [rs // nb, gs // nb, bs // nb] if nb else None,
        "content_bbox": bbox,
        "presentation": {"needs_review": bool(risk_reasons), "reasons": risk_reasons,
                         "bbox_coverage_pct": round(min(100, bbox_coverage), 2),
                         "scope": "nonblack pixels, not object segmentation", "semantic_status": "unverified"},
    }


def render_check(path: str, ref=None) -> dict:
    """渲染产物的**客观验证**——无视觉模型时的盲验手段。

    返回亮度统计 / 非黑像素占比 / 主色 / 内容 bbox，回答「渲染是不是黑的、
    有没有内容、内容在哪」；传 ``ref``（另一张图路径）再算两图差异
    （``identical`` / ``mean_abs_diff``），用于循环帧一致性、A/B 对比。

    解码优先 PySide6 QImage（PNG/JPEG/BMP/TGA），hython 无 GUI 时退回纯
    Python PNG 解码（8-bit）；EXR 等 HDR 格式不在覆盖范围（裸 hou 逃生舱）。
    """
    result = _read_pixels(path)
    if result is None:
        raise ValueError(
            f"无法解码 '{path}'（支持 PNG/JPEG/BMP/TGA，EXR 等请裸写 hou.image）"
        )
    w, h, pixels = result
    out: dict = {
        "path": path,
        "width": w,
        "height": h,
        "bytes": os.path.getsize(path),
    }
    out.update(_image_stats(w, h, pixels))

    if ref is not None:
        result2 = _read_pixels(ref)
        if result2 is None:
            raise ValueError(f"无法解码 ref 图 '{ref}'")
        w2, h2, pixels2 = result2
        if (w2, h2) != (w, h):
            out["diff_vs_ref"] = {"comparable": False, "ref_size": [w2, h2]}
        else:
            step = max(1, int(max(w, h) / 512) + 1)
            diffs = []
            squared = 0.0
            channel_abs = 0.0
            changed = meaningful = 0
            for y in range(0, h, step):
                for x in range(0, w, step):
                    p1, p2 = pixels[y][x], pixels2[y][x]
                    channels = [abs(p1[i] - p2[i]) for i in range(3)]
                    pixel_diff = max(channels)
                    diffs.append(pixel_diff)
                    channel_abs += sum(channels)
                    squared += sum(value * value for value in channels)
                    if pixel_diff > 0:
                        changed += 1
                    if pixel_diff > 2:
                        meaningful += 1
            count = len(diffs)
            out["diff_vs_ref"] = {
                "comparable": True,
                "identical": max(diffs) == 0 if diffs else True,
                # 不过早舍入：40054277 草地 frame 1/12 的微小非零差异曾被
                # round(..., 3) 压成 0，掩盖“几乎静止”的关键证据。
                "mean_abs_diff": round(channel_abs / (count * 3), 8) if count else 0,
                "mean_max_channel_diff": round(sum(diffs) / count, 8) if count else 0,
                "rmse": round(math.sqrt(squared / (count * 3)), 8) if count else 0,
                "max_abs_diff": max(diffs) if diffs else 0,
                "changed_pixel_pct": round(changed * 100.0 / count, 6) if count else 0,
                "meaningful_pixel_pct": round(meaningful * 100.0 / count, 6) if count else 0,
                "sample_step": step,
                "sampled_pixels": count,
            }
    return out
