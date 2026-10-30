#!/usr/bin/env bash
# Usage: ./run.sh LABEL AGP KOTLIN KSP GRADLE LAYOUT [extra gradle args...]
#   KOTLIN = a KGP version, or "builtin" (AGP 9 built-in Kotlin, no kotlin-android plugin)
#   LAYOUT = A1 | A2 | A3 | B
#     A1: root buildscript { classpath(AGP) }; KGP + KSP applied (with versions from
#         settings pluginManagement) only in :app's plugins block
#     A2: root buildscript { classpath(AGP) }; KGP + KSP declared "apply false" in the
#         root plugins block, applied in :app
#     A3: root buildscript { classpath(AGP); classpath(KGP) }; KSP only in :app plugins block
#     A4: root buildscript { classpath(AGP's gradle-api artifact only) }; AGP (version from
#         pluginManagement), KGP and KSP applied in :app's plugins block
#     C : like B, plus buildSrc with implementation("com.android.tools.build:gradle-api:AGP")
#         (the setup of google/ksp#2511)
#     Cfix: like C, but buildSrc uses compileOnly(...) (maintainer's advice in google/ksp#2511)
#     B : no buildscript classpath; AGP, KGP, KSP declared "apply false" in the root
#         plugins block (the documented layout), applied in :app
# Writes settings.gradle.kts, build.gradle.kts, app/build.gradle.kts and the wrapper
# properties, runs the build, and records the outcome in logs/LABEL.*
set -u
cd "$(dirname "$0")"
LABEL=$1 AGP=$2 KOTLIN=$3 KSP=$4 GRADLE=$5 LAYOUT=$6; shift 6
# PROC_KOTLIN: version for org.jetbrains.kotlin.jvm in :processor (default = KOTLIN; "none" = no version in pluginManagement)
PROC_KOTLIN=${PROC_KOTLIN:-$KOTLIN}
KSP_API=${KSP_API:-$KSP}

# Portable (GNU and BSD): rewrite the wrapper's distributionUrl without sed -i.
WP=gradle/wrapper/gradle-wrapper.properties
awk -v g="$GRADLE" '/^distributionUrl=/{print "distributionUrl=https\\://services.gradle.org/distributions/gradle-" g "-bin.zip"; next} {print}' "$WP" > "$WP.tmp" && mv "$WP.tmp" "$WP"

if [ "$KOTLIN" = builtin ]; then KPM=""; KAPP=""; KROOT=""; else
  KPM="id(\"org.jetbrains.kotlin.android\") version \"$KOTLIN\""
  KAPP='id("org.jetbrains.kotlin.android")'
  KROOT='id("org.jetbrains.kotlin.android") apply false'
fi

KJVMPM="id(\"org.jetbrains.kotlin.jvm\") version \"$PROC_KOTLIN\""
[ "$PROC_KOTLIN" = none ] && KJVMPM=""
case $LAYOUT in
  A1|A2|A3) AGPPM="" ;;
  A4|C|Cfix) AGPPM="id(\"com.android.application\") version \"$AGP\"" ;;
  B) AGPPM="id(\"com.android.application\") version \"$AGP\"" ;;
esac

cat > settings.gradle.kts <<EOF
pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
    plugins {
        $AGPPM
        $KPM
        id("com.google.devtools.ksp") version "$KSP"
        $KJVMPM
    }
}
dependencyResolutionManagement { repositories { google(); mavenCentral() } }
rootProject.name = "ksp-root-classpath"
include(":app", ":processor")
EOF

BS_KGP=""; [ "$LAYOUT" = A3 ] && BS_KGP="classpath(\"org.jetbrains.kotlin:kotlin-gradle-plugin:$KOTLIN\")"
case $LAYOUT in
  A1) cat > build.gradle.kts <<EOF
buildscript {
    repositories { google(); mavenCentral() }
    dependencies { classpath("com.android.tools.build:gradle:$AGP") }
}
EOF
  ;;
  A2) cat > build.gradle.kts <<EOF
