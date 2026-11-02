"""Check the CI run of the daemons lab against the conclusions of the original macOS run.
Usage: python3 -I compare.py OUT_DIR   (reads A.*.log, A.summary, B.*, C.*, C2run.*). Prints a Markdown table.
Experiment C is informational only: the original builds failed on a transforms-cache lock under heavy machine load,
and a quiet 4-core runner may behave differently."""
import re, sys
from pathlib import Path

out = Path(sys.argv[1])
def log(name):
    p = out / name
    return p.read_text(errors="replace") if p.exists() else None
rows = []
def check(label, expected, ok):
    rows.append((label, expected, {True: "match", False: "DIFFERS", None: "no data"}[ok]))
def has(name, pat):
    t = log(name)
    return None if t is None else re.search(pat, t) is not None
def n(name, pat):
    t = log(name)
    return None if t is None else len(re.findall(pat, t))
def gd(tag):
    """Number of Gradle daemons in the process snapshot taken after step TAG (A.summary)."""
    t = log("A.summary")
    if t is None: return None
    return len(re.findall(rf"^\s*after-{re.escape(tag)} pid=.*kind=gradle-daemon", t, re.M))
def both(*v):
    return None if any(x is None for x in v) else all(v)

check("A1 Tooling API cold: one Gradle daemon running afterwards", "1 daemon", None if gd("A1_tapi") is None else gd("A1_tapi") == 1)
check("A2 CLI after A1: same daemon, configuration cache reused", "reused", both(None if gd("A2_cli") is None else gd("A2_cli") == 1, has("A.A2_cli.log", r"Reusing configuration cache")))
check("A3 Tooling API again: same daemon, configuration cache reused", "reused", both(None if gd("A3_tapi") is None else gd("A3_tapi") == 1, has("A.A3_tapi.log", r"Reusing configuration cache")))
for k, f in (("A4", "A.A4_tapi_ide.log"), ("A5", "A.A5_cli.log")):
    check(f"{k} android.injected.invoked.from.ide toggled: configuration cache invalidated", "invalidated", has(f, r"android\.injected\.invoked\.from\.ide.{0,20}has changed"))
check("A6 IDE on JDK 21 vs CLI on 17: second daemon, 'JVM has changed'", "2 daemons, invalidated", both(None if gd("A6_tapi_jdk21") is None else gd("A6_tapi_jdk21") == 2, has("A.A6_tapi_jdk21.log", r"JVM has changed")))
check("A7 CLI on 17 after A6: configuration cache invalidated again", "invalidated", has("A.A7_cli.log", r"JVM has changed|cannot be reused"))
t = log("A.A8_updateDaemonJvm.log")
check("A8 updateDaemonJvm fails without toolchain download repositories", "fails", None if t is None else "Toolchain download repositories have not been configured" in t)
for k, f in (("A13", "A.A13_cli.log"), ("A22", "A.A22_cli_jdk21.log"), ("A23", "A.A23_cli_jdk17.log")):
    check(f"{k} with toolchainVersion=17 file: build succeeds", "success", has(f, r"BUILD SUCCESSFUL"))

bsum = log("B.summary")
if bsum is None:
    check("B --no-daemon: single-use daemon forked (-Xmx4g)", "forked", None)
else:
    info = (log("Binfo.B3.log") or "") + (log("Binfo.B4.log") or "")
    check("B3/B4 --info: 'single-use Daemon' message", "present", bool(re.search(r"single-use Daemon", info)) if info else None)
    def sec(h): x, y, z = map(int, h.split(":")); return x * 3600 + y * 60 + z
    starts = {k: v for k, v in re.findall(r"^=== (B\d) start (\d\d:\d\d:\d\d)", bsum, re.M)}
    ends = {k: v for k, v in re.findall(r"^(B\d) rc=\d+ end (\d\d:\d\d:\d\d)", bsum, re.M)}
    samples = re.findall(r"^(\d\d:\d\d:\d\d) pid=\d+ ppid=\d+ home=\w+ .* kind=kotlin-daemon", log("B.samples") or "", re.M)
    if "B1" in starts and "B1" in ends and "B2" in starts:
        window = [t for t in samples if sec(starts["B1"]) <= sec(t) < sec(starts["B2"])]  # samples of the B1 run only
        if window:
            lag = sec(max(window)) - sec(ends["B1"])
            check(f"B1 Kotlin daemon (child of the single-use daemon) last seen vs build end (lag {lag:+d} s)", "gone within ~2 s after end", lag <= 3)
        else:
            check("B1 Kotlin daemon sampled during the build", "sampled", False)
    else:
        check("B1 window found in B.summary", "found", None)

print("| checkpoint | macOS | CI (x86 Linux runner) |\n|---|---|---|")
for r in rows: print("| " + " | ".join(r) + " |")
print()
for tag, name in (("C (shared Gradle user home)", "C"), ("C (fresh Gradle user home)", "C2run")):
    s = log(f"{name}.summary")
    if s is None:
        print(f"- {tag}: no data"); continue
    walls = re.findall(r"^(C\d) rc=(\d+) wall_s=(\d+)", s, re.M)
    lock = sum((len(re.findall(r"Timeout waiting to lock", log(f"{name}.{c}.log") or "")) for c in ("C1", "C2")))
    lost = sum((len(re.findall(r"Connection to the Kotlin daemon has been unexpectedly lost", log(f"{name}.{c}.log") or "")) for c in ("C1", "C2")))
    print(f"- {tag}: " + ", ".join(f"{c} rc={rc} {w} s" for c, rc, w in walls) + f"; transforms-cache lock timeouts {lock}; Kotlin daemon connection lost {lost} (macOS: 3 of 4 builds failed on a lock timeout, 9 connection losses, machine under heavy load)")
