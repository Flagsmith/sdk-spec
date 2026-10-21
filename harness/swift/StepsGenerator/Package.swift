// swift-tools-version:5.9

import PackageDescription

// A package of its own, so that it can be tested without an SDK checked out next to the harness.
let package = Package(
    name: "StepsGenerator",
    products: [
        .executable(name: "StepsGenerator", targets: ["StepsGenerator"]),
    ],
    targets: [
        .executableTarget(name: "StepsGenerator", dependencies: ["StepsTable"]),
        .target(name: "StepsTable"),
        .testTarget(name: "StepsTableTests", dependencies: ["StepsTable"]),
    ]
)
