"""Pillow, Pillow-SIMD and Pillow-AllSIMD: every case in the catalogue."""

from __future__ import annotations

import io
from typing import Any, Callable

from common import BLUR_RADII, DRAW_SHAPES, OUTLINE_WIDTH, SCALE_DESTS, SCALE_FILTERS

from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
    __version__,
    features,
)

R = Image.Resampling
FILTERS = {"bilinear": R.BILINEAR, "bicubic": R.BICUBIC, "lanczos": R.LANCZOS, "nearest": R.NEAREST}


def version() -> str:
    return __version__


def cases(src: dict[str, Any]) -> dict[str, Callable[[], object]]:
    w, h = src["size"]
    rgb = Image.frombytes("RGB", (w, h), src["rgb"])
    rgb2 = Image.frombytes("RGB", (w, h), src["rgb2"])
    rgba = Image.frombytes("RGBA", (w, h), src["rgba"])
    rgba2 = Image.frombytes("RGBA", (w, h), src["rgba2"])
    L = Image.frombytes("L", (w, h), src["l"])
    rgba_pm = rgba.convert("RGBa")
    ycbcr = rgb.convert("YCbCr")
    c: dict[str, Callable[[], object]] = {}

    for mode, im in (("RGB", rgb), ("RGBA", rgba)):
        for dw, dh in SCALE_DESTS:
            for f in SCALE_FILTERS:
                c[f"scale/{mode}/{dw}x{dh}/{f}"] = (
                    lambda im=im, d=(dw, dh), f=FILTERS[f]: im.resize(d, f)
                )
    for dw, dh in SCALE_DESTS[1:3]:
        c[f"scale/L/{dw}x{dh}/bicubic"] = lambda d=(dw, dh): L.resize(d, R.BICUBIC)
    for n in (2, 4):
        c[f"reduce/RGB/{n}"] = lambda n=n: rgb.reduce(n)
    c["reduce/L/2"] = lambda: L.reduce(2)

    for r in BLUR_RADII:
        c[f"blur/gaussian/RGB/{r}"] = lambda r=r: rgb.filter(ImageFilter.GaussianBlur(r))
    c["blur/gaussian/RGBA/10"] = lambda: rgba.filter(ImageFilter.GaussianBlur(10))
    c["blur/gaussian/L/10"] = lambda: L.filter(ImageFilter.GaussianBlur(10))
    for r in (2, 10):
        c[f"blur/box/RGB/{r}"] = lambda r=r: rgb.filter(ImageFilter.BoxBlur(r))

    for name in ("SMOOTH", "SHARPEN", "EDGE_ENHANCE", "FIND_EDGES", "SMOOTH_MORE"):
        c[f"filter/RGB/{name}"] = lambda k=getattr(ImageFilter, name): rgb.filter(k)
    c["filter/L/SHARPEN"] = lambda: L.filter(ImageFilter.SHARPEN)
    c["filter/L/SMOOTH_MORE"] = lambda: L.filter(ImageFilter.SMOOTH_MORE)
    c["unsharp/RGB"] = lambda: rgb.filter(ImageFilter.UnsharpMask(2, 150, 3))
    c["unsharp/L"] = lambda: L.filter(ImageFilter.UnsharpMask(2, 150, 3))

    c["rank/median3/RGB"] = lambda: rgb.filter(ImageFilter.MedianFilter(3))
    c["rank/median5/RGB"] = lambda: rgb.filter(ImageFilter.MedianFilter(5))
    c["rank/median3/L"] = lambda: L.filter(ImageFilter.MedianFilter(3))
    c["rank/min3/RGB"] = lambda: rgb.filter(ImageFilter.MinFilter(3))
    c["rank/max3/RGB"] = lambda: rgb.filter(ImageFilter.MaxFilter(3))

    srcs = {"RGB": rgb, "RGBA": rgba, "RGBa": rgba_pm, "YCbCr": ycbcr, "L": L}
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
        c[f"convert/{a}/{b}"] = lambda im=srcs[a], b=b: im.convert(b)

    c["composite/alpha"] = lambda: Image.alpha_composite(rgba, rgba2)
    c["composite/blend"] = lambda: Image.blend(rgb, rgb2, 0.5)
    c["composite/mask"] = lambda: Image.composite(rgb, rgb2, L)

    T = Image.Transpose
    for t in ("FLIP_LEFT_RIGHT", "FLIP_TOP_BOTTOM", "ROTATE_90", "ROTATE_180", "ROTATE_270", "TRANSPOSE"):
        c[f"transpose/RGB/{t}"] = lambda t=getattr(T, t): rgb.transpose(t)
    c["transpose/L/ROTATE_90"] = lambda: L.transpose(T.ROTATE_90)
    c["transpose/RGBA/ROTATE_90"] = lambda: rgba.transpose(T.ROTATE_90)

    for f in ("nearest", "bilinear", "bicubic"):
        c[f"rotate/RGB/30/{f}"] = lambda f=FILTERS[f]: rgb.rotate(30, f)
    c["rotate/RGBA/30/bicubic"] = lambda: rgba.rotate(30, R.BICUBIC)
    coeffs = perspective_coeffs(w, h)
    c["rotate/RGB/perspective/bilinear"] = lambda: rgb.transform(
        (w, h), Image.Transform.PERSPECTIVE, coeffs, R.BILINEAR
    )

    for n in (4, 16, 36):
        lut = ImageFilter.Color3DLUT.generate(n, lambda r, g, b: (r, g * 0.9, b ** 1.2))
        c[f"lut/RGB/{n}"] = lambda lut=lut: rgb.filter(lut)
    lut4 = ImageFilter.Color3DLUT.generate(
        16, lambda r, g, b: (r, g * 0.9, b ** 1.2, r), channels=4
    )
    c["lut/RGBA/16"] = lambda: rgba.filter(lut4)

    gamma = [int(255 * (v / 255) ** 0.8 + 0.5) for v in range(256)]
    c["point/RGB/table"] = lambda: rgb.point(gamma * 3)
    c["point/RGB/invert"] = lambda: ImageOps.invert(rgb)
    c["point/L/table"] = lambda: L.point(gamma)

    for op in ("multiply", "screen", "add", "difference", "lighter"):
        c[f"chops/RGB/{op}"] = lambda f=getattr(ImageChops, op): f(rgb, rgb2)

    c["stats/histogram/RGB"] = lambda: rgb.histogram()
    c["stats/histogram/L"] = lambda: L.histogram()
    c["stats/extrema/RGB"] = lambda: rgb.getextrema()
    photo = src["photo"]
    c["quantize/mediancut"] = lambda: photo.quantize(256, Image.Quantize.MEDIANCUT)
    c["quantize/fastoctree"] = lambda: photo.quantize(256, Image.Quantize.FASTOCTREE)

    shapes = src["shapes"]

    def draw(kind: str) -> Callable[[], object]:
        items = shapes[kind]

        def run() -> object:
            canvas = Image.new("RGB", (w, h))
            d = ImageDraw.Draw(canvas)
            for box, color in items:
                if kind == "polygons":
                    d.polygon(box, fill=color)
                elif kind == "ellipses":
                    d.ellipse(box, fill=color)
                elif kind == "rectangles":
                    d.rectangle(box, fill=color)
                else:
                    d.line(box, fill=color, width=5)
            return canvas

        return run

    for kind in DRAW_SHAPES:
        c[f"draw/{kind}"] = draw(kind)

    def outline(kind: str) -> Callable[[], object]:
        items = shapes[f"outline_{kind}"]

        def run() -> object:
            canvas = Image.new("RGB", (w, h))
            d = ImageDraw.Draw(canvas)
            for shape, color in items:
                if kind == "polygons":
                    d.polygon(shape, outline=color, width=OUTLINE_WIDTH)
                else:
                    d.rectangle(shape, outline=color, width=OUTLINE_WIDTH)
            return canvas

        return run

    for kind in ("rectangles", "polygons"):
        c[f"draw/outline/{kind}"] = outline(kind)
    if features.check("freetype2"):
        font = ImageFont.load_default(24)
        lines = src["text"]

        def text() -> object:
            canvas = Image.new("RGB", (w, h))
            d = ImageDraw.Draw(canvas)
            for i, line in enumerate(lines):
                d.text((10, 10 + i * 15), line, fill=(255, 255, 255), font=font)
            return canvas

        c["draw/text"] = text

    enc = src["encoded"]

    def decode(data: bytes) -> Callable[[], object]:
        def run() -> object:
            im = Image.open(io.BytesIO(data))
            im.load()
            return im

        return run

    def encode(fmt: str, **kw: Any) -> Callable[[], object]:
        return lambda: photo.save(io.BytesIO(), fmt, **kw)

    opts = {"jpeg": {"quality": 85}, "png": {"compress_level": 6}, "webp": {"quality": 80}}
    for fmt in ("jpeg", "png", "webp"):
        if features.check({"jpeg": "jpg", "png": "zlib", "webp": "webp"}[fmt]):
            c[f"codec/decode/{fmt}"] = decode(enc[fmt])
            c[f"codec/encode/{fmt}"] = encode(fmt.upper(), **opts[fmt])

    if features.check("jpg"):
        jpeg = enc["jpeg"]

        def thumbnail() -> object:
            im = Image.open(io.BytesIO(jpeg))
            im.draft("RGB", (320, 200))
            im.thumbnail((320, 200), R.BICUBIC)
            return im

        c["codec/thumbnail/jpeg"] = thumbnail

        def cycle(level: int) -> Callable[[], object]:
            def run() -> object:
                im = Image.open(io.BytesIO(jpeg))
                if level > 0:
                    im = im.transpose(T.ROTATE_270)
                if level > 1:
                    im = im.resize((round(im.width * 0.4), round(im.height * 0.4)), R.BICUBIC)
                if level > 2:
                    im = im.filter(ImageFilter.GaussianBlur(4))
                im.save(io.BytesIO(), "JPEG", quality=85)
                return im

            return run

        for level in range(4):
            c[f"cycle/{level}"] = cycle(level)
    return c


def perspective_coeffs(w: int, h: int) -> tuple[float, ...]:
    """A mild keystone: the top edge shrunk by 10% on each side."""
    return (1.1, 0.1, -0.1 * w, 0.0, 1.05, 0.0, 0.00002, 0.00003)


def prepare(src: dict[str, Any]) -> None:
    """Pillow objects that other cases reuse."""
    w, h = src["size"]
    src["photo"] = Image.frombytes("RGB", (w, h), src["photo_rgb"])
