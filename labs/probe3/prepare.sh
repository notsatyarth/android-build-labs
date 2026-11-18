#!/bin/bash
# Prepare one side of a probe-3 pair in DIR (a new directory).
# Usage: prepare.sh DIR SHA [KOTLIN]
#   K pair: SHA = nowinandroid commit, KOTLIN = Kotlin version for the catalog's `kotlin` key (the Compose compiler
#           plugin follows it via version.ref). Applies labs/kotlin-readiness/fix_line64.sh (one line, explicit return
#           type in SystemTrayNotifier.kt) on both sides, then sets the Kotlin version and commits; a side whose
#           catalog already has KOTLIN gets no second commit. Fails unless the diff to SHA is exactly those lines.
#   A pair: SHA only (the commit as it is).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
DIR=$1; SHA=$2; KOTLIN=${3:-}
bash "$HERE/../../.github/scripts/clone_nia.sh" "$DIR" "$SHA"
git -C "$DIR" config user.email ci@example.invalid; git -C "$DIR" config user.name ci
[ -z "$KOTLIN" ] && exit 0
bash "$HERE/../kotlin-readiness/fix_line64.sh" "$DIR"
T=gradle/libs.versions.toml
grep -qE '^kotlin = "[^"]+"$' "$DIR/$T" || { echo "no kotlin key in $T"; exit 1; }
sed -i.bak -E "s/^kotlin = \"[^\"]+\"$/kotlin = \"$KOTLIN\"/" "$DIR/$T" && rm "$DIR/$T.bak"
if [ -n "$(git -C "$DIR" status --porcelain)" ]; then git -C "$DIR" commit -qam "lab: kotlin = $KOTLIN"; fi
echo "side: $(git -C "$DIR" log --oneline -1); catalog: $(grep -E '^(kotlin|ksp|androidGradlePlugin) = ' "$DIR/$T" | tr '\n' ' ')"
echo "diff to $SHA (numstat):"; git -C "$DIR" diff --numstat "$SHA" HEAD
