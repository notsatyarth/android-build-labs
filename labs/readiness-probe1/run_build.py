#!/usr/bin/env python3
"""Run one build of readiness probe 1 on a nowinandroid clone and write OUT/build.json.

Usage: run_build.py BUILD_ID --nia DIR --resolved resolved.json --out DIR [--timeout SEC]

BUILD_ID is a key of "builds" in probe_config.json (baseline, 1a-agp, 1a-kotlin, 1a-gradle, 1b-agp, 1b-kotlin,
1b-gradle). One build changes one tool: a version (1a, from resolved.json) or a switch (1b). Every build runs the same
task command (probe_config.json) with probe.init.gradle, which records each task's outcome and logs version markers.

Steps: edit the clone (version catalog, wrapper, settings), `./gradlew --version`, then the build (fresh daemon).
Versions are proven by `--version` and by markers the init script logs from inside the build: AGP and KGP on the root
project's classpath (configured before any subproject, so present even when a subproject fails to configure), AGP
and KGP as seen by :app and :core:model, Gradle and the JVM. For 1a-agp, if AGP refuses the Gradle version
("Minimum supported Gradle version is X"), the wrapper is raised to X (a released Gradle from services.gradle.org)
and the steps run again; build.json records the raise and the first attempt's log is kept.

A build is a harness fault (never a pass) when a marker that proves the change took effect is missing or wrong."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
INIT = os.path.join(HERE, "probe.init.gradle")
CONFIG = json.load(open(os.path.join(HERE, "probe_config.json")))
WRAPPER = "gradle/wrapper/gradle-wrapper.properties"
CATALOG = "gradle/libs.versions.toml"
VERSIONS_ALL = "https://services.gradle.org/versions/all"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def set_catalog(nia, key, value):
    p = os.path.join(nia, CATALOG)
    t = open(p).read()
    t2, n = re.subn(r'^(\s*%s\s*=\s*")[^"]+(")' % re.escape(key), r"\g<1>%s\g<2>" % value, t, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("catalog key %s not found in %s" % (key, p))
    open(p, "w").write(t2)
    return {"file": CATALOG, "key": key, "value": value}


def set_wrapper(nia, url):
    p = os.path.join(nia, WRAPPER)
    out = []
    for line in open(p).read().splitlines():
        if line.startswith("distributionSha256Sum="):
            continue  # the checksum belongs to the old distribution
        if line.startswith("distributionUrl="):
            line = "distributionUrl=" + url.replace(":", "\\:")
        out.append(line)
    open(p, "w").write("\n".join(out) + "\n")
    return {"file": WRAPPER, "key": "distributionUrl", "value": url}


def gradle_release_url(version):
    """Download URL of a Gradle version listed by services.gradle.org (release, rc, milestone or snapshot)."""
    req = urllib.request.Request(VERSIONS_ALL, headers={"User-Agent": "android-build-labs-readiness-probe"})
    for d in json.load(urllib.request.urlopen(req, timeout=60)):
        if d.get("version") == version and not d.get("broken"):
            return d["downloadUrl"]
    return None


def gradlew(nia, args, logpath, timeout):
    cmd = ["./gradlew"] + args
    t0 = time.time()
    with open(logpath, "w") as f:
        f.write("# cmd: %s\n" % " ".join(cmd))
        f.flush()
        try:
            p = subprocess.run(cmd, cwd=nia, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
        f.write("\n# exit=%s duration_s=%.1f\n" % (code, time.time() - t0))
    return code, round(time.time() - t0, 1)


def read(path):
    try:
        return open(path, errors="replace").read()
    except OSError:
        return ""


def parse_version_log(text):
    g = re.search(r"^Gradle (\S+)", text, re.M)
    jvms = re.findall(r"^(?:Launcher |Daemon )?JVM:\s+(.+)$", text, re.M)
    return {"gradle": g.group(1) if g else None, "jvm": jvms}


def parse_markers(text):
    m = re.search(r"^LAB-PROBE gradle=(\S+) jvm=(\S+) vendor=(\S+) warningMode=(\S+) previews=(\S+)", text, re.M)
    root = None
    if m:
        root = {"gradle": m.group(1), "jvm": m.group(2), "vendor": m.group(3), "warning_mode": m.group(4),
                "previews": m.group(5)}
    rc = re.search(r"^LAB-PROBE root-classpath agp=(\S+) kgp=(\S+)", text, re.M)
    agp = sorted(set(re.findall(r"^LAB-PROBE agp=(\S+) project=", text, re.M)))
    kgp = sorted(set(re.findall(r"^LAB-PROBE kgp=(\S+) project=", text, re.M)))
    lv = dict((t, v) for v, t in re.findall(r"^LAB-PROBE lv=(\S+) (\S+)$", text, re.M))
    return {"root": root, "root_agp": rc.group(1) if rc else None, "root_kgp": rc.group(2) if rc else None, "agp": agp, "kgp": kgp, "lv_by_task": lv, "lv_values": sorted(set(lv.values()))}


def first_errors(text, nia):
    """'What went wrong' blocks: first three lines of each of the first five blocks, verbatim (clone path removed)."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "* What went wrong:":
            block = [l.replace(nia + "/", "") for l in lines[i + 1:i + 4] if l.strip() and not l.startswith("* ")]
            out.append(block)
            if len(out) == 5:
                break
    return out


