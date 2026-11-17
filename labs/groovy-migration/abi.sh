#!/bin/bash
# Kotlin DSL vs Groovy scripts after a public API change in build-logic: every build script must be recompiled.
# Usage: abi.sh NIA_DIR OUT_DIR ROUNDS   (NIA_DIR: nowinandroid 2982e63; JAVA_HOME = JDK 17; ANDROID_HOME set)
# Per round and variant (kts, groovy alternating): clean tree (+ convert.py for groovy), two warm `help` runs (scripts and
# build-logic compiled, daemon warm), then append a new public function to a build-logic source file (an ABI change) and
# time `help` (s_abi), then time `help` again with nothing changed (s_same). Wall time from the shell, in seconds.
# Output: OUT_DIR/abi.tsv (variant, round, s_abi, s_same) and a median summary on stdout.
set -u
NIA=$(cd "$1" && pwd); OUT=$(mkdir -p "$2" && cd "$2" && pwd); ROUNDS=${3:-5}
HERE=$(cd "$(dirname "$0")" && pwd)
F=build-logic/convention/src/main/kotlin/com/google/samples/apps/nowinandroid/NiaFlavor.kt
now() { python3 -c 'import time;print(time.time())'; }
cd "$NIA"
printf 'variant\tround\ts_abi\ts_same\n' > "$OUT/abi.tsv"
for r in $(seq 1 "$ROUNDS"); do for v in kts groovy; do
  git checkout -q -- . && git clean -fdxq
  [ "$v" = groovy ] && python3 -I "$HERE/convert.py" . > /dev/null
  ./gradlew help -q --console=plain > /dev/null 2>&1; ./gradlew help -q --console=plain > /dev/null 2>&1
  printf '\nfun labAbiChange%s%s(): Int = %s\n' "$r" "$v" "$r" >> "$F"
  t0=$(now); ./gradlew help --console=plain > "$OUT/$v-r$r-abi.log" 2>&1; rc=$?; t1=$(now)
  t2=$(now); ./gradlew help --console=plain > "$OUT/$v-r$r-same.log" 2>&1; t3=$(now)
  a=$(python3 -c "print(round($t1-$t0,2))"); b=$(python3 -c "print(round($t3-$t2,2))")
  printf '%s\t%s\t%s\t%s\n' "$v" "$r" "$a" "$b" >> "$OUT/abi.tsv"
  echo "$v r$r rc=$rc abi-change help ${a}s, unchanged help ${b}s"
done; done
./gradlew --stop > /dev/null 2>&1; git checkout -q -- . && git clean -fdxq
python3 -I - "$OUT/abi.tsv" <<'P'
import csv, statistics as st, sys
rows = list(csv.DictReader(open(sys.argv[1]), delimiter="\t"))
for v in ("kts", "groovy"):
    a = [float(r["s_abi"]) for r in rows if r["variant"] == v]; s = [float(r["s_same"]) for r in rows if r["variant"] == v]
    a2 = a[1:] if len(a) > 2 else a
    print(f"{v:7s} abi-change help: median {st.median(a):.2f} s (all {a}); median without round 1 {st.median(a2):.2f} s | unchanged help median {st.median(s):.2f} s")
P
