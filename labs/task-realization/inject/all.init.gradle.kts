// tasks.all { } : every task in the project, now and later.

gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) tasks.all { }
}
