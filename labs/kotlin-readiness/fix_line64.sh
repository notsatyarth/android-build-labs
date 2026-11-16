#!/bin/bash
# Patch cells (E, F): give SystemTrayNotifier.postNewsNotifications an explicit return type, so the `return` on line 64
# is allowed under language 2.5 (KTLC-288) and the modules behind :core:notifications compile. Commits the change in
# the clone, so the cell's worktree (at HEAD) is a modified nowinandroid commit. Fails unless exactly one line changes.
set -eu
DIR=$1
F=core/notifications/src/main/kotlin/com/google/samples/apps/nowinandroid/core/notifications/SystemTrayNotifier.kt
sed -n '62p' "$DIR/$F" | grep -qx '    ) = with(context) {' || { echo "line 62 is not the expected text"; exit 1; }
sed -i.bak '62s/^    ) = with(context) {$/    ): Unit = with(context) {/' "$DIR/$F" && rm "$DIR/$F.bak"
test "$(git -C "$DIR" diff --numstat | awk '{s+=$1} END {print s}')" = 1
git -C "$DIR" commit -qam "lab: explicit return type for postNewsNotifications (KTLC-288)"
echo "patched: $(git -C "$DIR" log --oneline -1)"
git -C "$DIR" show --stat --format= HEAD
