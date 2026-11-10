import os
import unittest

import helpers  # noqa: F401  (sets sys.path)
from probes import configuration_cache as cc

FIX = os.path.join(helpers.FIX, "cc_reports")


def load(name):
    with open(os.path.join(FIX, name + ".html"), encoding="utf-8") as f:
        return f.read()


class ConfigurationCacheProbe(unittest.TestCase):
    def test_no_problems_is_pass(self):
        r = cc.parse(load("nia_help_no_problems"))
        self.assertEqual((r["state"], r["total_problems"], r["cache_action"]), ("pass", 0, "storing"))

    def test_task_project_at_execution_is_fail_with_origin_and_location(self):
        r = cc.parse(load("syn_task_project_at_execution"))
        self.assertEqual(r["state"], "fail")
        p = r["problems"][0]
        self.assertIn("Task.project", p["message"])
        self.assertEqual((p["origin_kind"], p["origin"]), ("Task", ":bad"))
        self.assertIn("build.gradle.kts:4", p["location"])
        self.assertIn("configuration_cache_requirements", p["doc"])

    def test_isolated_projects_problem_is_fail(self):
        r = cc.parse(load("syn_isolated_projects_subprojects_apply"))
        self.assertEqual(r["state"], "fail")
        self.assertIn("cannot access", r["problems"][0]["message"])
        self.assertIn("build.gradle.kts:8", r["problems"][0]["location"])

    def test_unreadable_reports_are_inconclusive_never_pass(self):
        for html in ("", "<html></html>", "// begin-report-data\nnot json\n// end-report-data",
                     '// begin-report-data\n{"totalProblemCount": 0}\n// end-report-data'):
            r = cc.parse(html)
            self.assertEqual(r["state"], "inconclusive", html)
            self.assertTrue(r["reason"])

    def test_counted_problems_that_cannot_be_read_are_inconclusive(self):
        html = ('// begin-report-data\n{"totalProblemCount": 2, "uniqueProblemCount": 2, '
                '"cacheAction": "storing", "diagnostics": []}\n// end-report-data')
        self.assertEqual(cc.parse(html)["state"], "inconclusive")


if __name__ == "__main__":
    unittest.main()


class FlagAvailabilityProbe(unittest.TestCase):
    def setUp(self):
        import tempfile
        import zipfile
        self.tmp = tempfile.TemporaryDirectory()
        self.jar = os.path.join(self.tmp.name, "agp.jar")
        with zipfile.ZipFile(self.jar, "w") as z:
            z.writestr("com/android/build/gradle/options/BooleanOption.class", b"xx android.builtInKotlin yy")
            z.writestr("com/android/build/gradle/Other.class", b"msg android.newDsl and android.builtInKotlin")
            z.writestr("README.txt", b"android.neverCounted")

    def tearDown(self):
        self.tmp.cleanup()

    def test_declared_mentioned_absent(self):
        from probes import flag_availability as fa
        r = fa.scan_jar(self.jar, "agp", ["android.builtInKotlin", "android.newDsl", "android.neverCounted", "android.gone"])
        self.assertEqual(r["android.builtInKotlin"]["status"], "declared")
        self.assertEqual(r["android.newDsl"]["status"], "mentioned")
        self.assertEqual(r["android.neverCounted"]["status"], "absent")   # only class files count
        self.assertEqual(r["android.gone"]["status"], "absent")

    def test_missing_version_is_not_absent(self):
        from probes import flag_availability as fa

        def fetch(tool, v, cache):
            if v == "1.0":
                return self.jar
            raise FileNotFoundError(v)
        d = fa.probe("agp", ["1.0", "9.9"], self.tmp.name, flags=[{"flag": "android.builtInKotlin", "tool": "agp"}], fetch=fetch)
        self.assertEqual(d["1.0"]["android.builtInKotlin"]["status"], "declared")
        self.assertEqual(d["9.9"], {"_error": "version_not_found"})
        s = fa.summarize(d)
        self.assertEqual(s["state"], "inconclusive")
        self.assertIn("9.9", s["reason"])
