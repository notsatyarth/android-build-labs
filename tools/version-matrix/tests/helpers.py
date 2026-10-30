"""Test helpers: sys.path setup and a fake project with a fake ./gradlew (no real Gradle involved)."""
import os
import stat
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
FIX = os.path.join(HERE, "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), "r", encoding="utf-8") as f:
        return f.read()


CATALOG = '''[versions]
androidGradlePlugin = "9.3.2"  # keep with tools
kotlin = "2.3.0"
ksp = "2.3.4"
other = "1.0"

[libraries]
kotlin-stdlib = { group = "org.jetbrains.kotlin", name = "kotlin-stdlib", version.ref = "kotlin" }

[plugins]
android-application = { id = "com.android.application", version.ref = "androidGradlePlugin" }
'''

WRAPPER = '''distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionSha256Sum=abc123
distributionUrl=https\\://services.gradle.org/distributions/gradle-9.7.1-bin.zip
zipStoreBase=GRADLE_USER_HOME
'''

# Reads versions from the files in the cwd, so the harness's edits are observable.
# If $FAKE_IGNORE_AGP is set it always reports AGP 9.3.2 (simulates an ignored override).
FAKE_GRADLEW = r'''#!/bin/sh
cat_ver() { grep "^$1 *=" gradle/libs.versions.toml | sed 's/.*"\(.*\)".*/\1/'; }
gv=$(grep '^distributionUrl' gradle/wrapper/gradle-wrapper.properties | sed 's/.*gradle-\(.*\)-bin.zip/\1/')
agp=$(cat_ver androidGradlePlugin); [ -n "$FAKE_IGNORE_AGP" ] && agp=9.3.2
kt=$(cat_ver kotlin)
case "$*" in
  *--version*) printf '\nGradle %s\n\nKotlin:        2.2.21\nLauncher JVM:  21.0.9\n' "$gv"; exit 0;;
  *--stop*) exit 0;;
  *buildEnvironment*)
    echo "classpath"
    echo "+--- com.android.application:com.android.application.gradle.plugin:$agp"
    echo "+--- org.jetbrains.kotlin:kotlin-gradle-plugin:$kt"
    echo "+--- com.google.devtools.ksp:symbol-processing-gradle-plugin:$(cat_ver ksp)"
    exit 0;;
  *FAILTASK*) echo "FAILURE: Build failed with an exception."; echo; echo "* What went wrong:"
    echo "Execution failed for task ':app:x'."; echo "> org.gradle.api.GradleException boom"; echo; echo "* Try:"
    echo "BUILD FAILED in 1s"; exit 1;;
  *SLEEP*) sleep 30; exit 0;;
esac
echo "The Task.getProject() method has been deprecated. This is scheduled to be removed in Gradle 10.0."
echo "	at org.gradle.api.internal.AbstractTask.getProject(AbstractTask.java:300)"
echo
echo "BUILD SUCCESSFUL in 1s"
'''


def make_project(root, git=False):
    os.makedirs(os.path.join(root, "gradle", "wrapper"), exist_ok=True)
    with open(os.path.join(root, "gradle", "libs.versions.toml"), "w") as f:
        f.write(CATALOG)
    with open(os.path.join(root, "gradle", "wrapper", "gradle-wrapper.properties"), "w") as f:
        f.write(WRAPPER)
    p = os.path.join(root, "gradlew")
    with open(p, "w") as f:
        f.write(FAKE_GRADLEW)
    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
    if git:
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t")
        for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "init"]):
            subprocess.run(["git"] + args, cwd=root, env=env, check=True, stdout=subprocess.DEVNULL)
    return root


def rd(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def wr(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
