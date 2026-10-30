#!/usr/bin/env python3
"""Sample the JVM processes of a Gradle build (macOS or Linux) and write a CSV plus a summary.

Usage: python3 procwatch.py OUT.csv [--interval 2] -- <command to run, e.g. ./gradlew assembleDemoDebug>

Samples `ps` every INTERVAL seconds while the command runs and for a short tail afterwards
(daemons outlive the build), classifies each java process by its main class and records RSS.
RSS is physical memory held by the process (what the OS sees), not the JVM heap.
"""
import csv, subprocess, sys, time, re, os

CLASSES = [
    ("kotlin-daemon", "KotlinCompileDaemon"),
    ("gradle-daemon", "GradleDaemon"),
    ("gradle-worker", "GradleWorkerMain"),
    ("gradle-wrapper", "GradleWrapperMain"),
    ("aapt2-daemon", "aapt2"),
    ("r8", "com.android.tools.r8"),
    ("lint", "com.android.tools.lint"),
    ("kotlin-other", "org.jetbrains.kotlin"),
]


def classify(cmd):
    if "java" not in cmd.split()[0] and "aapt2" not in cmd:
        return None
    for name, needle in CLASSES:
        if needle in cmd:
            return name
    return None


def snapshot():
    out = subprocess.run(["ps", "-eo", "pid=,ppid=,rss=,command="], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(\d+)\s+(\d+)\s+(.*)", line)
        if not m:
            continue
        pid, ppid, rss, cmd = m.groups()
        kind = classify(cmd)
        if kind:
            xmx = re.search(r"-Xmx(\S+)", cmd)
            gc = re.search(r"-XX:\+Use(\w+)GC", cmd)
            rows.append((int(pid), int(ppid), int(rss) // 1024, kind, xmx.group(1) if xmx else "", gc.group(1) if gc else ""))
    return rows


def main():
    args = sys.argv[1:]
    out = args[0]
    interval = 2.0
    if "--interval" in args:
        interval = float(args[args.index("--interval") + 1])
    cmd = args[args.index("--") + 1:]
    t0 = time.time()
    proc = subprocess.Popen(cmd)
    peak_total, peak_by, seen = 0, {}, {}
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["elapsed_s", "pid", "ppid", "kind", "rss_mb", "xmx", "gc"])
        tail_until = None
        while True:
            rows = snapshot()
            el = round(time.time() - t0, 1)
            for pid, ppid, rss, kind, xmx, gc in rows:
                w.writerow([el, pid, ppid, kind, rss, xmx, gc])
                seen.setdefault((pid, kind), 0)
                seen[(pid, kind)] = max(seen[(pid, kind)], rss)
            total = sum(r[2] for r in rows)
            peak_total = max(peak_total, total)
            f.flush()
            if proc.poll() is not None:
                tail_until = tail_until or time.time() + 6
                if time.time() >= tail_until:
                    break
            time.sleep(interval)
    final = snapshot()
    print(f"\nexit code {proc.returncode}; wall {round(time.time()-t0)} s; peak total RSS of sampled JVMs {peak_total} MB")
    print("peak RSS per process (pid, kind, MB):")
    for (pid, kind), mb in sorted(seen.items(), key=lambda x: -x[1]):
        print(f"  {pid:>7} {kind:<15} {mb:>6}")
    print("still running after the build (kind, pid, RSS MB):", [(k, p, r) for p, _, r, k, _, _ in final])
    sys.exit(proc.returncode or 0)


if __name__ == "__main__":
    main()
