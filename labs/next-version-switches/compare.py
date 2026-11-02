"""Check the CI run of the next-version-switches lab against the results of the original macOS lab (AGP 9.3.2, Gradle 9.7.1, KGP 2.3.0).
Usage: python3 -I compare.py OUT_DIR. Prints a Markdown table; 'DIFFERS' means the CI log does not show what the macOS log showed."""
import re, sys
from pathlib import Path
out = Path(sys.argv[1])
def L(i):
    p = out / f"{i}.log"
    return p.read_text(errors="replace") if p.exists() else None
def ok_build(t): return "BUILD SUCCESSFUL" in t
def fail_build(t): return "BUILD FAILED" in t
def has(t, s): return s in t
rows = []
def chk(i, what, expected, fn):
    t = L(i)
    rows.append((i, what, expected, "no data" if t is None else ("match" if fn(t) else "DIFFERS")))
chk("e0_baseline_jdk21", "baseline help on JDK 21", "success, no 'removed in version 10.0'", lambda t: ok_build(t) and not has(t, "removed in version 10.0"))
chk("e1a_simulate_jdk17", "simulate 10.0.0 on JDK 17", "fails: needs Java 21", lambda t: fail_build(t) and has(t, "Android Gradle plugin requires Java 21 to run. You are currently using Java 17."))
chk("e1b_simulate_jdk21", "simulate 10.0.0 on JDK 21", "fails on android.useAndroidX", lambda t: fail_build(t) and has(t, "The option 'android.useAndroidX' is deprecated. The current default is 'false'. It was removed in version 10.0"))
chk("e1c_simulate_jdk21_removed_props", "simulate, 3 removed properties deleted", "help passes", ok_build)
chk("e1d_simulate_jdk21_assemble", "same, assembleDemoDebug", "fails: AndroidX dependencies without useAndroidX", lambda t: fail_build(t) and "contains AndroidX dependencies" in t)
chk("e2a_optouts_jdk17", "builtInKotlin=false and newDsl=false", "fails: KotlinAndroidProjectExtension missing", lambda t: fail_build(t) and has(t, "Extension of type 'KotlinAndroidProjectExtension' does not exist."))
chk("e2b_newDsl_false_only_jdk17", "newDsl=false only", "help passes, deprecation warning", lambda t: ok_build(t) and has(t, "android.newDsl=false' is deprecated"))
chk("e2c_optouts_simulate_jdk21", "opt-outs plus simulate", "builtInKotlin opt-out becomes an error", lambda t: fail_build(t) and has(t, "The option 'android.builtInKotlin' is deprecated. The current default is 'true'. It was removed in version 10.0"))
chk("e3a_tryNext_baseline_info", "baseline compile, no tryNext", "no tryNext warning", lambda t: ok_build(t) and "kotlin.experimental.tryNext" not in t)
chk("e3b_tryNext_true_info", "kotlin.experimental.tryNext=true", "warning, 2.4 language version", lambda t: ok_build(t) and "Experimental 'kotlin.experimental.tryNext' Option Enabled" in t and "2.4 language version" in t)
chk("e4a_main_warning_mode_fail", "help --warning-mode=fail", "success (no deprecations at configuration time)", ok_build)
chk("e4b_no_implicit_lookup", "NO_IMPLICIT_LOOKUP_IN_PARENT_PROJECTS preview", "accepted, no warning", lambda t: ok_build(t) and "NO_IMPLICIT" not in t)
chk("e4c_featurepreview_enum_check", "feature name present in Gradle jars", "NO_IMPLICIT_LOOKUP_IN_PARENT_PROJECTS", lambda t: "NO_IMPLICIT_LOOKUP_IN_PARENT_PROJECTS" in t)
chk("e5a_bl_cc_false_run1", "build-logic cc=false, run 1", "entry stored (property ignored)", lambda t: has(t, "Configuration cache entry stored."))
chk("e5a_bl_cc_false_run2", "build-logic cc=false, run 2", "entry reused", lambda t: has(t, "Reusing configuration cache."))
chk("e5b_1_clean_then_compile", "build-logic caching=false, clean then compile", "build-logic compileKotlin still from cache", lambda t: "Loaded cache entry for task ':build-logic:convention:compileKotlin'" in t)
chk("e5c_all_flipped", "all four build-logic properties flipped", "root keeps configurationCache=true", lambda t: re.search(r"configurationCache=true", t) is not None)
chk("e5d_kotlin_daemon_included_build", "Kotlin daemons while building build-logic and a module", "two daemons: compiler 2.4.0 (256m, ParallelGC) and 2.3.0 (320m, G1)", lambda t: "2.4.0" in t and "2.3.0" in t and "ReservedCodeCacheSize=256m" in t and "ReservedCodeCacheSize=320m" in t)
chk("e6a_kotlin_android_plugin", "kotlin.android plugin on an AGP 9.3.2 module", "fails: no longer required since AGP 9.0", lambda t: fail_build(t) and "plugin is no longer required for Kotlin support since AGP 9.0" in t)
chk("e6a2_kotlin_android_plugin_with_optouts", "same with both opt-outs", "AGP no longer objects; build fails elsewhere", lambda t: fail_build(t) and "no longer required for Kotlin support" not in t and "KotlinAndroidProjectExtension" in t)
chk("e6b_assemble_rerun_warning_mode_all", "full assembleDemoDebug, warning-mode all", "success, problems report written", lambda t: ok_build(t) and "Problems report is available at" in t)
chk("e6c_buildEnvironment", "buildEnvironment", "KGP 2.2.10 -> 2.3.0", lambda t: "kotlin-gradle-plugin:2.2.10 -> 2.3.0" in t)
print("| experiment | what | macOS result | CI (x86 Linux runner) |\n|---|---|---|---|")
for r in rows: print("| " + " | ".join(r) + " |")
bad = [r for r in rows if r[3] != "match"]
print(f"\n{len(rows) - len(bad)} of {len(rows)} match the macOS results." + ("" if not bad else " Not matching: " + ", ".join(r[0] for r in bad)))
