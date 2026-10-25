"""Where blur and resize time goes: each pass alone, and the whole, for the
Pillow on sys.path (2560x1600 inputs as in perf.py)."""

import os
import resource
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "bench")]
from PIL import Image, ImageFilter  # noqa: E402

import perf  # noqa: E402


def measure(fn, runs=15):
    fn()
    best = float("inf")
    f0 = resource.getrusage(resource.RUSAGE_SELF).ru_minflt
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    f1 = resource.getrusage(resource.RUSAGE_SELF).ru_minflt
    return best * 1e3, (f1 - f0) / runs


d = Path(tempfile.mkdtemp())
perf.prepare(d, (2560, 1600))
src = perf.load_inputs(d)
w, h = src["size"]
rgb = Image.frombytes("RGB", (w, h), src["rgb"])
rgba = Image.frombytes("RGBA", (w, h), src["rgba"])
L = rgb.convert("L")
R = Image.Resampling
cases = {
    "new image RGB (dirty)": lambda: Image.core.new("RGB", (w, h)),
    "copy RGB": lambda: rgb.copy(),
    "box r2 h+v": lambda: rgb.filter(ImageFilter.BoxBlur(2)),
    "box r2 h only": lambda: rgb.filter(ImageFilter.BoxBlur((2, 0))),
    "box r2 v only": lambda: rgb.filter(ImageFilter.BoxBlur((0, 2))),
    "box r10 h+v": lambda: rgb.filter(ImageFilter.BoxBlur(10)),
    "box r10 h only": lambda: rgb.filter(ImageFilter.BoxBlur((10, 0))),
    "box r10 v only": lambda: rgb.filter(ImageFilter.BoxBlur((0, 10))),
    "gauss r1 h+v": lambda: rgb.filter(ImageFilter.GaussianBlur(1)),
    "gauss r1 h only": lambda: rgb.filter(ImageFilter.GaussianBlur((1, 0))),
    "gauss r1 v only": lambda: rgb.filter(ImageFilter.GaussianBlur((0, 1))),
    "resize RGB up bilinear": lambda: rgb.resize((5478, 3424), R.BILINEAR),
    "resize RGB up bilinear h only": lambda: rgb.resize((5478, h), R.BILINEAR),
    "resize RGB up bilinear v only": lambda: rgb.resize((w, 3424), R.BILINEAR),
    "resize RGBA up bilinear": lambda: rgba.resize((5478, 3424), R.BILINEAR),
    "RGBA premultiply (RGBa)": lambda: rgba.convert("RGBa"),
    "RGBa unpremultiply": lambda: rgba.convert("RGBa").convert("RGBA"),
    "resize RGB 320x200 lanczos": lambda: rgb.resize((320, 200), R.LANCZOS),
    "resize RGB 320x200 lanczos h only": lambda: rgb.resize((320, h), R.LANCZOS),
    "resize RGB 320x200 lanczos v only": lambda: rgb.resize((w, 200), R.LANCZOS),
}
only = sys.argv[1:]
for name, fn in cases.items():
    if only and not any(o in name for o in only):
        continue
    t, flt = measure(fn)
    print(f"{name:38} {t:8.2f} ms {flt:7.0f} faults", flush=True)
