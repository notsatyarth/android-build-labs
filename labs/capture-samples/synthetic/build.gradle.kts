// Deliberate violations, to get real reports that contain problems.
// 1. Configuration cache: a task reads the Project object at execution time.
tasks.register("bad") {
    doLast { println("project name: " + project.name) }
}
// 2. Isolated Projects: the root project configures its subprojects (cross-project access).
subprojects {
    apply(plugin = "base")
}
