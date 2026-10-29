@local-evaluation
Feature: Get environment flags with local evaluation
  A server-side SDK evaluates the flags for its environment against the environment document,
  serving the same flags Flagsmith would.

  Background:
    Given a Flagsmith environment
    And the SDK evaluates flags locally

  Scenario: Environment flags are disabled while a flag they depend on is disabled
    Given the environment has the following features:
      | feature      | enabled | value |
      | payments     | false   | null  |
      | checkout     | true    | "v2"  |
      | search       | true    | null  |
      | autocomplete | true    | 5     |
    And feature "checkout" depends on feature "payments"
    And feature "autocomplete" depends on feature "search"
    When the application gets the environment flags
    Then the application receives the following flags:
      | feature      | enabled | value |
      | payments     | false   | null  |
      | checkout     | false   | "v2"  |
      | search       | true    | null  |
      | autocomplete | true    | 5     |

  Scenario: Environment flags ignore segments that need an identity
    Given the environment has the following features:
      | feature | enabled | value   |
      | banner  | true    | "hello" |
    And a segment "premium_users" where trait "plan" equals "premium"
    And segment "premium_users" overrides feature "banner" with enabled false and value "hello premium user"
    When the application gets the environment flags
    Then the application receives the following flags:
      | feature | enabled | value   |
      | banner  | true    | "hello" |
