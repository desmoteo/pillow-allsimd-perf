"""libvips gaussblur against the same float references as accuracy.py, on the
perf.py photo, with its vector path on or off (VIPS_NOVECTOR=1)."""

import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "bench")]
import numpy as np  # noqa: E402
import pyvips  # noqa: E402

import accuracy as A  # noqa: E402
import perf  # noqa: E402

pyvips.cache_set_max(0)
d = Path(tempfile.mkdtemp())
perf.prepare(d, (2560, 1600))
src = perf.load_inputs(d)
w, h = src["size"]
rgb = np.frombuffer(src["rgb"], np.uint8).reshape(h, w, 3).copy()
vim = pyvips.Image.new_from_memory(src["rgb"], w, h, 3, "uchar")


def run(im):
    return np.ndarray(buffer=im.write_to_memory(), dtype=np.uint8, shape=(im.height, im.width, im.bands))


version = ".".join(str(pyvips.version(i)) for i in range(3))
print(f"libvips {version}, vector path {'off' if os.environ.get('VIPS_NOVECTOR') else 'on'}")
for sigma in (1, 2):
    ref = A.sep_conv(rgb.astype(np.float64), A.gauss_kernel(sigma, 4 * sigma))
    print(f"Gaussian sigma {sigma}")
    for name, kw in (
        ("gaussblur default (min_ampl 0.2)", {}),
        ("gaussblur min_ampl 0.01", {"min_ampl": 0.01}),
        ("gaussblur float precision", {"precision": "float"}),
    ):
        fn = lambda kw=kw: run(vim.gaussblur(sigma, **kw).rint().cast("uchar"))  # noqa: E731
        A.row(name, A.best(fn), A.err(fn(), ref))
