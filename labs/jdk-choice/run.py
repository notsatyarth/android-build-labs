#!/usr/bin/env python3
"""Which JDK does each Java-version choice in an Android build actually end up using?

Generates a one-module Android app (Gradle 9.7.1, AGP 9.3.2 with built-in Kotlin) with one Java class, one
Kotlin class and one unit test, then builds `:app:assembleDebug :app:testDebugUnitTest` once per cell and
records, for each choice:
  gradle  JDK of the Gradle daemon (process list, plus java.home printed from settings.gradle.kts)
  javac   JDK of the Java compile task (JavaCompile.javaCompiler, printed before the task runs)
  test    JDK the unit test ran on (the test writes its own java.home to a file)
  kotlin  JDK of the Kotlin compile daemon (process list)
  class   class file major version of the Java and the Kotlin class (61 = Java 17, 65 = Java 21, 55 = Java 11)
JDK versions come from the `release` file next to the java binary, not from a guess.

Cells (JAVA_HOME is JDK 21 unless noted; "detect" = Gradle's automatic JDK detection):
  k01 no toolchain, no compileOptions
  k02 no toolchain, compileOptions 11 (what nowinandroid sets)
  k03 kotlin { jvmToolchain(17) }, no compileOptions
  k04 kotlin { jvmToolchain(17) } + compileOptions 11
  k05 `java { toolchain }` extension looked up in the Android module (does it exist there?)
  k06 jvmToolchain(17), detect off, no resolver
  k07 jvmToolchain(17), detect off, Foojay resolver 1.0.0 (fresh Gradle user home)
  k08 no toolchain, JAVA_HOME unset, java 21 first on PATH
  k09 Daemon JVM criteria 17 (gradle/gradle-daemon-jvm.properties), JAVA_HOME 21
  k10 Daemon JVM criteria 21 written by `updateDaemonJvm`, JAVA_HOME 17, detect off, Foojay (fresh home)

Expectations, written before the first run (docs wording: developer.android.com/build/jdks and the
Gradle manual 9.9.1; None = no expectation, record only):
  k01 gradle 21, javac 21, test 21, kotlin 21, class 65/65 (target defaults to toolchain = JDK running Gradle)
  k02 gradle 21, javac 21, test 21, kotlin 21, class 55/55
  k03 gradle 21, javac 17, test 17, kotlin 17, class 61/61
  k04 gradle 21, javac 17, test 17, kotlin 17, class 55/55
  k05 None
  k06 build fails (no matching toolchain, nothing to download)
  k07 gradle 21, javac 17, test 17, kotlin 17, class 61/61, a JDK downloaded into the Gradle user home
  k08 gradle 21 (java from PATH), javac 21, test 21, kotlin 21, class 65/65
  k09 gradle 17, javac 17, test 17, kotlin 17, class 61/61 (criteria beat JAVA_HOME; toolchain defaults to it)
  k10 None (open question: does Gradle download the daemon JDK by itself?)

Usage (Linux; JAVA_HOME_17_X64 and JAVA_HOME_21_X64 set, ANDROID_HOME set):
  python3 run.py [--only k01,k03] [--logs logs] [--summary summary.md]
"""
import argparse, glob, os, re, shutil, struct, subprocess, tempfile, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
WRAPPER_SRC = os.path.join(HERE, "..", "..", "samples", "missing-dimension")  # Gradle 9.7.1 wrapper
AGP, FOOJAY, JUNIT = "9.3.2", "1.0.0", "4.13.2"

