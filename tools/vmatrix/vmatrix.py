#!/usr/bin/env python3
"""vmatrix: version-matrix shadow-job harness for Gradle projects (Gradle, AGP, Kotlin, KSP).

Subcommands: discover | plan | run | report.   Standard library only, Python 3.9+.
Exit codes: 0 ok; 1 a cell failed/timed out/errored; 2 usage or config error; 3 a cell is INVALID
(the versions that ran differ from the requested ones). --fail-on never|invalid|any adjusts 1 and 3.
With --json, stdout carries exactly one JSON document; progress and notes go to stderr.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vmlib import classify, config, discover, project, report, runner, util  # noqa: E402


def eprint(*a):
    print(*a, file=sys.stderr)


def emit(args, obj, human):
    if args.json:
        json.dump(obj, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(human)


def add_common(p, run=False):
    p.add_argument("--config", help="matrix JSON file (default: built-in baseline + next-version cells)")
    p.add_argument("--project", help="path to the project checkout (default: config 'project' or $VMATRIX_PROJECT)")
    p.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    p.add_argument("--offline", action="store_true", help="never touch the network; use the discovery cache")
    p.add_argument("--refresh", action="store_true", help="ignore a fresh cache and refetch")
    p.add_argument("--cache", help="discovery cache file (default ~/.cache/vmatrix/discover.json or $VMATRIX_CACHE)")
    p.add_argument("--cells", help="comma-separated cell names to include")
    p.add_argument("--java-home", dest="java_home", help="JAVA_HOME for cells that do not set their own")
    p.add_argument("--gradle-user-home", dest="gradle_user_home",
                   help="isolated GRADLE_USER_HOME (keeps --stop away from other builds on this machine)")


def load_cfg(args):
    over = {"project": args.project, "java_home": getattr(args, "java_home", None),
            "gradle_user_home": getattr(args, "gradle_user_home", None)}
    for k in ("mode", "ref", "daemon_cleanup", "workspace", "timeout_sec"):
        over[k] = getattr(args, k, None)
    return config.load(args.config, over)


def make_plan(args, cfg):
    need = any(isinstance(v, str) and v.startswith("@")
               for c in cfg["cells"] for v in (c.get("axes") or {}).values())
    disc = discover.Discovery(args.cache, args.offline, args.refresh) if need else None
    plan = config.resolve(cfg, disc)
    if args.cells:
        want = set(args.cells.split(","))
        unknown = want - {c["name"] for c in plan["cells"]}
        if unknown:
            raise config.ConfigError("unknown cell(s): %s" % ", ".join(sorted(unknown)))
        plan["cells"] = [c for c in plan["cells"] if c["name"] in want]
    plan["discovery_notes"] = disc.notes if disc else []
    return plan


def fmt_plan(plan):
    L = ["Project: %s (git %s)" % (plan["project"]["path"], (plan["project"].get("git") or "none")[:10]),
         "Current pins: " + ", ".join("%s %s" % kv for kv in plan["pins"].items()),
         "Catalogs: " + (", ".join(plan["catalogs"]) or "none")]
    for c in plan["cells"]:
        what = ", ".join("%s %s" % kv for kv in c["axes"].items()) or "no version change"
        extra = ["%s=%s" % kv for kv in c["flags"].items()] + c["gradle_args"]
        L.append("- %s: %s%s%s" % (c["name"], what, " + " + " ".join(extra) if extra else "",
                                   "   SKIP: " + c["skip"] if c["skip"] else ""))
    for n in plan.get("discovery_notes", []):
        L.append("note: " + n)
    return "\n".join(L)


def cmd_discover(args):
    d = discover.Discovery(args.cache, args.offline, args.refresh)
    tools = args.tools.split(",") if args.tools else list(discover.TOOLS)
    chans = args.channels.split(",") if args.channels else ["stable", "rc", "beta", "alpha", "next"]
    out = {"tools": d.summary(tools, chans), "notes": d.notes, "cache": d.cache_path}
    L = []
    for t, row in out["tools"].items():
        L.append("%-7s %s" % (t, "  ".join("%s=%s" % (k, v or "-") for k, v in row.items())))
    L += ["note: " + n for n in d.notes]
    emit(args, out, "\n".join(L))
    return 0


def cmd_plan(args):
    cfg = load_cfg(args)
    plan = make_plan(args, cfg)
    emit(args, plan, fmt_plan(plan))
    return 0


def skipped_result(c, cdir):
    return {"name": c["name"], "axes": c["axes"], "requested": c["requested"], "flags": c["flags"],
            "gradle_args": c["gradle_args"], "baseline": c["baseline"], "edits": [], "steps": [],
            "outcome": "SKIPPED", "skip_reason": c["skip"], "guard": None, "warnings": [], "duration_s": 0,
            "dir": cdir}


def cmd_run(args):
    cfg = load_cfg(args)
    plan = make_plan(args, cfg)
    if args.dry_run:
        dr = runner.dry_run_plan(cfg, plan)
        human = [fmt_plan(plan), ""]
        for c in dr:
            human.append("== %s%s" % (c["name"], "  (skipped: %s)" % c["skip"] if c["skip"] else ""))
            for e in c["edits"]:
                human.append("   edit %s: %s %s -> %s%s" % (e["file"], e["key"], e["old"], e["new"],
                                                        " (%s)" % e["url"] if e.get("url") else ""))
            if c.get("env"):
                human.append("   env " + " ".join("%s=%s" % kv for kv in c["env"].items()))
            for s in c["steps"]:
                human.append("   $ " + " ".join(s["cmd"]))
        human.append("\n(dry run: nothing executed, no workspace created, the project was not touched)")
        emit(args, {"dry_run": True, "plan": plan, "commands": dr}, "\n".join(human))
        return 0
    out = os.path.abspath(args.out or os.path.join("vmatrix-out", time.strftime("%Y%m%d-%H%M%S")))
    os.makedirs(out, exist_ok=True)
    workspace = os.path.abspath(cfg.get("workspace") or os.path.join(out, "work"))
    meta = {"started": util.now_iso(), "cells": [c["name"] for c in plan["cells"]],
            "project": plan["project"], "pins": plan["pins"], "config_file": args.config}
    util.write_json(os.path.join(out, "run.json"), meta)
    eprint("output: %s" % out)
    for c in plan["cells"]:
        cdir = os.path.join(out, util.slug(c["name"]))
        if args.resume and os.path.isfile(os.path.join(cdir, "cell.json")):
            eprint("== %s: resume, keeping previous result" % c["name"])
            continue
        if c["skip"]:
            eprint("== %s: skipped (%s)" % (c["name"], c["skip"]))
            os.makedirs(cdir, exist_ok=True)
            util.write_json(os.path.join(cdir, "cell.json"), skipped_result(c, cdir))
            continue
        eprint("== %s" % c["name"])
        r = runner.run_cell(cfg, c, out, workspace, log=eprint, keep=args.keep_workdirs)
        eprint("   -> %s in %ss" % (r["outcome"], r["duration_s"]))
    return finish_report(args, out)


def load_cells(out):
    meta = util.read_json(os.path.join(out, "run.json"))
    if not meta:
        raise config.ConfigError("no run.json in %s (not a vmatrix output directory)" % out)
    cells = []
    for name in meta["cells"]:
        c = util.read_json(os.path.join(out, util.slug(name), "cell.json"))
        if c:
            c["dir"] = os.path.join(out, util.slug(name))
            for s in c.get("steps", []):
                s["log"] = os.path.join(c["dir"], os.path.basename(s["log"]))
            cells.append(c)
    return meta, cells


def finish_report(args, out):
    meta, cells = load_cells(out)
    rules = classify.load_rules(getattr(args, "rules", None))
    rep = report.build_report(cells, meta["project"], rules, meta)
    report.write_reports(rep, out)
    summary = "\n".join(["Report: %s" % os.path.join(out, "report.md")] +
                        ["  %-20s %-8s guard=%s" % (c["name"], c["outcome"], (c.get("guard") or {}).get("result", "-"))
                         for c in rep["cells"]])
    if args.json:
        emit(args, rep, "")
    else:
        print(summary)
    return report.exit_code(rep, args.fail_on)


def cmd_report(args):
    return finish_report(args, os.path.abspath(args.out))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vmatrix", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="latest stable/rc/beta/alpha/next per tool")
    d.add_argument("--tools", help="comma list of gradle,agp,kotlin,ksp (default all)")
    d.add_argument("--channels", help="comma list: stable,rc,beta,alpha,milestone,nightly,dev,next,latest")
    d.add_argument("--json", action="store_true")
    d.add_argument("--offline", action="store_true")
    d.add_argument("--refresh", action="store_true")
    d.add_argument("--cache")
    d.set_defaults(fn=cmd_discover)

    p = sub.add_parser("plan", help="resolve channels and show the cells; no builds, no writes")
    add_common(p)
    p.set_defaults(fn=cmd_plan)

    r = sub.add_parser("run", help="run the cells and write report.json/report.md")
    add_common(r)
    r.add_argument("--out", help="output directory (default vmatrix-out/<timestamp>)")
    r.add_argument("--dry-run", action="store_true", help="print edits and commands only")
    r.add_argument("--resume", action="store_true", help="keep cells that already have a cell.json in --out")
    r.add_argument("--keep-workdirs", action="store_true", help="do not delete per-cell workspaces")
    r.add_argument("--workspace", help="parent directory for per-cell workspaces (default <out>/work)")
    r.add_argument("--mode", choices=["auto", "worktree", "copy"], help="workspace kind (default auto)")
    r.add_argument("--ref", help="git ref for worktree mode (default HEAD)")
    r.add_argument("--timeout", dest="timeout_sec", type=int, help="per-step timeout in seconds")
    r.add_argument("--daemon-cleanup", dest="daemon_cleanup", choices=["none", "stop", "stop+kill"])
    r.add_argument("--rules", help="owner rules JSON (default vmlib/owners.rules.json)")
    r.add_argument("--fail-on", choices=["never", "invalid", "any"], default="any")
    r.set_defaults(fn=cmd_run)

    rp = sub.add_parser("report", help="(re)classify logs of a finished run and rewrite the report")
    rp.add_argument("--out", required=True, help="output directory of a previous run")
    rp.add_argument("--rules")
    rp.add_argument("--json", action="store_true")
    rp.add_argument("--fail-on", choices=["never", "invalid", "any"], default="any")
    rp.set_defaults(fn=cmd_report)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (config.ConfigError, discover.DiscoveryError, project.ProjectError) as e:
        eprint("vmatrix: error: %s" % e)
        return 2
    except KeyboardInterrupt:
        eprint("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
