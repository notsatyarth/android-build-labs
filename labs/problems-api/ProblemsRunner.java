// Gradle Tooling API "problems runner": runs one build and writes every problem the build reports through the
// Problems API (Tooling API progress events of type PROBLEMS) as one JSON line, plus the console output to a log.
//
// Usage: java -cp gradle-tooling-api-9.7.1.jar:slf4j-api-<v>.jar ProblemsRunner.java PROJECT_DIR OUT_DIR TASK... [-- GRADLE_ARGS...]
// Env:   TAPI_JAVA_HOME  Java home for the build (what an IDE's "Gradle JDK" setting does); default: JAVA_HOME
//
// Writes into OUT_DIR:
//   problems.jsonl  one line per event: {"kind":"problem",...} per SingleProblemEvent, {"kind":"summary",...} per
//                   ProblemSummary of a ProblemSummariesEvent (count = problems of that id beyond the ones sent singly)
//   console.log     the build's stdout and stderr, as the Tooling API hands them over
//   runner.json     outcome, failure messages, event counts, Gradle and Java version reported by the daemon
// Paths under PROJECT_DIR are written as "<project>/...", paths under the user home as "~/...", so no runner path is kept.
//
// API names were checked against platforms/ide/tooling-api/src/main/java/org/gradle/tooling/events/problems in the
// Gradle source and with javap against gradle-tooling-api-9.7.1.jar. The problem interfaces are @Incubating.
import org.gradle.tooling.BuildLauncher;
import org.gradle.tooling.Failure;
import org.gradle.tooling.GradleConnectionException;
import org.gradle.tooling.GradleConnector;
import org.gradle.tooling.ProjectConnection;
import org.gradle.tooling.events.OperationDescriptor;
import org.gradle.tooling.events.OperationType;
import org.gradle.tooling.events.ProgressEvent;
import org.gradle.tooling.events.ProgressListener;
import org.gradle.tooling.events.problems.AdditionalData;
import org.gradle.tooling.events.problems.ContextualLabel;
import org.gradle.tooling.events.problems.Details;
import org.gradle.tooling.events.problems.DocumentationLink;
import org.gradle.tooling.events.problems.FileLocation;
import org.gradle.tooling.events.problems.LineInFileLocation;
import org.gradle.tooling.events.problems.Location;
import org.gradle.tooling.events.problems.OffsetInFileLocation;
import org.gradle.tooling.events.problems.PluginIdLocation;
import org.gradle.tooling.events.problems.Problem;
import org.gradle.tooling.events.problems.ProblemDefinition;
import org.gradle.tooling.events.problems.ProblemEvent;
import org.gradle.tooling.events.problems.ProblemGroup;
import org.gradle.tooling.events.problems.ProblemId;
import org.gradle.tooling.events.problems.ProblemSummariesEvent;
import org.gradle.tooling.events.problems.ProblemSummary;
import org.gradle.tooling.events.problems.Severity;
import org.gradle.tooling.events.problems.SingleProblemEvent;
import org.gradle.tooling.events.problems.Solution;
import org.gradle.tooling.events.problems.TaskPathLocation;
import org.gradle.tooling.events.task.TaskFinishEvent;
import org.gradle.tooling.events.task.TaskOperationDescriptor;
import org.gradle.tooling.model.build.BuildEnvironment;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class ProblemsRunner {
    static String projectPrefix;
    static String homePrefix = System.getProperty("user.home");

    public static void main(String[] a) throws Exception {
        File dir = new File(a[0]).getCanonicalFile();
        File out = new File(a[1]);
        out.mkdirs();
        projectPrefix = dir.getPath();
        List<String> tasks = new ArrayList<>();
        List<String> args = new ArrayList<>();
        boolean inArgs = false;
        for (int i = 2; i < a.length; i++) {
            if (a[i].equals("--")) { inArgs = true; continue; }
            (inArgs ? args : tasks).add(a[i]);
        }
        String jh = System.getenv("TAPI_JAVA_HOME");
        if (jh == null) jh = System.getenv("JAVA_HOME");

        PrintWriter jsonl = new PrintWriter(new java.io.OutputStreamWriter(
            new FileOutputStream(new File(out, "problems.jsonl")), StandardCharsets.UTF_8), true);
        OutputStream console = new FileOutputStream(new File(out, "console.log"));
        OutputStream consoleSync = new OutputStream() {  // stdout and stderr interleave into one file
            public synchronized void write(int b) throws IOException { console.write(b); }
            public synchronized void write(byte[] b, int off, int len) throws IOException { console.write(b, off, len); }
            public synchronized void flush() throws IOException { console.flush(); }
        };

        int[] counts = new int[5];  // 0 single problems, 1 summary records, 2 summarised count, 3 other problem events, 4 tasks
        Map<String, Integer> taskOutcomes = new TreeMap<>();
        ProgressListener listener = new ProgressListener() {
            public synchronized void statusChanged(ProgressEvent e) {
                if (e instanceof SingleProblemEvent) {
                    counts[0]++;
                    jsonl.println(problemJson(counts[0], (SingleProblemEvent) e));
                } else if (e instanceof ProblemSummariesEvent) {
                    for (ProblemSummary s : ((ProblemSummariesEvent) e).getProblemSummaries()) {
                        counts[1]++;
                        counts[2] += s.getCount() == null ? 0 : s.getCount();
                        Json j = new Json();
                        j.put("kind", "summary");
                        idFields(j, s.getProblemId());
                        j.put("count", s.getCount());
                        jsonl.println(j);
                    }
                } else if (e instanceof ProblemEvent) {
                    counts[3]++;
                    Json j = new Json();
                    j.put("kind", "other-problem-event");
                    j.put("class", e.getClass().getName());
                    j.put("display_name", e.getDisplayName());
                    jsonl.println(j);
                } else if (e instanceof TaskFinishEvent) {
                    counts[4]++;
                    String r = e.getDisplayName();
                    String outcome = r.substring(r.lastIndexOf(' ') + 1);
                    taskOutcomes.merge(outcome, 1, Integer::sum);
                }
            }
        };

        Json run = new Json();
        run.put("tasks", tasks);
        run.put("arguments", args);
        run.put("tooling_api_client", org.gradle.util.GradleVersion.current().getVersion());
        long t0 = System.currentTimeMillis();
        GradleConnector conn = GradleConnector.newConnector().forProjectDirectory(dir);
        try (ProjectConnection c = conn.connect()) {
            BuildLauncher b = c.newBuild().forTasks(tasks.toArray(new String[0])).withArguments(args)
                .setStandardOutput(consoleSync).setStandardError(consoleSync).setColorOutput(false)
                .withDetailedFailure()
                .addProgressListener(listener, OperationType.PROBLEMS, OperationType.TASK);
            if (jh != null) b.setJavaHome(new File(jh));
            try {
                b.run();
                run.put("outcome", "success");
            } catch (GradleConnectionException ex) {
                run.put("outcome", "failure");
                run.put("exception", ex.getClass().getName());
                run.put("message", rel(firstLines(ex.getMessage(), 3)));
                List<Object> fails = new ArrayList<>();
                for (Failure f : ex.getFailures()) fails.add(failureJson(f, 0));
                run.put("failures", fails);
            }
            run.put("wall_ms", System.currentTimeMillis() - t0);
            try {
                org.gradle.tooling.ModelBuilder<BuildEnvironment> mb = c.model(BuildEnvironment.class);
                if (jh != null) mb.setJavaHome(new File(jh));
                BuildEnvironment env = mb.get();
                run.put("gradle_version", env.getGradle().getGradleVersion());
                run.put("java_home", rel(env.getJava().getJavaHome().getPath()));
            } catch (RuntimeException ex) {
                run.put("build_environment_error", rel(firstLines(ex.toString(), 2)));
            }
        }
        consoleSync.flush();
        console.close();
        jsonl.close();
        run.put("single_problem_events", counts[0]);
        run.put("summary_records", counts[1]);
        run.put("summarised_count", counts[2]);
        run.put("other_problem_events", counts[3]);
        run.put("task_finish_events", counts[4]);
        run.put("task_outcomes", taskOutcomes);
        try (PrintWriter w = new PrintWriter(new File(out, "runner.json"), "UTF-8")) { w.println(run); }
        System.out.println("runner: " + run);
    }

    static Json problemJson(int seq, SingleProblemEvent e) {
        Problem p = e.getProblem();
        ProblemDefinition d = p.getDefinition();
        Json j = new Json();
        j.put("kind", "problem");
        j.put("seq", seq);
        idFields(j, d.getId());
        Severity s = d.getSeverity();
        if (s != null) {
            j.put("severity", s.getSeverity());
            j.put("severity_known", s.isKnown());
            j.put("severity_name", s.getSeverity() == 0 ? "ADVICE" : s.getSeverity() == 1 ? "WARNING" : s.getSeverity() == 2 ? "ERROR" : "UNKNOWN");
        }
        ContextualLabel cl = p.getContextualLabel();
        j.put("contextual_label", cl == null ? null : rel(cl.getContextualLabel()));
        Details det = p.getDetails();
        j.put("details", det == null ? null : rel(det.getDetails()));
        DocumentationLink dl = d.getDocumentationLink();
        j.put("documentation", dl == null ? null : dl.getUrl());
        j.put("origin_locations", locations(p.getOriginLocations()));
        j.put("contextual_locations", locations(p.getContextualLocations()));
        List<Object> sol = new ArrayList<>();
        if (p.getSolutions() != null) for (Solution x : p.getSolutions()) sol.add(rel(x.getSolution()));
        j.put("solutions", sol);
        Failure f = p.getFailure();
        j.put("has_failure", f != null);
        if (f != null) j.put("failure_message", rel(firstLines(f.getMessage(), 3)));
        AdditionalData ad = p.getAdditionalData();
        if (ad != null) {
            Map<String, Object> m = null;
            try { m = ad.getAsMap(); } catch (RuntimeException ex) { j.put("additional_data_error", ex.toString()); }
            if (m != null && !m.isEmpty()) {
                Json am = new Json();
                for (Map.Entry<String, Object> en : new TreeMap<>(m).entrySet()) am.put(en.getKey(), rel(trunc(String.valueOf(en.getValue()), 400)));
                j.put("additional_data", am);
            }
            j.put("additional_data_class", simpleIface(ad));
        }
        // the operation that reported the problem: direct parent, nearest task ancestor, else the task_path location
        OperationDescriptor parent = e.getDescriptor() == null ? null : e.getDescriptor().getParent();
        j.put("parent_operation", parent == null ? null : rel(parent.getDisplayName()));
        String task = null;
        for (OperationDescriptor o = parent; o != null; o = o.getParent()) {
            if (o instanceof TaskOperationDescriptor) { task = ((TaskOperationDescriptor) o).getTaskPath(); break; }
        }
        if (task == null && p.getContextualLocations() != null) {  // in practice the parent is "Run build"; the task comes as a location
            for (Location l : p.getContextualLocations()) {
                if (l instanceof TaskPathLocation) { task = ((TaskPathLocation) l).getBuildTreePath(); break; }
            }
        }
        j.put("task", task);
        return j;
    }

    static void idFields(Json j, ProblemId id) {
        List<Object> path = new ArrayList<>();
        List<Object> pathDisplay = new ArrayList<>();
        for (ProblemGroup g = id == null ? null : id.getGroup(); g != null; g = g.getParent()) {
            path.add(g.getName());
            pathDisplay.add(g.getDisplayName());
        }
        Collections.reverse(path);
        Collections.reverse(pathDisplay);
        j.put("group_path", path);
        j.put("group_display_path", pathDisplay);
        j.put("id_name", id == null ? null : id.getName());
        j.put("id_display_name", id == null ? null : rel(id.getDisplayName()));
    }

    static List<Object> locations(List<Location> ls) {
        List<Object> out = new ArrayList<>();
        if (ls == null) return out;
        for (Location l : ls) {
            Json j = new Json();
            if (l instanceof LineInFileLocation) {
                LineInFileLocation x = (LineInFileLocation) l;
                j.put("type", "line_in_file"); j.put("path", rel(x.getPath()));
                j.put("line", x.getLine()); j.put("column", x.getColumn()); j.put("length", x.getLength());
            } else if (l instanceof OffsetInFileLocation) {
                OffsetInFileLocation x = (OffsetInFileLocation) l;
                j.put("type", "offset_in_file"); j.put("path", rel(x.getPath()));
                j.put("offset", x.getOffset()); j.put("length", x.getLength());
            } else if (l instanceof FileLocation) {
                j.put("type", "file"); j.put("path", rel(((FileLocation) l).getPath()));
            } else if (l instanceof PluginIdLocation) {
                j.put("type", "plugin_id"); j.put("plugin_id", ((PluginIdLocation) l).getPluginId());
            } else if (l instanceof TaskPathLocation) {
                j.put("type", "task_path"); j.put("task_path", ((TaskPathLocation) l).getBuildTreePath());
            } else {
                j.put("type", "other"); j.put("class", simpleIface(l));
            }
            out.add(j);
        }
        return out;
    }

    static Json failureJson(Failure f, int depth) {
        Json j = new Json();
        j.put("message", rel(firstLines(f.getMessage(), 3)));
        List<Object> probs = new ArrayList<>();
        try {
            for (Problem p : f.getProblems()) {
                Json pj = new Json();
                idFields(pj, p.getDefinition().getId());
                pj.put("contextual_label", p.getContextualLabel() == null ? null : rel(p.getContextualLabel().getContextualLabel()));
                pj.put("origin_locations", locations(p.getOriginLocations()));
                probs.add(pj);
            }
        } catch (RuntimeException ex) {
            j.put("problems_error", ex.toString());
        }
        j.put("problems", probs);
        if (depth < 4) {
            List<Object> causes = new ArrayList<>();
            for (Failure c : f.getCauses()) causes.add(failureJson(c, depth + 1));
            j.put("causes", causes);
        }
        return j;
    }

    static String simpleIface(Object o) {
        for (Class<?> i : o.getClass().getInterfaces()) if (i.getName().startsWith("org.gradle.tooling")) return i.getSimpleName();
        return o.getClass().getSimpleName();
    }

    static String firstLines(String s, int n) {
        if (s == null) return null;
        String[] ls = s.split("\n", -1);
        if (ls.length <= n) return s;
        return String.join("\n", java.util.Arrays.copyOf(ls, n)) + "\n...";
    }

    static String trunc(String s, int n) { return s == null || s.length() <= n ? s : s.substring(0, n) + "..."; }

    static String rel(String s) {
        if (s == null) return null;
        s = s.replace("file://" + projectPrefix, "<project>").replace(projectPrefix, "<project>");
        if (homePrefix != null && homePrefix.length() > 1) s = s.replace(homePrefix, "~");
        return s;
    }

    // minimal ordered JSON object writer (standard library only)
    static class Json {
        final List<String> keys = new ArrayList<>();
        final List<Object> vals = new ArrayList<>();
        void put(String k, Object v) { keys.add(k); vals.add(v); }
        public String toString() { StringBuilder b = new StringBuilder(); write(b, this); return b.toString(); }
        static void write(StringBuilder b, Object v) {
            if (v == null) b.append("null");
            else if (v instanceof Json) {
                Json j = (Json) v; b.append('{');
                for (int i = 0; i < j.keys.size(); i++) {
                    if (i > 0) b.append(',');
                    str(b, j.keys.get(i)); b.append(':'); write(b, j.vals.get(i));
                }
                b.append('}');
            } else if (v instanceof Map) {
                b.append('{'); boolean first = true;
                for (Map.Entry<?, ?> e : ((Map<?, ?>) v).entrySet()) {
                    if (!first) b.append(','); first = false;
                    str(b, String.valueOf(e.getKey())); b.append(':'); write(b, e.getValue());
                }
                b.append('}');
            } else if (v instanceof List) {
                b.append('['); boolean first = true;
                for (Object o : (List<?>) v) { if (!first) b.append(','); first = false; write(b, o); }
                b.append(']');
            } else if (v instanceof Number || v instanceof Boolean) b.append(v);
            else str(b, v.toString());
        }
        static void str(StringBuilder b, String s) {
            b.append('"');
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                switch (c) {
                    case '"': b.append("\\\""); break;
                    case '\\': b.append("\\\\"); break;
                    case '\n': b.append("\\n"); break;
                    case '\r': b.append("\\r"); break;
                    case '\t': b.append("\\t"); break;
                    default:
                        if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c);
                }
            }
            b.append('"');
        }
    }
}
