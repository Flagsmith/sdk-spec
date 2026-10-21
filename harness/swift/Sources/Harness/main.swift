// Swift harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
//
// Swift cannot call a function by name at runtime, so the GenerateSteps plugin compiles this target
// together with a generated table of the steps file's functions, `steps`, in file order.

import Foundation
#if canImport(Glibc)
    import Glibc
#endif

struct Request: Decodable {
    let id: JSON
    let command: String
    let step: String?
    let args: [JSON]?
    let client: String?
    let returnsClient: Bool?
}

/// Formats an error as "<type>: <message>", e.g. "FlagsmithClient.FlagsmithError: …".
func describe(_ error: any Error) -> String {
    let message = (error as? any LocalizedError)?.errorDescription ?? String(describing: error)
    return "\(String(reflecting: type(of: error))): \(message)"
}

func handle(_ request: Request, clients: inout [String: Any]) async -> [String: JSON] {
    var response: [String: JSON] = ["id": request.id]
    if request.command == "hello" {
        response["steps"] = .array(steps.map { .string($0.text) })
        return response
    }
    guard let step = steps.first(where: { $0.text == request.step })?.step else {
        response["missing"] = .bool(true)
        return response
    }

    do {
        var client: Any?
        if let handle = request.client {
            guard let stored = clients[handle] else { throw HarnessError("No client \(handle)") }
            client = stored
        }
        let result = try await step(client, request.args ?? [])
        if request.returnsClient == true {
            let handle = String(clients.count + 1)
            clients[handle] = result
            response["client"] = .string(handle)
        } else if let result = result as? any Encodable {
            response["result"] = try JSONDecoder().decode(JSON.self, from: JSONEncoder().encode(result))
        } else if result is Void {
            response["result"] = .null
        } else {
            throw HarnessError("The step returned a \(type(of: result)), which is not Encodable")
        }
    } catch {
        FileHandle.standardError.write(Data("harness: \(request.step ?? ""): \(error)\n".utf8))
        response["error"] = .string(describe(error))
    }
    return response
}

// Responses go to the original stdout. Anything else written to stdout, e.g. SDK logging, goes to
// stderr.
let responses = FileHandle(fileDescriptor: dup(STDOUT_FILENO))
dup2(STDERR_FILENO, STDOUT_FILENO)

Task.detached {
    var clients: [String: Any] = [:]
    let encoder = JSONEncoder()
    encoder.outputFormatting = .withoutEscapingSlashes
    while let line = readLine() {
        guard !line.trimmingCharacters(in: .whitespaces).isEmpty else { continue }
        do {
            let request = try JSONDecoder().decode(Request.self, from: Data(line.utf8))
            let response = await handle(request, clients: &clients)
            responses.write(try encoder.encode(response) + Data("\n".utf8))
        } catch {
            FileHandle.standardError.write(Data("harness: invalid request: \(error)\n".utf8))
            exit(1)
        }
    }
    exit(0)
}

// Steps run off the main thread, which serves the main queue for SDKs that call back on it.
dispatchMain()
