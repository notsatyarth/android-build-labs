#!/bin/bash
# Next-version switches on nowinandroid (experiments e0 to e6c of the original macOS lab).
# Usage: run.sh NIA_DIR OUT_DIR     env: JAVA17_HOME, JAVA21_HOME (JDKs), ANDROID_HOME. NIA_DIR must be a git checkout (reset between experiments).
# Each experiment writes OUT_DIR/<id>.log with a header (branch, JDK, command) followed by the Gradle output.
set -u
NIA=$(cd "$1" && pwd); OUT=$(mkdir -p "$2" && cd "$2" && pwd)
: "${JAVA17_HOME:?}"; : "${JAVA21_HOME:?}"
SHA=$(git -C "$NIA" rev-parse --short HEAD)

reset() { git -C "$NIA" checkout -q -- . && git -C "$NIA" clean -fdxq; }
stop() { (cd "$NIA" && JAVA_HOME=$JAVA17_HOME ./gradlew --stop >/dev/null 2>&1); pkill -KILL -f "GradleDaemon|KotlinCompileDaemon" 2>/dev/null; sleep 2; return 0; }
# edits (the original lab kept these on local branches)
ed_simulate_fixed() { sed -i '/^android.useAndroidX=/d;/^android.defaults.buildfeatures.resvalues=/d;/^android.defaults.buildfeatures.shaders=/d' "$NIA/gradle.properties"; }
ed_no_implicit_lookup() { echo 'enableFeaturePreview("NO_IMPLICIT_LOOKUP_IN_PARENT_PROJECTS")' >> "$NIA/settings.gradle.kts"; }
bl_set() { for k in "$@"; do sed -i "s/^$k=true/$k=false/" "$NIA/build-logic/gradle.properties"; done; }
ed_bl_cc_off() { bl_set org.gradle.configuration-cache; }
ed_bl_caching_off() { bl_set org.gradle.caching; }
ed_bl_all_flipped() { bl_set org.gradle.parallel org.gradle.caching org.gradle.configuration-cache org.gradle.configuration-cache.parallel; }
ed_seam_kotlin_android() { sed -i '0,/^plugins {/s//plugins {\n    id("org.jetbrains.kotlin.android")/' "$NIA/core/analytics/build.gradle.kts"; }

# exp ID JDK(17|21) EDIT|- "gradle args..."
exp() {
  local id=$1 jdk=$2 edit=$3; shift 3
  local jh=$JAVA17_HOME; [ "$jdk" = 21 ] && jh=$JAVA21_HOME
  [ "$edit" != "-" ] && { reset; "ed_$edit"; }
  stop   # AGP reports some deprecations once per daemon, so each experiment starts with fresh daemons (as in the macOS lab)
  { echo "# experiment: $id  nowinandroid $SHA  edit=$edit"; echo "# JAVA_HOME=$jh"; "$jh/bin/java" -version 2>&1 | head -1; echo "# cmd: ./gradlew $*"; } > "$OUT/$id.log"
  (cd "$NIA" && JAVA_HOME=$jh ./gradlew "$@" --console=plain >> "$OUT/$id.log" 2>&1; echo "# build exit=$?" >> "$OUT/$id.log")
  grep -E "BUILD (SUCCESSFUL|FAILED)|# build exit" "$OUT/$id.log" | tr '\n' ' '; echo " <- $id"
}

