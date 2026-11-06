#!/usr/bin/env python3
"""Is R8 deterministic, and when do obfuscated field names change? (Gson without @SerializedName)

Part A, android: generates a small Kotlin app (AGP built-in Kotlin, release build with R8 and
proguard-android-optimize.txt) whose data classes are stored as JSON with Gson, as an app would in
SharedPreferences:
  lab.app.model.Settings           fields without @SerializedName (JSON keys = whatever R8 names them)
  lab.app.model.SettingsAnnotated  the same fields with @SerializedName
Each scenario changes one thing against the baseline and records: SHA-256 of every classes*.dex in the
APK, of the APK and of mapping.txt, and the obfuscated name of every field of both classes (mapping.txt).

Part B, jvm: the same question at run time. A plain Java program (Gson, one Settings class) is compiled,
shrunk by the R8 jar AGP uses (classfile output) and run: the baseline build WRITES the JSON, the other
builds READ it, so a renamed field shows up as a lost or wrong value.

Usage (JAVA_HOME 17, ANDROID_HOME set):
  python3 run.py [--logs logs] [--only android,jvm]
Writes logs/android.json, logs/jvm.json and build logs. compare.py checks the hypotheses.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WRAPPER_SRC = os.path.join(HERE, "..", "..", "samples", "missing-dimension")
BASE_AGP, BASE_GRADLE = "9.3.2", "9.7.1"
OTHER_AGP = "9.1.0"            # a different AGP, so a different bundled R8
BASE_GSON, OLD_GSON = "2.14.0", "2.10.1"   # 2.10.1: before Gson shipped its R8 rules (2.11.0)
GOOGLE = "https://dl.google.com/android/maven2"
CENTRAL = "https://repo1.maven.org/maven2"

# ---------------------------------------------------------------- Part A: Android app
FIELDS = [("userName", "String", '"jesse"'), ("themeId", "Int", "2"), ("notificationsOn", "Boolean", "true")]
ADDED = ("accountId", "String", '"acc-1"')   # sorts first and is declared first


def settings_kt(addfield, annotated):
    fs = ([ADDED] if addfield else []) + FIELDS
    name = "SettingsAnnotated" if annotated else "Settings"
    imp = "import com.google.gson.annotations.SerializedName\n" if annotated else ""
    body = ",\n".join(("    @SerializedName(\"%s\") " % n if annotated else "    ") + "val %s: %s" % (n, t) for n, t, _ in fs)
    return "package lab.app.model\n%s\ndata class %s(\n%s\n)\n" % (imp, name, body)


def store_kt(addfield):
    args = ", ".join(v for _, _, v in ([ADDED] if addfield else []) + FIELDS)
    return f'''package lab.app
import android.content.Context
import com.google.gson.Gson
import lab.app.model.Settings
import lab.app.model.SettingsAnnotated
object Store {{
    private val gson = Gson()
    fun save(c: Context) {{
        c.getSharedPreferences("prefs", Context.MODE_PRIVATE).edit()
            .putString("settings", gson.toJson(Settings({args})))
            .putString("settingsAnnotated", gson.toJson(SettingsAnnotated({args})))
            .apply()
    }}
    fun load(c: Context): Settings? =
        c.getSharedPreferences("prefs", Context.MODE_PRIVATE).getString("settings", null)?.let {{ gson.fromJson(it, Settings::class.java) }}
    fun loadAnnotated(c: Context): SettingsAnnotated? =
        c.getSharedPreferences("prefs", Context.MODE_PRIVATE).getString("settingsAnnotated", null)?.let {{ gson.fromJson(it, SettingsAnnotated::class.java) }}
}}
'''


def main_kt(addfield, unrelated):
    extra = "        title = title.toString() + lab.app.feature.Extra(\"e\", 1, 2L).describe()\n" if unrelated else ""
    acc = " + s.accountId + a.accountId" if addfield else ""
    return f'''package lab.app
import android.app.Activity
import android.os.Bundle
class MainActivity : Activity() {{
    override fun onCreate(b: Bundle?) {{
        super.onCreate(b)
        Store.save(this)
        val s = Store.load(this)!!
        val a = Store.loadAnnotated(this)!!
        title = s.userName + s.themeId + s.notificationsOn + a.userName + a.themeId + a.notificationsOn{acc}
{extra}    }}
}}
'''


EXTRA_KT = '''package lab.app.feature
class Extra(val label: String, val count: Int, val size: Long) {
    fun describe(): String = label + count + size
    fun unusedHelper(x: Int): Int = x * count
}
'''


def build_gradle(agp, gson):
    return f'''plugins {{ id("com.android.application") version "{agp}" }}
android {{
    namespace = "lab.app"; compileSdk = 36
    defaultConfig {{ applicationId = "lab.app"; minSdk = 24; targetSdk = 36 }}
    buildTypes {{ getByName("release") {{ isMinifyEnabled = true; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro") }} }}
}}
dependencies {{ implementation("com.google.code.gson:gson:{gson}") }}
'''


def write_android(proj, agp=BASE_AGP, gradle_v=BASE_GRADLE, gson=BASE_GSON, addfield=False, unrelated=False, keep=False, applymapping=None):
    if os.path.exists(proj):
        shutil.rmtree(proj)
    os.makedirs(proj)
    for f in ("gradlew", "gradlew.bat"):
        if os.path.exists(os.path.join(WRAPPER_SRC, f)):
            shutil.copy(os.path.join(WRAPPER_SRC, f), proj)
    shutil.copytree(os.path.join(WRAPPER_SRC, "gradle"), os.path.join(proj, "gradle"))
    open(os.path.join(proj, "gradle/wrapper/gradle-wrapper.properties"), "w").write(
        f"distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\ndistributionUrl=https\\://services.gradle.org/distributions/gradle-{gradle_v}-bin.zip\nzipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n")
    open(os.path.join(proj, "settings.gradle.kts"), "w").write(
        'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
        'dependencyResolutionManagement { repositories { google(); mavenCentral() } }\nrootProject.name = "r8lab"\ninclude(":app")\n')
    open(os.path.join(proj, "gradle.properties"), "w").write("org.gradle.jvmargs=-Xmx3g\nandroid.useAndroidX=false\n")
    files = {
        "app/src/main/AndroidManifest.xml": '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application><activity android:name=".MainActivity" android:exported="true"/></application></manifest>',
        "app/src/main/kotlin/lab/app/model/Settings.kt": settings_kt(addfield, False),
        "app/src/main/kotlin/lab/app/model/SettingsAnnotated.kt": settings_kt(addfield, True),
        "app/src/main/kotlin/lab/app/Store.kt": store_kt(addfield),
        "app/src/main/kotlin/lab/app/MainActivity.kt": main_kt(addfield, unrelated),
    }
    if unrelated:
        files["app/src/main/kotlin/lab/app/feature/Extra.kt"] = EXTRA_KT
    rules = ""
    if keep:
        rules += "-keepclassmembers class lab.app.model.Settings { <fields>; }\n"
    if applymapping:
        rules += "-applymapping " + applymapping + "\n"
    files["app/proguard-rules.pro"] = rules
    files["app/build.gradle.kts"] = build_gradle(agp, gson)
    for p, t in files.items():
        os.makedirs(os.path.dirname(os.path.join(proj, p)), exist_ok=True)
        open(os.path.join(proj, p), "w").write(t)


def gradle(proj, args, log):
    p = subprocess.run(["./gradlew", "--console=plain", "--no-daemon", "--no-build-cache"] + args, cwd=proj, capture_output=True, text=True)
    out = p.stdout + p.stderr
    open(log, "w").write("$ ./gradlew " + " ".join(args) + "\n" + out)
    return p.returncode, out


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def parse_mapping(path, classes):
    """Return {class: {"obfuscated_class": n, "fields": {original: obfuscated}}} for the given classes."""
    res, cur = {}, None
    for line in open(path, errors="replace"):
        if line.startswith("#"):
            continue
        m = re.match(r"^(\S+) -> (\S+):$", line.rstrip("\n"))
        if m:
            cur = m.group(1) if m.group(1) in classes else None
            if cur:
                res[cur] = {"obfuscated_class": m.group(2), "fields": {}}
            continue
        if cur:
            f = re.match(r"^\s+(?:\d+:\d+:)?(\S+) ([\w$]+) -> ([\w$]+)$", line.rstrip("\n"))
            if f and "(" not in line:
                res[cur]["fields"][f.group(2)] = f.group(3)
    return res


def collect(proj, rc, out):
    apk = os.path.join(proj, "app/build/outputs/apk/release/app-release-unsigned.apk")
    mp = os.path.join(proj, "app/build/outputs/mapping/release/mapping.txt")
    r = {"exit": rc, "error": "" if rc == 0 else (re.search(r"What went wrong:\n([^\n]*\n?[^\n]*)", out) or [None, out[-300:]])[1].strip()}
    if rc == 0 and os.path.exists(apk) and os.path.exists(mp):
        with zipfile.ZipFile(apk) as z:
            r["dex"] = {n: hashlib.sha256(z.read(n)).hexdigest() for n in sorted(z.namelist()) if re.match(r"classes\d*\.dex$", n)}
        r["apk_sha"] = sha(apk)
        r["mapping_sha"] = sha(mp)
        r["mapping_path"] = mp
        r["names"] = parse_mapping(mp, {"lab.app.model.Settings", "lab.app.model.SettingsAnnotated"})
        m = re.search(r"com\.android\.tools:r8:([\w.\-]+)", out)
        r["r8"] = m.group(1) if m else None
    return r


def r8_version(proj, logs, tag):
    rc, out = gradle(proj, [":app:buildEnvironment"], os.path.join(logs, f"android-{tag}-buildEnvironment.log"))
    vs = re.findall(r"com\.android\.tools:r8:([0-9][\w.\-]*)(?: -> ([0-9][\w.\-]*))?", out)
    return (vs[-1][1] or vs[-1][0]) if vs else None


def run_android(logs, work):
    res = {}

    def scenario(name, proj, build_args=(":app:assembleRelease",), **kw):
        if kw.get("_reuse") is None:
            write_android(proj, **{k: v for k, v in kw.items() if not k.startswith("_")})
        rc, out = gradle(proj, list(build_args), os.path.join(logs, f"android-{name}.log"))
        r = collect(proj, rc, out)
        r["r8"] = r8_version(proj, logs, name)
        r["params"] = {k: v for k, v in kw.items() if not k.startswith("_")}
        res[name] = r
        print("%-28s exit=%s r8=%s mapping=%s Settings=%s" % (name, rc, r.get("r8"), (r.get("mapping_sha") or "-")[:12],
                                                            (r.get("names") or {}).get("lab.app.model.Settings", {}).get("fields")), flush=True)
        return r

    base_dir = os.path.join(work, "base")
    base = scenario("base", base_dir)
    keep_map = os.path.join(work, "base-mapping.txt")
    if base.get("mapping_path"):
        shutil.copy(base["mapping_path"], keep_map)
    # same tree, everything rebuilt from scratch
    scenario("base-again", base_dir, build_args=("clean", ":app:assembleRelease", "--rerun-tasks"), _reuse=True)
    # same sources in a different directory
    scenario("base-copy", os.path.join(work, "elsewhere", "another-checkout"))
    scenario("unrelated", os.path.join(work, "unrelated"), unrelated=True)
    scenario("addfield", os.path.join(work, "addfield"), addfield=True)
    scenario("addfield-applymapping", os.path.join(work, "addfield-am"), addfield=True, applymapping=keep_map)
    scenario("agp-" + OTHER_AGP, os.path.join(work, "agp-other"), agp=OTHER_AGP)
    scenario("gson-" + OLD_GSON, os.path.join(work, "gson-old"), gson=OLD_GSON)
    scenario("keep-base", os.path.join(work, "keep-base"), keep=True)
    scenario("keep-addfield", os.path.join(work, "keep-addfield"), keep=True, addfield=True)
    for r in res.values():
        r.pop("mapping_path", None)
    return res


# ---------------------------------------------------------------- Part B: JVM runtime round trip
def java_settings(addfield, annotated):
    fs = ([("accountId", "String")] if addfield else []) + [("userName", "String"), ("themeId", "int"), ("notificationsOn", "boolean")]
    imp = "import com.google.gson.annotations.SerializedName;\n" if annotated else ""
    decl = "\n".join(("  @SerializedName(\"%s\") " % n if annotated else "  ") + "private final %s %s;" % (t, n) for n, t in fs)
    params = ", ".join("%s %s" % (t, n) for n, t in fs)
    assign = " ".join("this.%s = %s;" % (n, n) for n, _ in fs)
    getters = "\n".join("  public %s %s() { return %s; }" % (t, n, n) for n, t in fs)
    return f"package lab.jvm.model;\n{imp}public final class Settings {{\n{decl}\n  public Settings({params}) {{ {assign} }}\n{getters}\n}}\n"


def java_main(addfield, unrelated):
    args = ('"acc-1", ' if addfield else "") + '"jesse", 2, true'
    acc = ' + " accountId=" + s.accountId()' if addfield else ""
    extra = '    System.out.println("extra " + new lab.jvm.feature.Extra("e", 1).describe());\n' if unrelated else ""
    return f'''package lab.jvm;
import com.google.gson.Gson;
import java.nio.file.*;
import lab.jvm.model.Settings;
public final class Main {{
  public static void main(String[] a) throws Exception {{
    Gson gson = new Gson();
    Path p = Paths.get(a[1]);
    if (a[0].equals("write")) {{
      String json = gson.toJson(new Settings({args}));
      Files.write(p, json.getBytes("UTF-8"));
      System.out.println("LAB_JSON " + json);
    }} else {{
      Settings s = gson.fromJson(new String(Files.readAllBytes(p), "UTF-8"), Settings.class);
      System.out.println("LAB_READ userName=" + s.userName() + " themeId=" + s.themeId() + " notificationsOn=" + s.notificationsOn(){acc});
    }}
{extra}  }}
}}
'''


JAVA_EXTRA = '''package lab.jvm.feature;
public final class Extra {
  private final String label; private final int count;
  public Extra(String label, int count) { this.label = label; this.count = count; }
  public String describe() { return label + count; }
}
'''


def fetch(url, dst):
    if not os.path.exists(dst):
        urllib.request.urlretrieve(url, dst)
        h = hashlib.sha1(open(dst, "rb").read()).hexdigest()
        try:
            want = urllib.request.urlopen(url + ".sha1").read().decode().split()[0]
        except Exception as e:  # repository without .sha1 files: record, do not guess
            print("no .sha1 for %s (%s); sha1 of download %s" % (url, e, h), flush=True)
            return dst
        if h != want:
            raise SystemExit("checksum mismatch for " + url)
    return dst


def jvm_build(work, name, r8_jar, gson_jar, gson_rules, addfield=False, unrelated=False, annotated=False, applymapping=None):
    d = os.path.join(work, "jvm-" + name)
    shutil.rmtree(d, ignore_errors=True)
    src = os.path.join(d, "src")
    files = {"lab/jvm/model/Settings.java": java_settings(addfield, annotated), "lab/jvm/Main.java": java_main(addfield, unrelated)}
    if unrelated:
        files["lab/jvm/feature/Extra.java"] = JAVA_EXTRA
    for p, t in files.items():
        os.makedirs(os.path.dirname(os.path.join(src, p)), exist_ok=True)
        open(os.path.join(src, p), "w").write(t)
    classes = os.path.join(d, "classes")
    os.makedirs(classes)
    javas = [os.path.join(src, p) for p in files]
    subprocess.run(["javac", "--release", "17", "-cp", gson_jar, "-d", classes] + javas, check=True)
    app_jar = os.path.join(d, "app.jar")
    subprocess.run(["jar", "--create", "--file", app_jar, "-C", classes, "."], check=True)
    rules = os.path.join(d, "rules.pro")
    r = "-keep class lab.jvm.Main { public static void main(java.lang.String[]); }\n-dontwarn **\n"
    if applymapping:
        r += "-applymapping " + applymapping + "\n"
    open(rules, "w").write(r)
    out_jar, mp = os.path.join(d, "out.jar"), os.path.join(d, "mapping.txt")
    cmd = ["java", "-cp", r8_jar, "com.android.tools.r8.R8", "--release", "--classfile", "--output", out_jar,
           "--pg-conf", rules, "--pg-conf", gson_rules, "--pg-map-output", mp, "--lib", os.environ["JAVA_HOME"], app_jar, gson_jar]
    p = subprocess.run(cmd, capture_output=True, text=True)
    open(os.path.join(d, "r8.log"), "w").write("$ " + " ".join(cmd) + "\n" + p.stdout + p.stderr)
    res = {"r8_exit": p.returncode, "r8_output": (p.stdout + p.stderr)[-400:]}
    if p.returncode == 0:
        with zipfile.ZipFile(out_jar) as z:
            res["classes_sha"] = hashlib.sha256(b"".join(z.read(n) for n in sorted(z.namelist()) if n.endswith(".class"))).hexdigest()
        res["mapping_sha"] = sha(mp)
        res["names"] = parse_mapping(mp, {"lab.jvm.model.Settings"})
    return d, out_jar, mp, res


def run_jvm(logs, work, r8_version):
    r8_jar = fetch(f"{GOOGLE}/com/android/tools/r8/{r8_version}/r8-{r8_version}.jar", os.path.join(work, f"r8-{r8_version}.jar"))
    gson_jar = fetch(f"{CENTRAL}/com/google/code/gson/gson/{BASE_GSON}/gson-{BASE_GSON}.jar", os.path.join(work, f"gson-{BASE_GSON}.jar"))
    with zipfile.ZipFile(gson_jar) as z:
        gson_rules = os.path.join(work, "gson.pro")
        open(gson_rules, "wb").write(z.read("META-INF/proguard/gson.pro"))
    res = {"r8": r8_version, "gson": BASE_GSON, "builds": {}, "reads": {}}
    built = {}
    plan = [("base", {}), ("base-again", {}), ("unrelated", {"unrelated": True}), ("addfield", {"addfield": True}),
            ("annotated-base", {"annotated": True}), ("annotated-addfield", {"annotated": True, "addfield": True})]
    for name, kw in plan:
        built[name] = jvm_build(work, name, r8_jar, gson_jar, gson_rules, **kw)
        res["builds"][name] = built[name][3]
    _, _, base_map, _ = built["base"]
    built["addfield-applymapping"] = jvm_build(work, "addfield-applymapping", r8_jar, gson_jar, gson_rules, addfield=True, applymapping=base_map)
    res["builds"]["addfield-applymapping"] = built["addfield-applymapping"][3]

    def run(name, mode, path):
        _, jar, _, b = built[name]
        if b["r8_exit"] != 0:
            return {"exit": None, "out": "R8 failed"}
        p = subprocess.run(["java", "-cp", jar, "lab.jvm.Main", mode, path], capture_output=True, text=True)
        return {"exit": p.returncode, "out": (p.stdout + p.stderr).strip()[-500:]}

    for writer, readers in (("base", ["base", "base-again", "unrelated", "addfield", "addfield-applymapping"]),
                            ("annotated-base", ["annotated-base", "annotated-addfield"])):
        jf = os.path.join(work, writer + ".json")
        w = run(writer, "write", jf)
        res["reads"][writer + " writes"] = w
        for rd in readers:
            res["reads"][writer + " -> " + rd] = run(rd, "read", jf)
    for k, v in res["reads"].items():
        print("%-40s %s" % (k, v["out"].splitlines()[-1] if v["out"] else v), flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=os.path.join(HERE, "logs"))
    ap.add_argument("--only")
    a = ap.parse_args()
    logs = os.path.abspath(a.logs)
    os.makedirs(logs, exist_ok=True)
    only = set(a.only.split(",")) if a.only else {"android", "jvm"}
    work = tempfile.mkdtemp(prefix="r8-determinism-")
    r8v = None
    if "android" in only:
        ra = run_android(logs, work)
        json.dump(ra, open(os.path.join(logs, "android.json"), "w"), indent=1)
        r8v = ra.get("base", {}).get("r8")
    if "jvm" in only:
        if not r8v:
            proj = os.path.join(work, "probe")
            write_android(proj)
            r8v = r8_version(proj, logs, "probe")
        rj = run_jvm(logs, work, r8v)
        json.dump(rj, open(os.path.join(logs, "jvm.json"), "w"), indent=1)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
