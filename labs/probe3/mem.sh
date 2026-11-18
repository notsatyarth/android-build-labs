#!/bin/bash
# Probe 3, memory: N clean builds per side under tools/procwatch (--interval 0.5 --cpu --meta), old and new
# interleaved (old 1, new 1, old 2, ...) on one runner, a fresh Gradle daemon and no Kotlin daemon before every build.
# Build: :app:assembleDemoDebug --no-build-cache --rerun-tasks --no-configuration-cache (as the gradle-profiler "clean"
# scenario), plus -Dorg.gradle.isolated-projects=false for pair K (see time_k.sh). Both sides are primed first (not measured).
# Usage: mem.sh PAIR OUT [N]   PAIR = K (env NIA_REF, OLD_K, NEW_K) or A (AGP 8.13.1 -> 9.0.0: old-vs-new p2 commits)
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PAIR=$1; OUT=$(mkdir -p "$2" && cd "$2" && pwd); N=${3:-5}; W=${RUNNER_TEMP:-/tmp}/p3-$PAIR
: "${JAVA_HOME:?}"
tag() { echo "k$(echo "$1" | tr -d '.-' | tr 'A-Z' 'a-z')"; }
case "$PAIR" in
  K) OLD=$(tag "$OLD_K"); NEW=$(tag "$NEW_K"); EXTRA=-Dorg.gradle.isolated-projects=false
     bash "$HERE/prepare.sh" "$W/$OLD" "$NIA_REF" "$OLD_K" || exit 1; bash "$HERE/prepare.sh" "$W/$NEW" "$NIA_REF" "$NEW_K" || exit 1;;
  A) OLD=ade8065442; NEW=2c56ce13b; EXTRA=
     bash "$HERE/prepare.sh" "$W/$OLD" ade8065442099e1f63f6c4c716bafc84b053ca09 || exit 1
     bash "$HERE/prepare.sh" "$W/$NEW" 2c56ce13bf13bdc33259efdc215166ec7f036225 || exit 1;;
  *) echo "pair?"; exit 2;;
esac
echo "$OLD $NEW" > "$OUT/sides.txt"
ARGS=":app:assembleDemoDebug --no-build-cache --rerun-tasks --no-configuration-cache --console=plain $EXTRA"
echo "./gradlew $ARGS" > "$OUT/command.txt"
stop() { (cd "$1" && ./gradlew --stop >/dev/null 2>&1); pkill -f GradleDaemon; pkill -f KotlinCompileDaemon; sleep 3; true; }
for s in $OLD $NEW; do
  (cd "$W/$s" && ./gradlew $ARGS > "$OUT/prime-$s.log" 2>&1; echo "$s prime exit $?" >> "$OUT/status.txt")
  { echo "$s:"; bash "$HERE/versions.sh" "$W/$s" $EXTRA; } >> "$OUT/versions.txt"; stop "$W/$s"
done
grep -q "$NEW prime exit 0" "$OUT/status.txt" || { echo "new side does not assemble:"; grep -E '^e: |What went wrong' -A3 "$OUT/prime-$NEW.log" | head -40; exit 1; }
for i in $(seq 1 "$N"); do
  for s in $OLD $NEW; do
    stop "$W/$s"
    (cd "$W/$s" && python3 -I "$HERE/../../tools/procwatch/procwatch.py" "$OUT/$s-build$i.csv" --interval 0.5 --cpu --meta -- ./gradlew $ARGS > "$OUT/$s-build$i.log" 2>&1
     echo "$s build$i exit $?" >> "$OUT/status.txt")
  done
done
stop "$W/$OLD"
cat "$OUT/status.txt"
python3 -I "$HERE/memsum.py" "$OUT" "$PAIR"
