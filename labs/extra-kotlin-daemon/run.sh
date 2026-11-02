#!/bin/bash
# Extra Kotlin daemon 2x2 on nowinandroid: does the build-logic (Gradle-embedded Kotlin) compile start its own Kotlin daemon?
# Usage: run.sh NIA_DIR OUT_DIR   (NIA_DIR: git checkout of nowinandroid 2982e63; JAVA_HOME = JDK 17; ANDROID_HOME set)
#   run1  as shipped (project Kotlin 2.3.0)
#   run2  project Kotlin 2.4.0 + KSP 2.3.12 (matches the Kotlin embedded in Gradle 9.7.1)
#   run3b Kotlin 2.4.0 + the same kotlin.daemon.jvmargs in build-logic/gradle.properties
#   run4  Kotlin 2.3.0 + the same kotlin.daemon.jvmargs in build-logic/gradle.properties
# Each run: reset, edit, stop daemons, clean build-logic, then a clean :app:assembleDemoDebug sampled by procwatch.py.
set -u
NIA=$(cd "$1" && pwd); OUT=$(mkdir -p "$2" && cd "$2" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
: "${JAVA_HOME:?}"
KJ='-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=320m -XX:+HeapDumpOnOutOfMemoryError -Xmx4g -Xms4g'
edit() { python3 -I - "$NIA" "$1" "$KJ" <<'P'
import sys, re, pathlib
nia, what, kj = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
if "k24" in what:
    p = nia / "gradle/libs.versions.toml"; s = p.read_text()
    s = re.sub(r'^kotlin = "2\.3\.0"', 'kotlin = "2.4.0"', s, flags=re.M); s = re.sub(r'^ksp = "2\.3\.4"', 'ksp = "2.3.12"', s, flags=re.M); p.write_text(s)
if "args" in what:
    p = nia / "build-logic/gradle.properties"; p.write_text(p.read_text().rstrip("\n") + "\nkotlin.daemon.jvmargs=" + kj + "\n")
P
}
stop() { (cd "$NIA" && ./gradlew --stop >/dev/null 2>&1); pkill -f "GradleDaemon|KotlinCompileDaemon"; sleep 3; true; }
run() {  # label edit-tag
  local l=$1 e=$2
  git -C "$NIA" checkout -q -- . && git -C "$NIA" clean -fdxq; edit "$e"; stop
  (cd "$NIA" && ./gradlew -p build-logic :convention:clean --console=plain > "$OUT/$l.clean.log" 2>&1); stop
  (cd "$NIA" && python3 -I "$HERE/../../tools/procwatch/procwatch.py" "$OUT/$l.csv" --interval 1 -- ./gradlew :app:assembleDemoDebug --no-build-cache --rerun-tasks --console=plain > "$OUT/$l.log" 2>&1)
  echo "$l: $(grep -E 'BUILD (SUCCESSFUL|FAILED)' "$OUT/$l.log" | tr '\n' ' ')"
  stop
}
run run1 none; run run2 k24; run run3b k24+args; run run4 args
