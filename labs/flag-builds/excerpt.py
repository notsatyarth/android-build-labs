#!/usr/bin/env python3
"""Print why a flag build failed, and what the plugins said about the flag, from the cell logs.
Usage: excerpt.py OUT_DIR   (OUT_DIR holds <cell>/<step>.log files written by vmatrix)
Prints to stdout (the workflow appends it to the job summary): the "What went wrong" block, Kotlin and AGP
diagnostic lines (deprecated, removed, error, warning), and the lines that mention the flag keys."""
import glob
import os
import re
import sys

PAT = re.compile(r"(?i)(isolated.projects|configuration cache|feature preview|implicit lookup|BUILD (SUCCESSFUL|FAILED)|deprecat|removed in|no longer|is an error|\be: |\[Kotlin|KGP:|experimental|unsupported|not supported|AGP:|android\.[A-Za-z.]+.*(false|true))")


def main():
    out = sys.argv[1]
    for log in sorted(glob.glob(os.path.join(out, "*", "*.log"))):
        text = open(log, errors="replace").read()
        cell = os.path.basename(os.path.dirname(log))
        step = os.path.basename(log)
        m = re.search(r"\* What went wrong:\n(.*?)(?:\n\* Try:|\Z)", text, re.S)
        lines = [l.strip()[:300] for l in text.splitlines() if PAT.search(l) and not l.startswith("#")]
        seen, keep = set(), []
        for l in lines:
            if l not in seen:
                seen.add(l); keep.append(l)
        print("#### %s / %s" % (cell, step))
        cmd = next((l[7:].strip()[:500] for l in text.splitlines() if l.startswith("# cmd:")), None)
        if cmd:
            print("Command: `%s`" % cmd)
        if m:
            print("What went wrong:\n```\n%s\n```" % m.group(1).strip()[:1800])
        if keep:
            print("Diagnostic lines (first 25):\n```\n%s\n```" % "\n".join(keep[:25]))
        if not m and not keep:
            print("(nothing to report)")
        print()


if __name__ == "__main__":
    main()
