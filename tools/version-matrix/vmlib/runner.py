"""Run cells one at a time: prepare workspace, version guard, tasks, cleanup, logs."""
import glob
import os
import re
import shutil
import signal
import subprocess
import time

from . import config, guard, project, util

DAEMON_RE = re.compile(r"GradleDaemon|KotlinCompileDaemon|GradleWorkerMain|GradleWrapperMain")


def cell_args(cell, common, with_flags=True):
    # A cell's own `--name=value` option replaces the same option in the common arguments: Gradle rejects
    # a repeated --warning-mode ("Multiple arguments were provided for command-line option").
    own = {a.split("=", 1)[0] for a in cell["gradle_args"] if a.startswith("--") and "=" in a}
    args = [a for a in common if a.split("=", 1)[0] not in own]
    args += ["-P%s=%s" % (k, v) for k, v in sorted(cell["flags"].items())] if with_flags else []
    args += cell["gradle_args"]
    return args


def build_env(cfg, cell):
    env = dict(os.environ)
    jh = cell.get("java_home")
    if jh:
        jh = os.path.expanduser(jh)
        env["JAVA_HOME"] = jh
        env["PATH"] = os.path.join(jh, "bin") + os.pathsep + env.get("PATH", "")
    if cfg.get("gradle_user_home"):
        env["GRADLE_USER_HOME"] = os.path.expanduser(cfg["gradle_user_home"])
    env.update(cell.get("env") or {})
    return env


def steps_for(cfg, cell):
    """Ordered list of {name, args, role}. role: version | guard | task."""
    common = cfg["gradle_args"]
    quiet = ["--console=plain"]
    steps = [
        {"name": "version", "role": "version", "args": ["--version"]},
        {"name": "guard-buildEnvironment", "role": "guard",
         "args": quiet + ["-P%s=%s" % kv for kv in sorted(cell["flags"].items())] + cfg["guard_tasks"]},
    ]
    for i, t in enumerate(cell["tasks"], 1):
        steps.append({"name": "%02d-%s" % (i, util.slug(t[0] if t else "gradle")), "role": "task",
                      "args": cell_args(cell, common) + t})
    return steps


def command_for(step):
    return ["./gradlew"] + step["args"]


