plugins { id("com.android.application") }
android {
    namespace = "lab.app"; compileSdk = 36
    defaultConfig { applicationId = "lab.app"; minSdk = 24 }
    buildTypes { create("staging") { initWith(getByName("debug")) } }
    flavorDimensions += listOf("tier", "store")
    productFlavors {
        create("free") { dimension = "tier" }; create("paid") { dimension = "tier" }
        create("play") { dimension = "store" }; create("amazon") { dimension = "store" }
    }
}
dependencies { implementation(project(":shared")) }
