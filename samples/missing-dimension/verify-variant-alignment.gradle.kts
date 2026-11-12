// verifyVariantAlignment: fails when a library compiles against a different flavor of a module than
// the app packages (the usual cause is missingDimensionStrategy in a library).
// Use: apply(from = "verify-variant-alignment.gradle.kts") in the root build file, then
//      ./gradlew verifyVariantAlignment -PalignVariant=realdeviceDebug
// It compares resolved dependency graphs only; nothing is compiled.
import org.gradle.api.artifacts.component.ProjectComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult

val alignVariant = providers.gradleProperty("alignVariant")

tasks.register("verifyVariantAlignment") {
    notCompatibleWithConfigurationCache("reads other projects' resolved graphs at execution time")
    doLast {
        val variant = alignVariant.get() // for example realdeviceDebug
        val buildType = Regex("[A-Z][a-z]*$").find(variant)?.value?.lowercase() ?: variant

        // project path -> flavor and build type attributes of the variant Gradle picked for it
        fun chosen(c: Configuration) = c.incoming.resolutionResult.allDependencies
            .filterIsInstance<ResolvedDependencyResult>()
            .filter { it.selected.id is ProjectComponentIdentifier }
            .associate { d ->
                val attrs = d.resolvedVariant.attributes
                (d.selected.id as ProjectComponentIdentifier).projectPath to
                    attrs.keySet().filter { "Flavor" in it.name || "BuildType" in it.name }
                        .joinToString { "${it.name.substringAfterLast('.')}=${attrs.getAttribute(it)}" }
            }

        val packaged = chosen(project(":app").configurations["${variant}RuntimeClasspath"])
        val mismatches = subprojects.filter { it.plugins.hasPlugin("com.android.library") }.flatMap { m ->
            val c = m.configurations.findByName("${variant}CompileClasspath")
                ?: m.configurations.findByName("${buildType}CompileClasspath")
            chosen(c ?: return@flatMap emptyList())
                .filter { (dep, picked) -> packaged[dep]?.let { it != picked } == true }
                .map { (dep, picked) -> "  ${m.path} compiles against $dep [$picked], but :app packages [${packaged[dep]}]" }
        }
        check(mismatches.isEmpty()) { "Variant mismatch:\n" + mismatches.joinToString("\n") }
        logger.lifecycle("verifyVariantAlignment: no mismatch ($variant)")
    }
}