def snapshot_procs():
    try:
        out = subprocess.run(["ps", "-axo", "pid=,args="], stdout=subprocess.PIPE, universal_newlines=True,
                             timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    procs = {}
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and DAEMON_RE.search(parts[1]):
            procs[int(parts[0])] = parts[1]
    return procs


def run_step(ws, step, env, log_path, timeout):
    cmd = command_for(step)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    t0 = time.time()
    timed_out = False
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        log.write("# cmd: %s\n# cwd: %s\n# JAVA_HOME=%s\n" % (" ".join(cmd), ws, env.get("JAVA_HOME", "")))
        log.flush()
        try:
            p = subprocess.Popen(cmd, cwd=ws, env=env, stdout=log, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as e:
            log.write("# harness error: %s\n# exit=127\n" % e)
            return {"name": step["name"], "role": step["role"], "cmd": cmd, "exit_code": 127,
                    "duration_s": 0.0, "timed_out": False, "log": log_path}
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(p.pid, sig)
                except OSError:
                    pass
                try:
                    p.wait(timeout=10)
                    break
                except subprocess.TimeoutExpired:
                    continue
            code = 124
        log.write("\n# exit=%d%s\n" % (code, " (timeout)" if timed_out else ""))
    return {"name": step["name"], "role": step["role"], "cmd": cmd, "exit_code": code,
            "duration_s": round(time.time() - t0, 1), "timed_out": timed_out, "log": log_path}


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def cleanup_daemons(cfg, ws, env, before, log):
    mode = cfg["daemon_cleanup"]
    if mode == "none":
        return
    try:
        subprocess.run(["./gradlew", "--stop", "--console=plain"], cwd=ws, env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        log("  gradlew --stop failed: %s" % e)
    if mode == "stop+kill":
        time.sleep(2)
        for pid in set(snapshot_procs()) - set(before):
            try:
                os.kill(pid, signal.SIGTERM)
                log("  killed leftover pid %d" % pid)
            except OSError:
                pass


def run_cell(cfg, cell, out_dir, workspace, log=print, keep=False):
    """Run one cell. Returns the raw result dict (no classification; the collector does that from logs)."""
    root = cfg["project"]
    cdir = os.path.join(out_dir, util.slug(cell["name"]))
    os.makedirs(cdir, exist_ok=True)
    ws = os.path.join(workspace, util.slug(cell["name"]))
    res = {"name": cell["name"], "axes": cell["axes"], "requested": cell["requested"], "flags": cell["flags"],
           "gradle_args": cell["gradle_args"], "java_home": cell.get("java_home"), "baseline": cell["baseline"],
           "edits": cell["edits"], "ref": cell.get("ref"), "commit": cell.get("commit"), "pins": cell.get("pins"),
           "steps": [], "outcome": None, "guard": None, "warnings": [],
           "started": util.now_iso(), "dir": cdir}
    t0 = time.time()
    before = snapshot_procs() if cfg["daemon_cleanup"] == "stop+kill" else {}
    mode = None
    try:
        info = project.prepare_workspace(root, ws, cfg["mode"], cell.get("commit") or cell.get("ref") or cfg["ref"],
                                         cfg["copy_files"])
        mode = info["mode"]
        res["workspace"] = ws
        res["warnings"] += info["warnings"]
        project.apply_edits(ws, cell["edits"])
        env = build_env(cfg, cell)
        for step in steps_for(cfg, cell):
            log("  [%s] ./gradlew %s" % (step["name"], " ".join(step["args"])))
            r = run_step(ws, step, env, os.path.join(cdir, step["name"] + ".log"), cell["timeout_sec"])
            res["steps"].append(r)
            if step["role"] == "guard":
                res["guard"] = guard.check(cell["requested"], _read(res["steps"][0]["log"]), _read(r["log"]))
                res["guard"]["step_exit"] = r["exit_code"]
                if r["exit_code"] == 0 and res["guard"]["result"] != "OK":
                    res["outcome"] = "INVALID"
                    break
            if r["exit_code"] != 0:
                res["outcome"] = "TIMEOUT" if r["timed_out"] else "FAIL"
                res["failed_step"] = step["name"]
                break
        if res["outcome"] is None:
            res["outcome"] = "PASS"
        # keep the problems report of the last run
        pr = os.path.join(ws, cfg["problems_report"])
        if os.path.isfile(pr):
            shutil.copy2(pr, os.path.join(cdir, "problems-report.html"))
        # keep the newest configuration cache report (read by probes/configuration_cache.py)
        ccs = glob.glob(os.path.join(ws, "build", "reports", "configuration-cache", "*", "*",
                                     "configuration-cache-report.html"))
        if ccs:
            shutil.copy2(max(ccs, key=os.path.getmtime), os.path.join(cdir, "configuration-cache-report.html"))
        cleanup_daemons(cfg, ws, env, before, log)
    except (project.ProjectError, OSError) as e:
        res["outcome"] = "ERROR"
        res["error"] = str(e)
        log("  ERROR: %s" % e)
    finally:
        if mode and not keep:
            if os.path.abspath(ws).startswith(os.path.abspath(workspace) + os.sep):
                project.remove_workspace(root, ws, mode)
    res["duration_s"] = round(time.time() - t0, 1)
    util.write_json(os.path.join(cdir, "cell.json"), res)
    return res


def dry_run_plan(cfg, plan):
    """Commands and edits per cell, nothing executed or written."""
    out = []
    for cell in plan["cells"]:
        item = {"name": cell["name"], "skip": cell["skip"], "edits": cell["edits"], "steps": []}
        if not cell["skip"]:
            item["env"] = {k: v for k, v in (
                ("JAVA_HOME", cell.get("java_home")), ("GRADLE_USER_HOME", cfg.get("gradle_user_home"))) if v}
            for s in steps_for(cfg, cell):
                item["steps"].append({"name": s["name"], "cmd": command_for(s)})
        out.append(item)
    return out
