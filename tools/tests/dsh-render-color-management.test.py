"""H21/H22 regression for render_view output color management."""

from __future__ import annotations

from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "houdini" / "python3.11libs"))

import hou
import dsh_hou_helpers


assert dsh_hou_helpers._select_srgb_ocio_space([
    "sRGB - Display",
    "sRGB Encoded Rec.709 (sRGB)",
]) == "sRGB Encoded Rec.709 (sRGB)"
assert dsh_hou_helpers._select_srgb_ocio_space([
    "ACEScg",
    "sRGB - Texture",
]) == "sRGB - Texture"
assert dsh_hou_helpers._select_srgb_ocio_space([
    "studio encoded sRGB texture",
]) == "studio encoded sRGB texture"
assert dsh_hou_helpers._select_srgb_ocio_space([
    "ACEScg",
    "sRGB - Display",
]) is None

available = set(hou.Color.ocio_spaces())
png = dsh_hou_helpers._render_output_color_plan("preview.PNG")
assert png["mode"] == "display_srgb", png
assert png["extension"] == ".png", png
assert png["method"] == "ocio_colorspace", png
assert png["ocio_colorspace"] in available, png
assert png["settings"]["colorcorrect"] == "ocio", png
assert png["settings"]["gamma"] == 1.0, png
assert png["settings"]["ociocolorspace"] == png["ocio_colorspace"], png

exr = dsh_hou_helpers._render_output_color_plan("working.exr")
assert exr["mode"] == "scene_linear", exr
assert exr["method"] == "none", exr
assert exr["settings"]["colorcorrect"] == "none", exr
assert exr["settings"]["gamma"] == 1.0, exr
assert exr["settings"]["ociocolorspace"] == "", exr

fallback = dsh_hou_helpers._render_output_color_plan(
    "preview.png", ocio_spaces=["ACEScg", "sRGB - Display"])
assert fallback["method"] == "gamma_fallback", fallback
assert fallback["approximate"] is True, fallback
assert fallback["settings"]["colorcorrect"] == "lut_gamma", fallback
assert fallback["settings"]["gamma"] == 2.2, fallback

suffix = uuid.uuid4().hex[:8]
rop = hou.node("/out").createNode("opengl", f"__dsh_color_contract_{suffix}")
try:
    for name, value in png["settings"].items():
        assert dsh_hou_helpers._try_set(rop, name, value), (name, value)
    assert rop.parm("colorcorrect").rawValue() == "ocio"
    assert rop.parm("ociocolorspace").eval() == png["ocio_colorspace"]

    for name, value in exr["settings"].items():
        assert dsh_hou_helpers._try_set(rop, name, value), (name, value)
    assert rop.parm("colorcorrect").rawValue() == "none"
    assert rop.parm("ociocolorspace").eval() == ""
finally:
    rop.destroy()

print(
    "render color management regression passed "
    f"({hou.applicationVersionString()}, {png['ocio_colorspace']})"
)
