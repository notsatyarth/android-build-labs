#!/usr/bin/env python3
"""Does `-x <task>` defeat configuration on demand?

Writes a synthetic Android project (AGP 9.3.2, Gradle 9.7.1): root, :app, :lib1..:lib6.
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

Usage (JAVA_HOME 17, ANDROID_HOME set): python3 run.py [--logs logs] [--summary summary.md]
"""
import argparse, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WRAPPER_SRC = os.path.join(HERE, "..", "..", "samples", "missing-dimension")
AGP = "9.3.2"
LIBS = [f"lib{i}" for i in range(1, 7)]
CANDIDATES = ["mergeDebugJniLibFolders", "generateDebugResValues", "compileDebugJavaWithJavac"]


def write_project(proj):
    os.makedirs(proj)
    for f in ("gradlew",):
        shutil.copy(os.path.join(WRAPPER_SRC, f), proj)
    shutil.copytree(os.path.join(WRAPPER_SRC, "gradle"), os.path.join(proj, "gradle"))
    w = lambda p, t: (os.makedirs(os.path.dirname(os.path.join(proj, p)) or proj, exist_ok=True), open(os.path.join(proj, p), "w").write(t))
    w("settings.gradle.kts", 'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
      'dependencyResolutionManagement { repositories { google(); mavenCentral() } }\nrootProject.name = "cod"\n'
      'include(":app", ' + ", ".join(f'":{l}"' for l in LIBS) + ")\n")
    w("build.gradle.kts", f'plugins {{ id("com.android.application") version "{AGP}" apply false; id("com.android.library") version "{AGP}" apply false }}\n')
    w("gradle.properties", "org.gradle.jvmargs=-Xmx2g\n")
    for l in LIBS:
        dep = 'dependencies { implementation(project(":lib2")) }\n' if l == "lib1" else ""
        w(f"{l}/build.gradle.kts", f'plugins {{ id("com.android.library") }}\nandroid {{ namespace = "lab.{l}"; compileSdk = 36; defaultConfig {{ minSdk = 24 }} }}\n' + dep)
        w(f"{l}/src/main/java/lab/{l}/C.java", f"package lab.{l};\npublic class C {{ public static int v() {{ return 1; }} }}\n")
    w("app/build.gradle.kts", 'plugins { id("com.android.application") }\nandroid { namespace = "lab.app"; compileSdk = 36; defaultConfig { applicationId = "lab.app"; minSdk = 24 } }\n'
      "dependencies { " + "; ".join(f'implementation(project(":{l}"))' for l in LIBS) + " }\n")
    w("app/src/main/AndroidManifest.xml", '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application/></manifest>')


def gradle(proj, args, log):
    cmd = ["./gradlew", "--console=plain", "--no-configuration-cache", "-I", os.path.join(HERE, "init-markers.gradle")] + args
    p = subprocess.run(cmd, cwd=proj, capture_output=True, text=True)
    out = p.stdout + p.stderr
    open(log, "w").write("$ " + " ".join(cmd) + "\n" + out)
    return p.returncode, out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--logs", default="logs"); ap.add_argument("--summary")
    a = ap.parse_args(); os.makedirs(a.logs, exist_ok=True)
    work = tempfile.mkdtemp(prefix="cod-"); proj = os.path.join(work, "p"); write_project(proj)
    _, out = gradle(proj, [":lib1:assembleDebug", "--dry-run"], os.path.join(a.logs, "discover.log"))
    name = next((n for n in CANDIDATES if re.search(rf"^:lib1:{n} SKIPPED", out, re.M)), None)
    if not name:
        sys.exit("no candidate task found in :lib1:assembleDebug; see discover.log")
    T = ":lib1:assembleDebug"; COD = "--configure-on-demand"
    cases = [
        ("A", "on-demand off", [T]),
        ("B", "on-demand", [COD, T]),
        ("C", "on-demand, -x full path in :lib1", [COD, T, "-x", f":lib1:{name}"]),
        ("D", "on-demand, -x bare task name", [COD, T, "-x", name]),
        ("E", "on-demand, -x full path in unrelated :lib5", [COD, T, "-x", f":lib5:{name}"]),
        ("F", "on-demand, requested task as bare name (control)", [COD, "assembleDebug"]),
    ]
    rows = []
    for cid, desc, args in cases:
        rc, out = gradle(proj, args, os.path.join(a.logs, f"{cid}.log"))
        conf = re.findall(r"^LAB_CONFIGURED (\S+)", out, re.M)
        total = (re.findall(r"^LAB_TOTAL (\d+)", out, re.M) or ["?"])[0]
        warn = [l.strip() for l in out.splitlines() if re.search(r"(?i)configur\w* on demand|configure-on-demand", l) and "LAB_" not in l][:1]
        rows.append((cid, desc, " ".join(args), rc, len(set(conf)), total, ", ".join(sorted(set(conf))), warn[0][:120] if warn else ""))
    n = {r[0]: r[4] for r in rows}
    checks = [
        ("A: without on-demand all projects are configured", n["A"] == 8),
        ("B: on-demand configures fewer projects than A", n["B"] < n["A"]),
        ("C: -x with a full path in the target project keeps the B count (hypothesis predicts all)", n["C"] == n["B"]),
        ("D: -x with a bare name configures all projects", n["D"] == n["A"]),
        ("E: -x with a full path in :lib5 adds only :lib5", n["E"] == n["B"] + 1),
        ("F: bare requested task configures all projects", n["F"] == n["A"]),
    ]
    L = [f"Synthetic project, AGP {AGP}, Gradle 9.7.1, JDK 17, configuration cache off in every run. Excluded task: `{name}`. :lib1 depends on :lib2.", "",
         "| case | what | args | exit | projects configured | of total | which | Gradle message about on-demand |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r[0]} | {r[1]} | `{r[2]}` | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |" for r in rows]
    L += ["", "| check (expectation written before the run) | result |", "|---|---|"] + [f"| {c} | {'PASS' if ok else 'FAIL'} |" for c, ok in checks]
    text = "\n".join(L) + "\n"; print(text)
    if a.summary: open(a.summary, "a").write(text)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
