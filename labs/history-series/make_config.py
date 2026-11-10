#!/usr/bin/env python3
"""Write a vmatrix config with one cell per nowinandroid commit (per-cell ref).
Usage: make_config.py OUT.json SHA [SHA ...]   (SHAs are full 40-character commit ids)
Cell name: c<index>-<first 8 chars>. No version changes: each cell builds that commit with the pins it carries."""
import json
import sys

out, shas = sys.argv[1], sys.argv[2:]
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
with open(out, "w") as f:
    json.dump(cfg, f, indent=2)
print("wrote %s with %d cell(s)" % (out, len(shas)))
