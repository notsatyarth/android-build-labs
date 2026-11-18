# problems-api data

Run 44257421730 of the `problems-api` workflow (harness `ffaefec`, GitHub Actions ubuntu-24.04, x86 Linux), nowinandroid
`2982e63c`, JDK 21.0.13, Gradle 9.7.1, Tooling API client 9.7.1, AGP 9.3.2, KSP 2.3.4. Task in every cell:
`:app:assembleDemoDebug --rerun-tasks --no-build-cache --warning-mode=all`. Run 44256831905 (harness `e16d387`) gave
the same counts in every cell.

- `<cell>.jsonl`: the runner's output, one line per `SingleProblemEvent` (`"kind":"problem"`) and per `ProblemSummary`
  (`"kind":"summary"`, count = problems of that id beyond the 15 sent singly). Paths under the project are `<project>/`.
- `summary_run44257421730.json`: `summarize.py` output per cell (versions, outcome, Tooling API counts by owner, group
  and id, console counts of the same build) and the `compare.py` checks.

Console logs and `problems-report.html` are only in the workflow artifacts (they contain runner paths).

| Cell | Kotlin (resolved KGP) | Outcome | Tooling API single + summarised = total | Console `Problem found:` | Console `w:` | Console `WARNING:` |
|---|---|---|---|---|---|---|
| c1-k230 | 2.3.0 | success | 2 + 0 = 2 | 2 | 17 | 76 |
| c2-k230-agp | 2.3.0 | success | 19 + 61 = 80 | 19 | 17 | 78 |
| c3-k2421-agp | 2.4.21 | success | 24 + 61 = 85 | 24 | 0 | 78 |
| c4-k2421-agp-next | 2.4.21, tryNext | failure (line 64) | 36 + 61 = 97 | 36 | 2 | 78 |
