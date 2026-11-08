#!/usr/bin/env python3
"""Which build participants start a Kotlin daemon, and what makes a second one start?

Generates a small Android project (Gradle 9.7.1, AGP 9.3.2 with built-in Kotlin, JDK 17) per cell, turns
on one participant at a time, runs `:app:assembleDebug` from a clean state, and records every
KotlinCompileDaemon process seen during and after the build (sampled every 0.5 s from /proc):
the Kotlin version of its compiler jars (from its classpath), the JDK that runs it, and its key JVM args.
Between cells all Gradle and Kotlin daemons are stopped. The project's resolved KGP version is read from
`buildEnvironment`; Gradle's embedded Kotlin from `gradle --version`.

Expectations, written before the first run (E = expected Kotlin daemons):
  c01 base: :app + :lib, built-in Kotlin, no KGP declared            E=1, compiler = AGP's KGP (2.2.10)
  c02 KGP 2.1.21 declared (lower than AGP's 2.2.10)                   E=1, compiler 2.2.10 (AGP forces up)
  c03 KGP 2.4.0 declared (higher than AGP's)                          E=1, compiler 2.4.0
  c04 build-logic included build with kotlin-dsl                      E=2, Gradle-embedded + 2.2.10
  c05 buildSrc with kotlin-dsl                                        E=2, Gradle-embedded + 2.2.10
  c06 build-logic + KGP equal to Gradle-embedded Kotlin               E=1
  c07 kapt module (com.android.legacy-kapt, Moshi codegen)            E=1, kapt stubs in the same daemon
  c08 KSP module (KSP 2.3.4, Moshi codegen)                           E=1, KSP2 runs in the Gradle daemon
  c09 one module with jvmToolchain(21)                                E=2, same version, other JDK
  c10 c06 + kotlin.daemon.jvmargs in root gradle.properties only      E=2, root args do not reach build-logic
  c11 base + kotlin.compiler.execution.strategy=in-process            E=0
  c12 everything realistic: build-logic + buildSrc + kapt + KSP       E=2

Usage (JAVA_HOME 17, JAVA_HOME_21_X64 for c09, ANDROID_HOME set):
  python3 run.py [--only c01,c04] [--logs logs] [--summary summary.md]
"""
import argparse, glob, os, re, shutil, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
WRAPPER_SRC = os.path.join(HERE, "..", "..", "samples", "missing-dimension")  # Gradle 9.7.1 wrapper
AGP, KSP, MOSHI = "9.3.2", "2.3.4", "1.15.2"

CELLS = {
    "c01": dict(desc="base: :app + :lib, built-in Kotlin, no KGP declared", expect=1),
    "c02": dict(desc="KGP 2.1.21 declared (lower than AGP's)", kgp="2.1.21", expect=1),
    "c03": dict(desc="KGP 2.4.0 declared (higher than AGP's)", kgp="2.4.0", expect=1),
    "c04": dict(desc="build-logic included build (kotlin-dsl)", buildlogic=True, expect=2),
    "c05": dict(desc="buildSrc (kotlin-dsl)", buildsrc=True, expect=2),
    "c06": dict(desc="build-logic + KGP = Gradle-embedded Kotlin", buildlogic=True, kgp="EMBEDDED", expect=1),
    "c07": dict(desc="kapt module (com.android.legacy-kapt)", kapt=True, expect=1),
    "c08": dict(desc="KSP module (KSP " + KSP + ")", ksp=True, expect=1),
    "c09": dict(desc="one module with jvmToolchain(21)", toolchain=True, expect=2),
    "c10": dict(desc="c06 + kotlin.daemon.jvmargs in root gradle.properties only", buildlogic=True, kgp="EMBEDDED", rootargs=True, expect=2),
    "c11": dict(desc="base + execution strategy in-process", inprocess=True, expect=0),
    "c12": dict(desc="build-logic + buildSrc + kapt + KSP", buildlogic=True, buildsrc=True, kapt=True, ksp=True, expect=2),
}

KT = 'package lab.{m}\nclass {C} {{ fun v(): Int = 1 }}\n'
MOSHI_KT = 'package lab.{m}\nimport com.squareup.moshi.JsonClass\n@JsonClass(generateAdapter = true)\ndata class User(val name: String)\n'


def w(root, path, text):
    p = os.path.join(root, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)


