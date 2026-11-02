"""Compare the share of task time per tool owner on the CI runner with the original macOS runs (Apple M1, JDK 17).
Usage: python3 -I compare.py RAW_DIR   (reads RAW_DIR/<scenario>-<n>.json written by run_traced.sh)
Shares are shares of the summed task time (internal Gradle build operation trace; owner = package of the task class).
A scenario 'matches' when every owner's share is within 10 percentage points of the macOS median and the owner ranking by share has the same top owner."""
import glob, json, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import attribute

MAC = {  # median share of task sum, percent; nowinandroid 2982e63, build cache off, 5 measured builds each
    "clean-cc":   {"Gradle core": 4.1, "AGP": 24.8, "KGP/Kotlin": 34.8, "KSP": 35.0, "Hilt": 0.1, "Other": 0.2},
    "clean-nocc": {"Gradle core": 4.0, "AGP": 24.9, "KGP/Kotlin": 35.3, "KSP": 35.3, "Hilt": 0.1, "Other": 0.4},
    "nonabi":     {"Gradle core": 13.0, "AGP": 46.1, "KGP/Kotlin": 37.4, "KSP": 4.2, "Hilt": 0.4, "Other": 0.2},
    "abi":        {"Gradle core": 3.8, "AGP": 20.8, "KGP/Kotlin": 14.9, "KSP": 60.7, "Hilt": 0.1, "Other": 0.1},
}
MAC_WALL_S = {"clean-cc": 29.2, "clean-nocc": 36.8, "nonabi": 2.7, "abi": 3.9}
raw = Path(sys.argv[1])
print("| scenario | owner | macOS share % | CI share % | CI wall s (macOS) | |\n|---|---|---|---|---|---|")
verdicts = []
for scn, mac in MAC.items():
    files = sorted(glob.glob(str(raw / f"{scn}-[0-9]*.json")))
    if not files:
        print(f"| {scn} | - | - | no data | - | |"); verdicts.append((scn, "no data")); continue
    an = [attribute.analyse(json.load(open(f))) for f in files]
    ci = {o: statistics.median(a["owners"][o]["share_of_task_sum"] * 100 for a in an) for o in attribute.OWNERS}
    wall = statistics.median(a["wall_ms"] for a in an) / 1000
    for o in attribute.OWNERS:
        print(f"| {scn} | {o} | {mac[o]:.1f} | {ci[o]:.1f} | {wall:.1f} ({MAC_WALL_S[scn]}) | {'' if abs(ci[o]-mac[o]) <= 10 else 'off by >10 pp'} |")
    same_top = max(mac, key=mac.get) == max(ci, key=ci.get)
    within = all(abs(ci[o] - mac[o]) <= 10 for o in mac)
    verdicts.append((scn, "match" if same_top and within else f"DIFFERS (same top owner: {same_top})"))
print()
for scn, v in verdicts: print(f"- {scn}: {v}")
