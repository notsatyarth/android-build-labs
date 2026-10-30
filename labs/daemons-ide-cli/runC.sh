#!/bin/bash
# Experiment C: two worktrees of the same commit building at the same time (as two coding agents would).
# Usage: runC.sh WT1 WT2 LOGPREFIX [TASK] ; each build capped at 20 min with `timeout`.
set -u
LAB=$(cd "$(dirname "$0")" && pwd)
WT1="$1"; WT2="$2"; P="$3"; TASK="${4:-:app:assembleDemoDebug}"
: "${ANDROID_HOME:=$HOME/Library/Android/sdk}"; export ANDROID_HOME
: "${JAVA_HOME:?set JAVA_HOME to a JDK 17 (original runs: Temurin 17.0.13)}"; export JAVA_HOME
export PATH=$JAVA_HOME/bin:$PATH
export GRADLE_USER_HOME=${GUH:-${LAB_WORK:-$HOME/labs-work}/guh}
export GRADLE_RO_DEP_CACHE=$HOME/.gradle/caches
# Memory and load: vm_stat/sysctl on macOS, /proc on Linux.
memsnap() {
  local t; t=$(date +%T)
  if [ -r /proc/meminfo ]; then
    awk -v t="$t" '/^(MemFree|MemAvailable|SwapTotal|SwapFree):/ {printf "%s %s=%s ", t, $1, $2} END{print ""}' /proc/meminfo >> "$P.vmstat"
    echo "$t swap_used_kb: $(awk '/SwapTotal/{a=$2} /SwapFree/{b=$2} END{print a-b}' /proc/meminfo) loadavg: $(cut -d' ' -f1-3 /proc/loadavg)" >> "$P.mem"
  else
    vm_stat | awk -v t="$t" '/Pages free|Pages active|Pages wired|Swapouts|Pageouts/ {gsub("\\.","",$NF); printf "%s %s=%s ", t, $2$3, $NF} END{print ""}' >> "$P.vmstat"
    echo "$t swap: $(sysctl -n vm.swapusage) loadavg: $(sysctl -n vm.loadavg)" >> "$P.mem"
  fi
}
sampler() { while true; do bash "$LAB/../../tools/procwatch/jvmsnap.sh" "$(date +%T)" | grep -v jps: >> "$P.samples"; memsnap; sleep 2; done; }
sampler & SPID=$!
bash "$LAB/../../tools/procwatch/jvmsnap.sh" "  baseline" | tee -a "$P.summary"
run() { local wt="$1" n="$2"; local t0=$(date +%s)
  (cd "$wt" && timeout 1200 ./gradlew $TASK --no-build-cache --console=plain) > "$P.$n.log" 2>&1
  local rc=$?; echo "$n rc=$rc wall_s=$(( $(date +%s) - t0 )) end=$(date +%T)" >> "$P.summary"; }
echo "=== start $(date +%T): $TASK in $WT1 and $WT2 (--no-build-cache)" | tee -a "$P.summary"
run "$WT1" C1 & R1=$!
sleep 1
run "$WT2" C2 & R2=$!
wait $R1 $R2
for n in C1 C2; do grep -E "Starting a Gradle Daemon|BUILD|actionable|Timeout|waiting|lock" "$P.$n.log" | sed "s/^/    $n: /" | tee -a "$P.summary"; done
bash "$LAB/../../tools/procwatch/jvmsnap.sh" "  after" | tee -a "$P.summary"
sleep 10
bash "$LAB/../../tools/procwatch/jvmsnap.sh" "  after+10s" | tee -a "$P.summary"
kill $SPID
cat "$P.summary"
