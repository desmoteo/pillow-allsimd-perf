# Analysis scripts

Measurements behind pillow-simd's `PERFORMANCE_GAPS.md` and
`OTHER_LIBRARIES_KERNELS.md`: where the time goes in the cases other libraries
win, and how accurate each library's kernels are. They use the same inputs as
`bench/perf.py` (the 2560x1600 photo-like image) and the same modules.

| Script | What it prints |
|---|---|
| `gapcheck.py [ids]` | per case: best time and minor page faults per call for the Pillow on `sys.path` and for OpenCV, and OpenCV with IPP off (x86); a copy bandwidth reference |
| `parts.py [names]` | blur and resize split into their passes (horizontal only, vertical only, both), premultiply and unpremultiply |
| `accuracy.py [names]` | time and error against float64 references of the same operation (Gaussian, box, YCbCr both ways, HSV, bilinear upscale, rotation) for Pillow and for OpenCV with `ALGO_HINT_ACCURATE` and `ALGO_HINT_APPROX` |
| `vipsacc.py` | libvips `gaussblur` against the same references, with its vector path on, or off with `VIPS_NOVECTOR=1` |
| `gaussfast.py` | pillow-simd's fast-mode Gaussian against the exact one, sigma 0.5 to 10: times, difference, error against a true Gaussian |
| `drawprof.py` | the drawing cases split: polygons at full size and scaled down, lines 1 and 5 px wide, text and its parts, a profile of text drawing |

Errors are in 8-bit levels against the reference rounded to the nearest
integer, over the interior of the image: the maximum, the mean absolute error
and the share of values that differ.

Run them in the benchmark image with a pillow-simd build on `PYTHONPATH`, one
CPU, as the published runs do:

```bash
# a build of the pillow-simd checkout, in the image's Python
docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD/../pillow-simd:/src:ro \
    -v /tmp/build:/build pillow-simd-perf sh -c \
    'cp -r /src /tmp/s && cd /tmp/s && python3 -m pip install -q --no-deps \
     --no-build-isolation -C simd=avx2 --target /build .'
docker run --rm --cpuset-cpus=2 --user $(id -u):$(id -g) -e HOME=/tmp \
    -v $PWD:/perf:ro -v /tmp/build:/build:ro -e PYTHONPATH=/build \
    pillow-simd-perf python3 /perf/analysis/accuracy.py
```

`results-2026-10-31/` holds the outputs the documents quote. x86: the Intel
Core Ultra 9 285H (performance profile, turbo off), AVX2 builds of
d9203c783 (`gapcheck`, `parts`) and 28b55224b (`accuracy`, `vipsacc`,
`drawprof`), which differ only in the kernel filters. arm64: the Jetson
Orin, the NEON build of 28b55224b.
