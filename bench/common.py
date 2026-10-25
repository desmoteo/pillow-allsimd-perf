"""Case catalogue shared by every library.

Each case has an id ("suite/..."), a title for the page and the amount of
work it does: megapixels of the source image for image operations, shapes or
lines for the drawing ones. The library modules (lib_*.py) implement the
cases they can; a library that lacks an operation simply has no entry.
"""

from __future__ import annotations

import os

WIDTH, HEIGHT = 2560, 1600


def size() -> tuple[int, int]:
    w, h = os.environ.get("PERF_SIZE", f"{WIDTH}x{HEIGHT}").split("x")
    return int(w), int(h)


SUITES = [
    ("scale", "Resize", "Convolution resampling of the whole image."),
    ("reduce", "Reduce", "Integer downscale by box averaging."),
    ("blur", "Blur", "Gaussian and box blur."),
    ("filter", "Kernel filters", "3x3 and 5x5 convolution kernels."),
    ("unsharp", "Unsharp mask", "Sharpening with a Gaussian unsharp mask."),
    ("rank", "Rank filters", "Median, minimum and maximum filters."),
    ("convert", "Mode conversion", "Colour space and band conversions."),
    ("composite", "Composition", "Alpha compositing and blending."),
    ("transpose", "Flips and right angles", "Lossless flips and rotations."),
    ("rotate", "Rotation and transforms", "Arbitrary-angle affine and perspective warps."),
    ("lut", "Colour LUT", "3D colour lookup tables (Color3DLUT)."),
    ("point", "Point operations", "Per-value lookup tables."),
    ("chops", "Channel operations", "Pixel-wise arithmetic between two images."),
    ("stats", "Statistics", "Histograms and extrema."),
    ("quantize", "Quantization", "Reduction to a 256-colour palette."),
    ("draw", "Drawing", "Shapes and text on an RGB canvas."),
    ("codec", "Load and save", "Decoding and encoding in memory."),
    ("cycle", "Full cycle", "Decode a JPEG, transform it and encode it again."),
]

SCALE_DESTS = [(26, 16), (320, 200), (2048, 1280), (5478, 3424)]
SCALE_FILTERS = ["bilinear", "bicubic", "lanczos"]
BLUR_RADII = [1, 10, 30]
DRAW_SHAPES = {"polygons": 200, "ellipses": 200, "rectangles": 500, "lines": 500}


def _meta() -> dict[str, dict]:
    m: dict[str, dict] = {}

    def add(cid: str, title: str, work: str = "mpx", n: float | None = None) -> None:
        m[cid] = {"suite": cid.split("/")[0], "title": title, "work": work, "n": n}

    for mode in ("RGB", "RGBA"):
        for dw, dh in SCALE_DESTS:
            for f in SCALE_FILTERS:
                add(f"scale/{mode}/{dw}x{dh}/{f}", f"{mode} to {dw}x{dh} {f}")
    for mode in ("L",):
        for dw, dh in SCALE_DESTS[1:3]:
            add(f"scale/{mode}/{dw}x{dh}/bicubic", f"{mode} to {dw}x{dh} bicubic")
    for n in (2, 4):
        add(f"reduce/RGB/{n}", f"RGB by {n}")
    add("reduce/L/2", "L by 2")
    for r in BLUR_RADII:
        add(f"blur/gaussian/RGB/{r}", f"Gaussian RGB radius {r}")
    add("blur/gaussian/RGBA/10", "Gaussian RGBA radius 10")
    add("blur/gaussian/L/10", "Gaussian L radius 10")
    for r in (2, 10):
        add(f"blur/box/RGB/{r}", f"Box RGB radius {r}")
    for name in ("SMOOTH", "SHARPEN", "EDGE_ENHANCE", "FIND_EDGES"):
        add(f"filter/RGB/{name}", f"RGB 3x3 {name}")
    add("filter/RGB/SMOOTH_MORE", "RGB 5x5 SMOOTH_MORE")
    add("filter/L/SHARPEN", "L 3x3 SHARPEN")
    add("filter/L/SMOOTH_MORE", "L 5x5 SMOOTH_MORE")
    add("unsharp/RGB", "RGB radius 2, 150%, threshold 3")
    add("unsharp/L", "L radius 2, 150%, threshold 3")
    add("rank/median3/RGB", "Median 3x3 RGB")
    add("rank/median5/RGB", "Median 5x5 RGB")
    add("rank/median3/L", "Median 3x3 L")
    add("rank/min3/RGB", "Minimum 3x3 RGB")
    add("rank/max3/RGB", "Maximum 3x3 RGB")
    for a, b in [
        ("RGB", "L"),
        ("RGB", "RGBA"),
        ("RGBA", "RGB"),
        ("RGBA", "RGBa"),
        ("RGBa", "RGBA"),
        ("RGB", "HSV"),
        ("RGB", "YCbCr"),
        ("YCbCr", "RGB"),
        ("RGB", "CMYK"),
        ("L", "RGB"),
    ]:
        add(f"convert/{a}/{b}", f"{a} to {b}")
    add("composite/alpha", "RGBA over RGBA (alpha_composite)")
    add("composite/blend", "Blend two RGB images 50%")
    add("composite/mask", "RGB with an L mask (composite)")
    for t in ("FLIP_LEFT_RIGHT", "FLIP_TOP_BOTTOM", "ROTATE_90", "ROTATE_180", "ROTATE_270", "TRANSPOSE"):
        add(f"transpose/RGB/{t}", f"RGB {t}")
    add("transpose/L/ROTATE_90", "L ROTATE_90")
    add("transpose/RGBA/ROTATE_90", "RGBA ROTATE_90")
    for f in ("nearest", "bilinear", "bicubic"):
        add(f"rotate/RGB/30/{f}", f"RGB 30 degrees {f}")
    add("rotate/RGBA/30/bicubic", "RGBA 30 degrees bicubic")
    add("rotate/RGB/perspective/bilinear", "RGB perspective bilinear")
    for n in (4, 16, 36):
        add(f"lut/RGB/{n}", f"RGB, {n}³ table")
    add("lut/RGBA/16", "RGBA, 16³ table")
    add("point/RGB/table", "RGB per-channel table")
    add("point/RGB/invert", "RGB invert")
    add("point/L/table", "L table")
    for op in ("multiply", "screen", "add", "difference", "lighter"):
        add(f"chops/RGB/{op}", f"RGB {op}")
    add("stats/histogram/RGB", "Histogram RGB")
    add("stats/histogram/L", "Histogram L")
    add("stats/extrema/RGB", "Extrema RGB")
    add("quantize/mediancut", "Median cut, 256 colours")
    add("quantize/fastoctree", "Fast octree, 256 colours")
    for shape, n in DRAW_SHAPES.items():
        add(f"draw/{shape}", f"{n} filled {shape}" if shape != "lines" else f"{n} lines 5px wide", "shapes", n)
    add("draw/text", "100 lines of text", "lines", 100)
    for fmt, what in (("jpeg", "JPEG q85"), ("png", "PNG level 6"), ("webp", "WebP q80")):
        add(f"codec/decode/{fmt}", f"Decode {what} RGB")
        add(f"codec/encode/{fmt}", f"Encode {what} RGB")
    add("codec/thumbnail/jpeg", "JPEG to a 320x200 thumbnail")
    for level, title in enumerate(["Load + save", "+ rotate 270", "+ resize 0.4 bicubic", "+ Gaussian blur 4"]):
        add(f"cycle/{level}", title)
    return m


META = _meta()

