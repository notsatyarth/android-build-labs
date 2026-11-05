// Who realizes a task? A lazy configureEach action runs at the moment a task is realized, so a stack trace taken
// inside it shows the caller. Prints one line per realized task whose name matches -Dlab.who (a regex):
//   LAB_REALIZED_BY <task path> | frame < frame < ...   (JDK, Kotlin, Groovy, lambda and Gradle plumbing frames dropped)
// configureEach itself realizes nothing.
gradle.lifecycle.beforeProject {
    val who = System.getProperty("lab.who")?.toRegex()
    if (who != null) {
        tasks.configureEach {
            if (who.matches(name)) {
                val frames = Throwable().stackTrace
                    .map { it.className + "." + it.methodName }
                    .filter { f ->
                        listOf("java.", "jdk.", "sun.", "kotlin.", "groovy.", "org.codehaus.groovy.", "Who_realizes",
                            "org.gradle.internal.operations.", "org.gradle.internal.code.", "org.gradle.internal.Immutable",
                            "org.gradle.api.internal.DefaultCollectionCallbackActionDecorator",
                            "org.gradle.api.internal.DefaultMutationGuard", "org.gradle.api.internal.DefaultDomainObjectCollection",
                            "org.gradle.api.internal.DefaultNamedDomainObjectCollection", "org.gradle.api.internal.collections.",
                            "org.gradle.api.internal.provider.", "org.gradle.api.internal.tasks.DefaultTaskContainer\$TaskCreatingProvider",
                            "org.gradle.internal.Factories", "org.gradle.internal.model.", "org.gradle.internal.work.",
                            "org.gradle.internal.resources.", "org.gradle.internal.concurrent.")
                            .none { f.startsWith(it) } && !f.contains("\$\$Lambda")
                    }
                    .distinct()
                    .take(14)
                println("LAB_REALIZED_BY " + path + " | " + frames.joinToString(" < "))
            }
        }
    }
}
