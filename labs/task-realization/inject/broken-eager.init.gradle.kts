// The same broken configuration, created eagerly.

gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) tasks.create("labBroken") { throw IllegalStateException("labBroken: configuration failed") }
}
