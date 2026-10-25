#!/usr/bin/env python3
"""Benchmark Pillow builds against each other and against OpenCV, libvips
and ImageMagick, in the spirit of https://python-pillow.org/pillow-perf/.

    perf.py --variant pillow-13.0.0=/opt/variants/pillow-13.0.0 \\
            --variant simd-avx2=/work/variants/simd-avx2 \\
            --lib opencv --lib vips --lib wand --out results.json

Every library runs in its own process, single-threaded, on the same input
images: a 2560x1600 photo-like RGB image (smooth areas with a little noise),
an RGBA version with a soft alpha, L, and the photo as JPEG, PNG and WebP.
The inputs are made once with the first Pillow variant. The libraries take
turns suite by suite for --rounds rounds; in each, a case runs at least
--min-runs times and for --min-time seconds. The fastest run of all rounds
counts. Results are work per second: megapixels of the source image for
image operations, shapes or lines for drawing.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
LIBS = {"opencv": "lib_cv2", "vips": "lib_vips", "wand": "lib_wand"}

# One thread for everyone: Pillow is single-threaded, the others are not by
# default. Set before any of them is imported.
SINGLE_THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENCV_FOR_THREADS_NUM": "1",
    "VIPS_CONCURRENCY": "1",
    "MAGICK_THREAD_LIMIT": "1",
}


# --------------------------------------------------------------- inputs


def prepare(out: Path, size: tuple[int, int]) -> None:
    """Writes the shared inputs with the Pillow on sys.path."""
    import io
    import math

    from common import OUTLINE_SHAPES, ROI_POINTS
    from PIL import Image, ImageChops, ImageFilter

    w, h = size
    rnd = random.Random(1234)
    R = Image.Resampling

    def photo(seed: int) -> Image.Image:
        r = random.Random(seed)
        noise = Image.frombytes("RGB", (w, h), r.randbytes(w * h * 3))
        small = Image.frombytes("RGB", (w // 32, h // 32), r.randbytes(w // 32 * (h // 32) * 3))
        im = small.resize((w, h), R.BICUBIC)
        return ImageChops.add(im, noise.point(lambda v: v // 16), offset=-8)

    rgb, rgb2 = photo(1), photo(2)
    alpha = photo(3).convert("L").filter(ImageFilter.GaussianBlur(4))
    rgba = rgb.copy()
    rgba.putalpha(alpha)
    rgba2 = rgb2.copy()
    rgba2.putalpha(alpha.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
    out.mkdir(parents=True, exist_ok=True)
    for name, im in (("rgb", rgb), ("rgb2", rgb2), ("rgba", rgba), ("rgba2", rgba2), ("l", rgb.convert("L"))):
        (out / f"{name}.raw").write_bytes(im.tobytes())
    for fmt, kw in (("jpeg", {"quality": 90}), ("png", {}), ("webp", {"quality": 90})):
        buf = io.BytesIO()
        rgb.save(buf, fmt.upper(), **kw)
        (out / f"photo.{fmt}").write_bytes(buf.getvalue())

    def color() -> list[int]:
        return [rnd.randrange(256) for _ in range(3)]

    def box(m: int) -> list[float]:
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        return [x, y, x + rnd.uniform(4, m), y + rnd.uniform(4, m)]

    shapes = {
        "polygons": [
            ([(rnd.uniform(0, w), rnd.uniform(0, h)) for _ in range(6)], color()) for _ in range(200)
        ],
        "ellipses": [(box(300), color()) for _ in range(200)],
        "rectangles": [(box(300), color()) for _ in range(500)],
        "lines": [(box(400), color()) for _ in range(500)],
    }
    words = "the quick brown fox jumps over a lazy dog while pillow draws".split()
    text = [" ".join(rnd.choice(words) for _ in range(12)) for _ in range(100)]
    # Outline shapes from their own generator, so the inputs above don't change.
    orn = random.Random(5678)

    def ocolor() -> list[int]:
        return [orn.randrange(256) for _ in range(3)]

    def bbox() -> list[float]:
        bw, bh = orn.uniform(16, 320), orn.uniform(16, 320)
        x, y = orn.uniform(0, w - bw), orn.uniform(0, h - bh)
        return [x, y, x + bw, y + bh]

    def roi() -> list[tuple[float, float]]:
        r = orn.uniform(40, 300)
        cx, cy = orn.uniform(r, w - r), orn.uniform(r, h - r)
        step = 2 * math.pi / ROI_POINTS
        return [
            (
                cx + r * orn.uniform(0.7, 1.0) * math.cos(k * step),
                cy + r * orn.uniform(0.7, 1.0) * math.sin(k * step),
            )
            for k in range(ROI_POINTS)
        ]

    shapes["outline_rectangles"] = [(bbox(), ocolor()) for _ in range(OUTLINE_SHAPES["rectangles"])]
    shapes["outline_polygons"] = [(roi(), ocolor()) for _ in range(OUTLINE_SHAPES["polygons"])]
    (out / "shapes.json").write_text(json.dumps(shapes))
    (out / "text.json").write_text(json.dumps(text))
    (out / "meta.json").write_text(json.dumps({"size": [w, h]}))


def load_inputs(d: Path) -> dict[str, Any]:
    meta = json.loads((d / "meta.json").read_text())
    src: dict[str, Any] = {"size": tuple(meta["size"])}
    for name in ("rgb", "rgb2", "rgba", "rgba2", "l"):
        src[name] = (d / f"{name}.raw").read_bytes()
    src["photo_rgb"] = src["rgb"]
    src["encoded"] = {fmt: (d / f"photo.{fmt}").read_bytes() for fmt in ("jpeg", "png", "webp")}
    shapes = json.loads((d / "shapes.json").read_text())
    src["shapes"] = {
        k: [([tuple(p) for p in b] if k.endswith("polygons") else tuple(b), tuple(c)) for b, c in v]
        for k, v in shapes.items()
    }
    src["text"] = json.loads((d / "text.json").read_text())
    return src


# --------------------------------------------------------------- worker


def timeit(fn: Callable[[], object], min_runs: int, min_time: float, max_time: float) -> dict:
    fn()  # warm up: caches, lazy imports, first-touch allocation
    times: list[float] = []
    total = 0.0
    while len(times) < min_runs or total < min_time:
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        times.append(dt)
        total += dt
        if total > max_time and len(times) >= 3:
            break
    times.sort()
    return {"best": times[0], "median": times[len(times) // 2], "runs": len(times)}


def worker(kind: str, inputs: Path, only: list[str], args: argparse.Namespace) -> dict:
    """Times the cases of one library, of one suite if args.suite is set."""
    sys.path.insert(0, str(HERE))
    from common import META

    mod = __import__("lib_pillow" if kind == "pillow" else LIBS[kind])
    src = load_inputs(inputs)
    if hasattr(mod, "prepare"):
        mod.prepare(src)
    cases = mod.cases(src)
    out: dict[str, Any] = {"version": mod.version(), "results": {}, "notes": {}, "errors": {}}
    notes = getattr(mod, "NOTES", {})
    for cid, fn in cases.items():
        if cid not in META:
            raise KeyError(f"{kind}: unknown case {cid}")
        if only and not any(o in cid for o in only):
            continue
        if args.suite and META[cid]["suite"] != args.suite:
            continue
        try:
            r = timeit(fn, args.min_runs, args.min_time, args.max_time)
        except Exception as e:  # a library that can't do it on this build
            out["errors"][cid] = f"{type(e).__name__}: {e}"
            print(f"  {cid}: {out['errors'][cid]}", file=sys.stderr)
            continue
        out["results"][cid] = r
        # The most specific note applies.
        match = [p for p in notes if cid.startswith(p)]
        if match:
            out["notes"][cid] = notes[max(match, key=len)]
        print(f"  {cid:42} {r['best'] * 1000:9.2f} ms", file=sys.stderr)
    return out


# --------------------------------------------------------------- orchestrator


def machine() -> dict:
    info = {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    try:
        cpu = subprocess.run(["lscpu"], capture_output=True, text=True).stdout
        for line in cpu.splitlines():
            k, _, v = line.partition(":")
            if k.strip() in ("Model name", "Vendor ID", "Flags"):
                info[k.strip()] = v.strip()
    except OSError:
        pass
    try:
        info["gcc"] = subprocess.run(["gcc", "-dumpfullversion"], capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    return info


def run_worker(kind: str, path: str | None, inputs: Path, args: argparse.Namespace, suite: str) -> dict:
    env = dict(os.environ, **SINGLE_THREAD_ENV)
    if path:
        env["PYTHONPATH"] = path
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", kind, "--inputs", str(inputs)]
    cmd += ["--min-runs", str(args.min_runs), "--min-time", str(args.min_time), "--max-time", str(args.max_time)]
    cmd += ["--suite", suite]
    for o in args.only:
        cmd += ["--only", o]
    if args.cpu is not None:
        cmd = ["taskset", "-c", str(args.cpu)] + cmd
    p = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, text=True)
    if p.returncode:
        raise SystemExit(f"{kind} {path or ''} failed")
    return json.loads(p.stdout.strip().splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", action="append", default=[], metavar="NAME=PATH", help="a Pillow build")
    ap.add_argument("--lib", action="append", default=[], choices=sorted(LIBS))
    ap.add_argument("--only", action="append", default=[], help="cases whose id contains this")
    ap.add_argument("--size", default="2560x1600")
    ap.add_argument("--rounds", type=int, default=3, help="interleaved rounds; the best counts")
    ap.add_argument("--min-runs", type=int, default=3)
    ap.add_argument("--min-time", type=float, default=0.2)
    ap.add_argument("--max-time", type=float, default=4.0)
    ap.add_argument("--cpu", type=int, help="pin every worker to this CPU")
    ap.add_argument("--title", help="machine title for the page")
    ap.add_argument("--extra", action="append", default=[], metavar="KEY=VALUE", help="machine info")
    ap.add_argument("--out", required=False)
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    ap.add_argument("--inputs", help=argparse.SUPPRESS)
    ap.add_argument("--prepare", help=argparse.SUPPRESS)
    ap.add_argument("--suite", help=argparse.SUPPRESS)
    args = ap.parse_args()
    size = tuple(int(v) for v in args.size.split("x"))

    if args.prepare:
        prepare(Path(args.prepare), size)
        return 0
    if args.worker:
        print(json.dumps(worker(args.worker, Path(args.inputs), args.only, args)))
        return 0

    variants = [v.split("=", 1) for v in args.variant]
    if not variants:
        ap.error("at least one --variant (the first makes the inputs)")
    with tempfile.TemporaryDirectory() as tmp:
        inputs = Path(tmp)
        env = dict(os.environ, PYTHONPATH=variants[0][1])
        subprocess.run(
            [sys.executable, __file__, "--prepare", tmp, "--size", args.size], env=env, check=True
        )
        sys.path.insert(0, str(HERE))
        from common import SUITES

        # Suite by suite, every library in turn, several rounds: a machine
        # whose clock drifts (thermal limits, power management) then slows
        # every library alike instead of whichever ran during a slow spell.
        workers = [(n, "pillow", p) for n, p in variants] + [(lib, lib, None) for lib in args.lib]
        runs: dict[str, Any] = {}
        for rnd in range(args.rounds):
            for suite, _, _ in SUITES:
                for name, kind, path in workers:
                    print(f"== round {rnd + 1}/{args.rounds} {suite} {name}", file=sys.stderr)
                    r = run_worker(kind, path, inputs, args, suite)
                    run = runs.setdefault(
                        name, {"family": kind, "version": r["version"], "results": {}, "notes": {}, "errors": {}}
                    )
                    run["notes"].update(r["notes"])
                    run["errors"].update(r["errors"])
                    for cid, t in r["results"].items():
                        prev = run["results"].get(cid)
                        if prev is None:
                            run["results"][cid] = dict(t, rounds=[t["best"]])
                        else:
                            prev["rounds"].append(t["best"])
                            prev["runs"] += t["runs"]
                            if t["best"] < prev["best"]:
                                prev["best"], prev["median"] = t["best"], t["median"]

    sys.path.insert(0, str(HERE))
    from common import META, SUITES

    info = machine()
    for kv in args.extra:
        k, _, v = kv.partition("=")
        info[k] = v
    result = {
        "title": args.title or info.get("Model name", platform.machine()),
        "date": time.strftime("%Y-%m-%d"),
        "size": list(size),
        "machine": info,
        "suites": [{"id": s, "title": t, "about": a} for s, t, a in SUITES],
        "cases": META,
        "variants": runs,
    }
    text = json.dumps(result, indent=1)
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
