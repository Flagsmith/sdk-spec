// Generates the harness's table of steps from the SDK's steps file. See README.md.

import PackagePlugin

@main
struct GenerateSteps: BuildToolPlugin {
    func createBuildCommands(context: PluginContext, target: Target) throws -> [Command] {
        let stepsFile = target.recursiveTargetDependencies
            .compactMap { $0 as? SourceModuleTarget }
            .filter { $0.moduleName == "SDKSpecSteps" }
            .flatMap { $0.sourceFiles(withSuffix: "swift") }
            .first { $0.path.lastComponent == "steps.swift" }
        guard let stepsFile else {
            throw PluginError("The SDKSpecSteps target has no steps.swift")
        }
        let output = context.pluginWorkDirectory.appending("Steps.swift")
        return [
            .buildCommand(
                displayName: "Generating the steps table from \(stepsFile.path)",
                executable: try context.tool(named: "StepsGenerator").path,
                arguments: [stepsFile.path, output],
                inputFiles: [stepsFile.path],
                outputFiles: [output]
            ),
        ]
    }
}

struct PluginError: Error, CustomStringConvertible {
    let description: String

    init(_ description: String) {
        self.description = description
    }
}
