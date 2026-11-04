// Fetches the Tooling API GradleProject model, the model IntelliJ IDEA asks for during a Gradle sync, and counts
// the tasks it lists. Gradle's GradleProjectBuilder realizes every task of every project for this model unless the
// system property org.gradle.internal.GradleProjectBuilderOptions=omit_all_tasks is set (Android Studio sets it).
// Usage: java -cp gradle-tooling-api-9.7.1.jar:slf4j-api-2.0.17.jar TapiModel.java <projectDir> [gradle args...]
import org.gradle.tooling.GradleConnector;
import org.gradle.tooling.ProjectConnection;
import org.gradle.tooling.model.GradleProject;
import java.io.File;
import java.util.Arrays;

public class TapiModel {
    static int projects = 0, tasks = 0;

    static void walk(GradleProject p) {
        projects++;
        tasks += p.getTasks().size();
        for (GradleProject c : p.getChildren()) walk(c);
    }

    public static void main(String[] a) {
        File dir = new File(a[0]);
        String[] args = Arrays.copyOfRange(a, 1, a.length);
        long t0 = System.currentTimeMillis();
        GradleConnector conn = GradleConnector.newConnector().forProjectDirectory(dir);
        String guh = System.getenv("GRADLE_USER_HOME");
        if (guh != null) conn.useGradleUserHomeDir(new File(guh));
        String inst = System.getenv("TAPI_GRADLE_HOME");  // local harness test only; CI uses the project wrapper
        if (inst != null) ((org.gradle.tooling.GradleConnector) conn).useInstallation(new File(inst));
        try (ProjectConnection c = conn.connect()) {
            GradleProject root = c.model(GradleProject.class).withArguments(args)
                .setStandardOutput(System.out).setStandardError(System.err).get();
            walk(root);
        }
        System.out.println("TAPI GradleProject projects=" + projects + " tasksListed=" + tasks
            + " wallMs=" + (System.currentTimeMillis() - t0));
    }
}
