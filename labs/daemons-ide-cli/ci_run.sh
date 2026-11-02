#!/bin/bash
# CI driver for the daemons lab (experiments A, B, C). Usage: ci_run.sh setup|A|B|C   (JAVA_HOME = JDK 17, JAVA21_HOME = JDK 21)
# The work directory name contains "daemons-lab" because jvmsnap.sh uses that string to tell lab JVMs from others.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
export LAB_WORK=${LAB_WORK:?set LAB_WORK, e.g. \$RUNNER_TEMP/daemons-lab}
OUT=${OUT:-$LAB_WORK/out}; mkdir -p "$OUT"
NIA_SHA=${NIA_SHA:-2982e63cb691ad49cd009aab43dc206fee6699c2}
TAPI_URL=https://repo.gradle.org/gradle/libs-releases/org/gradle/gradle-tooling-api/9.7.1/gradle-tooling-api-9.7.1.jar
TAPI_SHA=e40a1f7707e4bf22f8039f6bbcdb012198f0f172d9331963bc7b41eb0ff5051b
clone() { cp -a "$LAB_WORK/nia-src" "$LAB_WORK/$1"; }
stop_all() { pkill -TERM -f "GradleDaemon|KotlinCompileDaemon" 2>/dev/null; sleep 3; pkill -KILL -f "GradleDaemon|KotlinCompileDaemon" 2>/dev/null; return 0; }
case "$1" in
setup)
  mkdir -p "$LAB_WORK/tapi-jar"
  bash "$HERE/../../.github/scripts/clone_nia.sh" "$LAB_WORK/nia-src" "$NIA_SHA"
  curl -sfL -o "$LAB_WORK/tapi-jar/gradle-tooling-api-9.7.1.jar" "$TAPI_URL"
  echo "$TAPI_SHA  $LAB_WORK/tapi-jar/gradle-tooling-api-9.7.1.jar" | sha256sum -c -
  # Prime the shared dependency cache in the default Gradle home (the scripts use it as GRADLE_RO_DEP_CACHE), then drop all daemons.
  clone prime
  (cd "$LAB_WORK/prime" && ./gradlew :app:assembleDemoDebug --console=plain > "$OUT/prime.log" 2>&1; tail -3 "$OUT/prime.log")
  (cd "$LAB_WORK/prime" && ./gradlew --stop >/dev/null 2>&1); stop_all
  rm -rf "$LAB_WORK/prime"
  # Isolated Gradle user home for the lab: only the wrapper distribution is downloaded into it.
  clone wtA
  (cd "$LAB_WORK/wtA" && GRADLE_USER_HOME="$LAB_WORK/guh" ./gradlew --version > "$OUT/wrapper.log" 2>&1; tail -12 "$OUT/wrapper.log")
  ;;
A)
  cd "$OUT" || exit 1
  WT=$LAB_WORK/wtA
  bash "$HERE/runA.sh" "$WT" A 1; bash "$HERE/runA.sh" "$WT" A 2; bash "$HERE/runA.sh" "$WT" A 3
  cp "$WT/gradle/gradle-daemon-jvm.properties" A.gradle-daemon-jvm.properties.used 2>/dev/null
  # Fresh start with the criteria file present (part 4), then part 5 on the same daemons.
  (cd "$WT" && GRADLE_USER_HOME="$LAB_WORK/guh" ./gradlew --stop >/dev/null 2>&1); stop_all
  bash "$HERE/runA.sh" "$WT" A 4; bash "$HERE/runA.sh" "$WT" A 5
  ;;
B)
  cd "$OUT" || exit 1
  clone wtB
  bash "$HERE/runB.sh" "$LAB_WORK/wtB" B
  bash "$HERE/runB_info.sh" "$LAB_WORK/wtB" Binfo
  ;;
C)
  cd "$OUT" || exit 1
  clone wtC1; clone wtC2; clone wtC3; clone wtC4
  stop_all
  GUH=$LAB_WORK/guh bash "$HERE/runC.sh" "$LAB_WORK/wtC1" "$LAB_WORK/wtC2" C
  stop_all
  GUH=$LAB_WORK/guh2 bash "$HERE/runC.sh" "$LAB_WORK/wtC3" "$LAB_WORK/wtC4" C2run
  ;;
esac
