#!/bin/bash
# Print the resolved build plugin versions of a prepared side (root buildEnvironment) and the Gradle version.
# Usage: versions.sh DIR [extra gradle args]
DIR=$1; shift
cd "$DIR" || exit 1
./gradlew --version 2>/dev/null | grep -E '^(Gradle|Kotlin|Launcher JVM|Daemon JVM)' | sed 's/^/  /'
./gradlew buildEnvironment --no-configuration-cache --console=plain "$@" 2>&1 \
  | grep -oE '(com\.android\.tools\.build:gradle|org\.jetbrains\.kotlin:kotlin-gradle-plugin|org\.jetbrains\.kotlin:compose-compiler-gradle-plugin|com\.google\.devtools\.ksp:symbol-processing-gradle-plugin|com\.google\.devtools\.ksp:symbol-processing-api):[^ ]+( -> [^ ]+)?' \
  | sort -u | sed 's/^/  /'
./gradlew --stop >/dev/null 2>&1; true
