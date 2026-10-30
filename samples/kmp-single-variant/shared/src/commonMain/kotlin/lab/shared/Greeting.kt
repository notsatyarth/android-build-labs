package lab.shared
expect fun platform(): String
fun greeting(): String = "Hello from ${platform()}"
