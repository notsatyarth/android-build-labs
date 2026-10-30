// Minimal Gradle Tooling API client (the API Android Studio and IntelliJ use to run builds).
// Usage: java -cp gradle-tooling-api-9.7.1.jar:slf4j-api-2.0.17.jar TapiClient.java <projectDir> <task> [-- <gradle args...>]
// Uses the project's wrapper distribution (connector default) and prints the build environment
// the daemon reports (Gradle version, Java home, daemon JVM args) after the build.
import org.gradle.tooling.GradleConnector;
import org.gradle.tooling.ProjectConnection;
import org.gradle.tooling.model.build.BuildEnvironment;
import java.io.File;
import java.util.ArrayList;
import java.util.List;

public class TapiClient {
    public static void main(String[] a) {
        File dir = new File(a[0]);
        List<String> tasks = new ArrayList<>();
        List<String> args = new ArrayList<>();
        boolean inArgs = false;
        for (int i = 1; i < a.length; i++) {
            if (a[i].equals("--")) { inArgs = true; continue; }
            (inArgs ? args : tasks).add(a[i]);
        }
        long t0 = System.currentTimeMillis();
        GradleConnector conn = GradleConnector.newConnector().forProjectDirectory(dir);
        String guh = System.getenv("GRADLE_USER_HOME");  // IDEs pass their configured Gradle user home the same way
        if (guh != null) conn.useGradleUserHomeDir(new File(guh));
        try (ProjectConnection c = conn.connect()) {
            org.gradle.tooling.BuildLauncher b = c.newBuild().forTasks(tasks.toArray(new String[0])).withArguments(args)
                .setStandardOutput(System.out).setStandardError(System.err);
            String jh = System.getenv("TAPI_JAVA_HOME");  // what an IDE's "Gradle JDK" setting does
            if (jh != null) { b.setJavaHome(new File(jh)); System.out.println("TAPI setJavaHome=" + jh); }
            b.run();
            System.out.println("TAPI build wall ms: " + (System.currentTimeMillis() - t0));
            org.gradle.tooling.ModelBuilder<BuildEnvironment> mb = c.model(BuildEnvironment.class);
            if (jh != null) mb.setJavaHome(new File(jh));  // same Java home, so the model query does not pick another daemon
            BuildEnvironment env = mb.get();
            System.out.println("TAPI gradleVersion=" + env.getGradle().getGradleVersion());
            System.out.println("TAPI javaHome=" + env.getJava().getJavaHome());
            System.out.println("TAPI daemonJvmArgs=" + env.getJava().getJvmArguments());
        }
    }
}
