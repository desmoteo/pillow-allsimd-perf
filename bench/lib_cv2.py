"""OpenCV (opencv-python-headless) on numpy arrays, single-threaded."""

from __future__ import annotations

from typing import Any, Callable

import cv2
import numpy as np

from common import BLUR_RADII, DRAW_SHAPES, SCALE_DESTS, SCALE_FILTERS

cv2.setNumThreads(1)

NOTES = {
    "scale/": "Shrinking uses INTER_AREA: OpenCV's linear, cubic and Lanczos "
    "filters don't antialias when shrinking. Enlarging uses the named filter.",
    "rotate/RGB/30": "warpAffine about the centre, same canvas.",
    "rotate/RGBA": "warpAffine about the centre, same canvas; no premultiplication.",
    "convert/RGB/YCbCr": "COLOR_RGB2YCrCb (Cr and Cb swapped).",
    "convert/YCbCr/RGB": "COLOR_YCrCb2RGB.",
    "convert/RGB/HSV": "COLOR_RGB2HSV_FULL (hue 0-255, like Pillow).",
    "unsharp/": "GaussianBlur + addWeighted; no threshold.",
    "composite/alpha": "Written with numpy: float32 'over' (no native operation).",
    "chops/RGB/screen": "255 - multiply(255 - a, 255 - b) / 255.",
    "draw/": "cv2.fillPoly, ellipse, rectangle and line, filled, no antialiasing.",
    "draw/text": "cv2.putText with a Hershey font: not comparable glyphs.",
    "codec/thumbnail": "IMREAD_REDUCED_COLOR_8 (DCT scaling), then INTER_AREA.",
    "cycle/": "imdecode, rotate, resize INTER_AREA, GaussianBlur, imencode.",
    "codec/": "OpenCV's bundled libjpeg-turbo, libpng and libwebp.",
}

INTER = {"bilinear": cv2.INTER_LINEAR, "bicubic": cv2.INTER_CUBIC, "lanczos": cv2.INTER_LANCZOS4}


def version() -> str:
    return cv2.__version__


