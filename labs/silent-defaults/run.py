#!/usr/bin/env python3
"""Which AGP 9 default changes are silent (green build, different output) and which fail loudly?

For each AGP version the script writes a small Java-only app (targetSdk NOT set, release build with
R8 and obfuscation), builds it, and records from the built APK: targetSdkVersion (aapt2 dump badging)
and the class descriptors in the dex (dexdump): how many obfuscated classes sit in the default
(unnamed) package versus a named package. Then two "loud" probes: a `switch` on an R id, and
getDefaultProguardFile("proguard-android.txt"). On 9.x it also builds with
-Pandroid.sdk.defaultTargetSdkToCompileSdkIfUnset=false to check the documented opt-out.

Usage (JAVA_HOME 17, ANDROID_HOME set):
  python3 run.py [--logs logs] [--summary summary.md] [--only 8.13.2,9.3.2]
"""
import argparse, glob, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WRAPPER_SRC = os.path.join(HERE, "..", "..", "samples", "missing-dimension")
# (AGP, Gradle)
VERSIONS = [("8.13.2", "8.14.3"), ("9.0.1", "9.7.1"), ("9.1.0", "9.7.1"), ("9.3.2", "9.7.1")]
COMPILE_SDK, MIN_SDK = 36, 24

def build_gradle(agp, proguard):
    return f'''plugins {{ id("com.android.application") version "{agp}" }}
android {{
    namespace = "lab.app"; compileSdk = {COMPILE_SDK}
    defaultConfig {{ applicationId = "lab.app"; minSdk = {MIN_SDK} }}
    buildTypes {{ getByName("release") {{ isMinifyEnabled = true; proguardFiles(getDefaultProguardFile("{proguard}")) }} }}
}}
'''

FILES = {
    "app/src/main/AndroidManifest.xml": '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name=".MainActivity" android:exported="true"/></application></manifest>',
    "app/src/main/res/values/ids.xml": '<resources><item name="action_a" type="id"/><item name="action_b" type="id"/></resources>',
    "app/src/main/java/lab/app/MainActivity.java": "package lab.app;\nimport android.app.Activity;\nimport android.os.Bundle;\nimport lab.app.model.User;\nimport lab.app.util.Helper;\npublic class MainActivity extends Activity {\n  @Override protected void onCreate(Bundle b) { super.onCreate(b); setTitle(Helper.greet(new User(\"x\"))); }\n}\n",
    "app/src/main/java/lab/app/model/User.java": "package lab.app.model;\npublic class User { private final String name; public User(String n) { name = n; } public String name() { return name; } }\n",
    "app/src/main/java/lab/app/util/Helper.java": "package lab.app.util;\nimport lab.app.model.User;\npublic class Helper { public static String greet(User u) { return \"hi \" + u.name(); } }\n",
}
SWITCH = "package lab.app;\npublic class Switchy { public static int f(int id) { switch (id) { case R.id.action_a: return 1; case R.id.action_b: return 2; default: return 0; } } }\n"

def tool(name):
    ah = os.environ["ANDROID_HOME"]
    c = sorted(glob.glob(os.path.join(ah, "build-tools", "*", name)))
    return c[-1] if c else None

def write_project(proj, agp, gradle, proguard="proguard-android-optimize.txt", switch=False):
    if os.path.exists(proj): shutil.rmtree(proj)
    os.makedirs(proj)
    for f in ("gradlew", "gradlew.bat"):
        if os.path.exists(os.path.join(WRAPPER_SRC, f)): shutil.copy(os.path.join(WRAPPER_SRC, f), proj)
    shutil.copytree(os.path.join(WRAPPER_SRC, "gradle"), os.path.join(proj, "gradle"))
    open(os.path.join(proj, "gradle/wrapper/gradle-wrapper.properties"), "w").write(
        f"distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\ndistributionUrl=https\\://services.gradle.org/distributions/gradle-{gradle}-bin.zip\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n")
    open(os.path.join(proj, "settings.gradle.kts"), "w").write(
        'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\ndependencyResolutionManagement { repositories { google(); mavenCentral() } }\nrootProject.name = "silent"\ninclude(":app")\n')
    open(os.path.join(proj, "gradle.properties"), "w").write("org.gradle.jvmargs=-Xmx2g\n")
    for p, t in FILES.items():
        os.makedirs(os.path.dirname(os.path.join(proj, p)), exist_ok=True)
        open(os.path.join(proj, p), "w").write(t)
    open(os.path.join(proj, "app/build.gradle.kts"), "w").write(build_gradle(agp, proguard))
    if switch:
        open(os.path.join(proj, "app/src/main/java/lab/app/Switchy.java"), "w").write(SWITCH)

