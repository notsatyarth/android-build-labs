// Kotlin DSL tasks.withType<T> { } : DomainObjectCollectionExtensions.kt documents it as withType(type).all(action), i.e. eager.

gradle.lifecycle.beforeProject {
    val labTarget = System.getProperty("lab.target")?.split(",")?.contains(path) ?: true
    if (labTarget) tasks.withType<JavaCompile> { }
}
