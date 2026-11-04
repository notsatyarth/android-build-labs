// Lazy counterpart: withType<T>().configureEach { }

gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) tasks.withType<JavaCompile>().configureEach { }
}
