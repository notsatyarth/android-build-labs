#!/bin/bash
# Experiment B: Kotlin daemon lifetime with --no-daemon. Two consecutive runs, JVMs sampled every 1 s.
# Usage: runB.sh WORKTREE LOGPREFIX
set -u
LAB=$(cd "$(dirname "$0")" && pwd)
WT="$1"; P="$2"
: "${ANDROID_HOME:=$HOME/Library/Android/sdk}"; export ANDROID_HOME
: "${JAVA_HOME:?set JAVA_HOME to a JDK 17 (original runs: Temurin 17.0.13)}"; export JAVA_HOME
export PATH=$JAVA_HOME/bin:$PATH
export GRADLE_USER_HOME=${LAB_WORK:-$HOME/labs-work}/guh
export GRADLE_RO_DEP_CACHE=$HOME/.gradle/caches
TASK=":core:model:compileKotlin"
sampler() { while true; do bash "$LAB/../../tools/procwatch/jvmsnap.sh" "$(date +%T)" | grep -v jps: >> "$P.samples"; sleep 1; done; }
sampler & SPID=$!
for n in B3 B4; do
  echo "=== $n start $(date +%T)" | tee -a "$P.summary"
  (cd "$WT" && ./gradlew --no-daemon $TASK --rerun-tasks --console=plain --info) > "$P.$n.log" 2>&1
  echo "$n rc=$? end $(date +%T)" | tee -a "$P.summary"
  grep -iE "single-use|kotlin.*daemon|daemon.*kotlin|BUILD|actionable|configuration cache" "$P.$n.log" | sed 's/^/    /' | tee -a "$P.summary"
  c=0; for t in 0 5 15; do sleep $t; c=$((c+t)); bash "$LAB/../../tools/procwatch/jvmsnap.sh" "  $n+${c}s" | grep -v jps: | tee -a "$P.summary"; done
done
kill $SPID
