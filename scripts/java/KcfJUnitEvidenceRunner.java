import java.io.File;
import java.io.PrintWriter;
import org.junit.runner.JUnitCore;
import org.junit.runner.Result;

/** Independent result evidence survives tests that close System.out. */
public final class KcfJUnitEvidenceRunner {
    public static void main(String[] args) throws Exception {
        Class<?>[] classes = new Class<?>[args.length - 1];
        for (int i = 1; i < args.length; i++) {
            classes[i - 1] = Class.forName(args[i]);
        }
        Result result = new JUnitCore().run(classes);
        try (PrintWriter writer = new PrintWriter(new File(args[0] + ".failures.log"), "UTF-8")) {
            for (org.junit.runner.notification.Failure failure : result.getFailures()) {
                writer.println(failure.toString());
                writer.println(failure.getTrace());
            }
        }
        try (PrintWriter writer = new PrintWriter(new File(args[0]), "UTF-8")) {
            writer.print("{\"schema\":1,\"tests_run\":" + result.getRunCount()
                + ",\"failures\":" + result.getFailureCount()
                + ",\"ignored\":" + result.getIgnoreCount()
                + ",\"assumption_failures\":" + result.getAssumptionFailureCount() + "}");
        }
        if (!result.wasSuccessful()) {
            System.exit(1);
        }
    }
}
