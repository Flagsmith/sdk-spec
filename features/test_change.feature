@core
Feature: Test change
  A minimal SDK step, used to check how the spec and its SDKs handle a newly added step.

  Background:
    Given a Flagsmith environment

  Scenario: The SDK answers a test change
    When the application calls testChange
    Then the SDK returns "testChange"
