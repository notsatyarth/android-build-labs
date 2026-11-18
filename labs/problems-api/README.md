# problems-api

What does a build already report through Gradle's Problems API, compared with what a script gets by parsing the
console? A small Tooling API client (`ProblemsRunner.java`) runs one nowinandroid build, listens for
`OperationType.PROBLEMS` progress events and writes one JSON line per problem. The same run's console output goes to
`console.log`, so both views of one build can be counted side by side.

## Cells

nowinandroid `2982e63c` (AGP 9.3.2, Gradle 9.7.1), JDK 21, Tooling API client 9.7.1 (same as the build's Gradle).
Every cell: `:app:assembleDemoDebug --rerun-tasks --no-build-cache --warning-mode=all`. Problems are reported only by
tasks that execute, so nothing may come from the build cache or be up to date.

| Cell | Kotlin | Extra properties |
|---|---|---|
| `c1-k230` | 2.3.0 (pinned) | none |
| `c2-k230-agp` | 2.3.0 | `-Pandroid.enableProblemsAPI=true` |
| `c3-k2421-agp` | 2.4.21 (catalog `kotlin` key) | `-Pandroid.enableProblemsAPI=true` |
| `c4-k2421-agp-next` | 2.4.21 | `-Pandroid.enableProblemsAPI=true -Pkotlin.experimental.tryNext=true` |

## Files

- `ProblemsRunner.java`: the runner, run with the JDK source launcher (`java -cp tooling-api.jar:slf4j-api.jar ProblemsRunner.java PROJECT OUT TASK -- ARGS`).
  Per `SingleProblemEvent`: group path (walks `ProblemId.getGroup()` and `ProblemGroup.getParent()`), id name and
  display name, severity (`getSeverity()` and `isKnown()`), contextual label, details, documentation link, origin and
  contextual locations (file, line, column, length; plugin id; task path), solutions, whether a failure is attached,
  additional data. Per `ProblemSummariesEvent`: one `summary` line per problem id with its count (problems beyond the
  ones sent singly; Gradle sends at most 15 per id by default). Paths under the project are written as `<project>/`.
  Also writes `runner.json` (outcome, failures with their problems from `withDetailedFailure()`, event counts).
- `run_cell.sh NIA CELL OUT TAPI_CP`: applies the cell, runs the runner, records resolved AGP, KGP and KSP from
  `buildEnvironment`.
- `summarize.py CELL_DIR`: `summary.json` per cell: Tooling API counts by owner, group path and id, against console
  counts of `Problem found:` blocks, `w:` and `e:` lines, Gradle deprecation lines, javac warnings and `WARNING:` lines.
  The owner (Gradle, Kotlin, AGP) is derived from the group path by this lab, not reported by the build.
- `compare.py DIR`: checks H1 to H6 (listed in its header). Exits non-zero only when the harness is broken.
- Workflow: `problems-api` (input `nia_ref`). Artifacts per cell: `problems.jsonl`, `console.log`, `runner.json`,
  `summary.json`, `cell.txt`, `buildEnvironment.log`, `problems-report.html`. Kept 90 days.

Committed results: `data/problems-api/` (JSONL and summary per cell; console logs stay in the workflow artifacts).

## Results (run 44257421730, CI x86 Linux; run 44256831905 gave the same counts)

- Gradle reported no problem of its own in any cell (no deprecation on Gradle 9.7.1 for this build).
- Kotlin 2.3.0 (c1, c2): the project's 17 compiler warnings appear only as console `w:` lines; the Tooling API gets
  none of them. The 2 Kotlin problems it does get come from `:build-logic:convention:compileKotlin` (Gradle's embedded
  Kotlin), with the generic id `compiler-warning`.
- Kotlin 2.4.21 (c3): no `w:` lines; the project's warnings arrive as problems in `kotlin > compiler:warning` with the
  compiler diagnostic name as id (`DEPRECATION`, `OPT_IN_REQUIREMENT_MARKER_IS_UNRESOLVED`,
  `RETURN_IN_FUNCTION_WITH_EXPRESSION_BODY_WARNING`), file, line and column.
- `-Pkotlin.experimental.tryNext=true` (c4): the line-64 error is one `ERROR` problem,
  `kotlin > compiler:error` / `RETURN_IN_FUNCTION_WITH_EXPRESSION_BODY_AND_IMPLICIT_TYPE`, at
  `SystemTrayNotifier.kt` line 64 column 13, with a failure attached; the same problem is on the build failure
  (`withDetailedFailure()`).
- `android.enableProblemsAPI=true` (c2 to c4): 78 AGP problems in group `agp-sync-issues` ("Sync Issues"): 76 `GENERIC`
  (id `0`, "androidTestImplementation dependencies are ignored because androidTest is disabled.") and 2
  `UNSUPPORTED_PROJECT_OPTION_USE` (id `32`, the warning that the flag itself is experimental). The ids are AGP's
  numeric sync-issue types. Without the flag (c1) AGP still prints the 76 `WARNING:` lines, but reports nothing.
- Only 15 problems per id arrive as single events; the other 61 `GENERIC` ones arrive as a summary count. The console
  prints a `Problem found:` block for exactly the single events, so console counting of those blocks undercounts.
