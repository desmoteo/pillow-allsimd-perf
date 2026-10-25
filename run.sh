#!/usr/bin/env bash
# Runs the benchmark on this machine or on a remote one over SSH, in Docker.
#
# Usage: ./run.sh [options] local|[user@]HOST
#
#   --simd-repo DIR   pillow-simd checkout to build (default: ../pillow-simd)
#   --ref REF         commit of it to build (default: HEAD)
#   --name NAME       results/NAME.json (default: the host name)
#   --title TITLE     machine title on the page
#   --cpu N           CPU to pin the container to (default: 2)
#   --only TEXT       only cases whose id contains TEXT (repeatable)
#   --size WxH        image size (default: 2560x1600)
#   --keep            keep the remote working directory
#
# Needs docker (or podman) on the target, and network access there for the
# first image build. The image holds the other libraries and the released
# Pillow builds; the pillow-simd builds of REF are compiled in the container
# on every run, so it's the commit that is measured, not a stale build.

set -euo pipefail
cd "$(dirname "$0")"

SIMD_REPO=../pillow-simd REF=HEAD NAME="" TITLE="" CPU=2 SIZE=2560x1600 KEEP=0 TARGET=""
ONLY=()
while [ $# -gt 0 ]; do
    case "$1" in
        --simd-repo) SIMD_REPO=$2; shift 2 ;;
        --ref) REF=$2; shift 2 ;;
        --name) NAME=$2; shift 2 ;;
        --title) TITLE=$2; shift 2 ;;
        --cpu) CPU=$2; shift 2 ;;
        --only) ONLY+=("--only" "$2"); shift 2 ;;
        --size) SIZE=$2; shift 2 ;;
        --keep) KEEP=1; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        -*) echo "unknown option $1" >&2; exit 2 ;;
        *) TARGET=$1; shift ;;
    esac
done
[ -n "$TARGET" ] || { sed -n '2,20p' "$0"; exit 2; }

COMMIT=$(git -C "$SIMD_REPO" rev-parse --short "$REF")
BRANCH=$(git -C "$SIMD_REPO" rev-parse --abbrev-ref "$REF" 2>/dev/null || echo "$REF")
[ "$BRANCH" = HEAD ] && BRANCH=$(git -C "$SIMD_REPO" rev-parse --abbrev-ref HEAD)
[ -n "$NAME" ] || NAME=$([ "$TARGET" = local ] && hostname -s || echo "${TARGET#*@}")

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/run"
cp -r docker bench "$STAGE/run/"
git -C "$SIMD_REPO" archive --prefix=simd-src/ "$REF" | tar -x -C "$STAGE/run"

# What runs in the container: build the branch, then benchmark everything.
cat > "$STAGE/run/inside.sh" <<EOF
set -euo pipefail
cd /work
builds=(disable)
if [ "\$(uname -m)" = x86_64 ]; then
    builds+=(sse4 avx2)
    grep -qw avx_vnni /proc/cpuinfo && builds+=(avxvnni)
else
    builds+=(neon)
fi
variants=(--variant pillow-13.0.0=/opt/variants/pillow-13.0.0)
for d in /opt/variants/pillow-simd-*; do
    [ -d "\$d" ] && variants+=(--variant "\$(basename "\$d")=\$d")
done
for b in "\${builds[@]}"; do
    name=branch-\$([ \$b = disable ] && echo scalar || echo \$b)
    echo "==> building \$name" >&2
    rm -rf simd-src/build
    (cd simd-src && python3 -m pip install -q --no-deps --no-build-isolation \
        -C simd=\$b --target /work/variants/\$name . >/work/build-\$name.log 2>&1) \
        || { tail -20 /work/build-\$name.log; exit 1; }
    variants+=(--variant "\$name=/work/variants/\$name")
done
python3 bench/perf.py "\${variants[@]}" --lib opencv --lib vips --lib wand \
    --size $SIZE --title "$TITLE" --extra "branch=$BRANCH" --extra "commit=$COMMIT" \
    ${ONLY[@]+"${ONLY[@]}"} --out /work/results.json
EOF

engine_run() {
    # \$1: directory holding run/; runs the build and the benchmark there.
    local dir=$1
    echo "cd $dir/run && E=\$(command -v docker || command -v podman) &&
        \$E build -q -t pillow-simd-perf docker >/dev/null &&
        \$E run --rm --cpuset-cpus=$CPU --user \$(id -u):\$(id -g) -e HOME=/tmp -v \"\$PWD:/work:Z\" pillow-simd-perf bash inside.sh"
}

mkdir -p results
if [ "$TARGET" = local ]; then
    bash -c "$(engine_run "$STAGE")"
    cp "$STAGE/run/results.json" "results/$NAME.json"
else
    REMOTE_DIR="pillow-simd-perf-run"
    ssh "$TARGET" "rm -rf $REMOTE_DIR && mkdir -p $REMOTE_DIR"
    tar -C "$STAGE" -cf - run | ssh "$TARGET" "tar -x -C $REMOTE_DIR"
    ssh "$TARGET" "$(engine_run "\$HOME/$REMOTE_DIR")"
    scp -q "$TARGET:$REMOTE_DIR/run/results.json" "results/$NAME.json"
    [ $KEEP = 1 ] || ssh "$TARGET" "rm -rf $REMOTE_DIR"
fi
echo "==> results/$NAME.json ($BRANCH @ $COMMIT)"
