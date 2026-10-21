import Foundation

/// A step function, called with the client, if the request names one, and the request's arguments.
typealias Step = (_ client: Any?, _ args: [JSON]) async throws -> Any

/// Reports a step the harness could not call, e.g. with the wrong arguments.
struct HarnessError: Error, CustomStringConvertible {
    let description: String

    init(_ description: String) {
        self.description = description
    }
}

/// Hands a step function its arguments: the client first, if there is one, then the JSON arguments,
/// each decoded to the function's parameter type.
struct Arguments {
    private var client: Any?
    private var args: [JSON]

    init(client: Any?, args: [JSON]) {
        self.client = client
        self.args = args
    }

    mutating func next<T>() throws -> T {
        if let client {
            self.client = nil
            guard let client = client as? T else {
                throw HarnessError("The client is a \(type(of: client)), but the step function takes a \(T.self)")
            }
            return client
        }
        guard !args.isEmpty else {
            throw HarnessError("The step function takes more arguments than the runner sent")
        }
        let arg = args.removeFirst()
        guard let type = T.self as? any Decodable.Type else {
            throw HarnessError("The step function takes a \(T.self), which is not Decodable")
        }
        guard let value = try JSONDecoder().decode(type, from: JSONEncoder().encode(arg)) as? T else {
            throw HarnessError("Cannot convert the argument to a \(T.self)")
        }
        return value
    }

    func finish() throws {
        guard client == nil, args.isEmpty else {
            throw HarnessError("The step function takes fewer arguments than the runner sent")
        }
    }
}

// The generated table wraps each step function with `step`, which is overloaded by the number of
// parameters, so that the compiler infers their types.

func step<R>(_ function: @escaping () async throws -> R) -> Step {
    { client, args in
        try Arguments(client: client, args: args).finish()
        return try await function()
    }
}

func step<A, R>(_ function: @escaping (A) async throws -> R) -> Step {
    { client, args in
        var arguments = Arguments(client: client, args: args)
        let a: A = try arguments.next()
        try arguments.finish()
        return try await function(a)
    }
}

func step<A, B, R>(_ function: @escaping (A, B) async throws -> R) -> Step {
    { client, args in
        var arguments = Arguments(client: client, args: args)
        let a: A = try arguments.next()
        let b: B = try arguments.next()
        try arguments.finish()
        return try await function(a, b)
    }
}

func step<A, B, C, R>(_ function: @escaping (A, B, C) async throws -> R) -> Step {
    { client, args in
        var arguments = Arguments(client: client, args: args)
        let a: A = try arguments.next()
        let b: B = try arguments.next()
        let c: C = try arguments.next()
        try arguments.finish()
        return try await function(a, b, c)
    }
}

func step<A, B, C, D, R>(_ function: @escaping (A, B, C, D) async throws -> R) -> Step {
    { client, args in
        var arguments = Arguments(client: client, args: args)
        let a: A = try arguments.next()
        let b: B = try arguments.next()
        let c: C = try arguments.next()
        let d: D = try arguments.next()
        try arguments.finish()
        return try await function(a, b, c, d)
    }
}

/// Any JSON value. Integers are kept apart from other numbers so that they round-trip exactly.
enum JSON: Codable {
    case null
    case bool(Bool)
    case int(Int64)
    case double(Double)
    case string(String)
    case array([JSON])
    case object([String: JSON])

    init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int64.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSON].self) {
            self = .array(value)
        } else {
            self = try .object(container.decode([String: JSON].self))
        }
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case let .bool(value): try container.encode(value)
        case let .int(value): try container.encode(value)
        case let .double(value): try container.encode(value)
        case let .string(value): try container.encode(value)
        case let .array(value): try container.encode(value)
        case let .object(value): try container.encode(value)
        }
    }
}
