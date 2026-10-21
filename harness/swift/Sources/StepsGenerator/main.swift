// Generates the harness's table of steps from a steps file. See README.md.
//
// Usage: StepsGenerator path/to/steps.swift path/to/Steps.swift
//
// Swift cannot call a function by name at runtime, so this finds every step marker in the steps file
// and writes a table mapping the step text to the first function defined after it.

import Foundation

/// A step marker is a line comment holding `Create the SDK client` or a step starting with `When `.
func marker(_ line: String) -> String? {
    guard line.hasPrefix("//") else { return nil }
    let text = line.drop { $0 == "/" }.trimmingCharacters(in: .whitespaces)
    return text == "Create the SDK client" || text.hasPrefix("When ") ? text : nil
}

/// The name of the function defined on this line, e.g. `public func createClient(`.
func functionName(_ line: String) -> String? {
    guard let keyword = line.range(of: "func "),
          keyword.lowerBound == line.startIndex || line[line.index(before: keyword.lowerBound)] == " "
    else { return nil }
    let name = line[keyword.upperBound...].prefix { $0.isLetter || $0.isNumber || $0 == "_" }
    return name.isEmpty ? nil : String(name)
}

func literal(_ text: String) -> String {
    "\"" + text.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"") + "\""
}

let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    FileHandle.standardError.write(Data("usage: StepsGenerator <steps file> <output>\n".utf8))
    exit(1)
}

var steps: [(text: String, function: String)] = []
var pending: String?
for line in try String(contentsOfFile: arguments[1], encoding: .utf8).components(separatedBy: .newlines) {
    let line = line.trimmingCharacters(in: .whitespaces)
    if let text = marker(line) {
        pending = text
    } else if let text = pending, let function = functionName(line) {
        steps.append((text, function))
        pending = nil
    }
}

var code = "// Generated from \(URL(fileURLWithPath: arguments[1]).lastPathComponent) by StepsGenerator. Do not edit.\n\n"
code += "import SDKSpecSteps\n\nlet steps: [(text: String, step: Step)] = [\n"
for step in steps {
    code += "    (\(literal(step.text)), step(SDKSpecSteps.\(step.function))),\n"
    FileHandle.standardError.write(Data("\(step.text) -> \(step.function)\n".utf8))
}
code += "]\n"
try code.write(toFile: arguments[2], atomically: true, encoding: .utf8)
