// Generates the harness's table of steps from a steps file. See ../../../README.md.
//
// Usage: StepsGenerator path/to/steps.swift path/to/Steps.swift
//
// Swift cannot call a function by name at runtime, so this finds every step marker in the steps file
// and writes a table mapping the step text to the first function declared after it.

import Foundation
import StepsTable

let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    FileHandle.standardError.write(Data("usage: StepsGenerator <steps file> <output>\n".utf8))
    exit(1)
}

let steps = findSteps(in: try String(contentsOfFile: arguments[1], encoding: .utf8))
for step in steps {
    FileHandle.standardError.write(Data("\(step.text) -> \(step.function)\n".utf8))
}
let table = generateTable(steps, from: URL(fileURLWithPath: arguments[1]).lastPathComponent)
try table.write(toFile: arguments[2], atomically: true, encoding: .utf8)
