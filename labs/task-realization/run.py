#!/usr/bin/env python3
"""Task configuration avoidance on nowinandroid: what gets realized, what one eager line costs, and what
Gradle does (and does not) tell you about it.

Every run uses Gradle's build operation trace (-Dorg.gradle.internal.operations.trace, internal format) and
realize.py to count "Register task" and "Realize task" operations. Nothing in nowinandroid is edited: each
pattern is injected with an init script from inject/ (gradle.lifecycle.beforeProject, so Isolated Projects
stays on, as nowinandroid configures it).

Unless a scenario says "hit", the configuration cache directory is deleted first, so the run configures.

Usage (JAVA_HOME = JDK 17, ANDROID_HOME set):
  python3 run.py NIA_DIR [--logs logs] [--repeat 3] [--tapi-cp CLASSPATH] [--only name,name]
Writes logs/<scenario>.json (realize.py summary plus exit code and console checks) and logs/<scenario>.console.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import realize  # noqa: E402

INJ = os.path.join(HERE, "inject")
TARGET = os.environ.get("LAB_TARGET", ":core:data")  # Android library used for the single-project patterns
APP = os.environ.get("LAB_APP", ":app")  # the overrides exist only for testing the harness on a small build
DRYRUN = os.environ.get("LAB_DRYRUN", ":app:assembleDemoDebug")

# name, gradle args, init script (or None), extra -D properties, delete CC entry first
SCENARIOS = [
    ("help-miss", ["help"], None, {}, True),
    ("help-hit", ["help"], None, {}, False),
    ("dryrun-miss", [DRYRUN, "--dry-run"], None, {}, True),
    ("dryrun-hit", [DRYRUN, "--dry-run"], None, {}, False),
    ("app-tasks-all", [APP + ":tasks", "--all"], None, {}, True),
    ("baseline-warnfail", ["help", "--warning-mode=fail"], None, {}, True),
    ("eager-withtype", ["help"], "eager-withtype.init.gradle.kts", {}, True),
    ("lazy-withtype", ["help"], "lazy-withtype.init.gradle.kts", {}, True),
    ("matching", ["help"], "matching.init.gradle.kts", {}, True),
    ("all", ["help"], "all.init.gradle.kts", {}, True),
    ("create-warnfail", ["help", "--warning-mode=fail"], "create.init.gradle.kts", {"lab.target": TARGET}, True),
    ("registering-warnfail", ["help", "--warning-mode=fail"], "registering.init.gradle.kts", {"lab.target": TARGET}, True),
    ("broken-lazy-help", ["help"], "broken-lazy.init.gradle.kts", {"lab.target": TARGET}, True),
    ("broken-lazy-tasks", [TARGET + ":tasks", "--all"], "broken-lazy.init.gradle.kts", {"lab.target": TARGET}, True),
    ("broken-eager-help", ["help"], "broken-eager.init.gradle.kts", {"lab.target": TARGET}, True),
    ("side-effect", [TARGET + ":check", "--dry-run"], "side-effect.init.gradle.kts", {"lab.target": TARGET}, True),
    ("side-effect-plus-all", [TARGET + ":check", "--dry-run"], "side-effect-plus-all.init.gradle.kts", {"lab.target": TARGET}, True),
]
TIMED = ["eager-withtype", "lazy-withtype", "all", "help-miss"]  # repeated for configuration time


def cc_dir_clear(nia):
    shutil.rmtree(os.path.join(nia, ".gradle", "configuration-cache"), ignore_errors=True)


def checks_from_console(out):
    return {
        "build_successful": "BUILD SUCCESSFUL" in out,
        "cc_reused": "Configuration cache entry reused" in out,
        "cc_stored": "Configuration cache entry stored" in out,
        "deprecation_failure": "Deprecated Gradle features were used in this build" in out,
        "kotlin_deprecation_warning": bool(re.search(r"^w: .*is deprecated", out, re.M)),
        "labVerify_in_graph": bool(re.search(r"^" + re.escape(TARGET) + r":labVerify ", out, re.M)),
        "labBroken_error": "labBroken: configuration failed" in out,
        "deprecation_lines": sorted({l.strip()[:200] for l in out.splitlines()
                                     if re.search(r"deprecated", l, re.I) and not l.startswith("$ ")})[:30],
        "what_went_wrong": (re.search(r"\* What went wrong:\n(.*(?:\n>.*){0,3})", out) or [None, ""])[1].strip(),
    }


def run_one(nia, logs, name, args, init, props, clear, suffix=""):
    if clear:
        cc_dir_clear(nia)
    prefix = os.path.join(logs, "trace-" + name + suffix)
    for f in (prefix + "-log.txt",):
        if os.path.exists(f):
            os.remove(f)
    cmd = ["./gradlew", "--console=plain", "-Dorg.gradle.internal.operations.trace=" + prefix,
           "-Dorg.gradle.internal.operations.trace.tree=false"]
    cmd += ["-D%s=%s" % kv for kv in props.items()]
    if init:
        cmd += ["--init-script", os.path.join(INJ, init)]
    cmd += args
    t0 = time.time()
    p = subprocess.run(cmd, cwd=nia, capture_output=True, text=True)
    wall = round(time.time() - t0, 2)
    out = p.stdout + p.stderr
    with open(os.path.join(logs, name + suffix + ".console"), "w") as f:
        f.write("$ " + " ".join(cmd) + "\n" + out)
    res = {"scenario": name, "args": args, "init": init, "props": props, "exit": p.returncode, "wall_s": wall}
    res.update(checks_from_console(out))
    trace = prefix + "-log.txt"
    if os.path.exists(trace):
        s = realize.summarize(realize.load(trace))
        res.update(s)
        os.remove(trace)
    return res


def tapi(nia, logs, cp, mode):
    cc_dir_clear(nia)
    name = "tapi-" + mode
    prefix = os.path.join(logs, "trace-" + name)
    extra = ["-Dorg.gradle.internal.GradleProjectBuilderOptions=omit_all_tasks"] if mode == "omit" else []
    cmd = ["java", "-cp", cp, os.path.join(HERE, "TapiModel.java"), nia,
           "-Dorg.gradle.internal.operations.trace=" + prefix, "-Dorg.gradle.internal.operations.trace.tree=false"] + extra
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = p.stdout + p.stderr
    with open(os.path.join(logs, name + ".console"), "w") as f:
        f.write("$ " + " ".join(cmd) + "\n" + out)
    m = re.search(r"TAPI GradleProject projects=(\d+) tasksListed=(\d+) wallMs=(\d+)", out)
    res = {"scenario": name, "exit": p.returncode,
           "model_projects": int(m[1]) if m else None, "model_tasks_listed": int(m[2]) if m else None,
           "wall_ms": int(m[3]) if m else None}
    res.update(checks_from_console(out))
    trace = prefix + "-log.txt"
    if os.path.exists(trace):
        res.update(realize.summarize(realize.load(trace)))
        os.remove(trace)
    return res


def save(logs, res):
    with open(os.path.join(logs, res["scenario"] + ".json"), "w") as f:
        json.dump(res, f, indent=1)
    c = res.get("configuration_phase", {})
    print("%-22s exit=%s registered=%s realized=%s eagerFlag=%s phases=%s config-phase=%s cfgMs=%s %s" % (
        res["scenario"], res["exit"], res.get("registered"), res.get("realized"), res.get("realized_eager_flag"),
        res.get("by_phase"), c.get("realized"), res.get("configure_build_ms"),
        ("model tasks=%s" % res["model_tasks_listed"]) if "model_tasks_listed" in res else ""), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nia")
    ap.add_argument("--logs", default=os.path.join(HERE, "logs"))
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--tapi-cp")
    ap.add_argument("--only")
    a = ap.parse_args()
    nia = os.path.abspath(a.nia)
    logs = os.path.abspath(a.logs)
    os.makedirs(logs, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    # warm-up: dependencies, build-logic compile, daemon start (not measured)
    subprocess.run(["./gradlew", "--console=plain", "help"], cwd=nia, capture_output=True)
    for name, args, init, props, clear in SCENARIOS:
        if only and name not in only:
            continue
        save(logs, run_one(nia, logs, name, args, init, props, clear))
    if a.tapi_cp and (not only or "tapi" in only):
        for mode in ("default", "omit"):
            save(logs, tapi(nia, logs, a.tapi_cp, mode))
    # configuration time: alternate the timed scenarios, configuration cache cleared each time
    timing = {n: [] for n in TIMED}
    if a.repeat > 0 and (not only or "timing" in only):
        by_name = {s[0]: s for s in SCENARIOS}
        for i in range(a.repeat):
            order = TIMED if i % 2 == 0 else list(reversed(TIMED))
            for n in order:
                _, args, init, props, _ = by_name[n]
                r = run_one(nia, logs, n, args, init, props, True, suffix="-t%d" % i)
                timing[n].append(r.get("configure_build_ms"))
                os.remove(os.path.join(logs, n + "-t%d" % i + ".console"))
        with open(os.path.join(logs, "timing.json"), "w") as f:
            json.dump(timing, f, indent=1)
        print("configure build ms:", json.dumps(timing))
    subprocess.run(["./gradlew", "--stop"], cwd=nia, capture_output=True)


if __name__ == "__main__":
    main()
