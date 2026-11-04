// The same antipattern, plus one unrelated eager line in the same project (tasks.all { } after evaluation).
gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) {
        tasks.register("labVerify") {
            tasks.named("check").get().dependsOn(this)
        }
        afterEvaluate { tasks.all { } }
    }
}
