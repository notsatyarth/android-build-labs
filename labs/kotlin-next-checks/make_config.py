#!/usr/bin/env python3
"""Write the vmatrix config for kotlin-next-checks: nowinandroid built with Kotlin K in three modes.

Cells: k<ver>-plain (no change), k<ver>-trynext (-Pkotlin.experimental.tryNext=true),
k<ver>-progressive (progressive.init.gradle sets compilerOptions.progressiveMode=true on every Kotlin compile task).
Usage: make_config.py OUT.json [--kotlin 2.3.0,2.4.21] [--list-cells]"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def cells(versions):
    out = []
    for v in versions:
        tag = "k" + v.replace(".", "")
        out.append({"name": tag + "-plain", "axes": {"kotlin": v}, "flags": {}})
        out.append({"name": tag + "-trynext", "axes": {"kotlin": v}, "flags": {"kotlin.experimental.tryNext": "true"}})
        out.append({"name": tag + "-progressive", "axes": {"kotlin": v}, "flags": {},
                    "gradle_args": ["--init-script", os.path.join(HERE, "progressive.init.gradle")]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--kotlin", default="2.3.0,2.4.21")
    ap.add_argument("--list-cells", action="store_true")
    a = ap.parse_args()
    cs = cells([v for v in a.kotlin.split(",") if v])
    if a.list_cells:
        print(json.dumps([c["name"] for c in cs]))
        return
    cfg = {"project": "path/to/nowinandroid", "mode": "worktree",
           "tasks": [[":app:assembleDemoDebug"]],
           "gradle_args": ["--console=plain", "--warning-mode=all", "--stacktrace", "--no-build-cache", "--continue"],
           "guard_tasks": ["buildEnvironment", ":app:buildEnvironment"], "timeout_sec": 3000,
           "daemon_cleanup": "stop+kill", "cells": cs}
    json.dump(cfg, open(a.out, "w"), indent=1)
    print("wrote %s: %d cell(s)" % (a.out, len(cs)))


if __name__ == "__main__":
    main()
