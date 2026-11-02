"""Version discovery with an offline cache.

Sources (all public, no auth):
  AGP    Google Maven metadata  com/android/tools/build/gradle
  KGP    Maven Central metadata org/jetbrains/kotlin/kotlin-gradle-plugin
  KSP    Maven Central metadata com/google/devtools/ksp/symbol-processing-gradle-plugin
  Gradle services.gradle.org/versions/all
"""
import os
import time
import urllib.request
import xml.etree.ElementTree as ET

from . import util

SOURCES = {
    "agp": "https://dl.google.com/android/maven2/com/android/tools/build/gradle/maven-metadata.xml",
    "kotlin": "https://repo1.maven.org/maven2/org/jetbrains/kotlin/kotlin-gradle-plugin/maven-metadata.xml",
    "ksp": "https://repo1.maven.org/maven2/com/google/devtools/ksp/symbol-processing-gradle-plugin/maven-metadata.xml",
    "gradle": "https://services.gradle.org/versions/all",
}
TOOLS = tuple(SOURCES)
CHANNELS = ("stable", "rc", "beta", "alpha", "milestone", "nightly", "release-nightly", "dev", "next", "latest")


class DiscoveryError(Exception):
    pass


def default_cache_path():
    base = os.environ.get("VMATRIX_CACHE") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"), "vmatrix")
    return os.path.join(base, "discover.json")


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "vmatrix/0.1 (+version matrix harness)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_maven_metadata(xml_text):
    root = ET.fromstring(xml_text)
    out = []
    for v in root.iter("version"):
        if v.text and v.text.strip():
            out.append({"version": v.text.strip(), "channel": util.channel_of(v.text.strip())})
    return out


def parse_gradle_all(json_text):
    import json
    data = json.loads(json_text)
    out = []
    for e in data:
        if e.get("broken"):
            continue
        ver = e.get("version")
        if not ver:
            continue
        if e.get("snapshot"):
            ch = "nightly" if e.get("nightly") else ("release-nightly" if e.get("releaseNightly") else "dev")
        elif e.get("milestoneFor"):
            ch = "milestone"
        elif e.get("rcFor"):
            ch = "rc"
        else:
            ch = "stable"
        out.append({"version": ver, "channel": ch, "url": e.get("downloadUrl"),
                    "build_time": e.get("buildTime")})
    return out


def _parse(tool, text):
    return parse_gradle_all(text) if tool == "gradle" else parse_maven_metadata(text)


class _Notes(list):
    def append(self, x):
        if x not in self:
            super().append(x)


class Discovery:
    def __init__(self, cache_path=None, offline=False, refresh=False, max_age_hours=24, fetch=http_get):
        self.cache_path = cache_path or default_cache_path()
        self.offline = offline
        self.refresh = refresh
        self.max_age = max_age_hours * 3600
        self.fetch = fetch
        self.cache = util.read_json(self.cache_path, {}) or {}
        self.notes = _Notes()

    def entries(self, tool):
        if tool not in SOURCES:
            raise DiscoveryError("unknown tool %r (expected one of %s)" % (tool, ", ".join(TOOLS)))
        c = self.cache.get(tool)
        fresh = c and (time.time() - c.get("fetched_epoch", 0) < self.max_age)
        if c and (self.offline or (fresh and not self.refresh)):
            if self.offline:
                self.notes.append("%s: offline, using cache from %s" % (tool, c.get("fetched_at")))
            return c["entries"]
        if self.offline:
            raise DiscoveryError("%s: offline and no cache at %s" % (tool, self.cache_path))
        try:
            entries = _parse(tool, self.fetch(SOURCES[tool]))
        except Exception as e:  # network, parse
            if c:
                self.notes.append("%s: fetch failed (%s); using cache from %s" % (tool, e, c.get("fetched_at")))
                return c["entries"]
            raise DiscoveryError("%s: fetch failed (%s) and no cache" % (tool, e))
        self.cache[tool] = {"fetched_at": util.now_iso(), "fetched_epoch": time.time(),
                            "source": SOURCES[tool], "entries": entries}
        try:
            util.write_json(self.cache_path, self.cache)
        except OSError as e:
            self.notes.append("cache not written: %s" % e)
        return entries

    def pick(self, tool, channel, include_older=False):
        """Return entry dict for the highest version in a channel, or None.

        Pre-release channels only count versions newer than the latest stable unless include_older.
        next = highest non-dev, non-nightly version above latest stable. latest = highest non-dev version overall.
        """
        ents = self.entries(tool)
        stable = [e for e in ents if e["channel"] == "stable"]
        top_stable = max(stable, key=lambda e: util.version_key(e["version"]), default=None)
        floor = util.version_key(top_stable["version"]) if top_stable else None

        def best(cands):
            if tool == "gradle" and cands and cands[0]["channel"] in ("nightly", "release-nightly"):
                return max(cands, key=lambda e: e.get("build_time") or e["version"])
            return max(cands, key=lambda e: util.version_key(e["version"]), default=None)

        if channel == "stable":
            return top_stable
        if channel == "latest":
            return best([e for e in ents if e["channel"] not in ("dev", "nightly", "release-nightly", "other")])
        if channel == "next":
            c = [e for e in ents if e["channel"] in ("rc", "beta", "alpha", "milestone")
                 and (floor is None or util.version_key(e["version"]) > floor)]
            return best(c)
        if channel in ("nightly", "release-nightly", "dev"):
            return best([e for e in ents if e["channel"] == channel])
        if channel in ("rc", "beta", "alpha", "milestone"):
            c = [e for e in ents if e["channel"] == channel]
            if not include_older and floor is not None:
                c = [e for e in c if util.version_key(e["version"]) > floor]
            return best(c)
        raise DiscoveryError("unknown channel %r (expected one of %s)" % (channel, ", ".join(CHANNELS)))

    def summary(self, tools=TOOLS, channels=("stable", "rc", "beta", "alpha", "next")):
        out = {}
        for t in tools:
            row = {}
            for ch in channels:
                if t != "gradle" and ch in ("nightly", "release-nightly"):
                    continue
                e = self.pick(t, ch)
                row[ch] = e["version"] if e else None
            out[t] = row
        return out
