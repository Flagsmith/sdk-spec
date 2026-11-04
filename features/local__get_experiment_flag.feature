@local-evaluation @events
Feature: Get an experiment flag with local evaluation
  A server-side SDK resolves a feature for an identity against the environment document, and
  records the exposure as it would with remote evaluation.

  Background:
    Given a Flagsmith environment
    And the SDK evaluates flags locally
    And the SDK sends events to Flagsmith

  Scenario: An identity in a running experiment is exposed to the variant it was served
    Given the environment has the following features:
      | feature  | enabled | value     |
      | checkout | true    | "control" |
    And a running experiment on feature "checkout" serving variant "treatment" with value "new checkout"
    When the application gets the experiment flag "checkout" for identity "user_123" with traits:
      | trait | value     |
      | plan  | "premium" |
    Then the application receives the following flags:
      | feature  | enabled | value          |
      | checkout | true    | "new checkout" |
    And Flagsmith has received the following events:
      | event          | feature  | identifier | value       | traits              |
      | $flag_exposure | checkout | user_123   | "treatment" | {"plan": "premium"} |

  Scenario: An identity a running experiment does not enroll is not exposed
    Given the environment has the following features:
      | feature  | enabled | value     |
      | checkout | true    | "control" |
    And a running experiment on feature "checkout" serving variant "treatment" with value "new checkout" to 0% of identities
    When the application gets the experiment flag "checkout" for identity "user_123" with traits:
      | trait | value     |
      | plan  | "premium" |
    Then the application receives the following flags:
      | feature  | enabled | value     |
      | checkout | true    | "control" |
    And Flagsmith has received no events

  Scenario: An identity outside a running experiment is not exposed
    Given the environment has the following features:
      | feature  | enabled | value     |
      | checkout | true    | "control" |
    When the application gets the experiment flag "checkout" for identity "user_123" with traits:
      | trait | value     |
      | plan  | "premium" |
    Then the application receives the following flags:
      | feature  | enabled | value     |
      | checkout | true    | "control" |
    And Flagsmith has received no events
