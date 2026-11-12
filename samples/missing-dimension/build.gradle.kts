plugins {
    id("com.android.application") version "9.3.2" apply false
    id("com.android.library") version "9.3.2" apply false
}

apply(from = "verify-variant-alignment.gradle.kts")
