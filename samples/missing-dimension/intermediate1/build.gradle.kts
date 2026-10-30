plugins { id("com.android.library") }
android {
    namespace = "lab.intermediate1"; compileSdk = 36
    defaultConfig { minSdk = 24  }
}
android { flavorDimensions += "target"; productFlavors { create("emulator") { dimension = "target" }; create("realdevice") { dimension = "target" } } }
dependencies { implementation(project(":leaf")) }
