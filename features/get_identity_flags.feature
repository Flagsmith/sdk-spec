@core
Feature: Get identity flags with traits
  An SDK fetches the flags for an identity from Flagsmith, sending the
  identity's traits so that Flagsmith persists them and uses them to
  evaluate segments.

  Background:
    Given a Flagsmith environment

  Scenario: Identity flags reflect segment overrides matched by traits
    Given the environment has the following features:
      | feature   | enabled | value   |
      | banner    | true    | "hello" |
      | max_items | true    | 10      |
    And a segment "premium_users" where trait "plan" equals "premium"
    And segment "premium_users" overrides feature "banner" with enabled true and value "hello premium user"
    And an SDK client for the environment
    When the application gets the flags for identity "user_123" with traits:
      | trait    | value     |
      | plan     | "premium" |
      | age      | 30        |
      | verified | true      |
    Then the application receives the following flags:
      | feature   | enabled | value                |
      | banner    | true    | "hello premium user" |
      | max_items | true    | 10                   |
    And Flagsmith has identity "user_123" with the following traits:
      | trait    | value     |
      | plan     | "premium" |
      | age      | 30        |
      | verified | true      |
