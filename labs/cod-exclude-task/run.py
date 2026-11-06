#!/usr/bin/env python3
"""Does `-x <task>` defeat configuration on demand?

Writes a synthetic Android project for each AGP version (7.4.2, 8.5.2, 8.13.2, 9.3.2) and root layout
(isolated; root subprojects {}; root allprojects {}; root subprojects {} with plugins.withId): root, :app, :lib1..:lib6.
:lib1 depends on :lib2; :app depends on every library; the other libraries are independent.
Every run uses --no-configuration-cache, so configuration is never skipped by the cache.
init-markers.gradle prints one LAB_CONFIGURED line per project Gradle configured.

Cases (target task :lib1:assembleDebug unless stated):
  A  on-demand off                                   baseline: expect all 8
  B  --configure-on-demand                            expect root, :lib1, :lib2
  C  on-demand, -x <path in :lib1>   e.g. -x :lib1:X   the hypothesis says all 8
  D  on-demand, -x <bare name>       e.g. -x X         name lookup may need all projects
  E  on-demand, -x <path in :lib5>   (unrelated project)
  F  on-demand, requested task given as a bare name (assembleDebug): control, all 8

  G  on-demand, -x a task name that exists in no project
Usage (JAVA_HOME 17, ANDROID_HOME set): python3 run.py [--agp 9.3.2] [--layouts isolated] [--logs logs] [--summary summary.md]
"""
import argparse, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WRAPPER_SRC = os.path.join(HERE, "..", "..", "samples", "missing-dimension")
VERSIONS = {"7.4.2": ("7.6.4", 34), "8.5.2": ("8.7", 34), "8.13.2": ("8.14.3", 36), "9.3.2": ("9.7.1", 36)}
LAYOUTS = {
    "isolated": "",
    "subprojects-block": 'subprojects { println("LAB_BLOCK ${path}"); tasks.register("labHello") }\n',
    "allprojects-block": 'allprojects { println("LAB_BLOCK ${path}"); tasks.register("labHello") }\n',
    "subprojects-plugin-hook": 'subprojects { println("LAB_BLOCK ${path}"); plugins.withId("com.android.library") { println("LAB_HOOK ${path}") } }\n',
}
LIBS = [f"lib{i}" for i in range(1, 7)]
CANDIDATES = ["mergeDebugJniLibFolders", "generateDebugResValues", "compileDebugJavaWithJavac", "compileDebugAidl"]


def write_project(proj, agp, gradle_v, sdk, layout):
    os.makedirs(proj)
    for f in ("gradlew",):
        shutil.copy(os.path.join(WRAPPER_SRC, f), proj)
    shutil.copytree(os.path.join(WRAPPER_SRC, "gradle"), os.path.join(proj, "gradle"))
    w = lambda p, t: (os.makedirs(os.path.dirname(os.path.join(proj, p)) or proj, exist_ok=True), open(os.path.join(proj, p), "w").write(t))
    w("settings.gradle.kts", 'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
      'dependencyResolutionManagement { repositories { google(); mavenCentral() } }\nrootProject.name = "cod"\n'
      'include(":app", ' + ", ".join(f'":{l}"' for l in LIBS) + ")\n")
    w("build.gradle.kts", f'plugins {{ id("com.android.application") version "{agp}" apply false; id("com.android.library") version "{agp}" apply false }}\n' + LAYOUTS[layout])
    w("gradle/wrapper/gradle-wrapper.properties", f"distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\ndistributionUrl=https\\://services.gradle.org/distributions/gradle-{gradle_v}-bin.zip\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n")
    w("gradle.properties", "org.gradle.jvmargs=-Xmx2g\n")
    for l in LIBS:
        dep = 'dependencies { implementation(project(":lib2")) }\n' if l == "lib1" else ""
        w(f"{l}/build.gradle.kts", f'plugins {{ id("com.android.library") }}\nandroid {{ namespace = "lab.{l}"; compileSdk = {sdk}; defaultConfig {{ minSdk = 24 }} }}\n' + dep)
        w(f"{l}/src/main/java/lab/{l}/C.java", f"package lab.{l};\npublic class C {{ public static int v() {{ return 1; }} }}\n")
    w("app/build.gradle.kts", 'plugins { id("com.android.application") }\nandroid { namespace = "lab.app"; compileSdk = ' + str(sdk) + '; defaultConfig { applicationId = "lab.app"; minSdk = 24 } }\n'
      "dependencies { " + "; ".join(f'implementation(project(":{l}"))' for l in LIBS) + " }\n")
    w("app/src/main/AndroidManifest.xml", '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application/></manifest>')


