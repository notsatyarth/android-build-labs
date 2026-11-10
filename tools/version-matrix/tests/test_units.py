import json
import os
import tempfile
import unittest

import helpers  # noqa: F401  (sets sys.path)
from vmlib import classify, collect, discover, guard, project, util


class VersionOrdering(unittest.TestCase):
    def test_order(self):
        order = ["9.9.0-milestone-1", "9.9.0-milestone-2", "9.9.0-rc-1", "9.9.0", "9.10.0"]
        self.assertEqual(sorted(reversed(order), key=util.version_key), order)
        self.assertLess(util.version_key("9.5.0-alpha10"), util.version_key("9.5.0-alpha11"))
        self.assertLess(util.version_key("9.5.0-alpha11"), util.version_key("9.5.0-beta01"))
        self.assertLess(util.version_key("2.4.20-RC"), util.version_key("2.4.20-RC2"))
        self.assertLess(util.version_key("2.4.20-RC2"), util.version_key("2.4.20"))

    def test_channels(self):
        c = util.channel_of
        self.assertEqual(c("9.3.2"), "stable")
        self.assertEqual(c("9.5.0-rc02"), "rc")
        self.assertEqual(c("2.4.20-RC2"), "rc")
        self.assertEqual(c("2.5.0-Beta2"), "beta")
        self.assertEqual(c("9.5.0-alpha10"), "alpha")
        self.assertEqual(c("9.9.0-milestone-2"), "milestone")
        self.assertEqual(c("2.3.0-dev-1234"), "dev")


