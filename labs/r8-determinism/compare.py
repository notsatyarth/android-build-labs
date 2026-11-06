#!/usr/bin/env python3
"""Check the R8 determinism hypotheses against logs/android.json and logs/jvm.json (written by run.py).

Predictions were written before the first CI run (2026-11-06); no macOS run exists for this lab, so each
line states the expectation and whether the CI run agrees. Verdicts: AGREES, DIFFERS, MISSING.
Exit code 0 always: a DIFFERS line is a finding.
Usage: compare.py LOGS_DIR [--markdown]
"""
import json
import os
import sys

FIELDS = ["userName", "themeId", "notificationsOn"]
S, SA = "lab.app.model.Settings", "lab.app.model.SettingsAnnotated"


def load(logs, n):
    p = os.path.join(logs, n)
    return json.load(open(p)) if os.path.exists(p) else None


def names(r, cls):
    return r["names"][cls]["fields"]


def compat(writer, reader, cls, annotated):
    """Simulated JSON round trip from mapping files: for each original field, where does its value land?"""
    w, r = names(writer, cls), names(reader, cls)
    key_of = (lambda f: f) if annotated else (lambda f: w.get(f))
    reader_field_by_key = {(f if annotated else obf): f for f, obf in r.items()}
    out = {}
    for f in FIELDS:
        k = key_of(f)
        g = reader_field_by_key.get(k) if k else None
        out[f] = "ok" if g == f else ("lost" if g is None else "into " + g)
    return out


