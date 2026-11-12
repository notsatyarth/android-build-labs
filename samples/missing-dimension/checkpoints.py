#!/usr/bin/env python3
"""missingDimensionStrategy pitfall: replay checkpoints 1 to 5 of the original lab.

The original lab edited the build files between checkpoints (one git commit each). This script
writes the files of each checkpoint, runs the same Gradle commands and checks the outcome, so the
whole sequence runs unattended. The committed sample is the state of checkpoint 5; the script
writes that state back at the end.

Usage (from this directory, ANDROID_HOME and JAVA_HOME 17 set):
  python3 checkpoints.py [--only 1b,2] [--logs logs] [--summary summary.md]
Expected outcomes from the original macOS run are in checkpoints.json ("mac").
Exit code 0 when every checkpoint ran (a failing Gradle build is an expected outcome, not an error);
the comparison is in the summary table.
"""
import glob, json, os, re, shutil, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

INTERMEDIATE = {
    # no strategy, no flavors
    "plain": 'plugins {{ id("com.android.library") }}\nandroid {{\n    namespace = "lab.{m}"; compileSdk = 36\n    defaultConfig {{ minSdk = 24 }}\n}}\ndependencies {{ implementation(project(":leaf")) }}\n',
    "strategy": 'plugins {{ id("com.android.library") }}\nandroid {{\n    namespace = "lab.{m}"; compileSdk = 36\n    defaultConfig {{ minSdk = 24 ; missingDimensionStrategy("target", "emulator") }}\n}}\ndependencies {{ implementation(project(":leaf")) }}\n',
    "flavors": 'plugins {{ id("com.android.library") }}\nandroid {{\n    namespace = "lab.{m}"; compileSdk = 36\n    defaultConfig {{ minSdk = 24  }}\n}}\nandroid {{ flavorDimensions += "target"; productFlavors {{ create("emulator") {{ dimension = "target" }}; create("realdevice") {{ dimension = "target" }} }} }}\ndependencies {{ implementation(project(":leaf")) }}\n',
}


def app_build(res_values, minify):
    return ('plugins { id("com.android.application") }\nandroid {\n    namespace = "lab.app"; compileSdk = 36\n'
            + ('    buildFeatures { resValues = true }\n' if res_values else '')
            + '    defaultConfig { applicationId = "lab.app"; minSdk = 24 }\n'
            + ('    buildTypes { getByName("release") { isMinifyEnabled = true; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt")) } }\n' if minify else '')
            + '    flavorDimensions += "target"\n    productFlavors {\n'
            '        create("emulator") { dimension = "target"; resValue("string", "name_app_module", "App Emulator") }\n'
            '        create("realdevice") { dimension = "target"; resValue("string", "name_app_module", "App Real Device") }\n'
            '    }\n}\n'
            'dependencies { implementation(project(":intermediate1")); implementation(project(":intermediate2")); implementation(project(":leaf")) }\n')


def leaf_build(res_values):
    return ('plugins { id("com.android.library") }\nandroid {\n    namespace = "lab.leaf"; compileSdk = 36\n'
            + ('    buildFeatures { resValues = true }\n' if res_values else '')
            + '    defaultConfig { minSdk = 24 }\n    flavorDimensions += "target"\n    productFlavors {\n'
            '        create("emulator") { dimension = "target"; resValue("string", "name_leaf_module", "Leaf module Emulator") }\n'
            '        create("realdevice") { dimension = "target"; resValue("string", "name_leaf_module", "Leaf module Real Device") }\n'
            '    }\n}\n')


READER = "package lab.intermediate1;\npublic final class Reader { public static String read() { return lab.leaf.FakeSensor.read(); } }\n"
FAKE = 'package lab.leaf;\n/** Exists only in the emulator flavor of :leaf. */\npublic final class FakeSensor { public static String read() { return "fake"; } }\n'
MAIN = "package lab.app;\npublic final class Main extends android.app.Activity {\n  @Override protected void onCreate(android.os.Bundle b) { super.onCreate(b); setTitle(lab.intermediate1.Reader.read()); }\n}\n"
MANIFEST_PLAIN = "<manifest><application /></manifest>\n"
MANIFEST_MAIN = '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name="lab.app.Main" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>\n'