def android_lib(ns, sdk=36, extra_plugins="", extra="", deps=""):
    return (f'plugins {{ id("com.android.library"){extra_plugins} }}\n'
            f'android {{ namespace = "lab.{ns}"; compileSdk = {sdk}; defaultConfig {{ minSdk = 24 }} }}\n{extra}'
            f'dependencies {{ {deps} }}\n')


def write_project(proj, cell, embedded):
    c = CELLS[cell]
    os.makedirs(proj)
    shutil.copy(os.path.join(WRAPPER_SRC, "gradlew"), proj)
    shutil.copytree(os.path.join(WRAPPER_SRC, "gradle"), os.path.join(proj, "gradle"))
    kgp = c.get("kgp")
    if kgp == "EMBEDDED":
        kgp = embedded
    mods = ["app", "lib"] + (["kaptlib"] if c.get("kapt") else []) + (["ksplib"] if c.get("ksp") else []) + (["tclib"] if c.get("toolchain") else [])
    w(proj, "settings.gradle.kts",
      "pluginManagement {\n" + ('    includeBuild("build-logic")\n' if c.get("buildlogic") else "") +
      "    repositories { google(); mavenCentral(); gradlePluginPortal() }\n}\n"
      "dependencyResolutionManagement { repositories { google(); mavenCentral() } }\n"
      'rootProject.name = "kd"\ninclude(' + ", ".join(f'":{m}"' for m in mods if m != "app") + ', ":app")\n')
    root = ""
    if kgp:
        root += ('buildscript {\n    repositories { google(); mavenCentral() }\n'
                 f'    dependencies {{ classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:{kgp}") }}\n}}\n')
    root += (f'plugins {{\n    id("com.android.application") version "{AGP}" apply false\n'
             f'    id("com.android.library") version "{AGP}" apply false\n'
             + (f'    id("com.android.legacy-kapt") version "{AGP}" apply false\n' if c.get("kapt") else "")
             + (f'    id("com.google.devtools.ksp") version "{KSP}" apply false\n' if c.get("ksp") else "")
             + "}\n")
    w(proj, "build.gradle.kts", root)
    props = "org.gradle.jvmargs=-Xmx2g\n"
    if c.get("rootargs"):
        props += "kotlin.daemon.jvmargs=-Xmx1536m -XX:+UseG1GC\n"
    if c.get("inprocess"):
        props += "kotlin.compiler.execution.strategy=in-process\n"
    w(proj, "gradle.properties", props)
    # modules
    w(proj, "lib/build.gradle.kts", android_lib("lib", extra_plugins='; id("lab.convention")' if c.get("buildlogic") else ""))
    w(proj, "lib/src/main/kotlin/lab/lib/Lib.kt", KT.format(m="lib", C="Lib"))
    if c.get("kapt"):
        w(proj, "kaptlib/build.gradle.kts", android_lib("kaptlib", extra_plugins='; id("com.android.legacy-kapt")',
          deps=f'implementation("com.squareup.moshi:moshi:{MOSHI}"); kapt("com.squareup.moshi:moshi-kotlin-codegen:{MOSHI}")'))
        w(proj, "kaptlib/src/main/kotlin/lab/kaptlib/User.kt", MOSHI_KT.format(m="kaptlib"))
    if c.get("ksp"):
        w(proj, "ksplib/build.gradle.kts", android_lib("ksplib", extra_plugins='; id("com.google.devtools.ksp")',
          deps=f'implementation("com.squareup.moshi:moshi:{MOSHI}"); ksp("com.squareup.moshi:moshi-kotlin-codegen:{MOSHI}")'))
        w(proj, "ksplib/src/main/kotlin/lab/ksplib/User.kt", MOSHI_KT.format(m="ksplib"))
    if c.get("toolchain"):
        w(proj, "tclib/build.gradle.kts", android_lib("tclib",
          extra="android { compileOptions { sourceCompatibility = JavaVersion.VERSION_11; targetCompatibility = JavaVersion.VERSION_11 } }\n"
                "kotlin { jvmToolchain(21); compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_11) } }\n"))
        w(proj, "tclib/src/main/kotlin/lab/tclib/Tc.kt", KT.format(m="tclib", C="Tc"))
    app_deps = "; ".join(f'implementation(project(":{m}"))' for m in mods if m != "app")
    w(proj, "app/build.gradle.kts", 'plugins { id("com.android.application") }\n'
      'android { namespace = "lab.app"; compileSdk = 36; defaultConfig { applicationId = "lab.app"; minSdk = 24 } }\n'
      f"dependencies {{ {app_deps} }}\n")
    w(proj, "app/src/main/AndroidManifest.xml", '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application/></manifest>')
    w(proj, "app/src/main/kotlin/lab/app/App.kt", KT.format(m="app", C="App"))
    if c.get("buildlogic"):
        w(proj, "build-logic/settings.gradle.kts", 'dependencyResolutionManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
          'rootProject.name = "build-logic"\ninclude(":convention")\n')
        w(proj, "build-logic/convention/build.gradle.kts", 'plugins { `kotlin-dsl` }\n'
          'gradlePlugin { plugins { register("lab") { id = "lab.convention"; implementationClass = "LabConvention" } } }\n')
        w(proj, "build-logic/convention/src/main/kotlin/LabConvention.kt",
          'import org.gradle.api.Plugin\nimport org.gradle.api.Project\nclass LabConvention : Plugin<Project> { override fun apply(target: Project) {} }\n')
    if c.get("buildsrc"):
        w(proj, "buildSrc/build.gradle.kts", 'plugins { `kotlin-dsl` }\nrepositories { mavenCentral() }\n')
        w(proj, "buildSrc/src/main/kotlin/Lab.kt", 'object Lab { const val X = 1 }\n')


