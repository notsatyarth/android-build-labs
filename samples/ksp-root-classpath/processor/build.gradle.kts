plugins { id("org.jetbrains.kotlin.jvm") }
kotlin { jvmToolchain(17) }
dependencies { implementation("com.google.devtools.ksp:symbol-processing-api:2.2.0-2.0.2") }
