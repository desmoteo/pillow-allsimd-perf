"""Speed and accuracy of Pillow's kernels and of OpenCV's accurate and
approximate (ALGO_HINT_APPROX) paths, against float64 references of the same
mathematical operation, on the perf.py photo (2560x1600).

Errors are in 8-bit levels against the reference rounded to the nearest
integer, over the image interior (borders excluded, the libraries' edge
conventions differ): max, mean absolute, and the share of values that differ.
Usage: accuracy.py [case substrings...]
"""

import os
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "bench")]
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

import perf  # noqa: E402

cv2.setNumThreads(1)
ACC, APPROX = cv2.ALGO_HINT_ACCURATE, cv2.ALGO_HINT_APPROX
B = 24  # border excluded from the error statistics


def best(fn, runs=7):
    fn()
    t = float("inf")
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        t = min(t, time.perf_counter() - t0)
    return t * 1e3


def err(out, ref, circular=None):
    out = np.asarray(out, np.float64)[B:-B, B:-B]
    ref = np.asarray(ref, np.float64)[B:-B, B:-B]
    d = np.abs(out - np.floor(ref + 0.5))
    if circular:
        d = np.minimum(d, circular - d)
    return f"max {d.max():3.0f}  mean {d.mean():.3f}  differ {100 * (d > 0).mean():5.1f}%"


def row(name, ms, e):
    print(f"  {name:34} {ms:8.2f} ms   {e}", flush=True)


def gauss_kernel(sigma, radius):
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-(x * x) / (2 * sigma * sigma))
    return k / k.sum()


def sep_conv(a, k):
    """Separable float64 convolution, edges clamped."""
    r = len(k) // 2
    p = np.pad(a, ((r, r), (r, r), (0, 0)), mode="edge")
    h = sum(k[i] * p[:, i : i + a.shape[1]] for i in range(len(k)))
    return sum(k[i] * h[i : i + a.shape[0]] for i in range(len(k)))


def bilinear(src, x, y):
    """float64 bilinear samples of src (H, W, C) at pixel coordinates x, y
    (integers at pixel centres), edges clamped."""
    h, w = src.shape[:2]
    x = np.clip(x, 0, w - 1)
    y = np.clip(y, 0, h - 1)
    x0 = np.minimum(np.floor(x).astype(np.int64), w - 2)
    y0 = np.minimum(np.floor(y).astype(np.int64), h - 2)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    s = src.astype(np.float64)
    top = s[y0, x0] * (1 - fx) + s[y0, x0 + 1] * fx
    bot = s[y0 + 1, x0] * (1 - fx) + s[y0 + 1, x0 + 1] * fx
    return top * (1 - fy) + bot * fy