# Files per checkpoint, as in the original commits.
STATES = {
    "1":  dict(res_values=False, inter="plain", sources=False, app_main=False, minify=False),
    "1b": dict(res_values=True, inter="plain", sources=False, app_main=False, minify=False),
    "2":  dict(res_values=True, inter="strategy", sources=False, app_main=False, minify=False),
    "3":  dict(res_values=True, inter="strategy", sources=True, app_main=False, minify=False),
    "4":  dict(res_values=True, inter="strategy", sources=True, app_main=True, minify=True),
    "5":  dict(res_values=True, inter="flavors", sources=True, app_main=True, minify=True),
    "6":  dict(res_values=True, inter="strategy", sources=True, app_main=True, minify=False),
    "7":  dict(res_values=True, inter="flavors", sources=True, app_main=True, minify=False),
}


def write(rel, text):
    p = os.path.join(HERE, rel)
    if text is None:
        if os.path.exists(p):
            os.remove(p)
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)


def apply_state(s):
    write("app/build.gradle.kts", app_build(s["res_values"], s["minify"]))
    write("leaf/build.gradle.kts", leaf_build(s["res_values"]))
    for m in ("intermediate1", "intermediate2"):
        write(f"{m}/build.gradle.kts", INTERMEDIATE[s["inter"]].format(m=m))
    write("intermediate1/src/main/java/lab/intermediate1/Reader.java", READER if s["sources"] else None)
    write("leaf/src/emulator/java/lab/leaf/FakeSensor.java", FAKE if s["sources"] else None)
    write("app/src/main/java/lab/app/Main.java", MAIN if s["app_main"] else None)
    write("app/src/main/AndroidManifest.xml", MANIFEST_MAIN if s["app_main"] else MANIFEST_PLAIN)


def gradle(log, *args):
    with open(log, "w") as f:
        f.write("$ ./gradlew " + " ".join(args) + "\n")
        f.flush()
        rc = subprocess.run(["./gradlew", "--console=plain", *args], cwd=HERE, stdout=f, stderr=subprocess.STDOUT).returncode
    return rc, open(log, errors="replace").read()


def build_tool(name):
    tools = sorted(glob.glob(os.path.join(os.environ["ANDROID_HOME"], "build-tools", "*", name)))
    return tools[-1] if tools else None


def dex_classes(apk):
    dexdump = build_tool("dexdump")
    out = set()
    with tempfile.TemporaryDirectory() as d, zipfile.ZipFile(apk) as z:
        for n in z.namelist():
            if re.fullmatch(r"classes\d*\.dex", n):
                z.extract(n, d)
                txt = subprocess.run([dexdump, os.path.join(d, n)], capture_output=True, text=True).stdout
                out |= set(re.findall(r"Class descriptor\s+:\s+'L([^;]+);'", txt))
    return {c.replace("/", ".") for c in out}


def apk(flavor, bt="debug"):
    return os.path.join(HERE, f"app/build/outputs/apk/{flavor}/{bt}/app-{flavor}-{bt}.apk")


def res_strings(apk_path):
    return subprocess.run([build_tool("aapt2"), "dump", "resources", apk_path], capture_output=True, text=True).stdout


def first(pattern, text):
    m = re.search(pattern, text)
    return m.group(0).strip() if m else None


