#!/usr/bin/env python3
"""Resolve the versions for readiness probe 1 at run time and write them to OUT.json.

  baseline  the pins of the nowinandroid clone (gradle/libs.versions.toml, gradle-wrapper.properties)
  agp       highest version of com.android.tools.build:gradle in Google Maven metadata (any channel, alpha included)
  kotlin    highest version of org.jetbrains.kotlin:kotlin-gradle-plugin in Maven Central metadata (any channel)
  gradle    the newer of services.gradle.org/versions/nightly and /versions/release-nightly

Usage: resolve.py NIA_DIR OUT.json. Standard library only. Prints a Markdown summary."""
import datetime
import json
import re
import sys
import urllib.request

AGP_META = "https://dl.google.com/android/maven2/com/android/tools/build/gradle/maven-metadata.xml"
KGP_META = "https://repo1.maven.org/maven2/org/jetbrains/kotlin/kotlin-gradle-plugin/maven-metadata.xml"
GRADLE_NIGHTLY = "https://services.gradle.org/versions/nightly"
GRADLE_RELEASE_NIGHTLY = "https://services.gradle.org/versions/release-nightly"

QUAL_RANK = {"dev": 0, "snapshot": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "m": 2, "milestone": 2, "rc": 3}


def vkey(v):
    """Sort key: 9.6.0-alpha04 < 9.6.0-beta01 < 9.6.0-rc01 < 9.6.0; 2.5.0-Beta2 < 2.5.0-RC < 2.5.0-RC2 < 2.5.0."""
    m = re.match(r"^(\d+(?:\.\d+)*)(?:-([A-Za-z]+)-?(\d*).*)?$", v)
    if not m:
        return ((), -1, 0)
    nums = tuple(int(x) for x in m.group(1).split("."))
    nums = nums + (0,) * (4 - len(nums))
    if m.group(2) is None:
        return (nums, 9, 0)
    return (nums, QUAL_RANK.get(m.group(2).lower(), -1), int(m.group(3) or 0))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "android-build-labs-readiness-probe"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def newest_maven(url):
    vs = re.findall(r"<version>([^<]+)</version>", fetch(url))
    vs = [v for v in vs if vkey(v)[1] >= 0]
    return max(vs, key=vkey)


def catalog_version(text, key):
    m = re.search(r'^\s*%s\s*=\s*"([^"]+)"' % re.escape(key), text, re.M)
    return m.group(1) if m else None


def baseline_pins(nia):
    cat = open(nia + "/gradle/libs.versions.toml").read()
    wrapper = open(nia + "/gradle/wrapper/gradle-wrapper.properties").read()
    m = re.search(r"gradle-([^/]+?)-(?:bin|all)\.zip", wrapper)
    return {"gradle": m.group(1) if m else None, "agp": catalog_version(cat, "androidGradlePlugin"),
            "kotlin": catalog_version(cat, "kotlin"), "ksp": catalog_version(cat, "ksp"),
            "androidTools": catalog_version(cat, "androidTools")}


def main():
    nia, out = sys.argv[1], sys.argv[2]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = baseline_pins(nia)
    agp = newest_maven(AGP_META)
    kotlin = newest_maven(KGP_META)
    nightlies = []
    for url in (GRADLE_NIGHTLY, GRADLE_RELEASE_NIGHTLY):
        d = json.loads(fetch(url))
        if d.get("version"):
            nightlies.append({"version": d["version"], "url": d["downloadUrl"], "channel": d.get("publicationSlot") or url.rsplit("/", 1)[1],
                              "build_time": d.get("buildTime"), "source": url})
    gradle = max(nightlies, key=lambda d: vkey(d["version"].split("-")[0]) + (d["version"],))
    res = {"resolved_at": now, "baseline": base,
           "next": {"agp": {"version": agp, "source": AGP_META},
                    "kotlin": {"version": kotlin, "source": KGP_META},
                    "gradle": gradle},
           "gradle_candidates": nightlies}
    json.dump(res, open(out, "w"), indent=1)
    print("### Versions resolved at %s" % now)
    print()
    print("| Tool | Baseline (nowinandroid pin) | Next (1a) | Source |")
    print("|---|---|---|---|")
    print("| AGP | %s | %s | Google Maven metadata |" % (base["agp"], agp))
    print("| Kotlin (KGP) | %s | %s | Maven Central metadata |" % (base["kotlin"], kotlin))
    print("| Gradle | %s | %s (%s) | %s |" % (base["gradle"], gradle["version"], gradle["channel"], gradle["source"]))
    print()
    print("Gradle candidates: " + ", ".join("%s (%s)" % (n["version"], n["channel"]) for n in nightlies))


if __name__ == "__main__":
    main()
