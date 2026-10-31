# Pillow-SIMD performance

Benchmarks of [Pillow-SIMD](https://github.com/desmoteo/pillow-simd) against
Pillow, the last Pillow-SIMD release, OpenCV, libvips and ImageMagick on x86-64
and arm64, in the spirit of [pillow-perf](https://python-pillow.org/pillow-perf/).

Results: **https://desmoteo.github.io/pillow-simd-perf/**

## What is compared

| Build | x86-64 | arm64 |
|---|---|---|
| Pillow 13.0.0 (PyPI wheel) | yes | yes |
| Pillow-SIMD 12.1.1.post0 (last release), SSE4 and AVX2 | yes | no, it has no arm64 code |
| Pillow-SIMD 13 (`simd/pillow-13`), scalar, SSE4, AVX2, AVX-VNNI | yes, AVX-VNNI if the CPU has it | |
| Pillow-SIMD 13 (`simd/pillow-13`), scalar and NEON | | yes |
| OpenCV (opencv-python-headless) | yes | yes |
| libvips (Debian, through pyvips) | yes | yes |
| ImageMagick 7 (Debian, through Wand) | yes | yes |

111 cases in 18 suites:
- pillow-perf's: resize, blur, kernel filters, conversion, composition, right-angle rotation, colour LUT, load and save, and the full cycle.
- Extended with reduce, unsharp mask, rank filters, arbitrary rotation and perspective, point operations, channel arithmetic, statistics, quantization and drawing (filled shapes, wide lines, text, and unfilled outlines as overlays draw them: bounding boxes and ROI polygons).

Every library runs single-threaded on the same 2560x1600 inputs.

## Running

Docker (or Podman) is the only requirement on the machine that runs the benchmark.

```bash
git clone https://github.com/desmoteo/pillow-simd
git clone https://github.com/desmoteo/pillow-simd-perf
git -C pillow-simd checkout simd/pillow-13
cd pillow-simd-perf
./run.sh local                        # this machine, CPU 2
./run.sh --cpu 2 user@arm64-host      # a remote machine over SSH
./run.sh --only scale/RGB local       # a subset
python3 tools/publish.py              # results/*.json -> docs/data/
python3 -m http.server -d docs        # look at the page
```

`run.sh` builds the image in `docker/` once. Each run then compiles the chosen
pillow-simd commit (`--ref`, default `HEAD`) in the container and runs
`bench/perf.py`, which writes `results/<name>.json`.

## Layout

- `bench/common.py`: the case catalogue, with ids, titles and units.
- `bench/lib_pillow.py`, `lib_cv2.py`, `lib_vips.py`, `lib_wand.py`: each library's implementation of the cases it has. Notes explain where an operation differs from Pillow's.
- `bench/perf.py`: makes the inputs, times each case in one process per build or library, and writes the JSON.
- `docker/Dockerfile`: the libraries and the released Pillow builds.
- `docs/`: the GitHub Pages site, plain HTML and JavaScript.
