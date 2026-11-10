Trimmed real configuration cache reports (Gradle 9.7.1, CI run captured by labs/capture-samples).
The embedded report data is kept in the original format; only most non-problem diagnostics and stack traces were
removed, and the surrounding page is cut to the text around the data markers. nia_* is nowinandroid
(2982e63cb691ad49cd009aab43dc206fee6699c2); syn_* come from the deliberate violations in labs/capture-samples/synthetic.

`../nia_assemble_warning_mode_all.excerpt.log`: excerpt (first 40 lines, last 14 lines, and every line
mentioning "deprecat" with one line of context) of `./gradlew --warning-mode=all :app:assembleDemoDebug` on
nowinandroid 2982e63, Gradle 9.7.1, AGP 9.3.2, JDK 21. No "Deprecated Gradle features were used" summary appears
in this build: Gradle-level deprecations need another source (older commit or a next Gradle version).

`../gradle_9.9.0-rc-1_help_warning_mode_all.excerpt.log`: `./gradlew --warning-mode=all --stacktrace help` on nowinandroid
2982e63 with Gradle 9.9.0-rc-1 (CI run 41388330540, 2026-11-02). Stack frames cut to 14 per record and repeated records
beyond the first six removed. The real full logs gave 69 to 70 deprecation messages (20 distinct) on Gradle 9.9.0-rc-1
and 0 on Gradle 9.7.1.
