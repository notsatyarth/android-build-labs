#!/usr/bin/env python3
"""Write a vmatrix config with one cell per flag (tier 2 flag probe): the project is built with that one flag set.

Usage: make_config.py OUT.json [--agp VERSION] [--kotlin VERSION] [--list-cells]
Flags come from tools/version-matrix/probes/flags.json (value_to_test). A flag with no value is not built.
With --agp, every cell also sets that AGP version (axes), and flags the tier 1 data (data/flag-availability)
shows as absent in that version are skipped with a reason instead of being built: a flag that does not exist
cannot be compared. With --list-cells only the cell names are printed (one per line)."""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def slug(flag):
    return re.sub(r"[^A-Za-z0-9]+", "-", flag).strip("-")


def availability(tool, version):
    path = os.path.join(ROOT, "data", "flag-availability", "%s.json" % tool)
    try:
        return json.load(open(path))["versions"].get(version)
    except (OSError, ValueError, KeyError):
        return None


def build(agp=None, kotlin=None):
    flags = json.load(open(os.path.join(ROOT, "tools", "version-matrix", "probes", "flags.json")))["flags"]
    avail = {"agp": availability("agp", agp) if agp else None, "kgp": availability("kgp", kotlin) if kotlin else None}
    cells, skipped = [], []
    for f in flags:
        if f.get("value_to_test") is None:
            skipped.append({"flag": f["flag"], "reason": f["value_basis"]})
            continue
        a = avail.get(f["tool"])
        if a and a.get(f["flag"], {}).get("status") == "absent":
            skipped.append({"flag": f["flag"], "reason": "not_applicable: absent in %s %s (tier 1 data)" % (f["tool"], agp or kotlin)})
            continue
        cell = {"name": "flag-" + slug(f["flag"]), "flags": {f["flag"]: f["value_to_test"]}}
        axes = {}
        if agp:
            axes["agp"] = agp
        if kotlin:
            axes["kotlin"] = kotlin
        if axes:
            cell["axes"] = axes
        cells.append(cell)
    return cells, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--agp")
    ap.add_argument("--kotlin")
    ap.add_argument("--list-cells", action="store_true")
    a = ap.parse_args()
    cells, skipped = build(a.agp, a.kotlin)
    if a.list_cells:
        print(json.dumps([c["name"] for c in cells]))
        return
    cfg = {"project": "path/to/nowinandroid", "mode": "worktree",
           "tasks": [[":app:assembleDemoDebug"]],
           "gradle_args": ["--console=plain", "--warning-mode=all", "--stacktrace", "--no-build-cache"],
           "guard_tasks": ["buildEnvironment", ":app:buildEnvironment"], "timeout_sec": 3000,
           "daemon_cleanup": "stop+kill", "cells": cells, "_skipped": skipped}
    json.dump(cfg, open(a.out, "w"), indent=1)
    print("wrote %s: %d cell(s), %d skipped" % (a.out, len(cells), len(skipped)))
    for s in skipped:
        print("  skipped %s: %s" % (s["flag"], s["reason"]))


if __name__ == "__main__":
    main()
