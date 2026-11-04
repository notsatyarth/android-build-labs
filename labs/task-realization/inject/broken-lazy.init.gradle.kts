// A registered task whose configuration throws. Does anything fail while the task is not needed?

gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) tasks.register("labBroken") { throw IllegalStateException("labBroken: configuration failed") }
}
