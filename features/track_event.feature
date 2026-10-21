@events
Feature: Track an event
  An SDK sends an application's tracking events to Flagsmith.

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
