@events
Feature: Flush events and close the client
  An application flushes events, or closes the client, so that its events are not lost when it
  stops. Neither ever fails the application.

  Background:
    Given a Flagsmith environment
    And the SDK sends events to Flagsmith

  Scenario: Flushing returns once the events are sent, retries included
    Given the events API fails the next requests with:
      | failure |
      | 503     |
    When the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    Then the SDK has sent the following events to the events API:
      | response | event    |
      | 503      | checkout |
      | 202      | checkout |
    And Flagsmith has received the following events:
      | event    | identifier | value |
      | checkout | user_123   | "42"  |

  Scenario: Closing the client sends the buffered events, retries included
    Given the events API fails the next requests with:
      | failure |
      | 503     |
    When the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application closes the client with a timeout of 5 seconds
    Then the SDK has sent the following events to the events API:
      | response | event    |
      | 503      | checkout |
      | 202      | checkout |
    And Flagsmith has received the following events:
      | event    | identifier | value |
      | checkout | user_123   | "42"  |

  Scenario: Closing the client returns within its timeout when the events API does not answer
    Given the events API fails the next requests with:
      | failure   |
      | ETIMEDOUT |
      | ETIMEDOUT |
      | ETIMEDOUT |
    When the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application closes the client with a timeout of 2 seconds
    Then the application waited less than 4 seconds
