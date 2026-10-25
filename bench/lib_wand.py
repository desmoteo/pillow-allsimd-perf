"""ImageMagick 7 through Wand, MAGICK_THREAD_LIMIT=1.

Wand operations modify the image in place, so each run works on a clone,
the counterpart of the new image Pillow allocates for its result.
"""

from __future__ import annotations

from typing import Any, Callable

from wand.image import Image
from wand.version import MAGICK_VERSION_INFO

from common import BLUR_RADII, SCALE_DESTS, SCALE_FILTERS

NOTES = {
    "scale/": "Filters triangle, catrom (Catmull-Rom, like Pillow's bicubic) and lanczos.",
    "blur/gaussian": "blur(): ImageMagick's separable Gaussian.",
    "unsharp/": "unsharp_mask(sigma 2, amount 1.5, threshold 3/255).",
    "rank/": "statistic() over a 3x3 or 5x5 window.",
    "rotate/RGB/30": "rotate(): ImageMagick's shear rotation, enlarges the canvas; no filter choice.",
    "rotate/RGB/perspective": "distort('perspective'): EWA resampling, higher quality and cost.",
    "point/RGB/table": "gamma(1.25), the same curve as the table.",
    "chops/RGB/add": "composite 'plus'.",
    "chops/RGB/lighter": "composite 'lighten'.",
    "quantize/": "quantize(256), no dither.",
    "codec/thumbnail": "jpeg:size hint (DCT scaling), then thumbnail().",
    "codec/encode/png": "compression_quality 65: zlib level 6, adaptive filter.",
    "codec/": "Debian's libjpeg-turbo, libpng and libwebp.",
    "cycle/": "read, rotate, resize (catrom), blur, JPEG q85.",
}

FILTER = {"bilinear": "triangle", "bicubic": "catrom", "lanczos": "lanczos"}


def version() -> str:
    return ".".join(str(v) for v in MAGICK_VERSION_INFO[:3])


