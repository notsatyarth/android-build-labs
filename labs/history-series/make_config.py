#!/usr/bin/env python3
"""Write a vmatrix config with one cell per nowinandroid commit (per-cell ref).
Usage: make_config.py [--ip] OUT.json SHA [SHA ...]   (SHAs are full 40-character commit ids)
--ip: the Isolated Projects variant. Same commits, but the task step is only `help` with the configuration cache and
Isolated Projects forced on (-Dorg.gradle.unsafe.isolated-projects=true). The version guard step does not get that flag,
so a commit that fails IP still passes the guard. Nothing in nowinandroid is edited.
Cell name: c<index>-<first 8 chars>. No version changes: each cell builds that commit with the pins it carries."""
import json
import sys

args = sys.argv[1:]
ip = bool(args) and args[0] == "--ip"
if ip:
    args = args[1:]
out, shas = args[0], args[1:]
cfg = {
    "project": "path/to/nowinandroid",
    "mode": "worktree",
    "tasks": [["help"], [":app:assembleDemoDebug"]],
    "gradle_args": ["--console=plain", "--warning-mode=all", "--stacktrace", "--no-build-cache"],
    "guard_tasks": ["buildEnvironment", ":app:buildEnvironment"],
    "timeout_sec": 3000,
    "daemon_cleanup": "stop+kill",
    "cells": [{"name": "c%02d-%s" % (i, s[:8]), "ref": s} for i, s in enumerate(shas)],
}
if ip:
    cfg["tasks"] = [["help"]]
    cfg["gradle_args"] = cfg["gradle_args"] + ["--configuration-cache", "-Dorg.gradle.unsafe.isolated-projects=true"]
with open(out, "w") as f:
    json.dump(cfg, f, indent=2)
print("wrote %s with %d cell(s)" % (out, len(shas)))
