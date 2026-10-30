package lab.processor

import com.google.devtools.ksp.processing.*
import com.google.devtools.ksp.symbol.*

/** Generates `<Class>Hello.kt` for every class annotated with `lab.app.Hello`. */
class HelloProcessor(private val env: SymbolProcessorEnvironment) : SymbolProcessor {
    override fun process(resolver: Resolver): List<KSAnnotated> {
        resolver.getSymbolsWithAnnotation("lab.app.Hello").filterIsInstance<KSClassDeclaration>().forEach { c ->
            val pkg = c.packageName.asString()
            val name = c.simpleName.asString() + "Hello"
            env.codeGenerator.createNewFile(Dependencies(false, c.containingFile!!), pkg, name).use {
                it.write("package $pkg\n\nobject $name { const val GREETING = \"hello from KSP\" }\n".toByteArray())
            }
        }
        return emptyList()
    }
}

class HelloProcessorProvider : SymbolProcessorProvider {
    override fun create(environment: SymbolProcessorEnvironment) = HelloProcessor(environment)
}
