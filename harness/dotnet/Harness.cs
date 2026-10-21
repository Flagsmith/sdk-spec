// .NET harness for the Flagsmith SDK behavioural spec. See HARNESS.md and README.md.
//
// Compiled together with an SDK's steps file (see Harness.csproj), then run as:
//   dotnet Harness.dll path/to/steps.cs

using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace SdkSpec.Harness;

static partial class Program
{
    [GeneratedRegex(@"^\s*//+\s*(When .+?|Create the SDK client)\s*$")]
    private static partial Regex Marker();

    // A static method declaration: modifiers including `static`, a return type, then the name.
    [GeneratedRegex(@"^\s*(?:\w+\s+)*static\s+(?:\w+\s+)*?.+?\s(\w+)\s*\(")]
    private static partial Regex Method();

    // Step arguments: JSON objects become Dictionary<string, object?>, values become CLR primitives.
    private static readonly JsonSerializerOptions ArgumentOptions = new() { Converters = { new JsonValueConverter() } };

    // Step results: records and classes serialise with camelCase names, e.g. `Feature` -> "feature".
    private static readonly JsonSerializerOptions ResultOptions = new(JsonSerializerDefaults.Web);

    private static async Task Main(string[] args)
    {
        var steps = LoadSteps(args[0]);
        var clients = new Dictionary<string, object?>();

        // Only protocol responses go to stdout: anything else written to the console goes to stderr.
        var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false));
        Console.SetOut(Console.Error);
        using var stdin = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false));

        while (await stdin.ReadLineAsync() is { } line)
        {
            var request = JsonNode.Parse(line)!.AsObject();
            var response = new JsonObject { ["id"] = request["id"]!.DeepClone() };
            if ((string?)request["command"] == "hello")
            {
                response["steps"] = new JsonArray(steps.Keys.Select(step => (JsonNode?)step).ToArray());
            }
            else if (!steps.TryGetValue((string)request["step"]!, out var step))
            {
                response["missing"] = true;
            }
            else
            {
                try
                {
                    var client = (string?)request["client"];
                    var result = await Invoke(step, client is null ? null : clients[client], request["args"]!.AsArray());
                    if ((bool?)request["returnsClient"] == true)
                    {
                        var handle = (clients.Count + 1).ToString();
                        clients[handle] = result;
                        response["client"] = handle;
                    }
                    else
                    {
                        response["result"] = JsonSerializer.SerializeToNode(result, ResultOptions);
                    }
                }
                catch (Exception e)
                {
                    if (e is TargetInvocationException { InnerException: { } inner })
                    {
                        e = inner;
                    }
                    Console.Error.WriteLine(e);
                    response["error"] = $"{e.GetType().Name}: {e.Message}";
                }
            }
            await stdout.WriteLineAsync(response.ToJsonString());
            await stdout.FlushAsync();
        }
    }

    // Maps each step's text to the static method declared after its marker comment in the steps file.
    private static Dictionary<string, MethodInfo> LoadSteps(string path)
    {
        var methods = typeof(Program).Assembly.GetTypes()
            .Where(type => type.Namespace != typeof(Program).Namespace && !type.IsDefined(typeof(CompilerGeneratedAttribute)))
            .SelectMany(type => type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.DeclaredOnly))
            .ToLookup(method => method.Name);

        var steps = new Dictionary<string, MethodInfo>();
        string? pending = null;
        foreach (var line in File.ReadLines(path))
        {
            if (Marker().Match(line) is { Success: true } marker)
            {
                pending = marker.Groups[1].Value;
            }
            else if (pending is not null && Method().Match(line) is { Success: true } method)
            {
                var name = method.Groups[1].Value;
                steps[pending] = methods[name].Count() == 1
                    ? methods[name].Single()
                    : throw new InvalidOperationException(
                        $"Expected exactly one static method named {name} for the step \"{pending}\" in {path}, found {methods[name].Count()}");
                pending = null;
            }
        }
        return steps;
    }

    private static async Task<object?> Invoke(MethodInfo step, object? client, JsonArray args)
    {
        var parameters = step.GetParameters();
        var offset = client is null ? 0 : 1;
        if (parameters.Length != args.Count + offset)
        {
            throw new TargetParameterCountException(
                $"{step.Name} takes {parameters.Length} parameters, but the step passes {args.Count + offset}");
        }

        // Convert each JSON argument to the type of the parameter it is passed as.
        var arguments = args.Select((arg, i) => arg.Deserialize(parameters[i + offset].ParameterType, ArgumentOptions));
        if (client is not null)
        {
            arguments = arguments.Prepend(client);
        }

        var result = step.Invoke(null, arguments.ToArray());
        if (result is Task task)
        {
            await task;
            result = step.ReturnType.IsGenericType ? step.ReturnType.GetProperty("Result")!.GetValue(task) : null;
        }
        return result;
    }

    // Reads JSON values into `object` as CLR primitives rather than JsonElement.
    private sealed class JsonValueConverter : JsonConverter<object>
    {
        public override object? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
            reader.TokenType switch
            {
                JsonTokenType.String => reader.GetString(),
                JsonTokenType.Number when reader.TryGetInt64(out var integer) => integer,
                JsonTokenType.Number => reader.GetDouble(),
                JsonTokenType.True => true,
                JsonTokenType.False => false,
                JsonTokenType.StartObject => JsonSerializer.Deserialize<Dictionary<string, object?>>(ref reader, options),
                JsonTokenType.StartArray => JsonSerializer.Deserialize<List<object?>>(ref reader, options),
                _ => throw new JsonException($"Unexpected JSON token: {reader.TokenType}"),
            };

        public override void Write(Utf8JsonWriter writer, object value, JsonSerializerOptions options) =>
            throw new NotSupportedException();
    }
}