def cmdline(pid):
    try:
        return open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
    except OSError:
        return None


def daemon_info(args):
    a = [x.decode(errors="replace") for x in args if x]
    cp = ""
    for i, x in enumerate(a):
        if x in ("-cp", "-classpath") and i + 1 < len(a):
            cp = a[i + 1]
    versions = sorted(set(re.findall(r"kotlin-(?:compiler-embeddable|daemon-embeddable|compiler|build-tools-impl)-(\d[\w.\-]*?)\.jar", cp)))
    java = a[0]
    jdk = re.search(r"(Java_Temurin-Hotspot_jdk/[^/]+|temurin-\d+[^/]*|jdk[^/]*)", java)
    xmx = next((x for x in a if x.startswith("-Xmx")), "")
    gc = next((x for x in a if re.match(r"-XX:\+Use\w+GC", x)), "default GC")
    jars = sorted(set(os.path.basename(x) for x in cp.split(":") if "kotlin" in os.path.basename(x)))[:6]
    return {"kotlin": ",".join(versions) or "?", "java": java, "jars": jars, "jdk": jdk.group(1) if jdk else java, "xmx": xmx, "gc": gc}


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.seen = {}; self.stop = False

    def poll(self):
        for d in os.listdir("/proc"):
            if not d.isdigit() or d in self.seen:
                continue
            a = cmdline(d)
            if a and any(b"KotlinCompileDaemon" in x for x in a):
                self.seen[d] = daemon_info(a)

    def run(self):
        while not self.stop:
            self.poll(); time.sleep(0.5)


def kill_all(proj):
    subprocess.run(["./gradlew", "--stop"], cwd=proj, capture_output=True)
    subprocess.run(["pkill", "-f", "KotlinCompileDaemon"], capture_output=True)
    subprocess.run(["pkill", "-f", "GradleDaemon"], capture_output=True)
    time.sleep(2)


def gradle(proj, args, log):
    env = dict(os.environ)
    p = subprocess.run(["./gradlew", "--console=plain", "--no-configuration-cache", "--no-build-cache",
                        "-Porg.gradle.java.installations.fromEnv=JAVA_HOME_17_X64,JAVA_HOME_21_X64",
                        "-Porg.gradle.java.installations.auto-download=false"] + args,
                       cwd=proj, capture_output=True, text=True, env=env)
    out = p.stdout + p.stderr
    open(log, "w").write("$ ./gradlew " + " ".join(args) + "\n" + out)
    return p.returncode, out