buildscript {
    repositories { google(); mavenCentral() }
    dependencies { classpath("com.android.tools.build:gradle:$AGP") }
}
plugins {
    $KROOT
    id("com.google.devtools.ksp") apply false
}
EOF
  ;;
  A3) cat > build.gradle.kts <<EOF
buildscript {
    repositories { google(); mavenCentral() }
    dependencies {
        classpath("com.android.tools.build:gradle:$AGP")
        $BS_KGP
    }
}
EOF
  ;;
  A4) cat > build.gradle.kts <<EOF
buildscript {
    repositories { google(); mavenCentral() }
    dependencies { classpath("com.android.tools.build:gradle-api:$AGP") }
}
EOF
  ;;
  B|C|Cfix) cat > build.gradle.kts <<EOF
plugins {
    id("com.android.application") apply false
    $KROOT
    id("com.google.devtools.ksp") apply false
}
EOF
  ;;
esac

# buildSrc is switched on and off by renaming (no deletes)
if [ "$LAYOUT" = C ] || [ "$LAYOUT" = Cfix ]; then
  [ -d buildSrc.off ] && mv buildSrc.off buildSrc
  CONF=implementation; [ "$LAYOUT" = Cfix ] && CONF=compileOnly
  cat > buildSrc/build.gradle.kts <<EOF
plugins { \`kotlin-dsl\` }
repositories { google(); mavenCentral(); gradlePluginPortal() }
dependencies { $CONF("com.android.tools.build:gradle-api:$AGP") }
EOF
else
  [ -d buildSrc ] && mv buildSrc buildSrc.off
fi

APPK="$KAPP"; [ "$LAYOUT" = A3 ] && [ "$KOTLIN" != builtin ] && APPK='id("org.jetbrains.kotlin.android")'
cat > app/build.gradle.kts <<EOF
plugins {
    id("com.android.application")
    $APPK
    id("com.google.devtools.ksp")
}
android {
    namespace = "lab.app"
    compileSdk = 35
    defaultConfig { applicationId = "lab.app"; minSdk = 24 }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
dependencies {
    implementation("com.squareup.moshi:moshi:1.15.2")
    ksp("com.squareup.moshi:moshi-kotlin-codegen:1.15.2")
    ksp(project(":processor"))
}
EOF

cat > processor/build.gradle.kts <<EOF
plugins { id("org.jetbrains.kotlin.jvm") }
kotlin { jvmToolchain(17) }
dependencies { implementation("com.google.devtools.ksp:symbol-processing-api:$KSP_API") }
EOF

mkdir -p logs
LOG=logs/$LABEL
{
  echo "# $LABEL AGP=$AGP KOTLIN=$KOTLIN KSP=$KSP GRADLE=$GRADLE LAYOUT=$LAYOUT extra=$*"
  echo "# java: $(java -version 2>&1 | head -1)"
  echo "## settings.gradle.kts"; cat settings.gradle.kts
  echo "## build.gradle.kts"; cat build.gradle.kts
  echo "## processor/build.gradle.kts"; cat processor/build.gradle.kts
  echo "## app/build.gradle.kts"; cat app/build.gradle.kts
  [ -d buildSrc ] && { echo "## buildSrc/build.gradle.kts"; cat buildSrc/build.gradle.kts; }
} > $LOG.log
./gradlew --console=plain :app:clean :app:compileDebugKotlin "$@" >> $LOG.log 2>&1
RC=$?
echo "## exit code $RC" >> $LOG.log
./gradlew --console=plain buildEnvironment "$@" > $LOG.buildenv.txt 2>&1
GEN=$(find app/build/generated/ksp -name '*.kt' 2>/dev/null | sort)
{
  echo "## generated by KSP:"; echo "${GEN:-<none>}"
} >> $LOG.log
echo "$LABEL rc=$RC moshi=$(echo "$GEN" | grep -c JsonAdapter) hello=$(echo "$GEN" | grep -c GreeterHello) kspTask=$(grep -E ':app:kspDebugKotlin' $LOG.log | head -1)"
