// Dart harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
//
// Dart cannot look up a function by name at runtime, so build.dart generates an entrypoint that
// passes the steps file's functions to `run`, keyed by step text in file order.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

Future<void> run(Map<String, Function> steps) async {
  // Keep stdout for responses: anything the SDK prints goes to stderr.
  await runZoned(
    () => _serve(steps),
    zoneSpecification: ZoneSpecification(
      print: (self, parent, zone, line) => stderr.writeln(line),
    ),
  );
  // The SDK may leave timers running, so exit rather than wait for them.
  exit(0);
}

Future<void> _serve(Map<String, Function> steps) async {
  final clients = <String, Object?>{};
  final lines = stdin.transform(utf8.decoder).transform(const LineSplitter());
  await for (final line in lines) {
    if (line.trim().isEmpty) {
      continue;
    }
    final request = jsonDecode(line) as Map<String, dynamic>;
    stdout.writeln(jsonEncode(await _handle(request, steps, clients)));
    await stdout.flush();
  }
}

Future<Map<String, Object?>> _handle(
  Map<String, dynamic> request,
  Map<String, Function> steps,
  Map<String, Object?> clients,
) async {
  final response = <String, Object?>{'id': request['id']};
  if (request['command'] == 'hello') {
    response['steps'] = steps.keys.toList();
    return response;
  }
  final step = steps[request['step']];
  if (step == null) {
    response['missing'] = true;
    return response;
  }

  try {
    final args = [
      if (request['client'] case final String client)
        clients.containsKey(client)
            ? clients[client]
            : throw HarnessException('no client $client'),
      ...request['args'] as List<dynamic>,
    ];
    var result = Function.apply(step, args);
    if (result is Future) {
      result = await result;
    }
    if (request['returnsClient'] == true) {
      final handle = '${clients.length + 1}';
      clients[handle] = result;
      response['client'] = handle;
    } else {
      // Encode here, so a result that is not JSON is reported as the step's error.
      response['result'] = jsonDecode(jsonEncode(result));
    }
  } catch (e, stackTrace) {
    stderr.writeln('harness: ${request['step']}: $e\n$stackTrace');
    response['error'] = _describe(e);
  }
  return response;
}

/// Formats an error as "<type>: <message>". Many Dart exceptions already start their
/// `toString()` with the type, e.g. "FormatException: …", so the type is not repeated.
String _describe(Object error) {
  final type = '${error.runtimeType}';
  final message = '$error';
  return message.startsWith(type) ? message : '$type: $message';
}

/// Reports a step the harness could not call.
class HarnessException implements Exception {
  HarnessException(this.message);

  final String message;

  @override
  String toString() => 'HarnessException: $message';
}
