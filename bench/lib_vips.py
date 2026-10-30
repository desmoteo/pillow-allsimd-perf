"""libvips through pyvips, one thread, operation cache off.

libvips is lazy: an operation builds a pipeline and nothing is computed
until the pixels are needed, so every case ends with copy_memory() (or an
encoder, or a statistic), which runs the whole pipeline into memory.
"""

from __future__ import annotations

from typing import Any, Callable

import pyvips

from common import BLUR_RADII, SCALE_DESTS, SCALE_FILTERS

pyvips.cache_set_max(0)
pyvips.concurrency_set(1)

NOTES = {
    "scale/RGBA": "resize without premultiplying alpha.",
    "blur/gaussian": "gaussblur with the default min_ampl 0.2: a shorter kernel than Pillow's.",
    "convert/RGB/L": "colourspace b-w, through CIE XYZ.",
    "convert/L/RGB": "colourspace srgb from b-w.",
    "convert/RGB/HSV": "colourspace hsv.",
    "convert/RGB/CMYK": "colourspace cmyk, through a colour profile (lcms).",
    "rotate/": "rotate() enlarges the canvas to fit the rotated image.",
    "composite/alpha": "composite2 'over', in float and premultiplied.",
    "codec/thumbnail": "thumbnail_buffer: shrink-on-load, then resize.",
    "codec/": "Debian's libjpeg-turbo, libspng and libwebp.",
    "cycle/": "One lazy pipeline: decode, rot, resize (cubic), gaussblur, jpegsave.",
}

KERNEL = {"bilinear": "linear", "bicubic": "cubic", "lanczos": "lanczos3"}


def version() -> str:
    return ".".join(str(pyvips.version(i)) for i in range(3))


