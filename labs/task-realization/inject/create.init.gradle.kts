// TaskContainer.create is @Deprecated in the API (Javadoc: use register). Does the build warn at run time?

gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) tasks.create("labEagerCreate")
}
