plugins { id("com.android.application") }
android {
    namespace = "lab.app"; compileSdk = 36
    buildFeatures { resValues = true }
    defaultConfig { applicationId = "lab.app"; minSdk = 24 }
    buildTypes { getByName("release") { isMinifyEnabled = true; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt")) } }
    flavorDimensions += "target"
    productFlavors {
        create("emulator") { dimension = "target"; resValue("string", "name_app_module", "App Emulator") }
        create("realdevice") { dimension = "target"; resValue("string", "name_app_module", "App Real Device") }
    }
}
dependencies { implementation(project(":intermediate1")); implementation(project(":intermediate2")); implementation(project(":leaf")) }