def run_cp(cp, logs):
    """Return (ci outcome text, dict of facts) for one checkpoint."""
    L = lambda n: os.path.join(logs, f"cp{cp}-{n}.log")
    facts = {}
    if cp in ("1", "1b"):
        rc, t = gradle(L("assemble"), "assembleRealdeviceDebug")
        facts["rc"] = rc
        facts["resvalues_disabled"] = "contains custom resource values, but the feature is disabled" in t
        facts["ambiguity"] = "cannot choose between the following variants of project ':leaf'" in t
        facts["candidates"] = sorted(set(re.findall(r"(emulatorDebugApiElements|realdeviceDebugApiElements)", t)))
        if cp == "1":
            return (f"rc {rc}; " + ("'contains custom resource values, but the feature is disabled'" if facts["resvalues_disabled"] else first(r"What went wrong:\n.*\n.*", t) or "no failure text")), facts
        return (f"rc {rc}; " + ("ambiguity: cannot choose between " + ", ".join(facts["candidates"]) if facts["ambiguity"] else (first(r"What went wrong:\n.*\n.*", t) or "no ambiguity text"))), facts
    if cp == "2":
        rc, t = gradle(L("assemble"), "assembleRealdeviceDebug", "assembleEmulatorDebug")
        facts["rc"] = rc
        _, i1 = gradle(L("intermediate1-insight"), ":intermediate1:dependencyInsight", "--configuration", "debugCompileClasspath", "--dependency", ":leaf")
        _, ia = gradle(L("app-leaf-insight"), ":app:dependencyInsight", "--configuration", "realdeviceDebugRuntimeClasspath", "--dependency", ":leaf")
        facts["intermediate1_compiles_against"] = (re.findall(r"Variant (\w+):", i1) or ["?"])[0]
        facts["app_realdevice_packages"] = (re.findall(r"Variant (\w+):", ia) or ["?"])[0]
        facts["warning_lines"] = len(re.findall(r"^w(arning)?:.*missingDimension", t, re.M | re.I))
        s_real = res_strings(apk("realdevice")) if rc == 0 else ""
        s_emu = res_strings(apk("emulator")) if rc == 0 else ""
        facts["strings_ok"] = ("Leaf module Real Device" in s_real and "Leaf module Emulator" not in s_real
                               and "Leaf module Emulator" in s_emu and "App Real Device" in s_real)
        return (f"rc {rc}; intermediate1 compiles against leaf {facts['intermediate1_compiles_against']}; "
                f"app realdeviceDebug packages leaf {facts['app_realdevice_packages']}; APK strings per flavor right: {facts['strings_ok']}"), facts
    if cp == "3":
        rc, t = gradle(L("assemble"), "assembleRealdeviceDebug", "assembleEmulatorDebug")
        facts["rc"] = rc
        if rc == 0:
            real, emu = dex_classes(apk("realdevice")), dex_classes(apk("emulator"))
            facts.update(real_reader="lab.intermediate1.Reader" in real, real_fake="lab.leaf.FakeSensor" in real,
                         emu_reader="lab.intermediate1.Reader" in emu, emu_fake="lab.leaf.FakeSensor" in emu)
            return (f"rc {rc}; realdevice APK: Reader {facts['real_reader']}, FakeSensor {facts['real_fake']}; "
                    f"emulator APK: Reader {facts['emu_reader']}, FakeSensor {facts['emu_fake']}"), facts
        return f"rc {rc}; " + (first(r"What went wrong:\n.*\n.*", t) or "build failed"), facts
    if cp == "4":
        rc, t = gradle(L("release"), "assembleRealdeviceRelease")
        facts["rc"] = rc
        m = first(r"ERROR: R8: Missing class .*", t)
        facts["r8_missing"] = m
        return f"rc {rc}; " + (m or first(r"What went wrong:\n.*\n.*", t) or "no R8 error"), facts
    if cp == "5":
        rc, t = gradle(L("assemble"), "assembleRealdeviceDebug")
        facts["rc"] = rc
        task = first(r"Execution failed for task '[^']+'", t)
        sym = "error: cannot find symbol" in t and "class FakeSensor" in t
        facts.update(failed_task=task, cannot_find_symbol=sym)
        return f"rc {rc}; {task}; cannot find symbol FakeSensor: {sym}", facts
    if cp in ("6", "7"):
        # verifyVariantAlignment (verify-variant-alignment.gradle.kts), run for the realdevice debug variant
        rc, t = gradle(L("verify"), "verifyVariantAlignment", "-PalignVariant=realdeviceDebug")
        facts["rc"] = rc
        facts["mismatch_lines"] = re.findall(r"^\s+:\w+ compiles against .*$", t, re.M)
        facts["ok_line"] = "no mismatch" in t
        return (f"rc {rc}; " + ("; ".join(x.strip() for x in facts["mismatch_lines"]) if facts["mismatch_lines"] else
                (first(r"verifyVariantAlignment: .*", t) or first(r"What went wrong:\n.*\n.*", t) or "no output"))), facts
    raise SystemExit(f"unknown checkpoint {cp}")


