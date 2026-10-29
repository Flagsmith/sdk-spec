@events
Feature: Get an experiment flag
  An SDK resolves a feature for an identity and records the exposure.

  Background:
    Given a Flagsmith environment
    And the SDK sends events to Flagsmith

  Scenario: An experiment flag is resolved for the identity, with its traits
    Given the environment has the following features:
      | feature | enabled | value   |
      | banner  | true    | "hello" |
    And a segment "premium_users" where trait "plan" equals "premium"
    And segment "premium_users" overrides feature "banner" with enabled true and value "hello premium user"
    When the application gets the experiment flag "banner" for identity "user_123" with traits:
      | trait | value     |
      | plan  | "premium" |
    Then the application receives the following flags:
      | feature | enabled | value                |
      | banner  | true    | "hello premium user" |
    And Flagsmith has identity "user_123" with the following traits:
      | trait | value     |
      | plan  | "premium" |

  Scenario: An identity in a running experiment is exposed to the variant it was served
    Given the environment has the following features:
      | feature | enabled | value     |
      | banner  | true    | "control" |
    And a running experiment on feature "banner" serving variant "treatment" with value "hello treatment"
    When the application gets the experiment flag "banner" for identity "user_123" with traits:
      | trait | value     |
      | plan  | "premium" |
    Then the application receives the following flags:
      | feature | enabled | value             |
      | banner  | true    | "hello treatment" |
    And Flagsmith has received the following events:
      | event          | feature | identifier | value       | traits              |
      | $flag_exposure | banner  | user_123   | "treatment" | {"plan": "premium"} |

  Scenario: An identity outside a running experiment is not exposed
    Given the environment has the following features:
      | feature | enabled | value   |
      | banner  | true    | "hello" |
    When the application gets the experiment flag "banner" for identity "user_123" with traits:
      | trait | value     |
      | plan  | "premium" |
    Then the application receives the following flags:
      | feature | enabled | value   |
      | banner  | true    | "hello" |
    And Flagsmith has received no events
