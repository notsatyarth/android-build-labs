# kotlin-next-checks

Does Kotlin progressive mode catch the same source break as `kotlin.experimental.tryNext`, and does that depend on
the Kotlin version? nowinandroid is built with Kotlin 2.3.0 and 2.4.21, each in three modes: plain, tryNext, and
progressive mode (`progressive.init.gradle` sets `compilerOptions.progressiveMode` on every Kotlin compile task).

The line under test is `SystemTrayNotifier.kt:64` (a `return` in a function with an expression body and no explicit
return type). The compiler source schedules that check (KTLC-288) for language 2.4 with progressive mode in 2.3.0,
and for language 2.5 without progressive mode in 2.4.21. `compare.py` checks these predictions:

| Cell | Expected |
|---|---|
| k230-plain | pass, line 64 a warning |
| k230-trynext | fail, line 64 an error |
| k230-progressive | fail, line 64 an error |
| k2421-plain | pass (recorded) |
| k2421-trynext | fail, line 64 an error |
| k2421-progressive | pass |

Run: workflow `kotlin-next-checks` (`workflow_dispatch`). Numbers and outcomes are from x86 Linux runners.
