// swift-tools-version:5.9

import PackageDescription

let package = Package(
    name: "sdk-spec-harness",
    platforms: [.macOS(.v10_15)],
    products: [
        .executable(name: "sdk-spec-harness", targets: ["Harness"]),
    ],
    dependencies: [
        // The SDK's steps package. The SDK must be checked out next to the harness, as `../sdk`.
        .package(path: "../sdk/sdk-spec"),
    ],
    targets: [
        .executableTarget(
            name: "Harness",
            dependencies: [.product(name: "SDKSpecSteps", package: "sdk-spec")],
            plugins: ["GenerateSteps"]
        ),
        .executableTarget(name: "StepsGenerator"),
        .plugin(name: "GenerateSteps", capability: .buildTool(), dependencies: ["StepsGenerator"]),
    ]
)
