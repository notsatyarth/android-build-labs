#!/bin/bash
# Same-runner comparison: two cells built alternately (A B A B ...) in one job, so runner speed is the same for both.
# Usage: pair.sh NIA_DIR OUT_DIR CELL_A CELL_B [N]   (N builds per cell, default 5; cells as in run.sh)
# Each cell gets one unmeasured warm-up build first; then build i of A, build i of B, for i = 1..N. Output: OUT_DIR/<cell>/...,
# the same layout as run.sh, plus OUT_DIR/runner.txt (CPU model, cores, memory) so compare.py can show both ran on one machine.
set -u
NIA=$1; OUT=$(mkdir -p "$2" && cd "$2" && pwd); A=$3; B=$4; N=${5:-5}
HERE=$(cd "$(dirname "$0")" && pwd)
{ awk -F': ' '/model name/{print "cpu: " $2; exit}' /proc/cpuinfo; echo "nproc: $(nproc)"; awk '/MemTotal/{printf "mem_gib: %.1f\n", $2/1048576}' /proc/meminfo; } > "$OUT/runner.txt"
cat "$OUT/runner.txt"
for c in "$A" "$B"; do WARMUP=1 bash "$HERE/run.sh" "$NIA" "$OUT/$c" "$c" 0 || exit 2; cp "$OUT/runner.txt" "$OUT/$c/runner.txt"; done
for i in $(seq 1 "$N"); do
  for c in "$A" "$B"; do WARMUP=0 START=$i bash "$HERE/run.sh" "$NIA" "$OUT/$c" "$c" 1 | grep -E '^run'; done
done