def cases(src: dict[str, Any]) -> dict[str, Callable[[], object]]:
    w, h = src["size"]
    rgb = np.frombuffer(src["rgb"], np.uint8).reshape(h, w, 3).copy()
    rgb2 = np.frombuffer(src["rgb2"], np.uint8).reshape(h, w, 3).copy()
    rgba = np.frombuffer(src["rgba"], np.uint8).reshape(h, w, 4).copy()
    rgba2 = np.frombuffer(src["rgba2"], np.uint8).reshape(h, w, 4).copy()
    L = np.frombuffer(src["l"], np.uint8).reshape(h, w).copy()
    c: dict[str, Callable[[], object]] = {}

    for mode, im in (("RGB", rgb), ("RGBA", rgba)):
        for dw, dh in SCALE_DESTS:
            for f in SCALE_FILTERS:
                inter = cv2.INTER_AREA if dw < w else INTER[f]
                c[f"scale/{mode}/{dw}x{dh}/{f}"] = (
                    lambda im=im, d=(dw, dh), i=inter: cv2.resize(im, d, interpolation=i)
                )
    for dw, dh in SCALE_DESTS[1:3]:
        c[f"scale/L/{dw}x{dh}/bicubic"] = lambda d=(dw, dh): cv2.resize(L, d, interpolation=cv2.INTER_AREA)
    for n in (2, 4):
        c[f"reduce/RGB/{n}"] = lambda n=n: cv2.resize(rgb, (w // n, h // n), interpolation=cv2.INTER_AREA)
    c["reduce/L/2"] = lambda: cv2.resize(L, (w // 2, h // 2), interpolation=cv2.INTER_AREA)

    for r in BLUR_RADII:
        c[f"blur/gaussian/RGB/{r}"] = lambda r=r: cv2.GaussianBlur(rgb, (0, 0), r)
    c["blur/gaussian/RGBA/10"] = lambda: cv2.GaussianBlur(rgba, (0, 0), 10)
    c["blur/gaussian/L/10"] = lambda: cv2.GaussianBlur(L, (0, 0), 10)
    for r in (2, 10):
        c[f"blur/box/RGB/{r}"] = lambda r=r: cv2.blur(rgb, (2 * r + 1, 2 * r + 1))

    kernels = {
        "SMOOTH": ([1, 1, 1, 1, 5, 1, 1, 1, 1], 13),
        "SHARPEN": ([-2, -2, -2, -2, 32, -2, -2, -2, -2], 16),
        "EDGE_ENHANCE": ([-1, -1, -1, -1, 10, -1, -1, -1, -1], 2),
        "FIND_EDGES": ([-1, -1, -1, -1, 8, -1, -1, -1, -1], 1),
        "SMOOTH_MORE": ([1] * 5 + [1, 5, 5, 5, 1, 1, 5, 44, 5, 1, 1, 5, 5, 5, 1] + [1] * 5, 100),
    }

    def kernel(name: str) -> np.ndarray:
        k, scale = kernels[name]
        n = 3 if len(k) == 9 else 5
        return np.array(k, np.float32).reshape(n, n) / scale

    for name in kernels:
        c[f"filter/RGB/{name}"] = lambda k=kernel(name): cv2.filter2D(rgb, -1, k, borderType=cv2.BORDER_REPLICATE)
    c["filter/L/SHARPEN"] = lambda k=kernel("SHARPEN"): cv2.filter2D(L, -1, k, borderType=cv2.BORDER_REPLICATE)
    c["filter/L/SMOOTH_MORE"] = lambda k=kernel("SMOOTH_MORE"): cv2.filter2D(
        L, -1, k, borderType=cv2.BORDER_REPLICATE
    )

    def unsharp(im: np.ndarray) -> Callable[[], object]:
        return lambda: cv2.addWeighted(im, 2.5, cv2.GaussianBlur(im, (0, 0), 2), -1.5, 0)

    c["unsharp/RGB"] = unsharp(rgb)
    c["unsharp/L"] = unsharp(L)

    k3 = np.ones((3, 3), np.uint8)
    c["rank/median3/RGB"] = lambda: cv2.medianBlur(rgb, 3)
    c["rank/median5/RGB"] = lambda: cv2.medianBlur(rgb, 5)
    c["rank/median3/L"] = lambda: cv2.medianBlur(L, 3)
    c["rank/min3/RGB"] = lambda: cv2.erode(rgb, k3)
    c["rank/max3/RGB"] = lambda: cv2.dilate(rgb, k3)

    ycrcb = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb)
    rgba_pm = cv2.cvtColor(rgba, cv2.COLOR_RGBA2mRGBA)
    for cid, im, code in [
        ("RGB/L", rgb, cv2.COLOR_RGB2GRAY),
        ("RGB/RGBA", rgb, cv2.COLOR_RGB2RGBA),
        ("RGBA/RGB", rgba, cv2.COLOR_RGBA2RGB),
        ("RGBA/RGBa", rgba, cv2.COLOR_RGBA2mRGBA),
        ("RGBa/RGBA", rgba_pm, cv2.COLOR_mRGBA2RGBA),
        ("RGB/HSV", rgb, cv2.COLOR_RGB2HSV_FULL),
        ("RGB/YCbCr", rgb, cv2.COLOR_RGB2YCrCb),
        ("YCbCr/RGB", ycrcb, cv2.COLOR_YCrCb2RGB),
        ("L/RGB", L, cv2.COLOR_GRAY2RGB),
    ]:
        c[f"convert/{cid}"] = lambda im=im, code=code: cv2.cvtColor(im, code)

    def over() -> object:
        a = rgba2[..., 3:4].astype(np.float32) / 255
        b = rgba[..., 3:4].astype(np.float32) / 255
        out_a = a + b * (1 - a)
        rgb_out = (rgba2[..., :3] * a + rgba[..., :3] * b * (1 - a)) / np.maximum(out_a, 1e-6)
        return np.dstack([rgb_out, out_a * 255]).astype(np.uint8)

    c["composite/alpha"] = over
    c["composite/blend"] = lambda: cv2.addWeighted(rgb, 0.5, rgb2, 0.5, 0)
    mask3 = cv2.cvtColor(L, cv2.COLOR_GRAY2RGB)
    c["composite/mask"] = lambda: cv2.blendLinear(
        rgb, rgb2, mask3[..., 0].astype(np.float32) / 255, 1 - mask3[..., 0].astype(np.float32) / 255
    )

    for t, fn in [
        ("FLIP_LEFT_RIGHT", lambda im: cv2.flip(im, 1)),
        ("FLIP_TOP_BOTTOM", lambda im: cv2.flip(im, 0)),
        ("ROTATE_90", lambda im: cv2.rotate(im, cv2.ROTATE_90_COUNTERCLOCKWISE)),
        ("ROTATE_180", lambda im: cv2.rotate(im, cv2.ROTATE_180)),
        ("ROTATE_270", lambda im: cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE)),
        ("TRANSPOSE", lambda im: cv2.transpose(im)),
    ]:
        c[f"transpose/RGB/{t}"] = lambda fn=fn: fn(rgb)
    c["transpose/L/ROTATE_90"] = lambda: cv2.rotate(L, cv2.ROTATE_90_COUNTERCLOCKWISE)
    c["transpose/RGBA/ROTATE_90"] = lambda: cv2.rotate(rgba, cv2.ROTATE_90_COUNTERCLOCKWISE)

    m = cv2.getRotationMatrix2D((w / 2, h / 2), 30, 1)
    for f, inter in (("nearest", cv2.INTER_NEAREST), ("bilinear", cv2.INTER_LINEAR), ("bicubic", cv2.INTER_CUBIC)):
        c[f"rotate/RGB/30/{f}"] = lambda i=inter: cv2.warpAffine(rgb, m, (w, h), flags=i)
    c["rotate/RGBA/30/bicubic"] = lambda: cv2.warpAffine(rgba, m, (w, h), flags=cv2.INTER_CUBIC)
    src_pts = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst_pts = np.float32([[0.1 * w, 0], [0.9 * w, 0], [w, h], [0, h]])
    pm = cv2.getPerspectiveTransform(src_pts, dst_pts)
    c["rotate/RGB/perspective/bilinear"] = lambda: cv2.warpPerspective(rgb, pm, (w, h), flags=cv2.INTER_LINEAR)

    gamma = np.array([int(255 * (v / 255) ** 0.8 + 0.5) for v in range(256)], np.uint8)
    c["point/RGB/table"] = lambda: cv2.LUT(rgb, gamma)
    c["point/RGB/invert"] = lambda: cv2.bitwise_not(rgb)
    c["point/L/table"] = lambda: cv2.LUT(L, gamma)

    c["chops/RGB/multiply"] = lambda: cv2.multiply(rgb, rgb2, scale=1 / 255)
    c["chops/RGB/screen"] = lambda: cv2.bitwise_not(
        cv2.multiply(cv2.bitwise_not(rgb), cv2.bitwise_not(rgb2), scale=1 / 255)
    )
    c["chops/RGB/add"] = lambda: cv2.add(rgb, rgb2)
    c["chops/RGB/difference"] = lambda: cv2.absdiff(rgb, rgb2)
    c["chops/RGB/lighter"] = lambda: cv2.max(rgb, rgb2)

    def hist(im: np.ndarray) -> Callable[[], object]:
        chans = 1 if im.ndim == 2 else im.shape[2]
        return lambda: [cv2.calcHist([im], [i], None, [256], [0, 256]) for i in range(chans)]

    c["stats/histogram/RGB"] = hist(rgb)
    c["stats/histogram/L"] = hist(L)
    c["stats/extrema/RGB"] = lambda: [cv2.minMaxLoc(p)[:2] for p in cv2.split(rgb)]

    shapes = src["shapes"]

    def draw(kind: str) -> Callable[[], object]:
        items = shapes[kind]
        if kind == "polygons":
            items = [(np.array(b, np.int32), col) for b, col in items]
        else:
            items = [(tuple(int(v) for v in b), col) for b, col in items]

        def run() -> object:
            canvas = np.zeros((h, w, 3), np.uint8)
            for b, col in items:
                if kind == "polygons":
                    cv2.fillPoly(canvas, [b], col)
                elif kind == "ellipses":
                    center = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
                    axes = ((b[2] - b[0]) // 2, (b[3] - b[1]) // 2)
                    cv2.ellipse(canvas, center, axes, 0, 0, 360, col, -1)
                elif kind == "rectangles":
                    cv2.rectangle(canvas, b[:2], b[2:], col, -1)
                else:
                    cv2.line(canvas, b[:2], b[2:], col, 5)
            return canvas

        return run

    for kind in DRAW_SHAPES:
        c[f"draw/{kind}"] = draw(kind)

    def text() -> object:
        canvas = np.zeros((h, w, 3), np.uint8)
        for i, line in enumerate(src["text"]):
            cv2.putText(canvas, line, (10, 25 + i * 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255))
        return canvas

    c["draw/text"] = text

    enc = src["encoded"]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    params = {
        "jpeg": (".jpg", [cv2.IMWRITE_JPEG_QUALITY, 85]),
        "png": (".png", [cv2.IMWRITE_PNG_COMPRESSION, 6]),
        "webp": (".webp", [cv2.IMWRITE_WEBP_QUALITY, 80]),
    }
    for fmt, (ext, p) in params.items():
        buf = np.frombuffer(enc[fmt], np.uint8)
        c[f"codec/decode/{fmt}"] = lambda buf=buf: cv2.imdecode(buf, cv2.IMREAD_COLOR)
        c[f"codec/encode/{fmt}"] = lambda ext=ext, p=p: cv2.imencode(ext, bgr, p)

    jpeg = np.frombuffer(enc["jpeg"], np.uint8)

    def thumbnail() -> object:
        im = cv2.imdecode(jpeg, cv2.IMREAD_REDUCED_COLOR_8)
        return cv2.resize(im, (320, 200), interpolation=cv2.INTER_AREA)

    c["codec/thumbnail/jpeg"] = thumbnail

    def cycle(level: int) -> Callable[[], object]:
        def run() -> object:
            im = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
            if level > 0:
                im = cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE)
            if level > 1:
                ih, iw = im.shape[:2]
                im = cv2.resize(im, (round(iw * 0.4), round(ih * 0.4)), interpolation=cv2.INTER_AREA)
            if level > 2:
                im = cv2.GaussianBlur(im, (0, 0), 4)
            cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return im

        return run

    for level in range(4):
        c[f"cycle/{level}"] = cycle(level)
    return c