def embedded_kotlin(work):
    proj = os.path.join(work, "probe"); os.makedirs(proj)
    shutil.copy(os.path.join(WRAPPER_SRC, "gradlew"), proj)
    shutil.copytree(os.path.join(WRAPPER_SRC, "gradle"), os.path.join(proj, "gradle"))
    open(os.path.join(proj, "settings.gradle.kts"), "w").write('rootProject.name = "probe"\n')
    out = subprocess.run(["./gradlew", "--version"], cwd=proj, capture_output=True, text=True).stdout
    m = re.search(r"Kotlin:\s+(\S+)", out); g = re.search(r"Gradle (\S+)", out)
    kill_all(proj)
    return (m.group(1) if m else "?"), (g.group(1) if g else "?")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--only"); ap.add_argument("--logs", default="logs"); ap.add_argument("--summary")
    a = ap.parse_args(); os.makedirs(a.logs, exist_ok=True)
    work = tempfile.mkdtemp(prefix="kd-")
    embedded, gradle_v = embedded_kotlin(work)
    cells = a.only.split(",") if a.only else list(CELLS)
    rows, detail = [], []
    for cell in cells:
        proj = os.path.join(work, cell)
        write_project(proj, cell, embedded)
        _, env_out = gradle(proj, ["buildEnvironment"], os.path.join(a.logs, f"{cell}-buildEnvironment.log"))
        kgp_line = re.search(r"org\.jetbrains\.kotlin:kotlin-gradle-plugin:(\S+(?: -> \S+)?)", env_out)
        kgp_res = kgp_line.group(1) if kgp_line else "not on root classpath"
        kill_all(proj)
        s = Sampler(); s.start()
        rc, out = gradle(proj, [":app:assembleDebug", "--info"], os.path.join(a.logs, f"{cell}.log"))
        time.sleep(3); s.poll(); s.stop = True; s.join()
        kill_all(proj)
        tasks = sorted(set(re.findall(r"^> Task (\S*(?:compile\w*Kotlin|kapt\w*|ksp\w*)\S*)", out, re.M)))
        err = re.search(r"What went wrong:\n(.*)", out)
        daemons = list(s.seen.values())
        n = len(daemons)
        rows.append((cell, CELLS[cell]["desc"], rc, kgp_res, CELLS[cell]["expect"], n,
                     "; ".join(f"Kotlin {d['kotlin']} on {d['jdk']} {d['xmx']} {d['gc']}" for d in daemons) or "-",
                     (err.group(1).strip()[:140] if (err and rc) else "")))
        gen = [m for m in ("kaptlib", "ksplib") if os.path.isdir(os.path.join(proj, m))]
        adapters = {m: bool(glob.glob(os.path.join(proj, m, "build", "**", "UserJsonAdapter.*"), recursive=True)) for m in gen}
        diag = []
        for l in out.splitlines():
            if re.search(r"(?i)(kotlin (compile )?daemon|fallback|execution strategy|compiler execution|in-process|KotlinCompileDaemon|Could not connect|connected to the daemon)", l) and len(diag) < 12:
                diag.append(l.strip()[:220])
        for d in daemons:
            detail.append(f"- {cell}: daemon java `{d['java']}` jars {d['jars']}")
        if diag:
            detail.append(f"- {cell}: --info lines about the daemon: " + " | ".join(diag))
        if rc and err:
            i = out.index("What went wrong:")
            detail.append(f"- {cell}: failure: " + " ".join(out[i:i + 1500].split())[:1200])
        detail.append(f"- {cell}: Kotlin compile/kapt/KSP tasks that ran: {', '.join(t for t in tasks if re.search(r'compile\w*Kotlin|:kapt\w*Kotlin|:ksp\w*Kotlin|kaptGenerateStubs', t)) or 'none'}"
                      + (f"; Moshi adapter generated: {adapters}" if adapters else ""))
    L = [f"Gradle {gradle_v} (embedded Kotlin {embedded}), AGP {AGP} built-in Kotlin, JDK 17 for Gradle, clean build of `:app:assembleDebug` per cell, all daemons stopped between cells.", "",
         "| cell | what changes | exit | KGP on root classpath (buildEnvironment) | expected Kotlin daemons | Kotlin daemons seen | each daemon: compiler version, JDK, JVM args | error |",
         "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} {'' if r[5] == r[4] or r[2] else '(differs)'} | {r[6]} | {r[7]} |" for r in rows]
    L += ["", "Tasks per cell:"] + detail
    text = "\n".join(L) + "\n"; print(text)
    if a.summary: open(a.summary, "a").write(text)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
