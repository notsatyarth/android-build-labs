pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement { repositories { google(); mavenCentral() } }
rootProject.name = "missing-dimension"
include(":app", ":intermediate1", ":intermediate2", ":leaf")