MAVEN = """<metadata><versioning><versions>
<version>9.3.2</version><version>9.4.1</version><version>9.5.0-rc02</version><version>9.5.0-alpha10</version>
<version>9.2.0-rc01</version><version>9.6.0-alpha01</version></versions></versioning></metadata>"""
GRADLE_ALL = json.dumps([
    {"version": "9.8.2", "current": True, "snapshot": False, "rcFor": "", "milestoneFor": "", "broken": False,
     "downloadUrl": "https://x/gradle-9.8.2-bin.zip"},
    {"version": "9.9.0-milestone-2", "snapshot": False, "rcFor": "", "milestoneFor": "9.9.0", "broken": False},
    {"version": "9.9.0-rc-1", "snapshot": False, "rcFor": "9.9.0", "milestoneFor": "", "broken": False},
    {"version": "9.10.0-20261026002358+0000", "snapshot": True, "nightly": True, "broken": False,
     "buildTime": "20261026002358+0000", "downloadUrl": "https://x/distributions-snapshots/gradle-9.10.0-bin.zip"},
    {"version": "9.7.0", "snapshot": False, "rcFor": "", "milestoneFor": "", "broken": True},
])


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = os.path.join(self.tmp, "c.json")
        self.calls = []

        def fetch(url):
            self.calls.append(url)
            return GRADLE_ALL if "gradle.org" in url else MAVEN
        self.fetch = fetch

    def test_pick_channels(self):
        d = discover.Discovery(self.cache, fetch=self.fetch)
        self.assertEqual(d.pick("agp", "stable")["version"], "9.4.1")
        self.assertEqual(d.pick("agp", "rc")["version"], "9.5.0-rc02")   # 9.2.0-rc01 is older than stable
        self.assertEqual(d.pick("agp", "alpha")["version"], "9.6.0-alpha01")
        self.assertEqual(d.pick("agp", "next")["version"], "9.6.0-alpha01")
        self.assertIsNone(d.pick("agp", "beta"))
        self.assertEqual(d.pick("gradle", "stable")["version"], "9.8.2")
        self.assertEqual(d.pick("gradle", "rc")["version"], "9.9.0-rc-1")
        self.assertEqual(d.pick("gradle", "milestone")["version"], "9.9.0-milestone-2")
        n = d.pick("gradle", "nightly")
        self.assertTrue(n["url"].endswith("gradle-9.10.0-bin.zip"))

    def test_cache_and_offline(self):
        discover.Discovery(self.cache, fetch=self.fetch).pick("agp", "stable")
        n = len(self.calls)
        d2 = discover.Discovery(self.cache, offline=True, fetch=self.fetch)
        self.assertEqual(d2.pick("agp", "stable")["version"], "9.4.1")
        self.assertEqual(len(self.calls), n)
        with self.assertRaises(discover.DiscoveryError):
            discover.Discovery(self.cache, offline=True, fetch=self.fetch).pick("kotlin", "stable")

    def test_fetch_failure_falls_back_to_cache(self):
        discover.Discovery(self.cache, fetch=self.fetch).pick("agp", "stable")

        def boom(url):
            raise OSError("no network")
        d = discover.Discovery(self.cache, refresh=True, fetch=boom)
        self.assertEqual(d.pick("agp", "stable")["version"], "9.4.1")
        self.assertTrue(any("fetch failed" in n for n in d.notes))
        with self.assertRaises(discover.DiscoveryError):
            discover.Discovery(os.path.join(self.tmp, "none.json"), fetch=boom).pick("agp", "stable")


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.root = helpers.make_project(tempfile.mkdtemp())
        self.keys = {"agp": ["androidGradlePlugin", "agp"], "kotlin": ["kotlin"], "ksp": ["ksp"]}

    def test_set_catalog_version_only_touches_versions_section(self):
        new, old = project.set_catalog_version(helpers.CATALOG, "androidGradlePlugin", "9.4.0")
        self.assertEqual(old, "9.3.2")
        self.assertIn('androidGradlePlugin = "9.4.0"  # keep with tools', new)
        self.assertEqual(new.count("9.4.0"), 1)
        self.assertEqual(new.replace("9.4.0", "9.3.2"), helpers.CATALOG)
        _, none = project.set_catalog_version(helpers.CATALOG, "missing", "1")
        self.assertIsNone(none)

    def test_pins(self):
        pins = project.read_pins(self.root, self.keys)
        self.assertEqual(pins, {"gradle": "9.7.1", "agp": "9.3.2", "kotlin": "2.3.0", "ksp": "2.3.4"})

    def test_wrapper_edit_drops_checksum(self):
        project.apply_wrapper(self.root, "9.9.0-rc-1")
        txt = helpers.rd(os.path.join(self.root, project.WRAPPER))
        self.assertIn("distributionUrl=https\\://services.gradle.org/distributions/gradle-9.9.0-rc-1-bin.zip", txt)
        self.assertNotIn("Sha256", txt)
        project.apply_wrapper(self.root, "x", "https://services.gradle.org/distributions-snapshots/gradle-9.10-bin.zip")
        self.assertIn("distributions-snapshots/gradle-9.10-bin.zip", helpers.rd(os.path.join(self.root, project.WRAPPER)))

    def test_plan_and_apply_edits(self):
        cats = project.find_catalogs(self.root)
        self.assertEqual(cats, [os.path.join("gradle", "libs.versions.toml")])
        edits = project.plan_edits(self.root, {"agp": "9.4.0", "gradle": "9.8.2"}, self.keys, cats)
        project.apply_edits(self.root, edits)
        self.assertEqual(project.read_pins(self.root, self.keys)["agp"], "9.4.0")
        self.assertEqual(project.read_pins(self.root, self.keys)["gradle"], "9.8.2")

    def test_separate_build_logic_catalog_is_edited_too(self):
        bl = os.path.join(self.root, "build-logic", "gradle")
        os.makedirs(bl)
        helpers.wr(os.path.join(bl, "libs.versions.toml"), '[versions]\nkotlin = "2.3.0"\n')
        cats = project.find_catalogs(self.root)
        self.assertEqual(len(cats), 2)
        edits = project.plan_edits(self.root, {"kotlin": "2.5.0-Beta2"}, self.keys, cats)
        self.assertEqual(len(edits), 2)
        project.apply_edits(self.root, edits)
        self.assertIn("2.5.0-Beta2", helpers.rd(os.path.join(bl, "libs.versions.toml")))

    def test_missing_key_is_an_error(self):
        with self.assertRaises(project.ProjectError):
            project.plan_edits(self.root, {"agp": "1"}, {"agp": ["nope"]}, project.find_catalogs(self.root))


