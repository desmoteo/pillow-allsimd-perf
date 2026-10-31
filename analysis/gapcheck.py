"""Per case: best time and minor page faults per call, for the Pillow on
sys.path and for OpenCV with IPP on and off (x86), plus a copy bandwidth
reference. Usage: gapcheck.py [ID substrings...]"""

import os
import resource
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "bench")]
import cv2  # noqa: E402
import numpy as np  # noqa: E402

import lib_cv2  # noqa: E402
import lib_pillow  # noqa: E402
import perf  # noqa: E402

CASES = [
    "chops/RGB/add",
    "chops/RGB/difference",
    "chops/RGB/lighter",
    "point/RGB/invert",
    "point/L/table",
    "point/RGB/table",
    "transpose/RGB/FLIP_TOP_BOTTOM",
    "transpose/RGB/FLIP_LEFT_RIGHT",
    "transpose/RGB/ROTATE_180",
    "transpose/L/ROTATE_90",
    "convert/RGBA/RGB",
    "convert/RGB/RGBA",
    "convert/L/RGB",
    "convert/RGB/YCbCr",
    "convert/YCbCr/RGB",
    "convert/RGB/HSV",
    "rank/min3/RGB",
    "rank/median3/RGB",
    "reduce/RGB/2",
    "reduce/RGB/4",
    "blur/box/RGB/2",
    "blur/box/RGB/10",
    "blur/gaussian/RGB/1",
    "unsharp/RGB",
    "unsharp/L",
    "composite/blend",
    "filter/RGB/FIND_EDGES",
    "scale/RGB/5478x3424/bilinear",
    "scale/RGBA/5478x3424/bilinear",
    "scale/RGBA/5478x3424/bicubic",
    "scale/RGB/320x200/lanczos",
    "rotate/RGB/30/bilinear",
    "rotate/RGB/30/bicubic",
    "rotate/RGB/perspective/bilinear",
    "draw/text",
    "draw/polygons",
    "draw/ellipses",
]


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


def main():
    only = sys.argv[1:]
    cases = [c for c in CASES if not only or any(o in c for o in only)]
    d = Path(tempfile.mkdtemp())
    perf.prepare(d, (2560, 1600))
    src = perf.load_inputs(d)
    for mod in (lib_pillow, lib_cv2):
        if hasattr(mod, "prepare"):
            mod.prepare(src)
    pil = lib_pillow.cases(src)
    cv = lib_cv2.cases(src)
    a = np.frombuffer(src["rgba"], np.uint8).copy()
    b = np.empty_like(a)
    t, _ = measure(lambda: np.copyto(b, a), 30)
    print(f"copy 16 MB into an existing buffer: {t:.2f} ms = {2 * a.nbytes / t / 1e6:.1f} GB/s (read+write)")
    t, flt = measure(lambda: a.copy(), 30)
    print(f"copy 16 MB into a new array: {t:.2f} ms, {flt:.0f} faults/call")
    has_ipp = hasattr(cv2, "ipp") and cv2.ipp.useIPP()
    print(f"OpenCV {cv2.__version__}, IPP {'on' if has_ipp else 'absent'}")
    print(f"{'case':36} {'pillow ms':>9} {'flt':>6} {'cv ms':>8} {'flt':>6}" + (f" {'cv noIPP':>9}" if has_ipp else ""))
    for c in cases:
        row = f"{c:36}"
        if c in pil:
            t, flt = measure(pil[c])
            row += f" {t:9.2f} {flt:6.0f}"
        else:
            row += f" {'-':>9} {'':>6}"
        if c in cv:
            if has_ipp:
                cv2.ipp.setUseIPP(True)
            t, flt = measure(cv[c])
            row += f" {t:8.2f} {flt:6.0f}"
            if has_ipp:
                cv2.ipp.setUseIPP(False)
                t2, _ = measure(cv[c])
                cv2.ipp.setUseIPP(True)
                row += f" {t2:9.2f}" + ("  <- IPP" if t2 > t * 1.15 else "")
        print(row, flush=True)


main()
