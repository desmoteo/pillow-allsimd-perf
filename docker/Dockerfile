# Benchmark image: the competing libraries and the released Pillow builds.
# The Pillow-AllSIMD builds of the branch under test are compiled at run time
# (run.sh), so this image only changes when a library version changes.
FROM python:3.12-slim-trixie

ARG PILLOW_VERSION=13.0.0
ARG PILLOW_SIMD_VERSION=12.1.1.post0
ARG PILLOW_SIMD_URL=https://files.pythonhosted.org/packages/b4/c6/21b1536f2f4b7cdea88ac4ddccfc779062774dea8169b5aeae9cfc25fb2d/pillow_simd-12.1.1.post0.tar.gz
ARG PILLOW_SIMD_SHA256=8e9694ec94c59d12f16753cbf48a3080266bdd704b0c51a630318c7a325625b1

ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Compilers and the image libraries Pillow builds against; libvips and
# ImageMagick for pyvips and Wand; util-linux for taskset.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config curl ca-certificates util-linux \
        libjpeg62-turbo-dev zlib1g-dev libpng-dev libtiff-dev libwebp-dev \
        libfreetype-dev liblcms2-dev libopenjp2-7-dev \
        libvips-dev libmagickwand-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir \
        numpy opencv-python-headless pyvips Wand \
        setuptools wheel pybind11

# Upstream Pillow as published (manylinux wheel, its own bundled codecs).
RUN python3 -m pip install --no-cache-dir --no-deps --only-binary :all: \
        --target /opt/variants/pillow-${PILLOW_VERSION} "Pillow==${PILLOW_VERSION}"

# The last Pillow-SIMD release, x86 only: its setup.py always adds -msse4.
RUN if [ "$(uname -m)" = x86_64 ]; then \
        set -e; cd /tmp; \
        curl -fsSL -o simd.tar.gz "$PILLOW_SIMD_URL"; \
        echo "$PILLOW_SIMD_SHA256  simd.tar.gz" | sha256sum -c; \
        tar -xzf simd.tar.gz; cd pillow_simd-*; \
        python3 -m pip install --no-cache-dir --no-deps --no-build-isolation \
            --target /opt/variants/pillow-simd-${PILLOW_SIMD_VERSION}-sse4 .; \
        rm -rf build; \
        CC="cc -mavx2" python3 -m pip install --no-cache-dir --no-deps \
            --no-build-isolation \
            --target /opt/variants/pillow-simd-${PILLOW_SIMD_VERSION}-avx2 .; \
        cd /; rm -rf /tmp/*; \
    fi

WORKDIR /work
