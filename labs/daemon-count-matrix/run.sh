#!/bin/bash
# One vs two Kotlin daemons on nowinandroid, across Kotlin daemon -Xms and -Xmx, with the Kotlin version held constant.
# Usage: run.sh NIA_DIR OUT_DIR CELL [N]   (NIA_DIR: git checkout of nowinandroid 2982e63; JAVA_HOME = JDK 17; ANDROID_HOME set; N builds, default 5)
# CELL is d1_lo_2g, d1_hi_2g, d2_lo_2g, d2_hi_2g, d1_lo_4g, d1_hi_4g, d2_lo_4g, d2_hi_4g, or shipped_4g:
#   d1 / d2  one or two Kotlin daemons. Kotlin 2.4.0 and KSP 2.3.12 everywhere (2.4.0 is the Kotlin embedded in Gradle 9.7.1, which
#            compiles build-logic), so both compiles use the same compiler. A Kotlin daemon is reused when the compiler is the same
#            and the request's -Xmx, MaxMetaspaceSize and ReservedCodeCacheSize fit into the running daemon's (KotlinCompilerClient.kt,
#            DaemonParams.kt, Kotlin 2.4.0); -Xms and other flags do not count. build-logic compiles first, so:
#            d1: build-logic and the app ask for ReservedCodeCacheSize=320m -> the app reuses the build-logic daemon.
#            d2: build-logic asks for 256m (what nowinandroid ships, inherited from org.gradle.jvmargs), the app for 320m -> a second daemon.
#   lo / hi  Kotlin daemon -Xms256m, or -Xms equal to -Xmx
#   2g / 4g  Kotlin daemon -Xmx (both daemons)
#   shipped_4g  nowinandroid as shipped (project Kotlin 2.3.0, KSP 2.3.4; build-logic on Gradle's 2.4.0; Xmx4g Xms4g), so two
#            daemons for two reasons (version and code cache). Same as d2_hi_4g except the Kotlin version.
# Every Kotlin daemon writes a GC log (-Xlog:gc to OUT/gc/kd-<pid>.log; logging flags do not affect daemon reuse).
# One unmeasured warm-up build first. Each build: stop daemons, clean build-logic, stop daemons, then a clean :app:assembleDemoDebug under procwatch.py --cpu --meta (0.5 s).
set -u
NIA=$(cd "$1" && pwd); OUT=$(mkdir -p "$2" && cd "$2" && pwd); CELL=$3; N=${4:-5}
HERE=$(cd "$(dirname "$0")" && pwd)
: "${JAVA_HOME:?}"
mkdir -p "$OUT/gc"
git -C "$NIA" checkout -q -- . && git -C "$NIA" clean -fdxq
python3 -I - "$NIA" "$CELL" "$OUT/gc" <<'P' || exit 2
import sys, re, pathlib
nia, cell, gc = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
base = "-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:+HeapDumpOnOutOfMemoryError"
log = f"-Xlog:gc:file={gc}/kd-%p.log"
def setprop(path, key, value):
    s = path.read_text() if path.exists() else ""
    s = re.sub(rf"^{re.escape(key)}=.*\n?", "", s, flags=re.M).rstrip("\n") + f"\n{key}={value}\n"
    path.write_text(s)
root, logic = nia / "gradle.properties", nia / "build-logic/gradle.properties"
if cell == "shipped_4g":
    # As shipped, plus the GC log. build-logic gets explicitly what it inherits from org.gradle.jvmargs today.
    setprop(root, "kotlin.daemon.jvmargs", f"{base} -XX:ReservedCodeCacheSize=320m -Xmx4g -Xms4g {log}")
    setprop(logic, "kotlin.daemon.jvmargs", f"{base} -XX:ReservedCodeCacheSize=256m -Xmx4g -Xms4g {log}")
else:
    m = re.fullmatch(r"d([12])_(lo|hi)_([24]g)", cell)
    if not m:
        sys.exit(f"unknown cell {cell}")
    d, xms, xmx = m.groups()
    xms = "256m" if xms == "lo" else xmx
    toml = nia / "gradle/libs.versions.toml"; s = toml.read_text()
    s = re.sub(r'^kotlin = "2\.3\.0"', 'kotlin = "2.4.0"', s, flags=re.M); s = re.sub(r'^ksp = "2\.3\.4"', 'ksp = "2.3.12"', s, flags=re.M)
    assert 'kotlin = "2.4.0"' in s and 'ksp = "2.3.12"' in s, "version edit failed"
    toml.write_text(s)
    setprop(root, "kotlin.daemon.jvmargs", f"{base} -XX:ReservedCodeCacheSize=320m -Xmx{xmx} -Xms{xms} {log}")
    setprop(logic, "kotlin.daemon.jvmargs", f"{base} -XX:ReservedCodeCacheSize={'320m' if d == '1' else '256m'} -Xmx{xmx} -Xms{xms} {log}")
P
{ echo "# $CELL"; grep -E '^(kotlin|ksp) = ' "$NIA/gradle/libs.versions.toml"; echo "root: $(grep '^kotlin.daemon.jvmargs' "$NIA/gradle.properties")"; echo "build-logic: $(grep '^kotlin.daemon.jvmargs' "$NIA/build-logic/gradle.properties")"; } > "$OUT/setup.txt"
cat "$OUT/setup.txt"
stop() { (cd "$NIA" && ./gradlew --stop >/dev/null 2>&1); pkill -f "GradleDaemon|KotlinCompileDaemon|GradleWorkerMain"; pkill -x aapt2; sleep 3; true; }
# Warm-up build with the cell's versions (not measured), so no measured build downloads dependencies. WARMUP=0 skips it and
# START=k numbers the measured builds from k (pair.sh uses both to alternate two cells build by build on one runner).
if [ "${WARMUP:-1}" = 1 ]; then
  stop; (cd "$NIA" && ./gradlew :app:assembleDemoDebug --console=plain > "$OUT/warmup.log" 2>&1); echo "warm-up: $(grep -E 'BUILD (SUCCESSFUL|FAILED)' "$OUT/warmup.log")"
  rm -f "$OUT"/gc/*.log
fi
[ "$N" -gt 0 ] || exit 0
S=${START:-1}
for i in $(seq "$S" $((S + N - 1))); do
  stop
  (cd "$NIA" && ./gradlew -p build-logic :convention:clean --console=plain > "$OUT/run$i.clean.log" 2>&1); stop
  (cd "$NIA" && python3 -I "$HERE/../../tools/procwatch/procwatch.py" "$OUT/run$i.csv" --interval 0.5 --cpu --client --meta -- ./gradlew :app:assembleDemoDebug --no-build-cache --rerun-tasks --console=plain > "$OUT/run$i.log" 2>&1)
  ps -eo pid=,args= | grep KotlinCompileDaemon | grep -v grep > "$OUT/run$i.kotlin-daemons.txt"
  echo "run$i: $(grep -E 'BUILD (SUCCESSFUL|FAILED)' "$OUT/run$i.log" | tr '\n' ' ')"
done
stop
