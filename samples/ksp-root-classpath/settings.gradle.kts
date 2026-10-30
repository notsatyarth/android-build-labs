pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
    plugins {
        id("com.android.application") version "8.10.1"
        id("org.jetbrains.kotlin.android") version "2.2.0"
        id("com.google.devtools.ksp") version "2.2.0-2.0.2"
        id("org.jetbrains.kotlin.jvm") version "2.2.0"
    }
}
dependencyResolutionManagement { repositories { google(); mavenCentral() } }
rootProject.name = "ksp-root-classpath"
include(":app", ":processor")
