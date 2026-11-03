#!/usr/bin/env python3
"""Does `-x <task>` make Gradle configure the (Android) projects again?

Runs the samples/missing-dimension project (AGP 9.3.2, Gradle 9.7.1, 4 Android modules, 4 variants
each) several times and counts configuration markers (init-markers.gradle) per run:
  LAB_CONFIGURED <project>  one per configured project
  LAB_VARIANT <project> <v> one per AGP variant created (AGP's own configuration work)
A run with 0 markers did not configure; a run with markers did.

Series NOCC: configuration cache off. Series CC: --configuration-cache on.
Each series: build, build again, build with -x, build with -x again, plus controls.

Usage (JAVA_HOME 17 and ANDROID_HOME set, from anywhere):
  python3 run.py [--logs logs] [--summary summary.md] [--exclude :app:mergeEmulatorDebugAssets]
Exit code 0 when the runs completed; the verdict table and checks are in the summary.
"""
import argparse, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "..", "samples", "missing-dimension")
TARGET = ":app:assembleEmulatorDebug"
CANDIDATES = [":app:mergeEmulatorDebugAssets", ":app:generateEmulatorDebugResValues", ":app:compileEmulatorDebugJavaWithJavac"]
OTHER_TARGET = ":app:assembleRealdeviceDebug"


def copy_project(dst):
    shutil.copytree(SAMPLE, dst, ignore=shutil.ignore_patterns(".gradle", "build", "logs", "local.properties"))


def gradle(proj, args, log, cc):
    cmd = ["./gradlew", "--console=plain", "-I", os.path.join(HERE, "init-markers.gradle"),
           "--configuration-cache" if cc else "--no-configuration-cache"] + args
    p = subprocess.run(cmd, cwd=proj, capture_output=True, text=True)
    out = p.stdout + p.stderr
    open(log, "w").write("$ " + " ".join(cmd) + "\n" + out)
    return p.returncode, out


def summarize(out):
    configured = len(re.findall(r"^LAB_CONFIGURED ", out, re.M))
    variants = len(re.findall(r"^LAB_VARIANT ", out, re.M))
    android = len(set(re.findall(r"^LAB_VARIANT (\S+) ", out, re.M)))
    cc = ""
    for pat in ("Reusing configuration cache", "Calculating task graph as [^\n]*", "Configuration cache entry stored", "Configuration cache entry reused"):
        m = re.search(pat, out)
        if m:
            cc = m.group(0).strip()
            break
    return configured, variants, android, cc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="logs")
    ap.add_argument("--summary")
    ap.add_argument("--exclude", help="task to pass to -x (default: first candidate present in the task graph)")
    a = ap.parse_args()
    os.makedirs(a.logs, exist_ok=True)
    work = tempfile.mkdtemp(prefix="exclude-task-config-")
    rows, checks = [], []
    exclude = a.exclude
    for series, cc in (("NOCC", False), ("CC", True)):
        proj = os.path.join(work, series)
        copy_project(proj)
        if exclude is None:
            _, out = gradle(proj, [TARGET, "--dry-run"], os.path.join(a.logs, "discover.log"), False)
            exclude = next((t for t in CANDIDATES if re.search(re.escape(t) + r"\s+SKIPPED", out)), None)
            if exclude is None:
                sys.exit("none of the candidate tasks is in the task graph of " + TARGET + "; see discover.log")
        steps = [
            ("1 build", [TARGET]),
            ("2 same build again", [TARGET]),
            ("3 build with -x", [TARGET, "-x", exclude]),
            ("4 build with -x again", [TARGET, "-x", exclude]),
            ("5 original build again", [TARGET]),
            ("6 control: other target, no -x", [OTHER_TARGET]),
        ]
        for name, args in steps:
            log = os.path.join(a.logs, f"{series}-{name.split()[0]}.log")
            rc, out = gradle(proj, args, log, cc)
            configured, variants, android, ccmsg = summarize(out)
            rows.append((series, name, " ".join(args), rc, configured, variants, android, ccmsg))
    by = {(r[0], r[1].split()[0]): r for r in rows}
    def cfg(s, n): return by[(s, n)][4]
    checks = [
        ("NOCC: step 2 (same build again) configures again", cfg("NOCC", "2") > 0),
        ("NOCC: step 3 (-x) configures", cfg("NOCC", "3") > 0),
        ("NOCC: step 4 (-x again) configures again", cfg("NOCC", "4") > 0),
        ("CC: step 1 configures and stores an entry", cfg("CC", "1") > 0),
        ("CC: step 2 (same build) reuses the entry, 0 markers", cfg("CC", "2") == 0),
        ("CC: step 3 (-x) does NOT reuse it: configures again", cfg("CC", "3") > 0),
        ("CC: step 4 (-x again) reuses the -x entry, 0 markers", cfg("CC", "4") == 0),
        ("CC: step 5 (original build) still reuses its entry, 0 markers", cfg("CC", "5") == 0),
        ("CC: step 6 (other target, no -x) configures: -x is not special", cfg("CC", "6") > 0),
    ]
    lines = [f"Excluded task: `{exclude}`. AGP 9.3.2, Gradle 9.7.1, JDK 17, sample `missing-dimension` (4 Android modules).", "",
             "| series | step | args | exit | projects configured | AGP variants created | Android modules with variants | Gradle message |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | `{r[2]}` | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
    lines += ["", "| check | result |", "|---|---|"] + [f"| {n} | {'PASS' if ok else 'FAIL'} |" for n, ok in checks]
    text = "\n".join(lines) + "\n"
    print(text)
    if a.summary:
        open(a.summary, "a").write(text)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
