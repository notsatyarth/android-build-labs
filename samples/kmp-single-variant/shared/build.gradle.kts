plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("com.android.library")
}
android { namespace = "lab.shared"; compileSdk = 36; defaultConfig { minSdk = 24 } }
kotlin {
    androidTarget()
    jvm()
}