class GuardTests(unittest.TestCase):
    def test_parse_fixtures(self):
        gv = collect.parse_gradle_version(helpers.fixture("gradle_version.txt"))
        self.assertEqual(gv["gradle"], "9.8.2")
        self.assertEqual(gv["gradle_embedded_kotlin"], "2.2.21")
        env = collect.parse_build_environment(helpers.fixture("build_environment.txt"))
        self.assertEqual(env["agp"], {"9.3.2"})
        self.assertEqual(env["kotlin"], {"2.3.0"})      # resolved side of "2.2.10 -> 2.3.0"
        self.assertEqual(env["ksp"], {"2.3.4"})

    def check(self, req):
        return guard.check(req, helpers.fixture("gradle_version.txt"), helpers.fixture("build_environment.txt"))

    def test_ok(self):
        self.assertEqual(self.check({"gradle": "9.8.2", "agp": "9.3.2", "kotlin": "2.3.0", "ksp": "2.3.4"})["result"], "OK")

    def test_mismatch(self):
        g = self.check({"gradle": "9.8.2", "agp": "9.4.0", "kotlin": "2.3.0"})
        self.assertEqual(g["result"], "MISMATCH")
        self.assertEqual(g["axes"]["agp"]["status"], "MISMATCH")
        self.assertEqual(g["axes"]["agp"]["actual"], "9.3.2")

    def test_unverified(self):
        g = guard.check({"agp": "9.3.2"}, "", "classpath\n")
        self.assertEqual(g["result"], "UNVERIFIED")

    def test_mixed_versions_are_mismatch(self):
        env = "+--- com.android.tools.build:gradle:9.3.2\n+--- com.android.tools.build:gradle:9.4.0\n"
        self.assertEqual(guard.check({"agp": "9.3.2"}, "", env)["result"], "MISMATCH")


class CollectClassifyTests(unittest.TestCase):
    def setUp(self):
        self.rules = classify.load_rules()

    def run_console(self, name):
        recs, meta = collect.parse_console(helpers.fixture(name))
        classify.classify_all(recs, self.rules)
        return recs, meta

    def test_failure_is_agp(self):
        recs, meta = self.run_console("console_failure_agp.log")
        f = [r for r in recs if r["kind"] == "failure"]
        self.assertEqual(len(f), 1)
        self.assertIn("android.builtInKotlin", f[0]["text"])
        self.assertEqual(f[0]["owner"], "AGP")
        self.assertIn("build.gradle.kts", f[0]["location"])
        self.assertEqual(meta["exit"], 1)
        self.assertEqual(meta["build"], "FAILED")
        self.assertEqual(meta["configuration_cache"], "stored")

    def test_mixed_log(self):
        recs, meta = self.run_console("console_mixed.log")
        by = lambda frag: next(r for r in recs if frag in r["text"])  # noqa: E731
        # duplicate AGP warning merged into one record with count 2
        w = by("androidTestImplementation")
        self.assertEqual(w["count"], 2)
        self.assertEqual(w["owner"], "AGP")
        # Gradle deprecation raised from an AGP frame is blamed on AGP; pure Gradle frames stay Gradle
        self.assertEqual(by("Project.getConvention()")["owner"], "AGP")
        self.assertEqual(by("Task.getProject()")["owner"], "Gradle")
        self.assertEqual(by("kotlin.gradle.plugin.mpp.Foo")["owner"], "KGP/Kotlin")
        self.assertEqual(len(by("Project.getConvention()")["frames"]), 2)
        # compiler warning in project sources belongs to the project
        self.assertEqual(by("xmlReport")["owner"], "Project")
        self.assertEqual(by("xmlReport")["kind"], "deprecation")
        self.assertEqual(by("Recipient not set")["group"], "Others > Hello Problems")
        self.assertEqual(by("never used")["owner"], "Project")
        self.assertEqual(by("[ksp]")["owner"], "KSP")
        self.assertEqual(meta["failed_tasks"], [":app:mergeDemoDebugResources"])

    def test_real_kotlin_warnings_keep_files_and_relative_paths(self):
        # real console output: the same text in different files must not merge, paths are workspace-relative
        recs, _ = collect.parse_console(helpers.fixture("console_real_kotlin_warnings.log"), "/ws/agp-next")
        ann = [r for r in recs if "applied to the value parameter only" in r["text"]]
        self.assertEqual(len(ann), 4)   # before the fix these merged into 2 records by text
        self.assertTrue(all(not r["location"].startswith(("file://", "/ws")) for r in ann))
        self.assertIn("core/data/src/main/kotlin/com/google/samples/apps/nowinandroid/core/data/repository/"
                      "DefaultSearchContentsRepository.kt:44:5", [r["location"] for r in ann])
        nofile = [r for r in recs if "Opt-in requirement marker" in r["text"]][0]
        self.assertIsNone(nofile["location"])

    def test_real_problems_report_details_and_dedupe(self):
        html = helpers.fixture("problems-report-real.html")
        recs, _ = collect.parse_problems_report(html, "/ws/agp-next")
        self.assertEqual(len(recs), 1)
        self.assertIn("'var xmlReport: Boolean' is deprecated", recs[0]["text"])   # key is problemDetails
        self.assertEqual(recs[0]["location"], "build-logic/convention/src/main/kotlin/AndroidLintConventionPlugin.kt line 45")
        # analyze_cell drops the entry because the console already has file:line 45
        import tempfile, os
        from vmlib import report
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "problems-report.html"), "w") as f:
            f.write(html)
        with open(os.path.join(d, "s.log"), "w") as f:
            f.write(helpers.fixture("console_real_kotlin_warnings.log"))
        res = {"dir": d, "workspace": "/ws/agp-next", "steps": [{"role": "task", "name": "s", "log": os.path.join(d, "s.log")}]}
        out = report.analyze_cell(res, self.rules)
        self.assertEqual(sum(1 for p in out["problems"] if "xmlReport" in p["text"]), 1)

    def test_problems_report_best_effort(self):
        recs, note = collect.parse_problems_report(helpers.fixture("problems-report.html"))
        classify.classify_all(recs, self.rules)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["group"], "Deprecation > Task usage")
        self.assertEqual(recs[0]["kind"], "deprecation")
        self.assertEqual(recs[1]["owner"], "KGP/Kotlin")   # group "KGP > Misconfiguration"
        self.assertIn("best effort", note)

    def test_problems_report_unknown_format(self):
        recs, note = collect.parse_problems_report("<html><script>var x = {\"a\": 1};</script></html>")
        self.assertEqual(recs, [])
        self.assertIn("internal format", note)
        self.assertEqual(collect.parse_problems_report("not html")[0], [])

    def test_custom_rules_file(self):
        p = os.path.join(tempfile.mkdtemp(), "r.json")
        helpers.wr(p, json.dumps({"default_owner": "Mine", "rules": [
            {"id": "x", "owner": "Acme", "field": "text", "regex": "acme"}]}))
        rs = classify.load_rules(p)
        self.assertEqual(classify.classify({"text": "ACME broke"}, rs)[0], "Mine")
        self.assertEqual(classify.classify({"text": "acme broke"}, rs), ("Acme", "x"))




