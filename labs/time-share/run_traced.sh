#!/bin/bash
# Usage: run_traced.sh SCENARIO WARMUPS MEASURED   (SCENARIO: clean-cc | clean-nocc | nonabi | abi)
# Runs :app:assembleDemoDebug in the lab clone with a Gradle build operation trace per build and writes
# reduced JSON per measured build to raw/. Warm-up builds are run the same way and not kept.
# Needs: JDK 17 in JAVA_HOME, ANDROID_HOME, python3. The clone is returned to a clean tree at the end.
set -u
SCN=$1; WARM=$2; N=$3
HERE=$(cd "$(dirname "$0")" && pwd)
LAB=${LAB:?set LAB to a nowinandroid checkout (commit 2982e63 in the original runs)}
TMP=${TMPDIR_TS:-/tmp/time-share}; mkdir -p "$TMP" "$HERE/raw"
FILE=core/model/src/main/kotlin/com/google/samples/apps/nowinandroid/core/model/data/Topic.kt
cd "$LAB" || exit 1
./gradlew --stop >/dev/null 2>&1; pkill -f GradleDaemon; pkill -f KotlinCompileDaemon; true; sleep 2
case $SCN in
  clean-cc)   ARGS="--no-build-cache --rerun-tasks";;
  clean-nocc) ARGS="--no-build-cache --rerun-tasks --no-configuration-cache --no-isolated-projects";;
  nonabi|abi) ARGS="--no-build-cache";;
  *) echo "unknown scenario"; exit 2;;
esac
# the incremental scenarios need a built state first
if [ "$SCN" = nonabi ] || [ "$SCN" = abi ]; then ./gradlew --console=plain $ARGS :app:assembleDemoDebug >/dev/null 2>&1; fi
TOTAL=$((WARM+N))
for i in $(seq 1 $TOTAL); do
  case $SCN in
    nonabi) printf '\nprivate fun nonAbiChange%s(): Int = %s\n' "$i" "$i" >> "$FILE";;
    abi)    printf '\nfun abiChange%s(): Int = %s\n' "$i" "$i" >> "$FILE";;
  esac
  PFX="$TMP/$SCN-$i"; rm -f "$PFX-log.txt"
  ./gradlew --console=plain $ARGS -Dorg.gradle.internal.operations.trace.tree=false \
     -Dorg.gradle.internal.operations.trace="$PFX" :app:assembleDemoDebug > "$PFX.console" 2>&1
  RC=$?
  if [ $i -gt $WARM ]; then
    K=$((i-WARM))
    python3 "$HERE/attribute.py" reduce "$PFX-log.txt" "$HERE/raw/$SCN-$K.json"
    { echo "# $SCN measured run $K (warm-ups: $WARM), exit=$RC"; grep -E "^BUILD|actionable tasks|Configuration cache entry" "$PFX.console"; } > "$HERE/raw/$SCN-$K.txt"
  fi
  rm -f "$PFX-log.txt"
  echo "$SCN $i/$TOTAL exit=$RC"
done
git checkout -- "$FILE"
./gradlew --stop >/dev/null 2>&1; pkill -f GradleDaemon; pkill -f KotlinCompileDaemon; true
git status --short