def cases(src: dict[str, Any]) -> dict[str, Callable[[], object]]:
    w, h = src["size"]

    def image(data: bytes, fmt: str) -> Image:
        return Image(blob=data, format=fmt, width=w, height=h, depth=8)

    rgb, rgb2 = image(src["rgb"], "rgb"), image(src["rgb2"], "rgb")
    rgba, rgba2 = image(src["rgba"], "rgba"), image(src["rgba2"], "rgba")
    L = image(src["l"], "gray")
    c: dict[str, Callable[[], object]] = {}

    def on(base: Image, fn: Callable[[Image], object]) -> Callable[[], object]:
        def run() -> object:
            with base.clone() as im:
                fn(im)
                return im.width

        return run

    for mode, base in (("RGB", rgb), ("RGBA", rgba)):
        for dw, dh in SCALE_DESTS:
            for f in SCALE_FILTERS:
                c[f"scale/{mode}/{dw}x{dh}/{f}"] = on(base, lambda im, d=(dw, dh), f=FILTER[f]: im.resize(*d, filter=f))
    for dw, dh in SCALE_DESTS[1:3]:
        c[f"scale/L/{dw}x{dh}/bicubic"] = on(L, lambda im, d=(dw, dh): im.resize(*d, filter="catrom"))

    for r in BLUR_RADII:
        c[f"blur/gaussian/RGB/{r}"] = on(rgb, lambda im, r=r: im.blur(sigma=r))
    c["blur/gaussian/RGBA/10"] = on(rgba, lambda im: im.blur(sigma=10))
    c["blur/gaussian/L/10"] = on(L, lambda im: im.blur(sigma=10))

    c["unsharp/RGB"] = on(rgb, lambda im: im.unsharp_mask(radius=0, sigma=2, amount=1.5, threshold=3 / 255))
    c["unsharp/L"] = on(L, lambda im: im.unsharp_mask(radius=0, sigma=2, amount=1.5, threshold=3 / 255))

    c["rank/median3/RGB"] = on(rgb, lambda im: im.statistic("median", 3, 3))
    c["rank/median5/RGB"] = on(rgb, lambda im: im.statistic("median", 5, 5))
    c["rank/median3/L"] = on(L, lambda im: im.statistic("median", 3, 3))
    c["rank/min3/RGB"] = on(rgb, lambda im: im.statistic("minimum", 3, 3))
    c["rank/max3/RGB"] = on(rgb, lambda im: im.statistic("maximum", 3, 3))

    def set_alpha(im: Image, v: str) -> None:
        im.alpha_channel = v

    c["convert/RGB/L"] = on(rgb, lambda im: im.transform_colorspace("gray"))
    c["convert/RGB/RGBA"] = on(rgb, lambda im: set_alpha(im, "opaque"))
    c["convert/RGBA/RGB"] = on(rgba, lambda im: set_alpha(im, "off"))
    c["convert/RGB/HSV"] = on(rgb, lambda im: im.transform_colorspace("hsv"))
    c["convert/RGB/YCbCr"] = on(rgb, lambda im: im.transform_colorspace("ycbcr"))
    c["convert/RGB/CMYK"] = on(rgb, lambda im: im.transform_colorspace("cmyk"))
    c["convert/L/RGB"] = on(L, lambda im: im.transform_colorspace("srgb"))

    c["composite/alpha"] = on(rgba, lambda im: im.composite(rgba2, 0, 0, operator="over"))

    c["transpose/RGB/FLIP_LEFT_RIGHT"] = on(rgb, lambda im: im.flop())
    c["transpose/RGB/FLIP_TOP_BOTTOM"] = on(rgb, lambda im: im.flip())
    c["transpose/RGB/ROTATE_90"] = on(rgb, lambda im: im.rotate(270))
    c["transpose/RGB/ROTATE_180"] = on(rgb, lambda im: im.rotate(180))
    c["transpose/RGB/ROTATE_270"] = on(rgb, lambda im: im.rotate(90))
    c["transpose/RGB/TRANSPOSE"] = on(rgb, lambda im: im.transpose())
    c["transpose/L/ROTATE_90"] = on(L, lambda im: im.rotate(270))
    c["transpose/RGBA/ROTATE_90"] = on(rgba, lambda im: im.rotate(270))

    c["rotate/RGB/30/bilinear"] = on(rgb, lambda im: im.rotate(-30))
    pts = (0, 0, 0.1 * w, 0, w, 0, 0.9 * w, 0, w, h, w, h, 0, h, 0, h)
    c["rotate/RGB/perspective/bilinear"] = on(rgb, lambda im: im.distort("perspective", pts))

    c["point/RGB/table"] = on(rgb, lambda im: im.gamma(1.25))
    c["point/RGB/invert"] = on(rgb, lambda im: im.negate())

    for op, iop in (("multiply", "multiply"), ("screen", "screen"), ("add", "plus"), ("difference", "difference"), ("lighter", "lighten")):
        c[f"chops/RGB/{op}"] = on(rgb, lambda im, o=iop: im.composite(rgb2, 0, 0, operator=o))

    photo = rgb
    c["quantize/mediancut"] = on(photo, lambda im: im.quantize(256, "srgb", 0, False, False))

    enc = src["encoded"]
    for fmt in ("jpeg", "png", "webp"):

        def decode(d: bytes = enc[fmt]) -> object:
            with Image(blob=d) as im:
                return im.width

        c[f"codec/decode/{fmt}"] = decode

    def encode(fmt: str, quality: int) -> Callable[[], object]:
        def run() -> object:
            with rgb.clone() as im:
                im.format = fmt
                im.compression_quality = quality
                return im.make_blob()

        return run

    c["codec/encode/jpeg"] = encode("jpeg", 85)
    c["codec/encode/png"] = encode("png", 65)
    c["codec/encode/webp"] = encode("webp", 80)
    jpeg = enc["jpeg"]

    def thumbnail() -> object:
        with Image() as im:
            im.options["jpeg:size"] = "640x400"
            im.read(blob=jpeg)
            im.thumbnail(320, 200)
            return im.width

    c["codec/thumbnail/jpeg"] = thumbnail

    def cycle(level: int) -> Callable[[], object]:
        def run() -> object:
            with Image(blob=jpeg) as im:
                if level > 0:
                    im.rotate(90)
                if level > 1:
                    im.resize(round(im.width * 0.4), round(im.height * 0.4), filter="catrom")
                if level > 2:
                    im.blur(sigma=4)
                im.compression_quality = 85
                return im.make_blob("jpeg")

        return run

    for level in range(4):
        c[f"cycle/{level}"] = cycle(level)
    return c
