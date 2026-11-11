#!/bin/bash
# Per-process CPU time, wall time and peak memory of a clean nowinandroid :app:assembleDemoDebug, N builds.
# Usage: run.sh NIA_DIR OUT_DIR [N]   (NIA_DIR: git checkout of nowinandroid; JAVA_HOME = JDK 17; ANDROID_HOME set)
# Each build: stop daemons, clean build-logic, stop daemons, then the build under procwatch.py --cpu (0.5 s samples).
set -u
NIA=$(cd "$1" && pwd); OUT=$(mkdir -p "$2" && cd "$2" && pwd); N=${3:-5}
HERE=$(cd "$(dirname "$0")" && pwd)
: "${JAVA_HOME:?}"
stop() { (cd "$NIA" && ./gradlew --stop >/dev/null 2>&1); pkill -f "GradleDaemon|KotlinCompileDaemon"; sleep 3; true; }
for i in $(seq 1 "$N"); do
  stop
  (cd "$NIA" && ./gradlew -p build-logic :convention:clean --console=plain > "$OUT/run$i.clean.log" 2>&1); stop
  (cd "$NIA" && python3 -I "$HERE/../../tools/procwatch/procwatch.py" "$OUT/run$i.csv" --interval 0.5 --cpu -- ./gradlew :app:assembleDemoDebug --no-build-cache --rerun-tasks --console=plain > "$OUT/run$i.log" 2>&1)
  echo "run$i: $(grep -E 'BUILD (SUCCESSFUL|FAILED)' "$OUT/run$i.log" | tr '\n' ' ')"
done
stop
