@testable import StepsTable
import XCTest

final class StepsTableTests: XCTestCase {
    func testFindsTheFunctionDeclaredAfterEachMarker() {
        let source = """
        import FlagsmithClient

        // Create the SDK client
        public func createClient(environmentKey: String, apiUrl: String) -> Client {
            Client(environmentKey: environmentKey, apiUrl: apiUrl)
        }

        // When the application gets the environment flags
        @MainActor public func getEnvironmentFlags(_ client: Client) async throws -> [SpecFlag] {
            try await client.getEnvironmentFlags()
        }
        """

        XCTAssertEqual(findSteps(in: source), [
            Step(text: "Create the SDK client", function: "createClient"),
            Step(text: "When the application gets the environment flags", function: "getEnvironmentFlags"),
        ])
    }

    func testFindsEveryClientCreatingMarker() {
        let source = """
        // Create the SDK client
        public func createClient(environmentKey: String, apiUrl: String) -> Client {
            Client(environmentKey: environmentKey, apiUrl: apiUrl)
        }

        // Create the SDK client with events enabled
        public func createClientWithEvents(environmentKey: String, apiUrl: String, eventsApiUrl: String) -> Client {
            Client(environmentKey: environmentKey, apiUrl: apiUrl, eventsApiUrl: eventsApiUrl)
        }
        """

        XCTAssertEqual(findSteps(in: source), [
            Step(text: "Create the SDK client", function: "createClient"),
            Step(text: "Create the SDK client with events enabled", function: "createClientWithEvents"),
        ])
    }

    func testIgnoresFuncInDocumentationComments() {
        let source = """
        // When the application gets the environment flags
        /// Call func before returning, and see `func other()`.
        public func getEnvironmentFlags(_ client: Client) async throws -> [SpecFlag] {
            try await client.getEnvironmentFlags()
        }
        """

        XCTAssertEqual(findSteps(in: source), [
            Step(text: "When the application gets the environment flags", function: "getEnvironmentFlags"),
        ])
    }

    func testIgnoresFuncInBlockComments() {
        let source = """
        // Create the SDK client
        /*
         A client for one environment.
         func notAStep() /* nested */ func stillNotAStep()
         */
        /* func inline() */ public func createClient(environmentKey: String, apiUrl: String) -> Client {
            Client(environmentKey: environmentKey, apiUrl: apiUrl)
        }
        """

        XCTAssertEqual(findSteps(in: source), [
            Step(text: "Create the SDK client", function: "createClient"),
        ])
    }

    func testIgnoresCommentsThatAreNotMarkers() {
        let source = """
        // Given a Flagsmith environment
        public func notAStep() {}

        // Helpers
        func asSpecFlags(_ flags: [Flag]) -> [SpecFlag] { [] }
        """

        XCTAssertEqual(findSteps(in: source), [])
    }

    func testGeneratesATableOfTheSteps() {
        let steps = [
            Step(text: #"When the application gets the flags for identity "{identifier}" with traits:"#, function: "getIdentityFlags"),
        ]

        XCTAssertEqual(generateTable(steps, from: "steps.swift"), #"""
        // Generated from steps.swift by StepsGenerator. Do not edit.

        import SDKSpecSteps

        let steps: [(text: String, step: Step)] = [
            ("When the application gets the flags for identity \"{identifier}\" with traits:", step(SDKSpecSteps.getIdentityFlags)),
        ]

        """#)
    }
}
