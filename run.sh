#!/usr/bin/env bash
# Runs the benchmark on this machine or on a remote one over SSH, in Docker.
#
# Usage: ./run.sh [options] local|[user@]HOST
#
#   --simd-repo DIR   Pillow-AllSIMD checkout to build (default: ../pillow-allsimd,
#                     or ../pillow-simd, its former name)
#   --ref REF         commit of it to build (default: HEAD)
#   --name NAME       results/NAME.json (default: the host name)
#   --title TITLE     machine title on the page
#   --cpu N           CPU to pin the container to (default: 2)
#   --only TEXT       only cases whose id contains TEXT (repeatable)
#   --size WxH        image size (default: 2560x1600)
#   --rounds N        interleaved rounds; the fastest run of all counts (default: 3)
#   --keep            keep the remote working directory
#   --detach          start the remote run in the background on the host
#                     (it survives this machine going off) and return
#   --fetch           copy back the results of a detached run, or show its
#                     log if it hasn't finished
#
# Needs docker (or podman) on the target, and network access there for the
# first image build. The image holds the other libraries and the released
# Pillow builds; the Pillow-AllSIMD builds of REF are compiled in the container
# on every run, so it's the commit that is measured, not a stale build.

set -euo pipefail
cd "$(dirname "$0")"

SIMD_REPO="" REF=HEAD NAME="" TITLE="" CPU=2 SIZE=2560x1600 KEEP=0 TARGET=""
DETACH=0 FETCH=0 ROUNDS=3
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
        --rounds) ROUNDS=$2; shift 2 ;;
        --keep) KEEP=1; shift ;;
        --detach) DETACH=1; shift ;;
        --fetch) FETCH=1; shift ;;
        -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
        -*) echo "unknown option $1" >&2; exit 2 ;;
        *) TARGET=$1; shift ;;
    esac
done
[ -n "$TARGET" ] || { sed -n '2,24p' "$0"; exit 2; }
if [ -z "$SIMD_REPO" ]; then
    SIMD_REPO=../pillow-allsimd
    [ -d "$SIMD_REPO" ] || [ ! -d ../pillow-simd ] || SIMD_REPO=../pillow-simd
fi
REMOTE_DIR="pillow-simd-perf-run"

if [ $FETCH = 1 ]; then
    [ -n "$NAME" ] || NAME="${TARGET#*@}"
    mkdir -p results
    if scp -q "$TARGET:$REMOTE_DIR/run/results.json" "results/$NAME.json" 2>/dev/null; then
        echo "==> results/$NAME.json"
        ssh "$TARGET" "rm -rf $REMOTE_DIR"
    else
        echo "==> not finished; the last lines of its log:"
        ssh "$TARGET" "tail -3 $REMOTE_DIR/run.log"
    fi
    exit 0
fi

COMMIT=$(git -C "$SIMD_REPO" rev-parse --short "$REF")
BRANCH=$(git -C "$SIMD_REPO" rev-parse --abbrev-ref "$REF" 2>/dev/null || echo "$REF")
[ "$BRANCH" = HEAD ] && BRANCH=$(git -C "$SIMD_REPO" rev-parse --abbrev-ref HEAD)
# a commit hash has no branch name: the checkout's branch, if it has the commit
if [ -z "$BRANCH" ]; then
    BRANCH=$(git -C "$SIMD_REPO" rev-parse --abbrev-ref HEAD)
    git -C "$SIMD_REPO" merge-base --is-ancestor "$REF" HEAD || BRANCH=$COMMIT
fi
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
    # every build in exact mode, and the main build again in fast mode, the
    # branch's default since October 2026 (PILLOW_SIMD_FAST is the
    # variable's name before the rename to Pillow-AllSIMD)
    variants+=(--variant "\$name=/work/variants/\$name,PILLOW_ALLSIMD_FAST=0,PILLOW_SIMD_FAST=0")
    if [ \$b = avx2 ] || [ \$b = neon ]; then
        variants+=(--variant "\$name-fast=/work/variants/\$name,PILLOW_ALLSIMD_FAST=1,PILLOW_SIMD_FAST=1")
    fi
done
python3 bench/perf.py "\${variants[@]}" --lib opencv --lib vips --lib wand \
    --size $SIZE --rounds $ROUNDS --title "$TITLE" --extra "branch=$BRANCH" --extra "commit=$COMMIT" \
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
    ssh "$TARGET" "rm -rf $REMOTE_DIR && mkdir -p $REMOTE_DIR"
    tar -C "$STAGE" -cf - run | ssh "$TARGET" "tar -x -C $REMOTE_DIR"
    if [ $DETACH = 1 ]; then
        engine_run "\$HOME/$REMOTE_DIR" | ssh "$TARGET" "cat > $REMOTE_DIR/go.sh"
        ssh "$TARGET" "nohup bash $REMOTE_DIR/go.sh > $REMOTE_DIR/run.log 2>&1 < /dev/null &"
        echo "==> running on $TARGET ($BRANCH @ $COMMIT); later: $0 --fetch --name $NAME $TARGET"
        exit 0
    fi
    ssh "$TARGET" "$(engine_run "\$HOME/$REMOTE_DIR")"
    scp -q "$TARGET:$REMOTE_DIR/run/results.json" "results/$NAME.json"
    [ $KEEP = 1 ] || ssh "$TARGET" "rm -rf $REMOTE_DIR"
fi
echo "==> results/$NAME.json ($BRANCH @ $COMMIT)"