# home: JAVA_HOME env var name, or None for "unset, 21 on PATH"
CELLS = {
    "k01": dict(desc="no toolchain, no compileOptions", home="21", expect=dict(gradle=21, javac=21, test=21, kotlin=21, java_cls=65, kt_cls=65)),
    "k02": dict(desc="no toolchain, compileOptions 11", home="21", compat=True, expect=dict(gradle=21, javac=21, test=21, kotlin=21, java_cls=55, kt_cls=55)),
    "k03": dict(desc="kotlin { jvmToolchain(17) }", home="21", tc="kotlin", expect=dict(gradle=21, javac=17, test=17, kotlin=17, java_cls=61, kt_cls=61)),
    "k04": dict(desc="jvmToolchain(17) + compileOptions 11", home="21", tc="kotlin", compat=True, expect=dict(gradle=21, javac=17, test=17, kotlin=17, java_cls=55, kt_cls=55)),
    "k05": dict(desc="java { toolchain } extension in the Android module", home="21", tc="javaext", expect=None),
    "k06": dict(desc="jvmToolchain(17), detect off, no resolver", home="21", tc="kotlin", detect=False, expect="fail"),
    "k07": dict(desc="jvmToolchain(17), detect off, Foojay resolver", home="21", tc="kotlin", detect=False, foojay=True, fresh=True,
                expect=dict(gradle=21, javac=17, test=17, kotlin=17, java_cls=61, kt_cls=61, downloaded=True)),
    "k08": dict(desc="no toolchain, JAVA_HOME unset, java 21 on PATH", home=None, expect=dict(gradle=21, javac=21, test=21, kotlin=21, java_cls=65, kt_cls=65)),
    "k09": dict(desc="Daemon JVM criteria 17, JAVA_HOME 21", home="21", daemon17=True, expect=dict(gradle=17, javac=17, test=17, kotlin=17, java_cls=61, kt_cls=61)),
    "k10": dict(desc="updateDaemonJvm 21, JAVA_HOME 17, detect off, Foojay", home="17", detect=False, foojay=True, fresh=True, updatedaemon=21, expect=None),
}

JAVA_SRC = "package lab.app;\npublic class Hello { public int v() { return 1; } }\n"
KT_SRC = "package lab.app\nclass KtHello { fun v(): Int = 1 }\n"
TEST_SRC = ('package lab.app\nimport org.junit.Test\nclass JdkTest {\n'
            '    @Test fun jdk() { java.io.File("build/lab-test-jdk.txt").writeText(System.getProperty("java.home") + "\\n" + System.getProperty("java.version")) }\n}\n')


def w(root, path, text):
    p = os.path.join(root, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)


def write_project(proj, c):
    os.makedirs(proj)
    shutil.copy(os.path.join(WRAPPER_SRC, "gradlew"), proj)
    shutil.copytree(os.path.join(WRAPPER_SRC, "gradle"), os.path.join(proj, "gradle"))
    w(proj, "settings.gradle.kts",
      'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
      + (f'plugins {{ id("org.gradle.toolchains.foojay-resolver-convention") version "{FOOJAY}" }}\n' if c.get("foojay") else "")
      + 'dependencyResolutionManagement { repositories { google(); mavenCentral() } }\n'
      'println("LAB gradle-jvm " + System.getProperty("java.home"))\n'
      'rootProject.name = "jdkchoice"\ninclude(":app")\n')
    w(proj, "build.gradle.kts", f'plugins {{ id("com.android.application") version "{AGP}" apply false }}\n')
    props = "org.gradle.jvmargs=-Xmx2g\n"
    if c.get("detect") is False:
        props += "org.gradle.java.installations.auto-detect=false\n"
    w(proj, "gradle.properties", props)
    tc = {"kotlin": "kotlin { jvmToolchain(17) }\n",
          "javaext": ('val je = extensions.findByType(JavaPluginExtension::class.java)\n'
                      'if (je == null) println("LAB java-extension absent") else { println("LAB java-extension present"); je.toolchain.languageVersion.set(JavaLanguageVersion.of(17)) }\n')}.get(c.get("tc"), "")
    compat = "    compileOptions { sourceCompatibility = JavaVersion.VERSION_11; targetCompatibility = JavaVersion.VERSION_11 }\n" if c.get("compat") else ""
    w(proj, "app/build.gradle.kts",
      'plugins { id("com.android.application") }\n'
      'android {\n    namespace = "lab.app"; compileSdk = 36\n    defaultConfig { applicationId = "lab.app"; minSdk = 24 }\n' + compat + '}\n'
      + tc +
      f'dependencies {{ testImplementation("junit:junit:{JUNIT}") }}\n'
      'tasks.withType<JavaCompile>().configureEach { doFirst { println("LAB javac " + javaCompiler.map { it.metadata.installationPath.asFile.path }.getOrElse("none")) } }\n'
      'tasks.withType<Test>().configureEach { doFirst { println("LAB test-launcher " + javaLauncher.map { it.metadata.installationPath.asFile.path }.getOrElse("none")) } }\n')
    w(proj, "app/src/main/AndroidManifest.xml", '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application/></manifest>')
    w(proj, "app/src/main/java/lab/app/Hello.java", JAVA_SRC)
    w(proj, "app/src/main/kotlin/lab/app/KtHello.kt", KT_SRC)
    w(proj, "app/src/test/kotlin/lab/app/JdkTest.kt", TEST_SRC)
    if c.get("daemon17"):
        w(proj, "gradle/gradle-daemon-jvm.properties", "toolchainVersion=17\n")


