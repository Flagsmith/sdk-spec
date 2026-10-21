import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Java harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
 *
 * <p>Usage: {@code java -cp <harness, steps and SDK classes> Harness path/to/Steps.java}
 *
 * <p>Steps are static methods of the class compiled from the steps file. The harness reads the
 * steps source to map each step's text to a method name, then invokes the method by reflection.
 */
public class Harness {

  private static final Pattern MARKER =
      Pattern.compile("^\\s*//+\\s*(When .+?|Create the SDK client)\\s*$");
  private static final Pattern METHOD =
      Pattern.compile("^\\s*(?:[\\w@]+\\s+)*static\\s+[^=;(]+?\\s(\\w+)\\s*\\(");
  private static final Pattern PACKAGE = Pattern.compile("^\\s*package\\s+([\\w.]+)\\s*;");
  private static final ObjectMapper JSON = new ObjectMapper();

  static Map<String, Method> loadSteps(Path path) throws Exception {
    List<String> lines = Files.readAllLines(path);
    String className = path.getFileName().toString().replaceFirst("\\.java$", "");
    for (String line : lines) {
      Matcher pkg = PACKAGE.matcher(line);
      if (pkg.find()) {
        className = pkg.group(1) + "." + className;
        break;
      }
    }
    Class<?> stepsClass = Class.forName(className);

    Map<String, Method> steps = new LinkedHashMap<>();
    String pending = null;
    for (String line : lines) {
      Matcher marker = MARKER.matcher(line);
      Matcher method = METHOD.matcher(line);
      if (marker.matches()) {
        pending = marker.group(1);
      } else if (pending != null && method.find()) {
        steps.put(pending, staticMethod(stepsClass, method.group(1)));
        pending = null;
      }
    }
    return steps;
  }

  private static Method staticMethod(Class<?> stepsClass, String name) {
    for (Method method : stepsClass.getDeclaredMethods()) {
      if (method.getName().equals(name) && Modifier.isStatic(method.getModifiers())) {
        method.setAccessible(true);
        return method;
      }
    }
    throw new IllegalStateException("No static method " + name + " in " + stepsClass.getName());
  }

  /** The client (if any), then the request's args, converted to the step's parameter types. */
  private static Object[] arguments(Method step, JsonNode request, Map<String, Object> clients) {
    List<Object> values = new ArrayList<>();
    JsonNode client = request.path("client");
    if (!client.isMissingNode() && !client.isNull()) {
      values.add(clients.get(client.asText()));
    }
    request.path("args").forEach(values::add);

    Type[] types = step.getGenericParameterTypes();
    if (types.length != values.size()) {
      throw new IllegalArgumentException(
          step.getName() + " takes " + types.length + " arguments, but was given " + values.size());
    }
    Object[] arguments = new Object[types.length];
    for (int i = 0; i < types.length; i++) {
      Object value = values.get(i);
      arguments[i] = value instanceof JsonNode
          ? JSON.convertValue(value, JSON.constructType(types[i]))
          : value;
    }
    return arguments;
  }

  /** Answers the runner's requests, one JSON line each, until stdin closes. */
  public static void main(String[] args) throws Exception {
    // Keep stdout for the protocol: anything else printed by the SDK or steps goes to stderr.
    PrintStream out = new PrintStream(System.out, false, StandardCharsets.UTF_8.name());
    System.setOut(System.err);

    Map<String, Method> steps = loadSteps(Paths.get(args[0]));
    Map<String, Object> clients = new HashMap<>();
    BufferedReader in =
        new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));

    for (String line = in.readLine(); line != null; line = in.readLine()) {
      JsonNode request = JSON.readTree(line);
      ObjectNode response = JSON.createObjectNode();
      response.set("id", request.get("id"));
      Method step = steps.get(request.path("step").asText());
      if ("hello".equals(request.path("command").asText())) {
        response.set("steps", JSON.valueToTree(steps.keySet()));
      } else if (step == null) {
        response.put("missing", true);
      } else {
        try {
          Object result = step.invoke(null, arguments(step, request, clients));
          if (request.path("returnsClient").asBoolean()) {
            String handle = String.valueOf(clients.size() + 1);
            clients.put(handle, result);
            response.put("client", handle);
          } else {
            response.set("result", JSON.valueToTree(result));
          }
        } catch (Exception e) {
          // Reported to the runner.
          Throwable error = e instanceof InvocationTargetException ? e.getCause() : e;
          error.printStackTrace();
          response.put("error", error.getClass().getSimpleName() + ": " + error.getMessage());
        }
      }
      out.println(JSON.writeValueAsString(response));
      out.flush();
    }
  }
}
