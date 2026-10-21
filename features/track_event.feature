@events
Feature: Track an event
  An SDK sends an application's tracking events to Flagsmith, so that an experiment can
  measure what the identities it exposed went on to do. Values reach Flagsmith as text,
  whatever type the application tracked them as.

  Background:
    Given a Flagsmith environment
    And the SDK sends events to Flagsmith

  Scenario: A tracked event reaches Flagsmith
    When the application tracks event "checkout_completed" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    Then Flagsmith has received the following events:
      | event              | identifier | value | metadata            |
      | checkout_completed | user_123   | "42"  | {"currency": "GBP"} |