def main():
    logs = sys.argv[1]
    md = "--markdown" in sys.argv
    A, J = load(logs, "android.json"), load(logs, "jvm.json")
    rows = []

    def check(hid, claim, fn, detail):
        try:
            v = "AGREES" if fn() else "DIFFERS"
        except (TypeError, KeyError, AttributeError):
            v = "MISSING"
        try:
            d = detail()
        except (TypeError, KeyError, AttributeError):
            d = "-"
        rows.append((hid, claim, v, d))

    a = (A or {}).get
    b = a("base")
    check("A0", "(sample check) R8 keeps the three Settings fields (values come from run time), so their names can be compared",
          lambda: all(x in names(b, S) for x in FIELDS),
          lambda: "Settings fields in mapping.txt: %s; SettingsAnnotated: %s" % (names(b, S), names(b, SA)))
    same = lambda x, y: x["dex"] == y["dex"] and x["mapping_sha"] == y["mapping_sha"]
    check("A1", "two clean release builds of the same sources in the same directory give identical dex and mapping.txt",
          lambda: same(b, a("base-again")),
          lambda: "dex %s vs %s; mapping %s vs %s" % (list(b["dex"].values())[0][:12], list(a("base-again")["dex"].values())[0][:12],
                                                      b["mapping_sha"][:12], a("base-again")["mapping_sha"][:12]))
    check("A2", "the same sources built in a different directory give identical dex and mapping.txt",
          lambda: same(b, a("base-copy")),
          lambda: "dex equal %s, mapping equal %s, APK equal %s" % (b["dex"] == a("base-copy")["dex"], b["mapping_sha"] == a("base-copy")["mapping_sha"],
                                                                    b["apk_sha"] == a("base-copy")["apk_sha"]))
    u = a("unrelated")
    check("A3", "an unrelated code change (new class elsewhere) changes the dex but not the obfuscated field names of Settings",
          lambda: u["dex"] != b["dex"] and names(u, S) == names(b, S),
          lambda: "dex changed %s; Settings fields base %s, unrelated %s" % (u["dex"] != b["dex"], names(b, S), names(u, S)))
    f = a("addfield")
    check("A4", "adding a field to Settings (declared first) renames at least one existing field",
          lambda: any(names(f, S).get(x) != names(b, S).get(x) for x in FIELDS),
          lambda: "base %s, addfield %s; round trip base->addfield %s" % (names(b, S), names(f, S), compat(b, f, S, False)))
    am = a("addfield-applymapping")
    check("A5", "-applymapping with the previous mapping.txt keeps the existing field names after adding a field",
          lambda: all(names(am, S).get(x) == names(b, S).get(x) for x in FIELDS),
          lambda: "addfield+applymapping %s; round trip %s" % (names(am, S), compat(b, am, S, False)))
    o = a("agp-9.1.0")
    check("A6", "a different AGP (so a different R8) on the same sources changes the dex: output depends on the toolchain, not only the code",
          lambda: o["dex"] != b["dex"],
          lambda: "R8 %s vs %s; dex changed %s; Settings fields %s vs %s" % (b["r8"], o["r8"], o["dex"] != b["dex"], names(b, S), names(o, S)))
    check("A7", "(informational) with the other AGP the Settings field names stay the same",
          lambda: names(o, S) == names(b, S), lambda: "round trip base->agp-9.1.0 %s" % compat(b, o, S, False))
    g = a("gson-2.10.1")
    check("A8", "(informational) a different Gson version (2.10.1, no bundled R8 rules) leaves the Settings field names the same",
          lambda: names(g, S) == names(b, S),
          lambda: "dex changed %s; Settings %s; SettingsAnnotated fields kept %s" % (g["dex"] != b["dex"], names(g, S), sorted(names(g, SA))))
    check("A9", "@SerializedName: the JSON keys do not depend on R8 names, so every build reads the baseline's SettingsAnnotated JSON",
          lambda: all(compat(b, a(n), SA, True) == {x: "ok" for x in FIELDS} for n in A if n not in ("keep-base", "keep-addfield")),
          lambda: "; ".join("%s %s" % (n, "ok" if compat(b, a(n), SA, True) == {x: "ok" for x in FIELDS} else compat(b, a(n), SA, True))
                            for n in A if n not in ("keep-base", "keep-addfield")))
    kb, ka = a("keep-base"), a("keep-addfield")
    check("A10", "a keep rule on the fields keeps the original names, so adding a field is safe",
          lambda: all(names(kb, S).get(x) == x for x in FIELDS) and compat(kb, ka, S, False) == {x: "ok" for x in FIELDS},
          lambda: "keep-base %s; round trip keep-base->keep-addfield %s" % (names(kb, S), compat(kb, ka, S, False)))

    j = (J or {}).get
    jb = (j("builds") or {}).get
    reads = j("reads") or {}
    ok_line = "LAB_READ userName=jesse themeId=2 notificationsOn=true"
    rd = lambda k: reads[k]["out"].splitlines()[-1] if reads[k]["out"] else ""
    check("J1", "R8 (classfile output, same R8 as AGP) twice on the same program: identical classes and mapping",
          lambda: jb("base")["classes_sha"] == jb("base-again")["classes_sha"] and jb("base")["mapping_sha"] == jb("base-again")["mapping_sha"],
          lambda: "R8 %s; Settings fields %s" % (j("r8"), jb("base")["names"]["lab.jvm.model.Settings"]["fields"]))
    check("J2", "run time: JSON written by the baseline is read correctly by a rebuild and by a build with an unrelated change",
          lambda: rd("base -> base-again").startswith(ok_line) and rd("base -> unrelated").startswith(ok_line),
          lambda: "%s | %s | %s" % (rd("base writes"), rd("base -> base-again"), rd("base -> unrelated")))
    check("J3", "run time: after adding a field the old JSON is read wrongly or fails (exit code or values differ)",
          lambda: not rd("base -> addfield").startswith(ok_line) or reads["base -> addfield"]["exit"] != 0,
          lambda: "exit %s: %s; fields base %s, addfield %s" % (reads["base -> addfield"]["exit"], rd("base -> addfield"),
                                                               jb("base")["names"]["lab.jvm.model.Settings"]["fields"],
                                                               jb("addfield")["names"]["lab.jvm.model.Settings"]["fields"]))
    check("J4", "run time: with -applymapping (previous mapping) the old JSON is read correctly after adding a field",
          lambda: rd("base -> addfield-applymapping").startswith(ok_line),
          lambda: rd("base -> addfield-applymapping"))
    check("J5", "run time: with @SerializedName the old JSON is read correctly after adding a field",
          lambda: rd("annotated-base -> annotated-addfield").startswith(ok_line),
          lambda: "%s | %s" % (rd("annotated-base writes"), rd("annotated-base -> annotated-addfield")))

    if md:
        print("| ID | Hypothesis | Verdict | Measured |\n|---|---|---|---|")
        for r in rows:
            print("| %s | %s | %s | %s |" % tuple(str(x).replace("|", "/") for x in r))
    else:
        for r in rows:
            print("%-4s %-8s %s\n       %s" % (r[0], r[2], r[1], r[3]))


if __name__ == "__main__":
    main()
