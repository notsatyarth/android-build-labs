# kotlin-readiness

What does an upgrade from Kotlin `current` to `next` mean for nowinandroid's code? Four builds of every Kotlin compile
task (main, unit test and Android test sources, all variants) at one nowinandroid commit:

| Cell | Compiler | Language | Gives |
|---|---|---|---|
| A | current | current default | today's full warning list; warnings that say "will become an error in language version N" are marked |
| B | current + `kotlin.experimental.tryNext=true` | current + 1 | errors under the next language's rules (a lower bound: modules depending on a failed one never compile) |
| C | next | 2.4 (pinned by `lang24.init.gradle`) | the next compiler's full warning list under today's language |
| D | next | next default | the real upgrade; a failure is classed as setup, source or toolchain |

- `compile_all.init.gradle` registers `readinessCompileAll` in each project (depends on every `compile*Kotlin` task) and
  prints the language version each compile task uses (`LAB lv=`).
- `extract.py CELL_DIR` writes `diagnostics.json` per cell: one record per compiler diagnostic (severity, name, file
  relative to the repo, line, task, module, origin, full message, marker), compile tasks expected and executed, failed
  tasks. Reads Problems API blocks (Kotlin >= 2.4.20 with `--warning-mode=all`) and classic `w:`/`e:` lines.
- `aggregate.py PARTS OUT.json` merges the cells into `readiness.json`, compares them and checks the predictions:
  - B's errors against A's warnings, joined on (file, line), never on the diagnostic name (the warning and the later
    error have different names): predicted, warned but not marked, silent, ambiguous, and marked but not failed.
  - C's warnings against A's: new and gone.
  - B's errors against D's (same language rules, different compiler).
  - Only project code counts. build-logic is compiled by Gradle's own Kotlin, and is tagged separately.
- Workflow: `kotlin-readiness` (inputs: `nia_ref`, `current`, `next`). Artifacts are kept 90 days.

Tests: `python3 labs/kotlin-readiness/test_extract.py`.
