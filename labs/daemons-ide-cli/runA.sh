#!/bin/bash
# Experiment A: Tooling API (IDE path) versus CLI on the same worktree. Same JDK for both.
# Usage: runA.sh WORKTREE LOGPREFIX [part]  (part 1: same JDK; part 2: IDE JDK differs, then gradle-daemon-jvm.properties)
set -u
LAB=$(cd "$(dirname "$0")" && pwd)
WT="$1"; P="$2"; PART="${3:-1}"
: "${ANDROID_HOME:=$HOME/Library/Android/sdk}"; export ANDROID_HOME
: "${JAVA_HOME:?set JAVA_HOME to a JDK 17 (original runs: Temurin 17.0.13)}"; export JAVA_HOME
export PATH=$JAVA_HOME/bin:$PATH
# Isolated Gradle user home so other agents' `gradlew --stop` (global per Gradle version and user home)
# cannot kill these daemons; dependencies come from the shared cache read-only.
export GRADLE_USER_HOME=${LAB_WORK:-$HOME/labs-work}/guh
export GRADLE_RO_DEP_CACHE=$HOME/.gradle/caches
LIB=$(ls -d $GRADLE_USER_HOME/wrapper/dists/gradle-9.7.1-bin/*/gradle-9.7.1/lib)
CP="${LAB_WORK:-$HOME/labs-work}/tapi-jar/gradle-tooling-api-9.7.1.jar:$LIB/slf4j-api-2.0.17.jar"
TASK=":core:model:compileKotlin"
tapi() { java -cp "$CP" "$LAB/TapiClient.java" "$WT" $TASK "$@"; }
cli() { (cd "$WT" && ./gradlew $TASK --console=plain "$@"); }
step() {  # name, command...
  local n="$1"; shift
  echo "=== $n: $* ($(date +%T))" | tee -a "$P.summary"
  local t0=$(python3 -c 'import time;print(time.time())')
  "$@" > "$P.$n.log" 2>&1; local rc=$?
  local t1=$(python3 -c 'import time;print(time.time())')
  echo "$n rc=$rc wall_s=$(python3 -c "print(round($t1-$t0,1))")" | tee -a "$P.summary"
  grep -E "Starting a Gradle Daemon|Reusing configuration cache|Configuration cache entry (stored|reused)|Calculating task graph as|cannot be reused because|BUILD (SUCCESSFUL|FAILED)|actionable task|Daemon JVM|TAPI " "$P.$n.log" | sed 's/^/    /' | tee -a "$P.summary"
  bash "$LAB/../../tools/procwatch/jvmsnap.sh" "  after-$n" | tee -a "$P.summary"
}
J21=${JAVA21_HOME:?set JAVA21_HOME to a JDK 21 (original runs: Temurin 21.0.9)}
cli21() { (cd "$WT" && JAVA_HOME=$J21 ./gradlew $TASK --console=plain "$@"); }
upd() { (cd "$WT" && ./gradlew updateDaemonJvm --jvm-version=17 --console=plain && echo "--- gradle/gradle-daemon-jvm.properties:" && cat gradle/gradle-daemon-jvm.properties); }
bash "$LAB/../../tools/procwatch/jvmsnap.sh" "  baseline-part$PART" | tee -a "$P.summary"
if [ "$PART" = 1 ]; then
step A1_tapi tapi
step A2_cli cli
step A3_tapi tapi
step A4_tapi_ide tapi -- -Pandroid.injected.invoked.from.ide=true
step A5_cli cli
elif [ "$PART" = 2 ]; then
step A6_tapi_jdk21 env TAPI_JAVA_HOME=$J21 java -cp "$CP" "$LAB/TapiClient.java" "$WT" $TASK
step A7_cli cli
step A8_updateDaemonJvm upd
step A9_cli cli
step A10_tapi_jdk21 env TAPI_JAVA_HOME=$J21 java -cp "$CP" "$LAB/TapiClient.java" "$WT" $TASK
step A11_tapi tapi
step A12_cli cli
fi
if [ "$PART" = 3 ]; then
# updateDaemonJvm failed (no toolchain download repositories); write the minimal file by hand in the worktree only.
printf 'toolchainVersion=17\n' > "$WT/gradle/gradle-daemon-jvm.properties"
echo "wrote $WT/gradle/gradle-daemon-jvm.properties: $(cat $WT/gradle/gradle-daemon-jvm.properties)" | tee -a "$P.summary"
step A13_cli cli
step A14_tapi_jdk21 env TAPI_JAVA_HOME=$J21 java -cp "$CP" "$LAB/TapiClient.java" "$WT" $TASK
step A15_tapi tapi
step A16_cli_jdk21 cli21
step A17_tapi_jdk21_again env TAPI_JAVA_HOME=$J21 java -cp "$CP" "$LAB/TapiClient.java" "$WT" $TASK
fi
if [ "$PART" = 4 ]; then
# Fresh start with the criteria file present: the caller has stopped the lab daemons.
step A18_tapi_jdk21_fresh env TAPI_JAVA_HOME=$J21 java -cp "$CP" "$LAB/TapiClient.java" "$WT" $TASK
step A19_cli_jdk17 cli
step A20_cli_jdk21 cli21
step A21_tapi_noJavaHome tapi
fi
if [ "$PART" = 5 ]; then
step A22_cli_jdk21 cli21
step A23_cli_jdk17 cli
fi