def main():
    only = sys.argv[1:]

    def want(name):
        return not only or any(o in name for o in only)

    d = Path(tempfile.mkdtemp())
    perf.prepare(d, (2560, 1600))
    src = perf.load_inputs(d)
    w, h = src["size"]
    rgb = np.frombuffer(src["rgb"], np.uint8).reshape(h, w, 3).copy()
    im = Image.frombytes("RGB", (w, h), src["rgb"])
    print(f"OpenCV {cv2.__version__}, default hint {cv2.getDefaultAlgorithmHint()}")

    if want("gaussian"):
        for sigma in (1, 2):
            ref = sep_conv(rgb.astype(np.float64), gauss_kernel(sigma, 4 * sigma))
            print(f"Gaussian sigma {sigma} (reference: true Gaussian, radius {4 * sigma})")
            row(
                "Pillow GaussianBlur",
                best(lambda: im.filter(ImageFilter.GaussianBlur(sigma))),
                err(np.asarray(im.filter(ImageFilter.GaussianBlur(sigma))), ref),
            )
            for name, hint in (("OpenCV accurate", ACC), ("OpenCV approx", APPROX)):
                f = lambda hint=hint: cv2.GaussianBlur(rgb, (0, 0), sigma, hint=hint)  # noqa: E731
                row(name, best(f), err(f(), ref))

    if want("box"):
        ref = sep_conv(rgb.astype(np.float64), np.full(5, 0.2))
        print("Box 5x5 (reference: exact mean)")
        row(
            "Pillow BoxBlur(2)",
            best(lambda: im.filter(ImageFilter.BoxBlur(2))),
            err(np.asarray(im.filter(ImageFilter.BoxBlur(2))), ref),
        )
        row("OpenCV blur", best(lambda: cv2.blur(rgb, (5, 5))), err(cv2.blur(rgb, (5, 5)), ref))

    if want("ycbcr"):
        f = rgb.astype(np.float64)
        R, G, Bc = f[..., 0], f[..., 1], f[..., 2]
        ref = np.stack(
            [
                0.299 * R + 0.587 * G + 0.114 * Bc,
                128 - 0.168736 * R - 0.331264 * G + 0.5 * Bc,
                128 + 0.5 * R - 0.418688 * G - 0.081312 * Bc,
            ],
            -1,
        )
        ref = np.clip(ref, 0, 255)
        print("RGB -> YCbCr (reference: JPEG full-range BT.601 in float)")
        row("Pillow convert('YCbCr')", best(lambda: im.convert("YCbCr")), err(np.asarray(im.convert("YCbCr")), ref))
        for name, hint in (("OpenCV accurate", ACC), ("OpenCV approx", APPROX)):
            fn = lambda hint=hint: cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb, hint=hint)  # noqa: E731
            row(name, best(fn), err(fn()[..., [0, 2, 1]], ref))
        # and back, from Pillow's YCbCr
        ycc = np.asarray(im.convert("YCbCr")).astype(np.float64)
        Y, Cb, Cr = ycc[..., 0], ycc[..., 1] - 128, ycc[..., 2] - 128
        ref2 = np.clip(np.stack([Y + 1.402 * Cr, Y - 0.344136 * Cb - 0.714136 * Cr, Y + 1.772 * Cb], -1), 0, 255)
        yim = im.convert("YCbCr")
        ycrcb = np.ascontiguousarray(np.asarray(yim)[..., [0, 2, 1]])
        print("YCbCr -> RGB (reference: JPEG inverse in float)")
        row("Pillow convert('RGB')", best(lambda: yim.convert("RGB")), err(np.asarray(yim.convert("RGB")), ref2))
        for name, hint in (("OpenCV accurate", ACC), ("OpenCV approx", APPROX)):
            fn = lambda hint=hint: cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB, hint=hint)  # noqa: E731
            row(name, best(fn), err(fn(), ref2))

    if want("hsv"):
        f = rgb.astype(np.float64) / 255
        mx, mn = f.max(-1), f.min(-1)
        diff = mx - mn
        safe = np.where(diff == 0, 1, diff)
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        hh = np.where(mx == r, (g - b) / safe, np.where(mx == g, 2 + (b - r) / safe, 4 + (r - g) / safe))
        hh = np.where(diff == 0, 0, (hh / 6) % 1.0)
        s = np.where(mx == 0, 0, diff / np.where(mx == 0, 1, mx))
        ref = np.stack([hh * 255, s * 255, mx * 255], -1)
        print("RGB -> HSV, hue in 0..255 (reference: colorsys in float; hue error is circular)")
        out = np.asarray(im.convert("HSV")).astype(np.float64)
        e_h = err(out[..., :1], ref[..., :1], circular=256)
        row("Pillow convert('HSV') hue", best(lambda: im.convert("HSV")), e_h)
        row("Pillow convert('HSV') sat, val", 0, err(out[..., 1:], ref[..., 1:]))
        cvo = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float64)
        row(
            "OpenCV HSV_FULL hue",
            best(lambda: cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL)),
            err(cvo[..., :1], ref[..., :1], circular=256),
        )
        row("OpenCV HSV_FULL sat, val", 0, err(cvo[..., 1:], ref[..., 1:]))

    if want("resize"):
        W, H = 5478, 3424
        xs = (np.arange(W) + 0.5) * w / W - 0.5
        ys = (np.arange(H) + 0.5) * h / H - 0.5
        X, Y = np.meshgrid(xs, ys)
        ref = bilinear(rgb, X, Y)
        print(f"Bilinear upscale RGB to {W}x{H} (reference: float bilinear)")
        R_ = Image.Resampling
        row(
            "Pillow resize BILINEAR",
            best(lambda: im.resize((W, H), R_.BILINEAR), 3),
            err(np.asarray(im.resize((W, H), R_.BILINEAR)), ref),
        )
        row(
            "OpenCV INTER_LINEAR",
            best(lambda: cv2.resize(rgb, (W, H), interpolation=cv2.INTER_LINEAR), 3),
            err(cv2.resize(rgb, (W, H), interpolation=cv2.INTER_LINEAR), ref),
        )
        rgba = np.frombuffer(src["rgba"], np.uint8).reshape(h, w, 4).copy()
        opaque = rgba.copy()
        opaque[..., 3] = 255
        ref4 = bilinear(opaque, X, Y)
        op_im = Image.fromarray(opaque, "RGBA")
        print(f"Bilinear upscale opaque RGBA to {W}x{H} (Carotene on arm64)")
        row(
            "Pillow resize BILINEAR",
            best(lambda: op_im.resize((W, H), R_.BILINEAR), 3),
            err(np.asarray(op_im.resize((W, H), R_.BILINEAR)), ref4),
        )
        row(
            "OpenCV INTER_LINEAR",
            best(lambda: cv2.resize(opaque, (W, H), interpolation=cv2.INTER_LINEAR), 3),
            err(cv2.resize(opaque, (W, H), interpolation=cv2.INTER_LINEAR), ref4),
        )

    if want("warp"):
        # Rotation by 30 degrees about the centre, given as the inverse map
        # (output -> input) so that both libraries use the same coordinates.
        a = np.deg2rad(30)
        c, s_ = np.cos(a), np.sin(a)
        cx, cy = w / 2, h / 2
        # input = R^-1 (output - centre) + centre, in continuous coordinates
        inv = np.array([[c, s_, cx - c * cx - s_ * cy], [-s_, c, cy + s_ * cx - c * cy]])
        X, Y = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
        # OpenCV: integer pixel coordinates are pixel centres
        xi = inv[0, 0] * X + inv[0, 1] * Y + inv[0, 2]
        yi = inv[1, 0] * X + inv[1, 1] * Y + inv[1, 2]
        inside = (xi >= 1) & (xi <= w - 2) & (yi >= 1) & (yi <= h - 2)
        ref_cv = bilinear(rgb, xi, yi)
        # Pillow: output pixel centre (x + 0.5) maps to the input, sampled at -0.5
        xp = inv[0, 0] * (X + 0.5) + inv[0, 1] * (Y + 0.5) + inv[0, 2] - 0.5
        yp = inv[1, 0] * (X + 0.5) + inv[1, 1] * (Y + 0.5) + inv[1, 2] - 0.5
        ref_pil = bilinear(rgb, xp, yp)
        data = (inv[0, 0], inv[0, 1], inv[0, 2], inv[1, 0], inv[1, 1], inv[1, 2])
        mask = inside[..., None]
        print("Rotate 30 degrees, bilinear (reference: float bilinear of the same map; inside only)")
        pil = lambda: im.transform((w, h), Image.Transform.AFFINE, data, Image.Resampling.BILINEAR)  # noqa: E731
        row(
            "Pillow transform AFFINE",
            best(pil, 3),
            err(np.where(mask, np.asarray(pil()), 0), np.where(mask, ref_pil, 0)),
        )
        for name, hint in (("OpenCV accurate", ACC), ("OpenCV approx", APPROX)):
            fn = lambda hint=hint: cv2.warpAffine(  # noqa: E731
                rgb, inv, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, hint=hint
            )
            row(name, best(fn, 3), err(np.where(mask, fn(), 0), np.where(mask, ref_cv, 0)))


if __name__ == "__main__":
    main()
