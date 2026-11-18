#!/usr/bin/env python3
"""Probe 3 checks. Usage: compare.py PROBE3.json TIME_K_DIR MEM_K_DIR MEM_A_DIR
Checks (CHECK = must hold for the numbers to mean what the slide says; INFO = reported, no expectation):
  C1  pair K: both sides assembled :app:assembleDemoDebug (prime build) and every measured build exited 0; same for pair A memory builds
  C2  pair K: the resolved Kotlin Gradle plugin is OLD_K on the old side and NEW_K on the new side; AGP, KSP and Gradle are the same on both
  C3  pair A time (CI run 44225818987, x86 Linux) against the macOS medians in labs/old-vs-new/compare.py (Apple M1, n = 10):
      a CI change marked measurable has the same direction as the macOS change; macOS changes under 5 % are not judged
  I1  Kotlin daemons per build, per side (both pairs)
Exit code 1 if a CHECK fails."""
import json, os, re, sys

MAC = {"ade8065442": {"config": 1.71, "clean": 37.63, "nonabi": 3.56}, "2c56ce13b": {"config": 1.24, "clean": 36.59, "nonabi": 3.16}}


def status(path):
    return open(path).read().split("\n") if os.path.exists(path) else []


def versions(path):
    """{side: {artifact: version}} from versions.txt (requested -> resolved keeps the resolved one)."""
    out, cur = {}, None
    for line in status(path):
        if re.match(r"^\S+:$", line):
            cur = line[:-1]; out[cur] = {}; continue
        m = re.match(r"^\s+([\w.\-]+:[\w.\-]+):(\S+)(?: -> (\S+))?", line)
        if cur and m:
            out[cur][m.group(1)] = m.group(3) or m.group(2)
        m = re.match(r"^\s+Gradle (\S+)", line)
        if cur and m:
            out[cur]["gradle"] = m.group(1)
    return out


def main(p3, tk, mk, ma):
    res = json.load(open(p3)); rows = res["rows"]; fails = 0
    def check(ok, text):
        nonlocal fails
        fails += 0 if ok else 1
        print("- %s %s" % ("PASS" if ok else "FAIL", text))
    print("### Checks")
    old_k, new_k = res["meta"]["pairs"]["K"]["time"]["old"], res["meta"]["pairs"]["K"]["time"]["new"]
    st_t = status(os.path.join(tk, "prime-status.txt")) + status(os.path.join(tk, "run-status.txt"))
    check(all(("%s prime exit 0" % s) in st_t for s in (old_k, new_k)) and sum(1 for l in st_t if re.search(r" r1 exit 0$", l)) == 2,
          "C1 pair K time: both sides assembled and both gradle-profiler runs exited 0 (%s)" % "; ".join(l for l in st_t if l))
    for d, name in ((mk, "K"), (ma, "A")):
        st = [l for l in status(os.path.join(d, "status.txt")) if l]
        check(bool(st) and all(l.endswith("exit 0") for l in st), "C1 pair %s memory: every build exited 0 (%d lines)" % (name, len(st)))
    want = {old_k: res["meta"].get("old_kotlin"), new_k: res["meta"].get("new_kotlin")}
    for d, name in ((tk, "time"), (mk, "memory")):
        v = versions(os.path.join(d, "versions.txt"))
        kgp = {s: v.get(s, {}).get("org.jetbrains.kotlin:kotlin-gradle-plugin") for s in (old_k, new_k)}
        check(all(kgp[s] == want[s] for s in kgp), "C2 pair K %s: KGP resolved %s (wanted %s)" % (name, kgp, want))
        for art in ("com.android.tools.build:gradle", "com.google.devtools.ksp:symbol-processing-gradle-plugin", "gradle"):
            a = {s: v.get(s, {}).get(art) for s in (old_k, new_k)}
            check(a[old_k] is not None and a[old_k] == a[new_k], "C2 pair K %s: %s same on both sides %s" % (name, art, a))
    for sc in ("config", "clean", "nonabi"):
        r = next((r for r in rows if r["pair"] == "A" and r["measure"] == "%s|total execution time" % sc), None)
        mac = 100 * (MAC["2c56ce13b"][sc] - MAC["ade8065442"][sc]) / MAC["ade8065442"][sc]
        if r is None or "pct_change" not in r:
            check(False, "C3 pair A %s: no CI row" % sc); continue
        if abs(mac) < 5 or not r["measurable"]:
            print("- INFO C3 pair A %s: CI %+.3g %% (measurable: %s), macOS %+.3g %%: not judged" % (sc, r["pct_change"], r["measurable"], mac)); continue
        check((r["pct_change"] > 0) == (mac > 0), "C3 pair A %s: CI %+.3g %% and macOS %+.3g %% same direction" % (sc, r["pct_change"], mac))
    for r in rows:
        if r["measure"] == "kotlin_daemons" and r["subset"] == "all builds":
            print("- INFO I1 pair %s Kotlin daemons per build: old %s, new %s" % (r["pair"], r["old"], r["new"]))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main(*sys.argv[1:5])
