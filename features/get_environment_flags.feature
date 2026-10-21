@core
Feature: Get environment flags
  An SDK fetches the flags for its environment from Flagsmith
  and exposes each flag's name, enabled state and value to the application.

  Background:
    Given a Flagsmith environment

  Scenario: Environment flags are returned as configured in Flagsmith
    Given the environment has the following features:
      | feature   | enabled | value     |
      | banner    | true    | "welcome" |
      | max_items | false   | 42        |
      | dark_mode | true    | true      |
      | beta      | true    | null      |
    And an SDK client for the environment
    When the application gets the environment flags
    Then the application receives the following flags:
      | feature   | enabled | value     |
      | banner    | true    | "welcome" |
      | max_items | false   | 42        |
      | dark_mode | true    | true      |
      | beta      | true    | null      |