def cmdline(pid):
    try:
        return [x.decode(errors="replace") for x in open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0") if x]
    except OSError:
        return None


def jdk_of(java_bin_or_home):
    """JAVA_VERSION from the release file of the JDK that owns a java binary or a JDK home."""
    p = os.path.realpath(java_bin_or_home)
    for cand in (p, os.path.dirname(os.path.dirname(p))):
        rel = os.path.join(cand, "release")
        if os.path.isfile(rel):
            m = re.search(r'JAVA_VERSION="([^"]+)"', open(rel).read())
            if m:
                return cand, m.group(1)
    return p, "?"


def major(v):
    m = re.match(r"(\d+)", v or "")
    return int(m.group(1)) if m else None


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.seen = {}; self.stop = False

    def poll(self):
        for d in os.listdir("/proc"):
            if not d.isdigit() or d in self.seen:
                continue
            a = cmdline(d)
            if not a:
                continue
            j = " ".join(a)
            kind = "gradle" if "GradleDaemon" in j else "kotlin" if "KotlinCompileDaemon" in j else None
            if kind:
                self.seen[d] = (kind, a[0])

    def run(self):
        while not self.stop:
            self.poll(); time.sleep(0.5)


def kill_all(proj, env):
    subprocess.run(["./gradlew", "--stop"], cwd=proj, capture_output=True, env=env)
    subprocess.run(["pkill", "-f", "KotlinCompileDaemon"], capture_output=True)
    subprocess.run(["pkill", "-f", "GradleDaemon"], capture_output=True)
    time.sleep(2)


def gradle(proj, args, log, env):
    p = subprocess.run(["./gradlew", "--console=plain", "--no-configuration-cache", "--no-build-cache"] + args,
                       cwd=proj, capture_output=True, text=True, env=env)
    out = p.stdout + p.stderr
    open(log, "a").write("$ ./gradlew " + " ".join(args) + "\n" + out + "\n")
    return p.returncode, out


def class_major(proj, name):
    for f in glob.glob(os.path.join(proj, "app", "build", "**", name), recursive=True):
        return struct.unpack(">H", open(f, "rb").read(8)[6:8])[0]
    return None


def make_env(c, guh):
    env = dict(os.environ)
    env["GRADLE_USER_HOME"] = guh
    j21, j17 = env.get("JAVA_HOME_21_X64"), env.get("JAVA_HOME_17_X64")
    if c["home"] is None:
        env.pop("JAVA_HOME", None)
        env["PATH"] = os.path.join(j21, "bin") + ":" + env["PATH"]
    else:
        env["JAVA_HOME"] = j21 if c["home"] == "21" else j17
    return env


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--only"); ap.add_argument("--logs", default="logs"); ap.add_argument("--summary")
    a = ap.parse_args(); os.makedirs(a.logs, exist_ok=True)
    work = tempfile.mkdtemp(prefix="jc-")
    shared_guh = os.path.join(work, "guh-shared")
    cells = a.only.split(",") if a.only else list(CELLS)
    rows, detail = [], []
    for cell in cells:
        c = CELLS[cell]
        proj = os.path.join(work, cell)
        guh = os.path.join(work, f"guh-{cell}") if c.get("fresh") else shared_guh
        env = make_env(c, guh)
        write_project(proj, c)
        log = os.path.join(a.logs, f"{cell}.log")
        open(log, "w").write(f"# {cell}: {c['desc']}\n# JAVA_HOME={env.get('JAVA_HOME')}\n")
        kill_all(proj, env)
        if c.get("updatedaemon"):
            rc0, out0 = gradle(proj, ["updateDaemonJvm", f"--jvm-version={c['updatedaemon']}"], log, env)
            p = os.path.join(proj, "gradle", "gradle-daemon-jvm.properties")
            detail.append(f"- {cell}: updateDaemonJvm exit {rc0}; file: " + (" | ".join(open(p).read().split("\n")[:8]) if os.path.isfile(p) else "not written"))
            kill_all(proj, env)
        s = Sampler(); s.start()
        rc, out = gradle(proj, [":app:assembleDebug", ":app:testDebugUnitTest"], log, env)
        time.sleep(3); s.poll(); s.stop = True; s.join()
        kill_all(proj, env)
        obs = {}
        gd = sorted({jdk_of(j)[1] for k, j in s.seen.values() if k == "gradle"})
        kd = sorted({jdk_of(j)[1] for k, j in s.seen.values() if k == "kotlin"})
        obs["gradle"] = major(gd[0]) if gd else None
        obs["kotlin"] = major(kd[0]) if kd else None
        jv = re.findall(r"^LAB javac (.+)$", out, re.M)
        obs["javac"] = major(jdk_of(jv[0])[1]) if jv and jv[0] != "none" else None
        tf = os.path.join(proj, "app", "build", "lab-test-jdk.txt")
        obs["test"] = major(open(tf).read().split("\n")[1]) if os.path.isfile(tf) else None
        obs["java_cls"] = class_major(proj, "Hello.class")
        obs["kt_cls"] = class_major(proj, "KtHello.class")
        jdks = os.path.join(guh, "jdks")
        dl = sorted(os.listdir(jdks)) if os.path.isdir(jdks) else []
        obs["downloaded"] = bool(dl)
        err = re.search(r"What went wrong:\n(.*(?:\n.*){0,3})", out)
        ext = re.findall(r"^LAB java-extension (\w+)$", out, re.M)
        exp = c["expect"]
        if exp == "fail":
            verdict = "as expected (build failed)" if rc else "DIFFERS: build passed"
        elif exp is None:
            verdict = "no expectation (recorded)"
        elif rc:
            verdict = "DIFFERS: build failed"
        else:
            bad = [f"{k}: expected {v}, got {obs.get(k)}" for k, v in exp.items() if obs.get(k) != v]
            verdict = "as expected" if not bad else "DIFFERS: " + "; ".join(bad)
        fmt = lambda v: "-" if v is None else str(v)
        rows.append((cell, c["desc"], rc, fmt(obs["gradle"]), fmt(obs["javac"]), fmt(obs["test"]), fmt(obs["kotlin"]),
                     f"{fmt(obs['java_cls'])}/{fmt(obs['kt_cls'])}", ", ".join(dl) or "-", verdict))
        detail.append(f"- {cell}: Gradle daemon java {[j for k, j in s.seen.values() if k == 'gradle']}, Kotlin daemon java {[j for k, j in s.seen.values() if k == 'kotlin']}, javac home {jv}, java extension {ext or 'n/a'}")
        if rc and err:
            detail.append(f"- {cell}: failure: " + " ".join(err.group(1).split())[:600])
    L = [f"Gradle 9.7.1, AGP {AGP} built-in Kotlin, clean one-module Android app, `:app:assembleDebug :app:testDebugUnitTest` per cell, daemons stopped between cells.", "",
         "| cell | what changes | exit | Gradle JDK | javac JDK | unit test JDK | Kotlin daemon JDK | class major java/kotlin | JDKs downloaded | against expectation |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    L += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    L += ["", "Details:"] + detail
    text = "\n".join(L) + "\n"; print(text)
    if a.summary:
        open(a.summary, "a").write(text)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