reset; stop
exp e0_baseline_jdk21 21 - help --warning-mode all
exp e1a_simulate_jdk17 17 - help --warning-mode all -Pandroid.simulateAgpVersionBehavior=10.0.0
exp e1b_simulate_jdk21 21 - help --warning-mode all -Pandroid.simulateAgpVersionBehavior=10.0.0
exp e1c_simulate_jdk21_removed_props 21 simulate_fixed help --warning-mode all -Pandroid.simulateAgpVersionBehavior=10.0.0
exp e1d_simulate_jdk21_assemble 21 - :app:assembleDemoDebug --warning-mode all -Pandroid.simulateAgpVersionBehavior=10.0.0   # same edit as e1c (no reset)
reset
exp e2a_optouts_jdk17 17 - help --warning-mode all -Pandroid.builtInKotlin=false -Pandroid.newDsl=false
exp e2b_newDsl_false_only_jdk17 17 - help --warning-mode all -Pandroid.newDsl=false
exp e2c_optouts_simulate_jdk21 21 - help --warning-mode all -Pandroid.builtInKotlin=false -Pandroid.newDsl=false -Pandroid.simulateAgpVersionBehavior=10.0.0
reset
exp e3a_tryNext_baseline_info 17 - :core:model:compileKotlin --rerun-tasks --no-build-cache --info
exp e3b_tryNext_true_info 17 - :core:model:compileKotlin --rerun-tasks --no-build-cache --info -Pkotlin.experimental.tryNext=true
exp e4a_main_warning_mode_fail 17 - help --warning-mode=fail
exp e4b_no_implicit_lookup 17 no_implicit_lookup help --warning-mode all
# e4c: is the feature preview a constant in the Gradle distribution used by the wrapper?
{ echo "# strings from org/gradle/api/internal/FeaturePreviews\$Feature in the Gradle distribution jars, grep NO_IMPLICIT"
  for d in "${GRADLE_USER_HOME:-$HOME/.gradle}"/wrapper/dists/gradle-*-bin/*/gradle-*/lib; do
    for j in "$d"/*.jar "$d"/plugins/*.jar; do unzip -p "$j" 'org/gradle/api/internal/FeaturePreviews$Feature.class' 2>/dev/null | strings | grep NO_IMPLICIT; done
  done; } > "$OUT/e4c_featurepreview_enum_check.log"
# 5a: configuration-cache=false only in build-logic/gradle.properties, two runs
exp e5a_bl_cc_false_run1 17 bl_cc_off help
exp e5a_bl_cc_false_run2 17 - help
# 5b: caching=false only; populate the local build cache first, then clean build-logic and compile
reset; ed_bl_caching_off
exp e5b_0_populate 17 - :core:model:compileKotlin
exp e5b_1_clean_then_compile 17 - :build-logic:convention:clean :core:model:clean :core:model:compileKotlin --info
exp e5b_2_help_after_clean 17 - help --info
exp e5c_all_flipped 17 bl_all_flipped help --info
# 5d: Kotlin daemon command lines while building the included build-logic and a project module
reset; stop
{ echo "# experiment: e5d  nowinandroid $SHA"
  echo "# cmd: ./gradlew :build-logic:convention:clean :core:model:clean :core:model:compileKotlin --rerun-tasks --no-build-cache --no-configuration-cache --no-isolated-projects"
  ( while true; do ps -eo command= | grep KotlinCompileDaemon | grep -v grep; sleep 1; done ) > "$OUT/e5d.ps" 2>&1 & W=$!
  (cd "$NIA" && JAVA_HOME=$JAVA17_HOME ./gradlew :build-logic:convention:clean :core:model:clean :core:model:compileKotlin --rerun-tasks --no-build-cache --no-configuration-cache --no-isolated-projects --console=plain > "$OUT/e5d.build" 2>&1; echo "# build exit=$?")
  kill $W 2>/dev/null
  echo "# unique KotlinCompileDaemon command lines (compiler jar, JVM flags)"
  sort -u "$OUT/e5d.ps" | python3 -I -c "
import re,sys
seen=set()
for l in sys.stdin:
    comp=re.findall(r'kotlin-(?:build-tools-impl|compiler-embeddable)-[0-9][^/:]*?\.jar', l)
    fl=' '.join(re.findall(r'(?<= )-X[^ ]+|(?<= )-D[^ ]+|(?<= )-XX:[^ ]+', l))
    key=(tuple(sorted(set(comp))), fl)
    if key not in seen: seen.add(key); print('compiler:', ' '.join(sorted(set(comp))), ' flags:', fl)
"; } > "$OUT/e5d_kotlin_daemon_included_build.log"
# 6: seam examples
exp e6a_kotlin_android_plugin 17 seam_kotlin_android help --warning-mode all
exp e6a2_kotlin_android_plugin_with_optouts 17 - help -Pandroid.builtInKotlin=false -Pandroid.newDsl=false
reset
exp e6b_assemble_rerun_warning_mode_all 17 - :app:assembleDemoDebug --rerun-tasks --no-build-cache --warning-mode=all
[ -f "$NIA/build/reports/problems/problems-report.html" ] && cp "$NIA/build/reports/problems/problems-report.html" "$OUT/e6b_problems-report.html"
exp e6c_buildEnvironment 17 - buildEnvironment
stop
