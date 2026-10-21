// Kotlin harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
//
// Usage: java -cp <harness, steps and SDK classes> Harness path/to/steps.kt
//
// Steps are top-level functions of the file facade class compiled from the steps file. The harness
// reads the steps source to map each step's text to a function name, then invokes the function by
// reflection.
@file:JvmName("Harness")

import com.google.gson.GsonBuilder
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.gson.ToNumberPolicy
import java.io.File
import java.io.PrintStream
import java.lang.reflect.InvocationTargetException
import java.lang.reflect.Method
import java.lang.reflect.Modifier
import kotlin.system.exitProcess

private val MARKER = Regex("""^\s*//+\s*(When .+?|Create the SDK client.*?)\s*$""")
private val FUNCTION = Regex("""^\s*(?:[\w@]+\s+)*fun\s+(\w+)\s*\(""")
private val PACKAGE = Regex("""^\s*package\s+([\w.]+)""")
private val JVM_NAME = Regex("""^\s*@file:JvmName\("(\w+)"\)""")

// Integers stay integers (Long) when converted to `Any` parameters, rather than Gson's default Double.
private val json = GsonBuilder()
    .serializeNulls()
    .setObjectToNumberStrategy(ToNumberPolicy.LONG_OR_DOUBLE)
    .create()

fun loadSteps(file: File): Map<String, Method> {
    val lines = file.readLines()
    val packageName = lines.firstNotNullOfOrNull { PACKAGE.find(it)?.groupValues?.get(1) }
    val facadeName = lines.firstNotNullOfOrNull { JVM_NAME.find(it)?.groupValues?.get(1) }
        ?: (file.nameWithoutExtension.replaceFirstChar(Char::uppercaseChar) + "Kt")
    val stepsClass = Class.forName(if (packageName == null) facadeName else "$packageName.$facadeName")

    val steps = LinkedHashMap<String, Method>()
    var pending: String? = null
    for (line in lines) {
        val marker = MARKER.matchEntire(line)
        val function = FUNCTION.find(line)
        if (marker != null) {
            pending = marker.groupValues[1]
        } else if (pending != null && function != null) {
            steps[pending] = staticMethod(stepsClass, function.groupValues[1])
            pending = null
        }
    }
    return steps
}

private fun staticMethod(stepsClass: Class<*>, name: String): Method =
    stepsClass.declaredMethods
        .firstOrNull { it.name == name && Modifier.isStatic(it.modifiers) }
        ?.apply { isAccessible = true }
        ?: throw IllegalStateException("No top-level function $name in ${stepsClass.name}")

/** The client (if any), then the request's args, converted to the step's parameter types. */
private fun arguments(step: Method, request: JsonObject, clients: Map<String, Any?>): Array<Any?> {
    val values = mutableListOf<Any?>()
    val client = request.get("client")
    if (client != null && !client.isJsonNull) {
        values.add(clients[client.asString])
    }
    request.getAsJsonArray("args")?.forEach { values.add(it) }

    val types = step.genericParameterTypes
    require(types.size == values.size) {
        "${step.name} takes ${types.size} arguments, but was given ${values.size}"
    }
    return Array(types.size) { i ->
        val value = values[i]
        if (value is JsonElement) json.fromJson<Any?>(value, types[i]) else value
    }
}

/** Answers the runner's requests, one JSON line each, until stdin closes. */
fun main(args: Array<String>) {
    // Keep stdout for the protocol: anything else printed by the SDK or steps goes to stderr.
    val out = PrintStream(System.out, false, Charsets.UTF_8.name())
    System.setOut(System.err)

    val steps = loadSteps(File(args[0]))
    val clients = HashMap<String, Any?>()

    for (line in System.`in`.bufferedReader(Charsets.UTF_8).lineSequence()) {
        val request = JsonParser.parseString(line).asJsonObject
        val response = JsonObject()
        response.add("id", request.get("id"))
        val step = request.get("step")?.takeUnless { it.isJsonNull }?.let { steps[it.asString] }
        if (request.get("command")?.asString == "hello") {
            response.add("steps", json.toJsonTree(steps.keys))
        } else if (step == null) {
            response.addProperty("missing", true)
        } else {
            try {
                val result = step.invoke(null, *arguments(step, request, clients))
                if (request.get("returnsClient")?.asBoolean == true) {
                    val handle = (clients.size + 1).toString()
                    clients[handle] = result
                    response.addProperty("client", handle)
                } else {
                    response.add("result", json.toJsonTree(result))
                }
            } catch (e: Exception) {
                // Reported to the runner.
                val error = if (e is InvocationTargetException) e.cause ?: e else e
                error.printStackTrace()
                response.addProperty("error", "${error.javaClass.simpleName}: ${error.message}")
            }
        }
        out.println(json.toJson(response))
        out.flush()
    }
    // SDK HTTP clients may hold non-daemon threads that would otherwise keep the JVM alive.
    exitProcess(0)
}
