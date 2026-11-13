#!/bin/bash
# Which processes of a nowinandroid build end when the build finishes, and when do the others go away?
# Usage: run.sh NIA_DIR OUT_DIR CELL   (NIA_DIR: git checkout of nowinandroid 2982e63; JAVA_HOME = JDK 17; ANDROID_HOME set)
# Cells (one per CI job):
#   a1a2  a1: clean :app:assembleDemoDebug with default settings, then 300 s of sampling after the build;
#         a2: the same build again right after a1 (warm), 30 s tail. Same Gradle and Kotlin daemon pids?
#   a3    Gradle daemon idle timeout 60 s (org.gradle.daemon.idletimeout=60000 in gradle.properties), 300 s tail
#   a4    Kotlin daemon idle shutdown 60 s (-Dkotlin.daemon.options=autoshutdownIdleSeconds=60 in org.gradle.jvmargs;
#         option name and the 7200 s default are from DaemonParams.kt in Kotlin 2.4.0), 300 s tail
#   a5    build, wait 20 s, ./gradlew --stop, 120 s tail
#   a6    build with --no-daemon, 120 s tail
# Every cell starts with no Gradle, Kotlin or worker processes and a clean build-logic.
# procwatch samples every second (--client --cpu --meta); each cell also saves the Kotlin daemon command lines and the
# lines of the Gradle and Kotlin daemon logs that mention stopping, expiry or idleness.
set -u
NIA=$(cd "$1" && pwd); OUT=$(mkdir -p "$2" && cd "$2" && pwd); CELL=$3
HERE=$(cd "$(dirname "$0")" && pwd)
PW="$HERE/../../tools/procwatch/procwatch.py"
: "${JAVA_HOME:?}"
B=(./gradlew :app:assembleDemoDebug --no-build-cache --rerun-tasks --console=plain)
stop() {
  (cd "$NIA" && ./gradlew --stop >/dev/null 2>&1)
  pkill -f "GradleDaemon|KotlinCompileDaemon|GradleWorkerMain" ; pkill -x aapt2; sleep 3; true
}
kd() { ps -eo pid=,args= | grep KotlinCompileDaemon | grep -v grep > "$OUT/$1.kotlin-daemons.txt"; true; }
logs() {  # label: daemon log lines about stop / expiry / idle (Gradle) and shutdown (Kotlin)
  grep -hiE "expir|idle|stop|shut ?down" "$HOME"/.gradle/daemon/*/daemon-*.out.log 2>/dev/null | tail -n 60 > "$OUT/$1.gradle-daemon-log.txt"
  grep -hiE "shut ?down|idle|unused" "${TMPDIR:-/tmp}"/kotlin-daemon.*.log 2>/dev/null | tail -n 60 > "$OUT/$1.kotlin-daemon-log.txt"
  true
}
sample() {  # label tail -- command...
  local l=$1 t=$2; shift 3
  (cd "$NIA" && python3 -I "$PW" "$OUT/$l.csv" --interval 1 --client --cpu --meta --tail "$t" -- "$@" > "$OUT/$l.log" 2>&1)
  echo "$l: $(grep -E 'BUILD (SUCCESSFUL|FAILED)' "$OUT/$l.log" | tr '\n' ' ')"
}
git -C "$NIA" checkout -q -- . && git -C "$NIA" clean -fdxq
case "$CELL" in
  a3) printf '\norg.gradle.daemon.idletimeout=60000\n' >> "$NIA/gradle.properties" ;;
  a4) sed -i -E 's/^(org\.gradle\.jvmargs=.*)$/\1 -Dkotlin.daemon.options=autoshutdownIdleSeconds=60/' "$NIA/gradle.properties" ;;
esac
grep -E "^org\.gradle\.(jvmargs|daemon)" "$NIA/gradle.properties" > "$OUT/$CELL.gradle-properties.txt"
stop
(cd "$NIA" && ./gradlew -p build-logic :convention:clean --console=plain > "$OUT/$CELL.clean.log" 2>&1); stop
case "$CELL" in
  a1a2)
    sample a1 300 -- "${B[@]}"; kd a1; logs a1
    sample a2 30 -- "${B[@]}"; kd a2; logs a2 ;;
  a3|a4)
    sample "$CELL" 300 -- "${B[@]}"; kd "$CELL"; logs "$CELL" ;;
  a5)
    # The marker files hold epoch seconds; compare.py converts them with t0_epoch from a5.csv.meta.json.
    sample a5 120 -- bash -c "\"\$@\"; rc=\$?; date +%s.%N > '$OUT/a5.build_end'; sleep 20; date +%s.%N > '$OUT/a5.stop_at'; ./gradlew --stop; exit \$rc" _ "${B[@]}"
    kd a5; logs a5 ;;
  a6)
    sample a6 120 -- "${B[@]}" --no-daemon; kd a6; logs a6 ;;
  *) echo "unknown cell $CELL" >&2; exit 2 ;;
esac
stop
