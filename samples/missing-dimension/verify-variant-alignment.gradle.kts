// verifyVariantAlignment: fails when a library compiles against a different flavor of a project
// dependency than the app packages. Apply from the root build file:
//   apply(from = "verify-variant-alignment.gradle.kts")
// Run:  ./gradlew verifyVariantAlignment -PalignVariant=realdeviceDebug [-PalignApp=:app]
//
// How it works: for every library module, compare the variant of each project dependency that the
// module's own compile classpath selects with the variant the app's runtime classpath selects.
// Only the flavor and build type attributes are compared. This is the same check you would do by
// hand with dependencyInsight, for all modules at once.
// Limits: it reads the resolved graphs only (nothing is compiled); it looks at direct project
// dependencies of each library; it needs the same flavor dimensions to be named in both modules.

import org.gradle.api.artifacts.component.ProjectComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedComponentResult
import org.gradle.api.artifacts.result.ResolvedDependencyResult

abstract class VerifyVariantAlignment : DefaultTask() {
    @get:Input abstract val appPath: Property<String>
    @get:Input abstract val appVariant: Property<String>
    @get:Internal abstract val appGraph: Property<ResolvedComponentResult>
    // module path -> that module's compile classpath graph
    @get:Internal abstract val moduleGraphs: MapProperty<String, ResolvedComponentResult>

    private fun flavorAttrs(variant: org.gradle.api.artifacts.result.ResolvedVariantResult): Map<String, String> =
        variant.attributes.keySet()
            .filter { it.name.contains("ProductFlavor") || it.name.contains("BuildType") }
            .associate { it.name.substringAfterLast('.') to variant.attributes.getAttribute(it).toString() }
            .toSortedMap()

    // project path -> flavor/build type attributes of the variant selected for it
    private fun selected(root: ResolvedComponentResult, direct: Boolean): Map<String, Map<String, String>> {
        val out = linkedMapOf<String, Map<String, String>>()
        val seen = mutableSetOf<ResolvedComponentResult>()
        fun walk(c: ResolvedComponentResult) {
            if (!seen.add(c)) return
            for (d in c.dependencies.filterIsInstance<ResolvedDependencyResult>()) {
                val id = d.selected.id
                if (id is ProjectComponentIdentifier) out.putIfAbsent(id.projectPath, flavorAttrs(d.resolvedVariant))
                if (!direct) walk(d.selected)
            }
        }
        walk(root)
        return out
    }

    @TaskAction
    fun check() {
        val packaged = selected(appGraph.get(), direct = false)
        val problems = mutableListOf<String>()
        moduleGraphs.get().toSortedMap().forEach { (module, graph) ->
            selected(graph, direct = true).forEach { (dep, compiled) ->
                val inApp = packaged[dep] ?: return@forEach
                if (compiled != inApp) {
                    problems += "$module compiles against $dep $compiled, but ${appPath.get()} (${appVariant.get()}) packages $dep $inApp"
                }
            }
        }
        if (problems.isNotEmpty()) {
            throw GradleException(
                "Variant mismatch (a missingDimensionStrategy in a library is the usual cause):\n  " +
                    problems.joinToString("\n  ") +
                    "\nInspect one pair with: ./gradlew <module>:dependencyInsight --configuration <config> --dependency <dep>")
        }
        logger.lifecycle("verifyVariantAlignment: ${moduleGraphs.get().size} modules checked, no mismatch (${appVariant.get()}).")
    }
}

gradle.projectsEvaluated {
    val appPath = providers.gradleProperty("alignApp").orElse(":app").get()
    val variant = providers.gradleProperty("alignVariant").orNull
    rootProject.tasks.register<VerifyVariantAlignment>("verifyVariantAlignment") {
        group = "verification"
        description = "Fails when a library compiles against a different flavor of a module than the app packages."
        if (variant == null) {
            doFirst { throw GradleException("Pass the app variant, for example -PalignVariant=realdeviceDebug") }
            return@register
        }
        val buildType = Regex("[A-Z][a-z]*$").find(variant)?.value?.lowercase() ?: variant
        this.appPath.set(appPath)
        appVariant.set(variant)
        val app = rootProject.project(appPath)
        appGraph.set(app.configurations.getByName("${variant}RuntimeClasspath").incoming.resolutionResult.rootComponent)
        rootProject.subprojects.filter { it.path != appPath && it.plugins.hasPlugin("com.android.library") }.forEach { m ->
            val cfg = m.configurations.findByName("${variant}CompileClasspath")
                ?: m.configurations.findByName("${buildType}CompileClasspath")
            if (cfg != null) moduleGraphs.put(m.path, cfg.incoming.resolutionResult.rootComponent)
        }
    }
}
