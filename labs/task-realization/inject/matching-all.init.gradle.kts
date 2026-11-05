// matching { } with an eager consumer: tasks.matching { name spec }.all { } (compare matching { }.configureEach { }).
gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) tasks.matching { it.name == "labNoSuchTask" }.all { }
}
