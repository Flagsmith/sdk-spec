@local-evaluation
Feature: Get identity flags with local evaluation
  A server-side SDK evaluates the flags for an identity against the environment document, using
  the identity's traits to evaluate segments, and tells the application why each flag has its
  value.

  Background:
    Given a Flagsmith environment
    And the SDK evaluates flags locally

  Scenario: Identity flags carry the segment override their traits matched
    Given the environment has the following features:
      | feature   | enabled | value   |
      | banner    | true    | "hello" |
      | max_items | true    | 10      |
    And a segment "premium_users" where trait "plan" equals "premium"
    And segment "premium_users" overrides feature "banner" with enabled true and value "hello premium user"
    When the application gets the flags for identity "user_123" with traits:
      | trait | value     |
      | plan  | "premium" |
    Then the application receives the following flags:
      | feature   | enabled | value                | reason                                   |
      | banner    | true    | "hello premium user" | "TARGETING_MATCH; segment=premium_users" |
      | max_items | true    | 10                   | "STATIC"                                 |

  Scenario: Identity flags fall back to the environment's when no segment matches
    Given the environment has the following features:
      | feature   | enabled | value   |
      | banner    | true    | "hello" |
      | max_items | true    | 10      |
    And a segment "premium_users" where trait "plan" equals "premium"
    And segment "premium_users" overrides feature "banner" with enabled true and value "hello premium user"
    When the application gets the flags for identity "user_123" with traits:
      | trait | value  |
      | plan  | "free" |
    Then the application receives the following flags:
      | feature   | enabled | value   | reason    |
      | banner    | true    | "hello" | "DEFAULT" |
      | max_items | true    | 10      | "STATIC"  |
