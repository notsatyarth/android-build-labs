#!/bin/bash
# Probe 3, time, pair K: gradle-profiler 0.26.0 with labs/old-vs-new/scenarios.conf (config, clean, nonabi; warm-ups
# as there, iterations = ITER) on two prepared sides of one nowinandroid commit that differ only in the Kotlin version.
# Old side first, then new, on one runner, through labs/old-vs-new/run_commit.sh and agg.py (same agg.json shape).
# Every scenario also gets -Dorg.gradle.isolated-projects=false: at 2982e63 Isolated Projects is on, and Gradle refuses
# --no-configuration-cache with "Configuration Cache cannot be disabled when Isolated Projects is enabled.".
# Usage: time_k.sh   env: WORK (output root), JAVA_HOME, ITER (default 10), NIA_REF, OLD_K, NEW_K
set -u
HERE=$(cd "$(dirname "$0")" && pwd); OVN=$HERE/../old-vs-new
: "${WORK:?}" "${NIA_REF:?}" "${OLD_K:?}" "${NEW_K:?}"; export WORK; mkdir -p "$WORK/profiler-out"
ITER=${ITER:-10}
tag() { echo "k$(echo "$1" | tr -d '.-' | tr 'A-Z' 'a-z')"; }
OLD=$(tag "$OLD_K"); NEW=$(tag "$NEW_K")
echo "$OLD $NEW" > "$WORK/profiler-out/sides.txt"
GP_VER=0.26.0; GP_SHA=c573cdaffac8ecfa60cdd0624274511f46cbdde77fbba39ce35eae0fae7c9877
curl -sfL -o "$WORK/gp.zip" "https://github.com/gradle/gradle-profiler/releases/download/v$GP_VER/gradle-profiler-$GP_VER.zip"
echo "$GP_SHA  $WORK/gp.zip" | sha256sum -c - || exit 1
unzip -q -o "$WORK/gp.zip" -d "$WORK/gp"; export GRADLE_PROFILER=$WORK/gp/gradle-profiler-$GP_VER/bin/gradle-profiler
IP=-Dorg.gradle.isolated-projects=false
sed -e "s/iterations = 5/iterations = $ITER/" -e "s/gradle-args = \[\"--no-build-cache\"/gradle-args = [\"$IP\", \"--no-build-cache\"/" \
  "$OVN/scenarios.conf" > "$WORK/scenarios.k.conf"; export SCENARIOS=$WORK/scenarios.k.conf
cp "$WORK/scenarios.k.conf" "$WORK/profiler-out/scenarios.k.conf"
bash "$HERE/prepare.sh" "$WORK/wt-$OLD" "$NIA_REF" "$OLD_K" || exit 1
bash "$HERE/prepare.sh" "$WORK/wt-$NEW" "$NIA_REF" "$NEW_K" || exit 1
for c in $OLD $NEW; do
  ( . "$OVN/env.sh"; cd "$WORK/wt-$c" && ./gradlew :app:assembleDemoDebug $IP --no-build-cache --no-configuration-cache --console=plain > "$WORK/profiler-out/prime-$c.log" 2>&1
    echo "$c prime exit $?" >> "$WORK/profiler-out/prime-status.txt"; ./gradlew --stop >/dev/null 2>&1; pkill -f GradleDaemon; pkill -f KotlinCompileDaemon; true )
  { echo "$c:"; bash "$HERE/versions.sh" "$WORK/wt-$c" $IP; } >> "$WORK/profiler-out/versions.txt"
done
cat "$WORK/profiler-out/prime-status.txt" "$WORK/profiler-out/versions.txt"
grep -q "$NEW prime exit 0" "$WORK/profiler-out/prime-status.txt" || { echo "new side does not assemble:"; grep -E '^e: |What went wrong' -A3 "$WORK/profiler-out/prime-$NEW.log" | head -40; exit 1; }
grep -q "$OLD prime exit 0" "$WORK/profiler-out/prime-status.txt" || { echo "old side does not assemble"; exit 1; }
bash "$OVN/run_commit.sh" "$OLD" 1; bash "$OVN/run_commit.sh" "$NEW" 1
( cd "$WORK" && python3 -I "$OVN/agg.py" )
