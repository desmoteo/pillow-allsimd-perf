"""Fast-mode Gaussian blur against the exact one for a range of sigmas: times,
the largest and mean difference, and both errors against a true Gaussian
(accuracy.py's reference), on the perf.py photo, for the Pillow on sys.path
(a pillow-simd build with fast mode)."""

import os
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "bench")]
import numpy as np  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

import accuracy as A  # noqa: E402
import perf  # noqa: E402


def best(fn, runs=7):
    fn()
    t = float("inf")
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        t = min(t, time.perf_counter() - t0)
    return t * 1e3


def main():
    d = Path(tempfile.mkdtemp())
    perf.prepare(d, (2560, 1600))
    src = perf.load_inputs(d)
    w, h = src["size"]
    im = Image.frombytes("RGB", (w, h), src["rgb"])
    rgb = np.asarray(im)
    print(f"{'sigma':>5} {'exact ms':>9} {'fast ms':>8}  fast-exact max/mean   exact vs ref           fast vs ref")
    for s in (0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10):
        flt = ImageFilter.GaussianBlur(s)
        Image.set_fast(False)
        te = best(lambda: im.filter(flt))
        ex = np.asarray(im.filter(flt)).astype(int)
        Image.set_fast(True)
        tf = best(lambda: im.filter(flt))
        fa = np.asarray(im.filter(flt)).astype(int)
        Image.set_fast(False)
        dd = np.abs(fa - ex)[24:-24, 24:-24]
        e1 = e2 = "-"
        if s <= 4:
            ref = A.sep_conv(rgb.astype(np.float64), A.gauss_kernel(s, int(np.ceil(4 * s))))
            e1, e2 = A.err(ex, ref), A.err(fa, ref)
        print(f"{s:5} {te:9.2f} {tf:8.2f}  {dd.max():3d} / {dd.mean():.3f}   {e1:24} {e2}", flush=True)


main()