def gradle(proj, args, log):
    cmd = ["./gradlew", "--console=plain", "--no-configuration-cache", "-I", os.path.join(HERE, "init-markers.gradle")] + args
    p = subprocess.run(cmd, cwd=proj, capture_output=True, text=True)
    out = p.stdout + p.stderr
    open(log, "w").write("$ " + " ".join(cmd) + "\n" + out)
    return p.returncode, out


def run_one(agp, layout, logs):
    gradle_v, sdk = VERSIONS[agp]
    work = tempfile.mkdtemp(prefix="cod-"); proj = os.path.join(work, "p"); write_project(proj, agp, gradle_v, sdk, layout)
    tag = f"{agp}-{layout}"
    _, out = gradle(proj, [":lib1:assembleDebug", "--dry-run"], os.path.join(logs, f"{tag}-discover.log"))
    name = next((n for n in CANDIDATES if re.search(rf"^:lib1:{n} SKIPPED", out, re.M)), None)
    if not name:
        return [(tag, "-", "no candidate task found; see discover log", "", "", "", "", "", "")], {}
    T = ":lib1:assembleDebug"; COD = "--configure-on-demand"
    cases = [
        ("A", "on-demand off", [T]),
        ("B", "on-demand", [COD, T]),
        ("C", "on-demand, -x full path in :lib1", [COD, T, "-x", f":lib1:{name}"]),
        ("D", "on-demand, -x bare task name", [COD, T, "-x", name]),
        ("E", "on-demand, -x full path in unrelated :lib5", [COD, T, "-x", f":lib5:{name}"]),
        ("F", "on-demand, requested task as bare name", [COD, "assembleDebug"]),
        ("G", "on-demand, -x name that exists nowhere", [COD, T, "-x", "labNoSuchTask"]),
    ]
    rows, n = [], {}
    for cid, desc, args in cases:
        rc, out = gradle(proj, args, os.path.join(logs, f"{tag}-{cid}.log"))
        ev = sorted(set(re.findall(r"^LAB_CONFIGURED (\S+)", out, re.M)))
        blk = set(re.findall(r"^LAB_BLOCK (\S+)", out, re.M))
        hook = set(re.findall(r"^LAB_HOOK (\S+)", out, re.M))
        err = re.search(r"What went wrong:\n(.*)", out)
        n[cid] = len(ev)
        rows.append((tag, cid, desc, " ".join(args[1:] if args[0] == COD else args), rc, len(ev), len(blk) if LAYOUTS[layout] else "-", len(hook) if "HOOK" in LAYOUTS[layout] else "-", ", ".join(ev) + (f" (error: {err.group(1).strip()[:80]})" if err and rc else "")))
    shutil.rmtree(work, ignore_errors=True)
    return rows, n


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--logs", default="logs"); ap.add_argument("--summary")
    ap.add_argument("--agp", default=",".join(VERSIONS)); ap.add_argument("--layouts", default=",".join(LAYOUTS))
    a = ap.parse_args(); os.makedirs(a.logs, exist_ok=True)
    L = ["Synthetic project: root, :app, :lib1..:lib6 (8 projects); :lib1 depends on :lib2; target `:lib1:assembleDebug`; configuration cache off in every run. On-demand = `--configure-on-demand`.",
         "Columns: scripts evaluated = projects whose build script ran (afterProject); root block ran for = projects the root subprojects/allprojects block executed for; plugin hook = projects where plugins.withId fired.", "",
         "| AGP-layout | case | what | args | exit | scripts evaluated | root block ran for | plugin hook fired | which (and error) |", "|---|---|---|---|---|---|---|---|---|"]
    verdict = ["", "| AGP-layout | B on-demand | C -x full path | D -x bare name | E -x other project | G -x missing name | -x keeps on-demand? (C and D equal B) |", "|---|---|---|---|---|---|---|"]
    for agp in a.agp.split(","):
        for layout in a.layouts.split(","):
            rows, n = run_one(agp, layout, a.logs)
            L += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
            if n:
                verdict.append(f"| {agp}-{layout} | {n['B']} | {n['C']} | {n['D']} | {n['E']} | {n['G']} | {'yes' if n['C'] == n['B'] == n['D'] else 'NO'} |")
    text = "\n".join(L + verdict) + "\n"; print(text)
    if a.summary: open(a.summary, "a").write(text)


if __name__ == "__main__":
    main()
