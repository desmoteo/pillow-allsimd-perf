"""Where the drawing cases spend their time: polygons at full size and
scaled down (fill against setup), lines 1 and 5 px wide, text and its parts,
and a profile of text drawing, for the Pillow on sys.path."""

import cProfile
import io
import os
import pstats
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "bench")]
import perf  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

d = Path(tempfile.mkdtemp())
perf.prepare(d, (2560, 1600))
src = perf.load_inputs(d)
w, h = src["size"]
shapes = src["shapes"]
lines = src["text"]
font = ImageFont.load_default(24)


def best(fn, n=15):
    fn()
    t = 1e9
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        t = min(t, time.perf_counter() - t0)
    return t * 1e3


canvas = Image.new("RGB", (w, h))
print(f"Image.new RGB             {best(lambda: Image.new('RGB', (w, h))):7.2f} ms")


def poly():
    dr = ImageDraw.Draw(canvas)
    for b, c in shapes["polygons"]:
        dr.polygon(b, fill=c)


def lines5():
    dr = ImageDraw.Draw(canvas)
    for b, c in shapes["lines"]:
        dr.line(b, fill=c, width=5)


def lines1():
    dr = ImageDraw.Draw(canvas)
    for b, c in shapes["lines"]:
        dr.line(b, fill=c, width=1)


def text():
    dr = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        dr.text((10, 10 + i * 15), line, fill=(255, 255, 255), font=font)


def text_mask_only():
    for line in lines:
        font.getmask2(line, "L")


def text_bbox_only():
    for line in lines:
        font.getbbox(line)


# the same polygons, but tiny (fill cost removed): Python + edge setup
small = [([(x / 40, y / 40) for x, y in b], c) for b, c in shapes["polygons"]]


def poly_small():
    dr = ImageDraw.Draw(canvas)
    for b, c in small:
        dr.polygon(b, fill=c)


area = 0
for name, fn in (
    ("polygons (200 hexagons)", poly),
    ("polygons scaled 1/40", poly_small),
    ("lines 5px (500)", lines5),
    ("lines 1px (500)", lines1),
    ("text (100 lines)", text),
    ("  font.getmask2 x100", text_mask_only),
    ("  font.getbbox x100", text_bbox_only),
):
    print(f"{name:26} {best(fn):7.2f} ms")
pr = cProfile.Profile()
pr.enable()
for _ in range(20):
    text()
pr.disable()
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(8)
print(s.getvalue()[-2200:])
