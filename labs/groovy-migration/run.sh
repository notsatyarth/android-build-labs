#!/bin/bash
# Kotlin DSL vs Groovy DSL build scripts on nowinandroid 2982e63, one machine, one run per call.
# Usage: run.sh NIA_DIR OUT_DIR VARIANT RUN_LABEL [--include-build-logic]
#   VARIANT kts    : the checkout as shipped
#   VARIANT groovy : the 37 module/settings scripts converted by convert.py (build-logic scripts too with --include-build-logic)
# JAVA_HOME = JDK 17, ANDROID_HOME set. Alternate the variants (kts, groovy, kts, groovy, ...) and use the same RUN_LABEL pairs.
# Every run starts with no Gradle/Kotlin processes, git clean -fdx, and the script caches (groovy-dsl, kotlin-dsl) emptied,
# so the first step pays for compiling the build scripts. Steps (procwatch --client --cpu --meta, 1 s):
#   s1 `help` (configuration only, cold script cache, empty configuration cache)
#   s2 clean :app:assembleDemoDebug --rerun-tasks --no-build-cache (daemons already warm from s1)
#   s3 the same build again, nothing to do, configuration cache hit
#   s4 the same build again after deleting .gradle/configuration-cache (full configuration, every task up to date; --no-configuration-cache is refused because Isolated Projects is on)
set -u
NIA=$(cd "$1" && pwd); OUT=$(mkdir -p "$2" && cd "$2" && pwd); V=$3; RUN=$4; EXTRA=${5:-}
HERE=$(cd "$(dirname "$0")" && pwd)
PW="$HERE/../../tools/procwatch/procwatch.py"
: "${JAVA_HOME:?}"; : "${ANDROID_HOME:?}"
D="$OUT/$V-$RUN"; mkdir -p "$D"
GV=$(grep -oE 'gradle-[0-9.]+-' "$NIA/gradle/wrapper/gradle-wrapper.properties" | sed 's/gradle-//; s/-$//')
stop() { (cd "$NIA" && ./gradlew --stop >/dev/null 2>&1); pkill -f "GradleDaemon|KotlinCompileDaemon|GradleWorkerMain"; pkill -x aapt2; sleep 3; true; }
sample() {  # label -- command...
  local l=$1; shift 2
  (cd "$NIA" && python3 -I "$PW" "$D/$l.csv" --interval 1 --client --cpu --meta --tail 5 -- "$@" > "$D/$l.log" 2>&1)
  echo "$V-$RUN $l: $(grep -E 'BUILD (SUCCESSFUL|FAILED)' "$D/$l.log" | tr '\n' ' ')"
}
stop
git -C "$NIA" checkout -q -- . && git -C "$NIA" clean -fdxq
[ "$V" = groovy ] && python3 -I "$HERE/convert.py" "$NIA" $EXTRA | tee "$D/convert.txt"
find "$NIA" -name "*.gradle.kts" -not -path "*/build/*" | sed "s|$NIA/||" | sort > "$D/kts-scripts.txt"
find "$NIA" -name "*.gradle" -not -path "*/build/*" | sed "s|$NIA/||" | sort > "$D/groovy-scripts.txt"
rm -rf "$HOME/.gradle/caches/$GV/groovy-dsl" "$HOME/.gradle/caches/$GV/kotlin-dsl"
B=(./gradlew :app:assembleDemoDebug --no-build-cache --console=plain)
sample s1 -- ./gradlew help --console=plain
sample s2 -- "${B[@]}" --rerun-tasks
sample s3 -- "${B[@]}"
rm -rf "$NIA/.gradle/configuration-cache"
sample s4 -- "${B[@]}"
cp "$NIA/app/build/outputs/apk/demo/debug/app-demo-debug.apk" "$D/app-demo-debug.apk" 2>/dev/null
stop
git -C "$NIA" checkout -q -- . && git -C "$NIA" clean -fdxq   # leave the checkout as shipped