def verdict(cp, f):
    """same when the CI facts match the macOS outcome recorded in checkpoints.json."""
    if cp == "1":
        return f["rc"] != 0 and f["resvalues_disabled"]
    if cp == "1b":
        return f["rc"] != 0 and f["ambiguity"] and f["candidates"] == ["emulatorDebugApiElements", "realdeviceDebugApiElements"]
    if cp == "2":
        return (f["rc"] == 0 and f["intermediate1_compiles_against"] == "emulatorDebugApiElements"
                and f["app_realdevice_packages"] == "realdeviceDebugRuntimeElements" and f["strings_ok"])
    if cp == "3":
        return f["rc"] == 0 and f.get("real_reader") and not f.get("real_fake") and f.get("emu_reader") and f.get("emu_fake")
    if cp == "4":
        return f["rc"] != 0 and f["r8_missing"] == "ERROR: R8: Missing class lab.leaf.FakeSensor (referenced from: java.lang.String lab.intermediate1.Reader.read())"
    if cp == "6":
        return f["rc"] != 0 and len(f["mismatch_lines"]) == 2 and all("emulator" in l and "realdevice" in l for l in f["mismatch_lines"])
    if cp == "7":
        return f["rc"] == 0 and f["ok_line"]
    if cp == "5":
        return f["rc"] != 0 and f["failed_task"] == "Execution failed for task ':intermediate1:compileRealdeviceDebugJavaWithJavac'" and f["cannot_find_symbol"]


def main():
    args = sys.argv[1:]
    only = args[args.index("--only") + 1].split(",") if "--only" in args else None
    logs = os.path.abspath(args[args.index("--logs") + 1] if "--logs" in args else os.path.join(HERE, "logs"))
    summary = args[args.index("--summary") + 1] if "--summary" in args else None
    os.makedirs(logs, exist_ok=True)
    cps = json.load(open(os.path.join(HERE, "checkpoints.json")))
    rows, facts_all = [], {}
    try:
        for c in cps:
            cp = c["id"]
            if only and cp not in only:
                continue
            apply_state(STATES[cp])
            shutil.rmtree(os.path.join(HERE, "app/build"), ignore_errors=True)
            ci, facts = run_cp(cp, logs)
            facts_all[cp] = facts
            same = "same" if verdict(cp, facts) else "**DIFFERENT**"
            rows.append(f"| {cp} | {c['change']} | {c['mac']} | {ci} | {same} |")
            print(rows[-1], flush=True)
    finally:
        apply_state(STATES["5"])
        subprocess.run(["./gradlew", "--stop"], cwd=HERE, capture_output=True)
    json.dump(facts_all, open(os.path.join(logs, "facts.json"), "w"), indent=1)
    table = ["| Checkpoint | Change | macOS outcome | CI outcome | Same? |", "|---|---|---|---|---|"] + rows
    if summary:
        with open(summary, "a") as f:
            f.write("\n".join(table) + "\n")
    print("\n".join(table))


if __name__ == "__main__":
    main()
