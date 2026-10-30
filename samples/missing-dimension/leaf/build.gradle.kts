plugins { id("com.android.library") }
android {
    namespace = "lab.leaf"; compileSdk = 36
    buildFeatures { resValues = true }
    defaultConfig { minSdk = 24 }
    flavorDimensions += "target"
    productFlavors {
        create("emulator") { dimension = "target"; resValue("string", "name_leaf_module", "Leaf module Emulator") }
        create("realdevice") { dimension = "target"; resValue("string", "name_leaf_module", "Leaf module Real Device") }
    }
}
