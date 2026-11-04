// The Gradle docs' side-effect antipattern (task_configuration_avoidance.adoc, guideline 2): the dependency
// check -> labVerify is added inside labVerify's own configuration action, so it exists only if something
// realizes labVerify.
gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) {
        tasks.register("labVerify") {
            tasks.named("check").get().dependsOn(this)
        }
    }
}