class CellArgsTests(unittest.TestCase):
    def test_cell_option_replaces_common_option(self):
        from vmlib import runner
        cell = {"flags": {}, "gradle_args": ["--warning-mode=fail"]}
        args = runner.cell_args(cell, ["--console=plain", "--warning-mode=all", "--stacktrace"])
        self.assertEqual(args, ["--console=plain", "--stacktrace", "--warning-mode=fail"])


if __name__ == "__main__":
    unittest.main()


class PerCellRefTests(unittest.TestCase):
    """A cell can name its own commit; pins and planned edits then come from that commit, not from HEAD."""

    def setUp(self):
        import subprocess
        from vmlib import config
        self.config = config
        self.tmp = tempfile.TemporaryDirectory()
        self.root = helpers.make_project(os.path.join(self.tmp.name, "p"), git=True)
        self.env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.git = lambda *a: subprocess.run(["git"] + list(a), cwd=self.root, env=self.env, check=True,
                                             stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()
        self.old = self.git("rev-parse", "HEAD")
        cat = os.path.join(self.root, "gradle", "libs.versions.toml")
        helpers.wr(cat, helpers.rd(cat).replace('"9.3.2"', '"9.4.0"'))
        self.git("commit", "-qam", "bump agp")

    def tearDown(self):
        self.tmp.cleanup()

    def _plan(self, cells):
        cfg = self.config.load(None, {"project": self.root})
        cfg["cells"] = cells
        return self.config.resolve(cfg)

    def test_cell_reads_pins_from_its_own_ref(self):
        plan = self._plan([{"name": "head"}, {"name": "old", "ref": self.old}])
        head, old = plan["cells"]
        self.assertEqual(head["pins"]["agp"], "9.4.0")
        self.assertEqual(old["pins"]["agp"], "9.3.2")
        self.assertEqual(old["requested"]["agp"], "9.3.2")
        self.assertEqual(old["commit"], self.old)
        self.assertIsNone(head["commit"])

    def test_edits_are_planned_against_the_ref(self):
        plan = self._plan([{"name": "old-kotlin", "ref": self.old, "axes": {"agp": "9.5.0"}}])
        edit = plan["cells"][0]["edits"][0]
        self.assertEqual((edit["old"], edit["new"]), ("9.3.2", "9.5.0"))

    def test_unknown_ref_skips_the_cell_with_a_reason(self):
        plan = self._plan([{"name": "bad", "ref": "no-such-ref"}])
        self.assertIn("cannot read ref", plan["cells"][0]["skip"])

    def test_working_tree_is_untouched(self):
        self._plan([{"name": "old", "ref": self.old}])
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertIn("9.4.0", helpers.rd(os.path.join(self.root, "gradle", "libs.versions.toml")))
