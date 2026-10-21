// Finds the steps in a steps file and generates the harness's table of them. See ../../../README.md.

import Foundation

public struct Step: Equatable {
    public let text: String
    public let function: String

    public init(text: String, function: String) {
        self.text = text
        self.function = function
    }
}

/// Finds every step marker in a steps file and the first function declared after it, in file order.
public func findSteps(in source: String) -> [Step] {
    var steps: [Step] = []
    var pending: String?
    var commentDepth = 0
    for line in source.components(separatedBy: .newlines) {
        let line = removingBlockComments(from: line, depth: &commentDepth).trimmingCharacters(in: .whitespaces)
        if let text = marker(line) {
            pending = text
        } else if let text = pending, let function = declaredFunction(line) {
            steps.append(Step(text: text, function: function))
            pending = nil
        }
    }
    return steps
}

/// Generates the table the harness is compiled with, mapping each step's text to its function.
public func generateTable(_ steps: [Step], from stepsFile: String) -> String {
    var code = "// Generated from \(stepsFile) by StepsGenerator. Do not edit.\n\n"
    code += "import SDKSpecSteps\n\nlet steps: [(text: String, step: Step)] = [\n"
    for step in steps {
        code += "    (\(literal(step.text)), step(SDKSpecSteps.\(step.function))),\n"
    }
    return code + "]\n"
}

/// A step marker is a line comment holding `Create the SDK client` or a step starting with `When `.
func marker(_ line: String) -> String? {
    guard line.hasPrefix("//") else { return nil }
    let text = line.drop { $0 == "/" }.trimmingCharacters(in: .whitespaces)
    return text == "Create the SDK client" || text.hasPrefix("When ") ? text : nil
}

// `func` after any attributes and modifiers, e.g. `@MainActor public func createClient(`.
private let declaration = try! NSRegularExpression(pattern: """
^(?:@\\w+(?:\\([^)]*\\))?\\s+)*\
(?:(?:public|package|internal|fileprivate|private|nonisolated|static|final)\\s+)*\
func\\s+([A-Za-z_][A-Za-z0-9_]*)
""")

/// The name of the function declared on this line, if it declares one.
func declaredFunction(_ line: String) -> String? {
    let range = NSRange(line.startIndex..., in: line)
    guard let match = declaration.firstMatch(in: line, range: range),
          let name = Range(match.range(at: 1), in: line)
    else { return nil }
    return String(line[name])
}

/// Removes block comments from a line. They can nest and span lines, so `depth` carries the nesting
/// depth from one line to the next. A line comment is kept, so that markers can be found.
func removingBlockComments(from line: String, depth: inout Int) -> String {
    var code = ""
    var rest = Substring(line)
    while let next = rest.first {
        if depth == 0, rest.hasPrefix("//") {
            return code + rest
        } else if rest.hasPrefix("/*") {
            depth += 1
            rest = rest.dropFirst(2)
        } else if depth > 0, rest.hasPrefix("*/") {
            depth -= 1
            rest = rest.dropFirst(2)
        } else {
            if depth == 0 { code.append(next) }
            rest = rest.dropFirst()
        }
    }
    return code
}

func literal(_ text: String) -> String {
    "\"" + text.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") + "\""
}
