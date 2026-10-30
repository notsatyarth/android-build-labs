package lab.app

import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class User(val name: String, val age: Int)
