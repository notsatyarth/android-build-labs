#!/usr/bin/env python3
"""Write the vmatrix config for kotlin-readiness: nowinandroid, every Kotlin compile task, four cells.

  A  <current> plain           today's compiler and language: the full warning list
  B  <current> tryNext         today's compiler, language + 1: errors under the next language rules
  C  <next>    language 2.4    the next compiler under today's language: its full warning list
  D  <next>    plain           the real upgrade: next compiler, its default language

Usage: make_config.py OUT.json [--current 2.4.21] [--next 2.5.0-RC] [--list-cells]"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
COMPILE_ALL = os.path.join(HERE, "compile_all.init.gradle")
LANG24 = os.path.join(HERE, "lang24.init.gradle")


def tag(v):
    return "k" + v.replace(".", "").replace("-", "").lower()


def cells(current, nxt):
    ca, nx = tag(current), tag(nxt)
    return [
        {"name": "A-%s-plain" % ca, "axes": {"kotlin": current}, "flags": {}, "gradle_args": ["-Dlab.cell=A"]},
        {"name": "B-%s-trynext" % ca, "axes": {"kotlin": current}, "flags": {"kotlin.experimental.tryNext": "true"}},
        {"name": "C-%s-lang24" % nx, "axes": {"kotlin": nxt}, "flags": {}, "gradle_args": ["--init-script", LANG24]},
        {"name": "D-%s-plain" % nx, "axes": {"kotlin": nxt}, "flags": {}, "gradle_args": ["-Dlab.cell=D"]},
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--current", default="2.4.21")
    ap.add_argument("--next", default="2.5.0-RC")
    ap.add_argument("--list-cells", action="store_true")
    a = ap.parse_args()
    cs = cells(a.current, a.next)
    if a.list_cells:
        print(json.dumps([c["name"] for c in cs]))
        return
    cfg = {"project": "path/to/nowinandroid", "mode": "worktree",
           "tasks": [["readinessCompileAll"]],
           # --warning-mode=all makes Kotlin >= 2.4.20 print compiler diagnostics as Problems API blocks with names
           "gradle_args": ["--console=plain", "--warning-mode=all", "--stacktrace", "--no-build-cache", "--continue",
                           "--init-script", COMPILE_ALL],
           "guard_tasks": ["buildEnvironment", ":app:buildEnvironment"], "timeout_sec": 5400,
           "daemon_cleanup": "stop+kill", "cells": cs}
    json.dump(cfg, open(a.out, "w"), indent=1)
    print("wrote %s: %d cell(s)" % (a.out, len(cs)))


if __name__ == "__main__":
    main()