def gradle(proj, args, log):
    p = subprocess.run(["./gradlew", "--console=plain", "--no-daemon", "--warning-mode=all"] + args, cwd=proj, capture_output=True, text=True)
    out = p.stdout + p.stderr
    open(log, "w").write("$ ./gradlew " + " ".join(args) + "\n" + out)
    return p.returncode, out

def first_error(out):
    m = re.search(r"(?:error:|What went wrong:\n)([^\n]*\n?[^\n]*)", out)
    return re.sub(r"\s+", " ", m.group(0)).strip()[:200] if m else ""

def warnings(out):
    return len(re.findall(r"(?i)^(?:warning|w:).*|deprecat", out, re.M))

def inspect_apk(proj):
    apks = glob.glob(os.path.join(proj, "app/build/outputs/apk/release/*.apk"))
    if not apks: return None
    apk = apks[0]
    badging = subprocess.run([tool("aapt2"), "dump", "badging", apk], capture_output=True, text=True).stdout
    t = re.search(r"targetSdkVersion:'(\d+)'", badging); m = re.search(r"sdkVersion:'(\d+)'", badging)
    dump = subprocess.run([tool("dexdump"), apk], capture_output=True, text=True).stdout
    classes = re.findall(r"Class descriptor\s+:\s+'([^']+)'", dump)
    lab = [c for c in classes if not c.startswith(("Landroid", "Ljava", "Lkotlin", "Landroidx", "Lcom/"))]
    default_pkg = [c for c in lab if "/" not in c]
    named = [c for c in lab if "/" in c]
    return {"target": t.group(1) if t else "?", "min": m.group(1) if m else "?",
            "classes": len(lab), "default_pkg": len(default_pkg), "named_pkg": len(named), "named_examples": ", ".join(sorted(named)[:4])}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="logs"); ap.add_argument("--summary"); ap.add_argument("--only")
    a = ap.parse_args()
    os.makedirs(a.logs, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    work = tempfile.mkdtemp(prefix="silent-defaults-")
    rows, loud, optout = [], [], []
    for agp, gv in VERSIONS:
        if only and agp not in only: continue
        proj = os.path.join(work, agp)
        write_project(proj, agp, gv)
        rc, out = gradle(proj, [":app:assembleRelease"], os.path.join(a.logs, f"{agp}-base.log"))
        info = inspect_apk(proj) if rc == 0 else None
        rows.append((agp, gv, rc, warnings(out), info, first_error(out) if rc else ""))
        if info and not agp.startswith("8."):
            rc2, out2 = gradle(proj, [":app:assembleRelease", "-Pandroid.sdk.defaultTargetSdkToCompileSdkIfUnset=false", "--rerun-tasks"], os.path.join(a.logs, f"{agp}-optout.log"))
            i2 = inspect_apk(proj) if rc2 == 0 else None
            optout.append((agp, rc2, i2["target"] if i2 else "?"))
        write_project(proj, agp, gv, switch=True)
        rc3, out3 = gradle(proj, [":app:assembleDebug"], os.path.join(a.logs, f"{agp}-switch.log"))
        write_project(proj, agp, gv, proguard="proguard-android.txt")
        rc4, out4 = gradle(proj, [":app:assembleRelease"], os.path.join(a.logs, f"{agp}-proguardtxt.log"))
        loud.append((agp, rc3, first_error(out3) if rc3 else "", rc4, first_error(out4) if rc4 else ""))
    L = [f"compileSdk {COMPILE_SDK}, minSdk {MIN_SDK}, targetSdk NOT set, Java-only app, release with R8 (proguard-android-optimize.txt).", "",
         "| AGP | Gradle | build exit | warning/deprecation lines | targetSdk in APK | classes in default package | classes in named packages | examples |", "|---|---|---|---|---|---|---|---|"]
    for agp, gv, rc, w, i, err in rows:
        L.append(f"| {agp} | {gv} | {rc} | {w} | {i['target'] if i else '-'} | {i['default_pkg'] if i else '-'} | {i['named_pkg'] if i else '-'} | {i['named_examples'] if i else err} |")
    L += ["", "Opt-out `-Pandroid.sdk.defaultTargetSdkToCompileSdkIfUnset=false` (9.x):", "", "| AGP | build exit | targetSdk in APK |", "|---|---|---|"]
    L += [f"| {x[0]} | {x[1]} | {x[2]} |" for x in optout]
    L += ["", "Loud probes (does the build fail?):", "", "| AGP | `switch` on R.id: exit | message | `proguard-android.txt`: exit | message |", "|---|---|---|---|---|"]
    L += [f"| {x[0]} | {x[1]} | {x[2]} | {x[3]} | {x[4]} |" for x in loud]
    text = "\n".join(L) + "\n"
    print(text)
    if a.summary: open(a.summary, "a").write(text)
    shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    main()
