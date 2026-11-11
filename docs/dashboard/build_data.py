#!/usr/bin/env python3
"""Bundle the frozen JSON files under data/ into docs/dashboard/data.js.

The dashboard reads window.DATA, so it opens from Pages or from a local file
with no network. Run from the repo root: python3 docs/dashboard/build_data.py
"""
import glob, json, os

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
def load(p):
    with open(os.path.join(root, p)) as f:
        return json.load(f)

data = {
    "history": load("data/history/nowinandroid.json"),
    "flagAvailability": {"agp": load("data/flag-availability/agp.json"),
                         "kgp": load("data/flag-availability/kgp.json")},
    "flagBuilds": [load(p) for p in sorted(
        os.path.relpath(g, root) for g in glob.glob(os.path.join(root, "data/flag-builds/*.json")))],
    "features": load("data/features/features.json"),
    "knownIssues": [load(p) for p in sorted(
        os.path.relpath(g, root) for g in glob.glob(os.path.join(root, "data/known-issues/*.json")))],
}
out = os.path.join(root, "docs", "dashboard", "data.js")
with open(out, "w") as f:
    f.write("window.DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
print("wrote", out, os.path.getsize(out), "bytes")
