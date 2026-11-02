#!/bin/bash
# Compact object headers lab: one clean :app:assembleDemoDebug per call, fresh daemons.
# usage: run.sh <label> <arm: base|coh>
# Flags are passed on the command line only; nowinandroid's gradle.properties is not changed.
set -u
LABEL=$1; ARM=$2
NIA=${NIA:-$HOME/nowinandroid}   # nowinandroid checkout (commit 2982e63 in the original runs)
OUT_ROOT=${OUT_ROOT:-$(cd "$(dirname "$0")" && pwd)}
OUT=$OUT_ROOT/raw
mkdir -p "$OUT"
# Required: JAVA_HOME pointing at a JDK 25 or later (UseCompactObjectHeaders is a product flag from JDK 25, JEP 519).
: "${JAVA_HOME:?set JAVA_HOME to a JDK 25+}"
: "${ANDROID_HOME:=$HOME/Library/Android/sdk}"
# Resolve symlinks: Gradle starts daemons from the real path (CI runners link JAVA_HOME to /usr/lib/jvm/...),
# and the process match below compares command lines against this path.
JAVA_HOME=$(python3 -I -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$JAVA_HOME")
export ANDROID_HOME JAVA_HOME
LOAD_MAX=${LOAD_MAX:-8}   # idle gate: 1-minute load must be below this
# Same strings as nowinandroid gradle.properties (commit 2982e63); coh arm appends one flag.
GJ="-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=256m -XX:+HeapDumpOnOutOfMemoryError -Xmx4g -Xms4g"
KJ="-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=320m -XX:+HeapDumpOnOutOfMemoryError -Xmx4g -Xms4g"
# Kotlin daemon run-files directory private to this lab, so the Kotlin client neither reuses nor
# offers Kotlin daemons started by other builds on the machine (the default dir is shared per user).
KDRUN=$OUT/kotlin-daemon-run; mkdir -p "$KDRUN"
GJ="$GJ -Dkotlin.daemon.options=runFilesPath=$KDRUN"
# GC logging is added to both arms equally (heap occupancy after each GC).
GJ="$GJ -Xlog:gc:file=$OUT/$LABEL.gradle-gc-%p.log"; KJ="$KJ -Xlog:gc:file=$OUT/$LABEL.kotlin-gc-%p.log"
if [ "$ARM" = coh ]; then GJ="$GJ -XX:+UseCompactObjectHeaders"; KJ="$KJ -XX:+UseCompactObjectHeaders"; fi
cd "$NIA"
# Other builds may share this machine and Gradle version, so `gradlew --stop` (which stops every
# daemon of that version in the user home) is not used. Only JVMs started from this JAVA_HOME are stopped.
NEEDLE=$JAVA_HOME/bin/java
stop_mine() { pkill -TERM -f "$NEEDLE" 2>/dev/null; sleep 3; pkill -KILL -f "$NEEDLE" 2>/dev/null; }
stop_mine
sleep 5
# Idle gate: wait until no Gradle or Kotlin daemon other than ours runs and the 1-minute load is below 8.
foreign() { ps -eo command= | grep -E "GradleDaemon|KotlinCompileDaemon|GradleWorkerMain" | grep -v grep | grep -vc "$NEEDLE"; }
load1() { if [ -r /proc/loadavg ]; then cut -d' ' -f1 /proc/loadavg; else sysctl -n vm.loadavg | awk '{print $2}'; fi; }
swap_used() { if [ -r /proc/meminfo ]; then awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{printf "%dM", (t-f)/1024}' /proc/meminfo; else sysctl -n vm.swapusage | awk '{print $6}'; fi; }
while true; do
  f=$(foreign); l=$(load1)
  if [ "$f" -eq 0 ] && awk "BEGIN{exit !($l < $LOAD_MAX)}"; then break; fi
  echo "$(date +%T) $LABEL waiting: foreign=$f load1=$l" >> "$OUT/gate.txt"
  sleep 60
done
# Contention log during the build: load and number of foreign daemons every 5 s.
( while true; do echo "$(date +%T) load1=$(load1) foreign=$(foreign) swap_used=$(swap_used)"; sleep 5; done ) > "$OUT/$LABEL.contention" 2>&1 &
CPID=$!
{ date; uname -a; "$JAVA_HOME/bin/java" -version 2>&1; echo "swap_used=$(swap_used)"; } > "$OUT/$LABEL.env"
python3 -I "$OUT_ROOT/../../tools/procwatch/procwatch_match.py" "$OUT/$LABEL.csv" --interval 1 --match "$JAVA_HOME" -- \
  ./gradlew :app:assembleDemoDebug --no-build-cache --rerun-tasks --no-configuration-cache -Dorg.gradle.isolated-projects=false --console=plain \
  "-Dorg.gradle.jvmargs=$GJ" "-Pkotlin.daemon.jvmargs=$KJ" > "$OUT/$LABEL.log" 2>&1
echo "exit $?" >> "$OUT/$LABEL.env"
kill $CPID 2>/dev/null
# After the build: daemon command lines, heap use, then live set after a full GC.
for pat in GradleDaemon KotlinCompileDaemon; do
  for pid in $(pgrep -f "$NEEDLE.*$pat"); do
    echo "== $pat $pid" >> "$OUT/$LABEL.heap"
    { echo "== $pat $pid"; ps -o command= -p "$pid"; } >> "$OUT/$LABEL.cmd"
    ps -o command= -p "$pid" | tr ' ' '\n' | grep -E "^-X" | tr '\n' ' ' >> "$OUT/$LABEL.heap"; echo >> "$OUT/$LABEL.heap"
    "$JAVA_HOME/bin/jcmd" "$pid" GC.heap_info >> "$OUT/$LABEL.heap" 2>&1
    "$JAVA_HOME/bin/jcmd" "$pid" GC.run >/dev/null 2>&1
    echo "-- after GC.run" >> "$OUT/$LABEL.heap"
    "$JAVA_HOME/bin/jcmd" "$pid" GC.heap_info >> "$OUT/$LABEL.heap" 2>&1
  done
done
stop_mine || true
exit 0
