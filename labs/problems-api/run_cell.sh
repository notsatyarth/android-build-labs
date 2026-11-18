#!/bin/bash
# One cell of the problems-api lab: apply the cell's version override to a nowinandroid clone, run the build through
# the Tooling API problems runner, then record the resolved plugin versions.
# Usage: run_cell.sh NIA_DIR CELL OUT_DIR TAPI_CLASSPATH
# Cells (same task and base arguments in all):
#   c1-k230             Kotlin as pinned (2.3.0), AGP as pinned
#   c2-k230-agp         c1 plus -Pandroid.enableProblemsAPI=true
#   c3-k2421-agp        Kotlin 2.4.21 (version catalog override) plus -Pandroid.enableProblemsAPI=true
#   c4-k2421-agp-next   c3 plus -Pkotlin.experimental.tryNext=true
set -eu
NIA=$1; CELL=$2; OUT=$3; CP=$4
HERE=$(cd "$(dirname "$0")" && pwd)
TASK=":app:assembleDemoDebug"
# --rerun-tasks and --no-build-cache: problems are reported only by tasks that execute
ARGS=(--rerun-tasks --no-build-cache --warning-mode=all)
CAT="$NIA/gradle/libs.versions.toml"
set_kotlin() {
  grep -qx 'kotlin = "2.3.0"' "$CAT" || { echo "catalog: kotlin is not \"2.3.0\""; exit 1; }
  sed -i.bak "s/^kotlin = \"2.3.0\"\$/kotlin = \"$1\"/" "$CAT" && rm "$CAT.bak"
  grep -qx "kotlin = \"$1\"" "$CAT"
}
case "$CELL" in
  c1-k230) ;;
  c2-k230-agp) ARGS+=(-Pandroid.enableProblemsAPI=true) ;;
  c3-k2421-agp) set_kotlin 2.4.21; ARGS+=(-Pandroid.enableProblemsAPI=true) ;;
  c4-k2421-agp-next) set_kotlin 2.4.21; ARGS+=(-Pandroid.enableProblemsAPI=true -Pkotlin.experimental.tryNext=true) ;;
  *) echo "unknown cell $CELL"; exit 2 ;;
esac
mkdir -p "$OUT"
{
  echo "cell=$CELL"
  echo "nia=$(git -C "$NIA" rev-parse HEAD)"
  echo "task=$TASK"
  echo "args=${ARGS[*]}"
  echo "catalog_kotlin=$(sed -n 's/^kotlin = "\(.*\)"$/\1/p' "$CAT")"
  echo "catalog_agp=$(sed -n 's/^androidGradlePlugin = "\(.*\)"$/\1/p' "$CAT")"
  echo "catalog_ksp=$(sed -n 's/^ksp = "\(.*\)"$/\1/p' "$CAT")"
  echo "java=$(java -version 2>&1 | head -1)"
} > "$OUT/cell.txt"
cat "$OUT/cell.txt"
# The runner exits 0 whether the build passes or fails; outcome is in runner.json. A non-zero exit is a harness error.
java -cp "$CP" "$HERE/ProblemsRunner.java" "$NIA" "$OUT" "$TASK" -- "${ARGS[@]}"
# Resolved plugin versions on the root build classpath (CLI, same properties as the cell)
EXTRA=()
for a in "${ARGS[@]}"; do case "$a" in -P*) EXTRA+=("$a");; esac; done
(cd "$NIA" && ./gradlew --console=plain buildEnvironment "${EXTRA[@]}" > "$OUT/buildEnvironment.log" 2>&1) || echo "buildEnvironment failed (see log)"
{
  echo "resolved_agp=$(grep -o 'com\.android\.tools\.build:gradle:[^ ]*\( -> [^ ]*\)\?' "$OUT/buildEnvironment.log" | head -1)"
  echo "resolved_kgp=$(grep -o 'org\.jetbrains\.kotlin:kotlin-gradle-plugin:[^ ]*\( -> [^ ]*\)\?' "$OUT/buildEnvironment.log" | head -1)"
  echo "resolved_ksp=$(grep -o 'com\.google\.devtools\.ksp:symbol-processing-gradle-plugin:[^ ]*\( -> [^ ]*\)\?' "$OUT/buildEnvironment.log" | head -1)"
} >> "$OUT/cell.txt"
(cd "$NIA" && ./gradlew --version --console=plain | sed -n 's/^Gradle /gradle=/p') >> "$OUT/cell.txt"
# Gradle's HTML problems report for the app project, kept for comparison (its embedded data is not a public API)
cp "$NIA/build/reports/problems/problems-report.html" "$OUT/" 2>/dev/null || echo "no problems-report.html at the root build dir"
tail -6 "$OUT/cell.txt"
