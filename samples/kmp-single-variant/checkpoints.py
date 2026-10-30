#!/usr/bin/env python3
"""Flavored app consuming a single-variant KMP library: replay checkpoints c1, c2, c3, c3b, c3c.

c1  :shared on com.android.kotlin.multiplatform.library; app has 3 build types x 2 flavor dimensions (12 variants)
c2  buildTypes {} inside the KMP library's android {} block
c3  legacy KMP (org.jetbrains.kotlin.multiplatform + androidTarget() + com.android.library) on AGP 9.3.2
c3b c3 with -Pandroid.builtInKotlin=false
c3c c3 with -Pandroid.builtInKotlin=false -Pandroid.newDsl=false

The original lab kept c1 to c3 on git branches; this script writes :shared's build file per checkpoint.
The committed sample is the c3 state; it is written back at the end.
Usage (from this directory, ANDROID_HOME and JAVA_HOME 17 set):
  python3 checkpoints.py [--only c1,c3] [--logs logs] [--summary summary.md]
"""
import glob, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

SHARED_KMP_LIB = '''plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("com.android.kotlin.multiplatform.library")
}
kotlin {
    android {
        namespace = "lab.shared"
        compileSdk = 36
        minSdk = 24
%s    }
    jvm()
}
'''
SHARED_LEGACY = '''plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("com.android.library")
}
android { namespace = "lab.shared"; compileSdk = 36; defaultConfig { minSdk = 24 } }
kotlin {
    androidTarget()
    jvm()
}
'''
STATES = {
    "c1": SHARED_KMP_LIB % "",
    "c2": SHARED_KMP_LIB % '        buildTypes { getByName("debug") { } }\n',
    "c3": SHARED_LEGACY, "c3b": SHARED_LEGACY, "c3c": SHARED_LEGACY,
}
ARGS = {
    "c1": ["assemble"],
    "c2": ["help"],
    "c3": ["help"],
    "c3b": ["help", "-Pandroid.builtInKotlin=false"],
    "c3c": ["help", "-Pandroid.builtInKotlin=false", "-Pandroid.newDsl=false"],
}


def gradle(log, *args):
    with open(log, "w") as f:
        f.write("$ ./gradlew " + " ".join(args) + "\n")
        f.flush()
        rc = subprocess.run(["./gradlew", "--console=plain", *args], cwd=HERE, stdout=f, stderr=subprocess.STDOUT).returncode
    return rc, open(log, errors="replace").read()


def has(t, s):
    return s in t


def run_cp(cp, logs):
    open(os.path.join(HERE, "shared/build.gradle.kts"), "w").write(STATES[cp])
    rc, t = gradle(os.path.join(logs, f"{cp}.log"), *ARGS[cp])
    f = {"rc": rc}
    if cp == "c1":
        f["apks"] = len(glob.glob(os.path.join(HERE, "app/build/outputs/apk/**/*.apk"), recursive=True))
        _, ins = gradle(os.path.join(logs, "c1-insight.log"), ":app:dependencyInsight",
                        "--configuration", "paidAmazonStagingRuntimeClasspath", "--dependency", ":shared")
        f["variant"] = (re.findall(r"Variant (\w+):", ins) or ["?"])[0]
        # Attribute rows where the consumer requests a value and :shared provides none.
        f["unprovided"] = sorted(set(m.group(1) for m in re.finditer(
            r"\|\s*(com\.android\.build\.api\.attributes\.(?:BuildTypeAttr|ProductFlavor:\w+))\s*\|\s*\|\s*\w+\s*\|", ins)))
        ci = f"rc {rc}; {f['apks']} APKs; :shared variant {f['variant']}; requested but not provided: {', '.join(f['unprovided']) or 'none'}"
        same = rc == 0 and f["apks"] == 12 and f["variant"] == "androidRuntimeElements" and len(f["unprovided"]) == 3
    elif cp == "c2":
        f["unresolved"] = has(t, "Unresolved reference 'buildTypes'.")
        ci = f"rc {rc}; " + ("script compilation error: Unresolved reference 'buildTypes'." if f["unresolved"] else "no 'Unresolved reference buildTypes'")
        same = rc != 0 and f["unresolved"]
    elif cp == "c3":
        f["agp_msg"] = has(t, "plugin is not compatible with the 'org.jetbrains.kotlin.multiplatform' plugin since AGP 9.0.")
        ci = f"rc {rc}; AGP message 'not compatible with the org.jetbrains.kotlin.multiplatform plugin since AGP 9.0': {f['agp_msg']}"
        same = rc != 0 and f["agp_msg"]
    elif cp == "c3b":
        f["kgp_msg"] = has(t, "enabled is not compatible with AGP's 9.0 new DSL")
        f["cce"] = has(t, "cannot be cast to class com.android.build.gradle.BaseExtension")
        f["agp_msg"] = has(t, "plugin is not compatible with the 'org.jetbrains.kotlin.multiplatform' plugin since AGP 9.0.")
        ci = f"rc {rc}; KGP 'androidTarget() ... not compatible with AGP's 9.0 new DSL': {f['kgp_msg']}; ClassCastException to BaseExtension: {f['cce']}"
        same = rc != 0 and f["kgp_msg"] and f["cce"]
    else:
        f["newdsl_warn"] = has(t, "The option setting 'android.newDsl=false' is deprecated.")
        f["androidtarget_warn"] = has(t, "plugin will not be compatible with most of the Android Gradle plugins since Android Gradle Plugin version 9.0.0")
        ci = f"rc {rc}; newDsl=false deprecation warning: {f['newdsl_warn']}; androidTarget() deprecation warning: {f['androidtarget_warn']}"
        same = rc == 0 and f["newdsl_warn"] and f["androidtarget_warn"]
    return ci, f, same


def main():
    args = sys.argv[1:]
    only = args[args.index("--only") + 1].split(",") if "--only" in args else None
    logs = os.path.abspath(args[args.index("--logs") + 1] if "--logs" in args else os.path.join(HERE, "logs"))
    summary = args[args.index("--summary") + 1] if "--summary" in args else None
    os.makedirs(logs, exist_ok=True)
    rows, facts = [], {}
    try:
        for c in json.load(open(os.path.join(HERE, "checkpoints.json"))):
            if only and c["id"] not in only:
                continue
            ci, f, same = run_cp(c["id"], logs)
            facts[c["id"]] = f
            rows.append(f"| {c['id']} | {c['change']} | {c['mac']} | {ci} | {'same' if same else '**DIFFERENT**'} |")
            print(rows[-1], flush=True)
    finally:
        open(os.path.join(HERE, "shared/build.gradle.kts"), "w").write(STATES["c3"])
        subprocess.run(["./gradlew", "--stop"], cwd=HERE, capture_output=True)
    json.dump(facts, open(os.path.join(logs, "facts.json"), "w"), indent=1)
    table = ["| Checkpoint | Change | macOS outcome | CI outcome | Same? |", "|---|---|---|---|---|"] + rows
    if summary:
        open(summary, "a").write("\n".join(table) + "\n")
    print("\n".join(table))


if __name__ == "__main__":
    main()
