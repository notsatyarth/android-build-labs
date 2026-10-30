Daemons lab: IDE (Tooling API) vs CLI, Kotlin daemon under --no-daemon, parallel worktree builds.
Scripts (run from any directory; they set JAVA_HOME, ANDROID_HOME and an isolated GRADLE_USER_HOME):
  TapiClient.java   Gradle Tooling API 9.7.1 client (the API IDEs use). Env TAPI_JAVA_HOME = IDE "Gradle JDK".
  jvmsnap.sh        one line per Gradle/Kotlin JVM: pid, ppid, home (lab = our Gradle user home), start, RSS, java binary.
  runA.sh WT A N    Experiment A, parts 1..5 (see note). Summary in A.summary, one log per step A<n>_*.log.
  runB.sh / runB_info.sh   Experiment B (--no-daemon, two runs each; B1-B2 lifecycle logging, B3-B4 --info). B.samples = 1 s JVM samples.
  runC.sh WT1 WT2 P Experiment C (two worktrees at once, timeout 1200 s each). C.* = run 1, C2run.* = run 2 (fresh user home).
Caveats:
  - A.A6..A12 logs were overwritten by an accidental second pass (part 3 also ran part 2); A.summary keeps both passes.
  - old/ holds the first, aborted A attempt on the shared ~/.gradle (Tooling API classpath error; daemons stopped mid-run by another session's `gradlew --stop`).
  - Other lab sessions ran Gradle/Kotlin builds on the same machine during all runs (home=other in samples).
Tooling API jar: https://repo.gradle.org/gradle/libs-releases/org/gradle/gradle-tooling-api/9.7.1/gradle-tooling-api-9.7.1.jar
  sha256 e40a1f7707e4bf22f8039f6bbcdb012198f0f172d9331963bc7b41eb0ff5051b (kept in ${LAB_WORK:-$HOME/labs-work}/tapi-jar).
