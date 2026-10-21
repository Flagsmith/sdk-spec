@events
Feature: Track an exposure event
  An SDK records which variant of a feature an identity was shown, as the reserved
  "$flag_exposure" event, so that an experiment can attribute later events to it.

  Background:
    Given a Flagsmith environment
    And the SDK sends events to Flagsmith

  Scenario: An exposure reaches Flagsmith as a $flag_exposure event
    When the application tracks an exposure of feature "banner" for identity "user_123" with value "control" and metadata:
      | key           | value |
      | experiment_id | 1     |
    Then Flagsmith has received the following events:
      | event          | feature | identifier | value     | metadata             |
      | $flag_exposure | banner  | user_123   | "control" | {"experiment_id": 1} |
