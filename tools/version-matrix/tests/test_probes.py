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