def cases(src: dict[str, Any]) -> dict[str, Callable[[], object]]:
    w, h = src["size"]

    def image(data: bytes, bands: int) -> pyvips.Image:
        im = pyvips.Image.new_from_memory(data, w, h, bands, "uchar")
        return im.copy(interpretation="b-w" if bands == 1 else "srgb").copy_memory()

    rgb, rgb2 = image(src["rgb"], 3), image(src["rgb2"], 3)
    rgba, rgba2 = image(src["rgba"], 4), image(src["rgba2"], 4)
    L = image(src["l"], 1)
    c: dict[str, Callable[[], object]] = {}

    def mem(fn: Callable[[], pyvips.Image]) -> Callable[[], object]:
        return lambda: fn().copy_memory()

    for mode, im in (("RGB", rgb), ("RGBA", rgba)):
        for dw, dh in SCALE_DESTS:
            for f in SCALE_FILTERS:
                c[f"scale/{mode}/{dw}x{dh}/{f}"] = mem(
                    lambda im=im, d=(dw, dh), k=KERNEL[f]: im.resize(d[0] / w, vscale=d[1] / h, kernel=k)
                )
    for dw, dh in SCALE_DESTS[1:3]:
        c[f"scale/L/{dw}x{dh}/bicubic"] = mem(lambda d=(dw, dh): L.resize(d[0] / w, vscale=d[1] / h, kernel="cubic"))
    for n in (2, 4):
        c[f"reduce/RGB/{n}"] = mem(lambda n=n: rgb.shrink(n, n))
    c["reduce/L/2"] = mem(lambda: L.shrink(2, 2))

    for r in BLUR_RADII:
        c[f"blur/gaussian/RGB/{r}"] = mem(lambda r=r: rgb.gaussblur(r))
    c["blur/gaussian/RGBA/10"] = mem(lambda: rgba.gaussblur(10))
    c["blur/gaussian/L/10"] = mem(lambda: L.gaussblur(10))

    kernels = {
        "SMOOTH": ([[1, 1, 1], [1, 5, 1], [1, 1, 1]], 13),
        "SHARPEN": ([[-2, -2, -2], [-2, 32, -2], [-2, -2, -2]], 16),
        "EDGE_ENHANCE": ([[-1, -1, -1], [-1, 10, -1], [-1, -1, -1]], 2),
        "FIND_EDGES": ([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]], 1),
        "SMOOTH_MORE": (
            [[1, 1, 1, 1, 1], [1, 5, 5, 5, 1], [1, 5, 44, 5, 1], [1, 5, 5, 5, 1], [1, 1, 1, 1, 1]],
            100,
        ),
    }
    masks = {k: pyvips.Image.new_from_list(m, scale=s) for k, (m, s) in kernels.items()}
    for name, mask in masks.items():
        c[f"filter/RGB/{name}"] = mem(lambda m=mask: rgb.conv(m, precision="integer").cast("uchar"))
    c["filter/L/SHARPEN"] = mem(lambda: L.conv(masks["SHARPEN"], precision="integer").cast("uchar"))
    c["filter/L/SMOOTH_MORE"] = mem(lambda: L.conv(masks["SMOOTH_MORE"], precision="integer").cast("uchar"))

    c["rank/median3/RGB"] = mem(lambda: rgb.median(3))
    c["rank/median5/RGB"] = mem(lambda: rgb.median(5))
    c["rank/median3/L"] = mem(lambda: L.median(3))
    c["rank/min3/RGB"] = mem(lambda: rgb.rank(3, 3, 0))
    c["rank/max3/RGB"] = mem(lambda: rgb.rank(3, 3, 8))

    rgba_pm = rgba.premultiply().cast("uchar").copy_memory()
    c["convert/RGB/L"] = mem(lambda: rgb.colourspace("b-w"))
    c["convert/RGB/RGBA"] = mem(lambda: rgb.bandjoin(255))
    c["convert/RGBA/RGB"] = mem(lambda: rgba.extract_band(0, n=3))
    c["convert/RGBA/RGBa"] = mem(lambda: rgba.premultiply().cast("uchar"))
    c["convert/RGBa/RGBA"] = mem(lambda: rgba_pm.unpremultiply().cast("uchar"))
    c["convert/RGB/HSV"] = mem(lambda: rgb.colourspace("hsv"))
    c["convert/RGB/CMYK"] = mem(lambda: rgb.colourspace("cmyk"))
    c["convert/L/RGB"] = mem(lambda: L.colourspace("srgb"))

    c["composite/alpha"] = mem(lambda: rgba.composite2(rgba2, "over").cast("uchar"))
    c["composite/blend"] = mem(lambda: (rgb * 0.5 + rgb2 * 0.5).cast("uchar"))
    c["composite/mask"] = mem(lambda: L.ifthenelse(rgb, rgb2, blend=True))

    c["transpose/RGB/FLIP_LEFT_RIGHT"] = mem(lambda: rgb.fliphor())
    c["transpose/RGB/FLIP_TOP_BOTTOM"] = mem(lambda: rgb.flipver())
    c["transpose/RGB/ROTATE_90"] = mem(lambda: rgb.rot("d270"))
    c["transpose/RGB/ROTATE_180"] = mem(lambda: rgb.rot("d180"))
    c["transpose/RGB/ROTATE_270"] = mem(lambda: rgb.rot("d90"))
    c["transpose/L/ROTATE_90"] = mem(lambda: L.rot("d270"))
    c["transpose/RGBA/ROTATE_90"] = mem(lambda: rgba.rot("d270"))

    for f in ("nearest", "bilinear", "bicubic"):
        interp = pyvips.Interpolate.new(f)
        c[f"rotate/RGB/30/{f}"] = mem(lambda i=interp: rgb.rotate(30, interpolate=i))
    bicubic = pyvips.Interpolate.new("bicubic")
    c["rotate/RGBA/30/bicubic"] = mem(lambda: rgba.rotate(30, interpolate=bicubic))

    gamma = [int(255 * (v / 255) ** 0.8 + 0.5) for v in range(256)]
    lut = pyvips.Image.new_from_list([gamma]).cast("uchar").copy_memory()
    c["point/RGB/table"] = mem(lambda: rgb.maplut(lut))
    c["point/RGB/invert"] = mem(lambda: rgb.invert())
    c["point/L/table"] = mem(lambda: L.maplut(lut))

    c["chops/RGB/multiply"] = mem(lambda: (rgb * rgb2 / 255).cast("uchar"))
    c["chops/RGB/add"] = mem(lambda: (rgb + rgb2).cast("uchar"))
    c["chops/RGB/difference"] = mem(lambda: (rgb - rgb2).abs().cast("uchar"))
    c["chops/RGB/lighter"] = mem(lambda: (rgb > rgb2).ifthenelse(rgb, rgb2))

    c["stats/histogram/RGB"] = mem(lambda: rgb.hist_find(band=-1))
    c["stats/histogram/L"] = mem(lambda: L.hist_find())
    c["stats/extrema/RGB"] = lambda: [(b.min(), b.max()) for b in rgb.bandsplit()]

    enc = src["encoded"]
    for fmt in ("jpeg", "png", "webp"):
        data = enc[fmt]
        c[f"codec/decode/{fmt}"] = mem(lambda d=data: pyvips.Image.new_from_buffer(d, "", access="sequential"))
    c["codec/encode/jpeg"] = lambda: rgb.write_to_buffer(".jpg", Q=85)
    c["codec/encode/png"] = lambda: rgb.write_to_buffer(".png", compression=6)
    c["codec/encode/webp"] = lambda: rgb.write_to_buffer(".webp", Q=80)
    jpeg = enc["jpeg"]
    c["codec/thumbnail/jpeg"] = mem(lambda: pyvips.Image.thumbnail_buffer(jpeg, 320, height=200))

    def cycle(level: int) -> Callable[[], object]:
        def run() -> object:
            # Random access: the rotation reads the decoded image out of order.
            im = pyvips.Image.new_from_buffer(jpeg, "")
            if level > 0:
                im = im.rot("d90")
            if level > 1:
                im = im.resize(0.4, kernel="cubic")
            if level > 2:
                im = im.gaussblur(4)
            return im.write_to_buffer(".jpg", Q=85)

        return run

    for level in range(4):
        c[f"cycle/{level}"] = cycle(level)
    return c
