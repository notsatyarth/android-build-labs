#!/bin/bash
# nowinandroid variant and task counts with and without beforeVariants filtering (init script only;
# nowinandroid is not edited). Usage: run.sh NIA_DIR OUT_DIR [TIMING_N]
# Needs JAVA_HOME (17) and ANDROID_HOME. The original runs used nowinandroid 2982e63.
# Isolated Projects and the configuration cache are turned off because the counting hook
# (projectsEvaluated + allprojects) is not IP-safe; timings therefore measure a full configuration.
set -u
NIA=$(cd "$1" && pwd); OUT=$(mkdir -p "$2" && cd "$2" && pwd); N=${3:-6}
INIT=$(cd "$(dirname "$0")" && pwd)/variants.init.gradle
KEEP=demoDebug,debug
cd "$NIA"
g() { ./gradlew --init-script "$INIT" --no-configuration-cache -Dorg.gradle.isolated-projects=false --console=plain "$@"; }
step() { local n=$1; shift; echo "\$ gradlew $*" > "$OUT/$n.log"; g "$@" >> "$OUT/$n.log" 2>&1; echo "$n rc=$?" | tee -a "$OUT/steps.txt"; }
step print-all help -Dlab.print=true
step print-keep help -Dlab.print=true -Dlab.keep=$KEEP
step count-all help -Dlab.count=true
step count-keep help -Dlab.count=true -Dlab.keep=$KEEP
step dryrun-all :app:assembleDemoDebug --dry-run
step dryrun-keep :app:assembleDemoDebug --dry-run -Dlab.keep=$KEEP
step tasks-all tasks --all
step tasks-keep tasks --all -Dlab.keep=$KEEP
# Configuration time of `help -q` with a warm daemon: one warm-up per arm, then N per arm alternating.
g help -q > /dev/null 2>&1; g help -q -Dlab.keep=$KEEP > /dev/null 2>&1
python3 - "$N" "$KEEP" "$INIT" > "$OUT/config-time.json" <<'PY'
import json, subprocess, sys, time
n, keep, init = int(sys.argv[1]), sys.argv[2], sys.argv[3]
base = ["./gradlew", "--init-script", init, "--no-configuration-cache", "-Dorg.gradle.isolated-projects=false", "help", "-q"]
res = {"all": [], "keep": []}
for i in range(n):
    for arm in (["all", "keep"] if i % 2 == 0 else ["keep", "all"]):
        t0 = time.time()
        subprocess.run(base + ([f"-Dlab.keep={keep}"] if arm == "keep" else []), capture_output=True)
        res[arm].append(round(time.time() - t0, 2))
print(json.dumps(res, indent=1))
PY
./gradlew --stop > /dev/null 2>&1
