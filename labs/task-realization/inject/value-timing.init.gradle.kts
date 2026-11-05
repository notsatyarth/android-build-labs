// When does a task read its inputs? (bead droidcon-5z1, 2026-11-05)
// labGen writes build/lab/gen.txt ("generated-by-<lab.runid>") when it RUNS. labUse needs that text. -Dlab.mode picks how labUse gets it:
//   eager-read     tasks.create + read the file in the configuration action
//   lazy-read      tasks.register + read the file in the configuration action
//   provider       tasks.register + input wired as a Provider from labGen, read in doLast (at execution)
// Part 2 (all modes): a value the "build script" sets after the plugin registered the tasks (simulated with
// afterEvaluate, which runs after the project's build script). Three tasks report what they saw:
//   labOrderEager (create, reads in configuration), labOrderLazy (register, reads in configuration),
//   labOrderProvider (register, reads the Property in doLast)
// Output lines: LAB_VALUE <task> <what it saw>.  Applies to -Dlab.target (default :core:data).
gradle.lifecycle.beforeProject {
    val target = System.getProperty("lab.target") ?: ":core:data"
    if (path == target) {
        val mode = System.getProperty("lab.mode") ?: "provider"
        val genFile = layout.buildDirectory.file("lab/gen.txt")
        val runId = System.getProperty("lab.runid") ?: "run"
        val gen = tasks.register("labGen") {
            val out = genFile
            val id = runId
            outputs.file(out)
            outputs.upToDateWhen { false }
            doLast { out.get().asFile.apply { parentFile.mkdirs(); writeText("generated-by-" + id) } }
        }
        when (mode) {
            "eager-read" -> tasks.create("labUse") {
                dependsOn(gen)
                val text = genFile.get().asFile.readText()  // configuration time
                doLast { println("LAB_VALUE labUse " + text) }
            }
            "lazy-read" -> tasks.register("labUse") {
                dependsOn(gen)
                val text = genFile.get().asFile.readText()  // configuration time, but only when realized
                doLast { println("LAB_VALUE labUse " + text) }
            }
            else -> tasks.register("labUse") {
                val input = gen.map { it.outputs.files.singleFile }  // Provider: carries the task dependency
                inputs.files(input)
                doLast { println("LAB_VALUE labUse " + input.get().readText()) }  // execution time
            }
        }

        // Part 2: value set later by the build script
        val setting = objects.property(String::class.java).convention("unset")
        afterEvaluate { setting.set("set-by-build-script") }
        tasks.create("labOrderEager") {
            val v = setting.get()
            doLast { println("LAB_VALUE labOrderEager " + v) }
        }
        tasks.register("labOrderLazy") {
            val v = setting.get()
            doLast { println("LAB_VALUE labOrderLazy " + v) }
        }
        tasks.register("labOrderProvider") {
            val p = setting
            doLast { println("LAB_VALUE labOrderProvider " + p.get()) }
        }
    }
}
