#!/usr/bin/env python3
"""Unit tests for extract.py on log excerpts in both formats (shapes copied from nowinandroid CI logs of 2026-11-16,
Kotlin 2.4.21 and 2.3.0; paths replaced). Run: python3 labs/kotlin-readiness/test_extract.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract  # noqa: E402

WS = "/w/out/work/A-k2421-plain"
PROBLEMS = """> Task :build-logic:convention:compileKotlin
Problem found: Kotlin compiler warning (id: kotlin:compiler:warning:compiler-warning)
  Kotlin compiler warning
    'var xmlReport: Boolean' is deprecated.
    Location: /w/out/work/A-k2421-plain/build-logic/convention/src/main/kotlin/AndroidLintConventionPlugin.kt line 45

LAB lv=2.5 :core:notifications:compileDemoDebugKotlin
> Task :core:notifications:compileDemoDebugKotlin
Problem found: Kotlin compiler: RETURN_IN_FUNCTION_WITH_EXPRESSION_BODY_WARNING (id: kotlin:compiler:warning:RETURN_IN_FUNCTION_WITH_EXPRESSION_BODY_WARNING)
  Kotlin compiler warning
    Return in function with expression body and without explicit return type. This will become an error in language version 2.5. See https://youtrack.jetbrains.com/issue/KTLC-288.
    Location: /w/out/work/A-k2421-plain/core/notifications/src/main/kotlin/x/SystemTrayNotifier.kt line 64

> Task :core:model:compileKotlin
Problem found: Kotlin compiler: OPT_IN_REQUIREMENT_MARKER_IS_UNRESOLVED (id: kotlin:compiler:warning:OPT_IN_REQUIREMENT_MARKER_IS_UNRESOLVED)
  Kotlin compiler warning
    Opt-in requirement marker 'kotlinx.coroutines.ExperimentalCoroutinesApi' is unresolved.

> Task :core:data:compileDemoDebugKotlin UP-TO-DATE
"""
CLASSIC = """> Task :core:notifications:compileDemoDebugKotlin FAILED
e: file:///w/out/work/k230/core/notifications/src/main/kotlin/x/SystemTrayNotifier.kt:64:13 Returns are prohibited.
> Task :core:network:compileDemoDebugKotlin
w: file:///w/out/work/k230/core/network/src/main/kotlin/x/Demo.kt:40:5 This annotation is currently applied to the value parameter only, but in the future it will also be applied to field.
> Task :core:model:compileKotlin
w: Opt-in requirement marker kotlinx.coroutines.ExperimentalCoroutinesApi is unresolved.
Execution failed for task ':core:notifications:compileDemoDebugKotlin'.
"""


class T(unittest.TestCase):
    def test_problems_api(self):
        d, tasks, failed, lv = extract.parse_log(PROBLEMS, WS)
        self.assertEqual(len(d), 3)
        bl, ret, opt = d
        self.assertEqual(bl["origin"], "build-logic")
        self.assertIsNone(bl["name"])
        self.assertEqual(ret["name"], "RETURN_IN_FUNCTION_WITH_EXPRESSION_BODY_WARNING")
        self.assertEqual((ret["file"], ret["line"]), ("core/notifications/src/main/kotlin/x/SystemTrayNotifier.kt", 64))
        self.assertEqual(ret["marker"]["language"], "2.5")
        self.assertEqual(ret["task"], ":core:notifications:compileDemoDebugKotlin")
        self.assertEqual(ret["module"], ":core:notifications")
        self.assertEqual(opt["origin"], "no-file")
        self.assertEqual(tasks[":core:data:compileDemoDebugKotlin"], "UP-TO-DATE")
        self.assertEqual(lv, {":core:notifications:compileDemoDebugKotlin": "2.5"})
        self.assertNotIn("/w/", repr(d))

    def test_classic(self):
        d, tasks, failed, lv = extract.parse_log(CLASSIC, None)
        self.assertEqual([x["severity"] for x in d], ["error", "warning", "warning"])
        self.assertEqual((d[0]["file"], d[0]["line"], d[0]["column"]),
                         ("core/notifications/src/main/kotlin/x/SystemTrayNotifier.kt", 64, 13))
        self.assertTrue(d[1]["future_wording_unmarked"])
        self.assertEqual(d[2]["origin"], "no-file")
        self.assertEqual(failed, [":core:notifications:compileDemoDebugKotlin"])
        self.assertEqual(tasks[":core:notifications:compileDemoDebugKotlin"], "FAILED")


if __name__ == "__main__":
    unittest.main()