def compile_errors_for(task, text, nia):
    proj = task.rsplit(":", 1)[0]
    pdir = "/" + proj.strip(":").replace(":", "/") + "/"
    res = []
    for line in text.splitlines():
        if (line.startswith("e: ") or "ERROR:" in line) and pdir in line:
            res.append(line.replace("file://" + nia + "/", "").replace(nia + "/", "")[:400])
            if len(res) == 3:
                break
    return res


def tasks_from_probe(pdir):
    planned_path = os.path.join(pdir, "planned.json")
    planned = json.load(open(planned_path)) if os.path.exists(planned_path) else None
    events = {}
    ep = os.path.join(pdir, "events.jsonl")
    if os.path.exists(ep):
        for line in open(ep):
            line = line.strip()
            if line:
                e = json.loads(line)
                events[e["path"]] = e
    return planned, events


def run_once(nia, out, b, extra_args, timeout, tag):
    """--version, then the build. Returns a dict of raw results."""
    props = ["-P%s=%s" % kv for kv in sorted(b.get("props", {}).items())]
    pdir = os.path.join(out, "probe" + tag)
    os.makedirs(pdir, exist_ok=True)
    r = {}
    code, _ = gradlew(nia, ["--version"], os.path.join(out, "version%s.log" % tag), 600)
    r["version_exit"] = code
    r["version"] = parse_version_log(read(os.path.join(out, "version%s.log" % tag)))
    # A fresh daemon for the build: AGP prints some warnings (the experimental-option one) once per daemon.
    subprocess.run(["./gradlew", "--stop"], cwd=nia, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    args = ["--init-script", INIT, "-Dprobe.out=" + pdir] + CONFIG["common_args"] + extra_args + props + CONFIG["tasks"]
    r["command"] = "./gradlew " + " ".join(a.replace(HERE + "/", "").replace(pdir, "PROBE_OUT") for a in args)
    code, dur = gradlew(nia, args, os.path.join(out, "build%s.log" % tag), timeout)
    r["build_exit"] = code
    r["duration_s"] = dur
    r["probe_dir"] = pdir
    subprocess.run(["./gradlew", "--stop"], cwd=nia, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("build")
    ap.add_argument("--nia", required=True)
    ap.add_argument("--resolved", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=4800)
    ap.add_argument("--tasks", help="local smoke test only: replace the shared task command (CI never sets this)")
    a = ap.parse_args()
    if a.tasks:
        CONFIG["tasks"] = a.tasks.split()
    nia = os.path.realpath(a.nia)
    out = os.path.realpath(a.out)
    os.makedirs(out, exist_ok=True)
    b = CONFIG["builds"][a.build]
    res = json.load(open(a.resolved))
    base = res["baseline"]
    nxt = res["next"]
    commit = subprocess.run(["git", "-C", nia, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    expected = {"gradle": base["gradle"], "agp": base["agp"], "kotlin": base["kotlin"]}
    edits, notes = [], []
    tool, mode = b["tool"], b["mode"]
    if mode == "real" and tool == "agp":
        edits.append(set_catalog(nia, "androidGradlePlugin", nxt["agp"]["version"]))
        expected["agp"] = nxt["agp"]["version"]
        # nowinandroid's catalog: "AGP and tools should be updated together" (androidTools = AGP + 23.0.0)
        m = re.match(r"^(\d+)(\..*)$", nxt["agp"]["version"])
        if m and base.get("androidTools"):
            edits.append(set_catalog(nia, "androidTools", "%d%s" % (int(m.group(1)) + 23, m.group(2))))
    elif mode == "real" and tool == "kotlin":
        edits.append(set_catalog(nia, "kotlin", nxt["kotlin"]["version"]))
        expected["kotlin"] = nxt["kotlin"]["version"]
    elif mode == "real" and tool == "gradle":
        edits.append(set_wrapper(nia, nxt["gradle"]["url"]))
        expected["gradle"] = nxt["gradle"]["version"]
    if b.get("settings_append"):
        with open(os.path.join(nia, "settings.gradle.kts"), "a") as f:
            f.write("\n" + b["settings_append"] + "\n")
        edits.append({"file": "settings.gradle.kts", "append": b["settings_append"]})
    log("build %s: edits %s" % (a.build, edits))

    attempts = []
    r = run_once(nia, out, b, b.get("args", []), a.timeout, "")
    attempts.append({k: r[k] for k in ("version_exit", "build_exit", "duration_s", "command")})
    gradle_raised = None
    text = read(os.path.join(out, "build.log"))
    m = re.search(r"Minimum supported Gradle version is (\S+?)\.?\s+Current version is (\S+?)\.?(?:\s|$)", text)
    if m and mode == "real" and tool == "agp":
        need = m.group(1)
        url = gradle_release_url(need)
        gradle_raised = {"from": expected["gradle"], "to": need, "reason": m.group(0).strip(), "url": url}
        if url:
            log("AGP needs Gradle %s: raising the wrapper and running again" % need)
            for name in ("version", "build"):
                os.replace(os.path.join(out, name + ".log"), os.path.join(out, name + "-attempt1.log"))
            os.replace(r["probe_dir"], os.path.join(out, "probe-attempt1"))
            edits.append(set_wrapper(nia, url))
            expected["gradle"] = need
            r = run_once(nia, out, b, b.get("args", []), a.timeout, "")
            attempts.append({k: r[k] for k in ("version_exit", "build_exit", "duration_s", "command")})
            text = read(os.path.join(out, "build.log"))
        else:
            notes.append("AGP needs Gradle %s but services.gradle.org lists no such version; not raised" % need)

    planned, events = tasks_from_probe(r["probe_dir"])
    markers = parse_markers(text)
    exit_code = r["build_exit"]

    # Per-task outcomes: every planned task (root build) plus every event (included builds such as build-logic).
    outcomes = {}
    for t in planned or []:
        e = events.get(t)
        outcomes[t] = e["outcome"] if e else "not-run"
    for t, e in events.items():
        if t not in outcomes:
            outcomes[t] = e["outcome"]
    configuration_failed = exit_code != 0 and planned is None
    failed = sorted(t for t, o in outcomes.items() if o == "failed")
    # Counts cover the root build's task graph (planned tasks). Included builds (build-logic) are counted apart.
    root_outcomes = [outcomes[t] for t in (planned or [])]
    other = {t: o for t, o in outcomes.items() if t not in set(planned or [])}
    counts = {"failed": root_outcomes.count("failed"), "not_run": root_outcomes.count("not-run"),
              "passed": sum(1 for o in root_outcomes if o in ("success", "up-to-date", "from-cache", "no-source", "skipped")),
              "planned": len(planned) if planned is not None else None,
              "included_build_tasks": len(other), "included_build_failed": sum(1 for o in other.values() if o == "failed")}
    for o in ("success", "up-to-date", "from-cache", "no-source", "skipped", "failed", "not-run"):
        counts["by_outcome_" + o.replace("-", "_")] = root_outcomes.count(o)
    failed_detail = {}
    for t in failed:
        msgs = events.get(t, {}).get("messages", [])
        failed_detail[t] = {"messages": msgs[:4], "compiler_errors": compile_errors_for(t, text, nia)}
    test_failures = re.findall(r"^(\S+ > .+ FAILED)$", text, re.M)[:10]

    # Proof that the change took effect. Any problem here makes the build a harness fault.
    faults, proof = [], {}
    root = markers["root"]
    if root is None:
        faults.append("init-script marker 'LAB-PROBE gradle=' missing")
    else:
        proof["gradle_in_build"] = root["gradle"]
        proof["jvm"] = root["jvm"]
        if root["gradle"] != expected["gradle"]:
            faults.append("Gradle in build %s != expected %s" % (root["gradle"], expected["gradle"]))
        if not root["jvm"].startswith("21"):
            faults.append("JVM in build %s is not 21" % root["jvm"])
    if r["version"]["gradle"] != expected["gradle"]:
        faults.append("gradlew --version reports %s, expected %s" % (r["version"]["gradle"], expected["gradle"]))
    proof["agp_root_classpath"] = markers["root_agp"]
    proof["kgp_root_classpath"] = markers["root_kgp"]
    proof["agp_app"] = markers["agp"]
    proof["kgp_app_core_model"] = markers["kgp"]
    if markers["root_agp"] != expected["agp"]:
        faults.append("AGP on the root classpath %s != expected %s" % (markers["root_agp"], expected["agp"]))
    if markers["root_kgp"] != expected["kotlin"]:
        faults.append("KGP on the root classpath %s != expected %s" % (markers["root_kgp"], expected["kotlin"]))
    if markers["agp"] and markers["agp"] != [expected["agp"]]:
        faults.append("AGP in :app %s != expected %s" % (markers["agp"], expected["agp"]))
    if markers["kgp"] and markers["kgp"] != [expected["kotlin"]]:
        faults.append("KGP in :app/:core:model %s != expected %s" % (markers["kgp"], expected["kotlin"]))
    if not markers["agp"] and not configuration_failed:
        faults.append("AGP marker of :app missing although configuration did not fail")
    flat = re.sub(r"\s+", " ", text)
    if a.build == "1b-agp":
        exp_line = re.search(r"WARNING: The option setting '[^']*simulateAgpVersionBehavior[^']*' is experimental\.?", flat)
        removed = re.search(r"The option '[^']+' is deprecated\. The current default is '[^']*'\. It was removed in version 10\.0", flat)
        proof["agp_experimental_option_line"] = exp_line.group(0).strip() if exp_line else None
        proof["agp_removed_in_10_line"] = removed.group(0) if removed else None
        if not exp_line and not removed:
            faults.append("1b-agp: neither AGP's experimental-option warning nor a 'removed in version 10.0' message in the log")
    if a.build == "1b-kotlin":
        km = re.match(r"^(\d+)\.(\d+)", expected["kotlin"])
        want = "%s.%d" % (km.group(1), int(km.group(2)) + 1)
        proof["kotlin_language_expected"] = want
        proof["kotlin_language_values"] = markers["lv_values"]
        proof["kotlin_compile_tasks_logged"] = len(markers["lv_by_task"])
        trynext = re.search(r"^[^#\n][^\n]*Experimental 'kotlin\.experimental\.tryNext' Option Enabled[^\n]*", text, re.M)
        proof["trynext_line"] = trynext.group(0).strip()[:300] if trynext else None
        if not markers["lv_by_task"]:
            faults.append("1b-kotlin: no Kotlin compile task logged a language version")
        elif markers["lv_values"] != [want]:
            faults.append("1b-kotlin: language versions %s, expected only %s" % (markers["lv_values"], want))
    if a.build in ("1a-kotlin", "baseline"):
        proof["kotlin_language_values"] = markers["lv_values"]
        proof["kotlin_compile_tasks_logged"] = len(markers["lv_by_task"])
    if a.build == "1b-gradle":
        ok_wm = root is not None and root["warning_mode"] == "Fail"
        ok_fp = root is not None and "NO_IMPLICIT_LOOKUP_IN_PARENT_PROJECTS" in root["previews"].split(",")
        proof["warning_mode"] = root["warning_mode"] if root else None
        proof["feature_previews"] = root["previews"] if root else None
        if not ok_wm:
            faults.append("1b-gradle: warning mode is not Fail")
        if not ok_fp:
            faults.append("1b-gradle: feature preview NO_IMPLICIT_LOOKUP_IN_PARENT_PROJECTS not active")
    if exit_code == 0 and planned is None:
        faults.append("build passed but planned.json is missing (init script did not record the task graph)")
    if exit_code == "timeout":
        faults.append("build timed out after %d s" % a.timeout)

    result = {
        "schema": "readiness-probe1-build/1", "build": a.build, "mode": mode, "tool": tool,
        "nia_commit": commit, "resolved_at": res["resolved_at"], "expected": expected, "edits": edits,
        "gradle_raised": gradle_raised, "notes": notes, "attempts": attempts, "command": r["command"],
        "jvm": r["version"]["jvm"], "build_exit": exit_code, "duration_s": r["duration_s"],
        "configuration_failed": configuration_failed, "counts": counts, "failed": failed_detail,
        "build_errors": first_errors(text, nia), "test_failures": test_failures,
        "proof": proof, "harness_fault": bool(faults), "harness_faults": faults,
        "outcomes": outcomes, "kotlin_language_by_task": markers["lv_by_task"],
    }
    json.dump(result, open(os.path.join(out, "build.json"), "w"), indent=1, sort_keys=True)
    print("## %s (%s, %s)" % (a.build, mode, tool))
    print()
    print("- nowinandroid %s; expected Gradle %s, AGP %s, Kotlin %s; JVM %s" % (commit[:10], expected["gradle"], expected["agp"], expected["kotlin"], "; ".join(r["version"]["jvm"])))
    if gradle_raised:
        print("- Gradle raised from %s to %s: %s" % (gradle_raised["from"], gradle_raised["to"], gradle_raised["reason"]))
    print("- exit %s, configuration failed: %s, %s" % (exit_code, configuration_failed, json.dumps(counts)))
    print("- harness fault: %s %s" % (bool(faults), "; ".join(faults)))
    print("- proof: `%s`" % json.dumps(proof)[:1500])
    for t, d in failed_detail.items():
        print("- FAILED %s: %s" % (t, " / ".join((d["compiler_errors"] or d["messages"])[:2])[:500]))
    if not failed_detail:
        for blk in result["build_errors"][:2]:
            print("- build error: %s" % " / ".join(blk)[:500])
    print()


if __name__ == "__main__":
    main()
