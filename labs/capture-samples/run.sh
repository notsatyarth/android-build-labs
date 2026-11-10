#!/bin/bash
# Capture real Gradle outputs to use as parser test inputs (feature compatibility probes).
# Usage: run.sh NIA_DIR OUT_DIR
# nowinandroid cells: cc (configuration cache), ip (+ Isolated Projects), warn (deprecations, warning-mode all).
# synthetic cells (labs/capture-samples/synthetic, deliberate violations, so the reports contain problems):
#   syn-cc (configuration cache problem), syn-ip (Isolated Projects problem).
# A cell that fails is a result: exit codes are recorded, the script itself only fails if it cannot run.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
NIA=$(cd "$1" && pwd); mkdir -p "$2"; OUT=$(cd "$2" && pwd)   # absolute: we cd into the projects below
WORK=$NIA
run_cell() {  # name, then gradle args; runs in $WORK
  local name=$1; shift
  mkdir -p "$OUT/$name"
  echo "== $name: ./gradlew $*"
  ( cd "$WORK" || exit 1
    rm -rf ./.gradle/configuration-cache   # each cell starts without a stored entry
    ./gradlew --console=plain --stacktrace "$@" > "$OUT/$name/build.log" 2>&1
    echo $? > "$OUT/$name/exit_code"
    find . \( -name 'configuration-cache-report.html' -o -name 'problems-report.html' \) -print | while read -r f; do
      d="$OUT/$name/reports/$(dirname "$f")"; mkdir -p "$d"; cp "$f" "$d/"
      echo "$f" >> "$OUT/$name/report_paths.txt"
    done
    ./gradlew --stop > /dev/null 2>&1 || true
    find . \( -name 'configuration-cache-report.html' -o -name 'problems-report.html' \) -delete 2>/dev/null || true
    rm -rf ./build/reports 2>/dev/null || true )
}
( cd "$NIA" && ./gradlew --version ) > "$OUT/gradle_version.txt" 2>&1 || true
run_cell cc   --configuration-cache --warning-mode=all help
run_cell ip   --configuration-cache -Dorg.gradle.unsafe.isolated-projects=true --warning-mode=all help
run_cell warn --warning-mode=all :app:assembleDemoDebug
# synthetic project with nowinandroid's wrapper
SYN=$(mktemp -d); cp -R "$HERE/synthetic/." "$SYN/"; cp "$NIA/gradlew" "$SYN/"; mkdir -p "$SYN/gradle"; cp -R "$NIA/gradle/wrapper" "$SYN/gradle/"
WORK=$SYN
run_cell syn-cc --configuration-cache --warning-mode=all bad
run_cell syn-ip --configuration-cache -Dorg.gradle.unsafe.isolated-projects=true --warning-mode=all bad
echo "done"; for c in cc ip warn syn-cc syn-ip; do echo "$c exit $(cat "$OUT/$c/exit_code") reports: $(wc -l < "$OUT/$c/report_paths.txt" 2>/dev/null || echo 0)"; done
