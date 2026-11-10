#!/bin/bash
# Capture real Gradle outputs from nowinandroid to use as parser test inputs (feature compatibility probes).
# Usage: run.sh NIA_DIR OUT_DIR
# Cells: cc (configuration cache), ip (configuration cache + Isolated Projects), warn (deprecations, warning-mode all).
# A cell that fails is a result: exit codes are recorded, the script itself only fails if it cannot run.
set -u
NIA=$(cd "$1" && pwd); OUT=$2; mkdir -p "$OUT"
cd "$NIA"
run_cell() {  # name, then gradle args
  local name=$1; shift
  mkdir -p "$OUT/$name"
  echo "== $name: ./gradlew $*"
  ./gradlew --console=plain --stacktrace "$@" > "$OUT/$name/build.log" 2>&1
  echo $? > "$OUT/$name/exit_code"
  # keep every report this cell produced, with its path relative to the project
  find . -path ./node_modules -prune -o \( -name 'configuration-cache-report.html' -o -name 'problems-report.html' \) -print \
    | while read -r f; do
        d="$OUT/$name/reports/$(dirname "$f")"; mkdir -p "$d"; cp "$f" "$d/"
        echo "$f" >> "$OUT/$name/report_paths.txt"
      done
  ./gradlew --stop > /dev/null 2>&1 || true
  # reports are rebuilt per cell
  find . \( -name 'configuration-cache-report.html' -o -name 'problems-report.html' \) -delete 2>/dev/null || true
  rm -rf build/reports 2>/dev/null || true
}
./gradlew --version > "$OUT/gradle_version.txt" 2>&1 || true
run_cell cc   --configuration-cache --warning-mode=all help
run_cell ip   --configuration-cache -Dorg.gradle.unsafe.isolated-projects=true --warning-mode=all help
run_cell warn --warning-mode=all :app:assembleDemoDebug
echo "done"; for c in cc ip warn; do echo "$c exit $(cat "$OUT/$c/exit_code") reports: $(wc -l < "$OUT/$c/report_paths.txt" 2>/dev/null || echo 0)"; done
