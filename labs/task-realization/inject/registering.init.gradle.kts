// Kotlin DSL delegate 'by tasks.registering' is lazy, but deprecated in Gradle 9.6 (removal in Gradle 10).

gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) {
        val labRegistering by tasks.registering
    }
}
