// tasks.matching { name-based spec }.configureEach { } : the docs say matching() needs all tasks created.

gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) tasks.matching { it.name == "labNoSuchTask" }.configureEach { }
}
