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
