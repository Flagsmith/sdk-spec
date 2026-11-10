@events
Feature: Flush events and close the client
  An application flushes events, or closes the client, so that its events are not lost when it
  stops. Neither ever fails the application.

  - Flushing sends the buffered events, and returns once they are sent, retries included.
  - Closing flushes, and returns within the timeout the application gives it.

  Background:
    Given a Flagsmith environment
    And the SDK sends events to Flagsmith

  Scenario: Flushing returns once the events are sent, retries included
    Given the events API responds to the next requests with:
      | response |
      | 503      |
    When the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    Then the SDK has sent the following requests to the events API:
      | response         | events       |
      | 503              | ["checkout"] |
      | "passed through" | ["checkout"] |
    And Flagsmith has received the following events:
      | event    | identifier | value |
      | checkout | user_123   | "42"  |

  Scenario: Closing the client sends the buffered events, retries included
    Given the events API responds to the next requests with:
      | response |
      | 503      |
    When the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application closes the client with a timeout of 5 seconds
    Then the SDK has sent the following requests to the events API:
      | response         | events       |
      | 503              | ["checkout"] |
      | "passed through" | ["checkout"] |
    And Flagsmith has received the following events:
      | event    | identifier | value |
      | checkout | user_123   | "42"  |

  Scenario: Closing the client returns within its timeout when the events API does not answer
    Given the events API responds to the next requests with:
      | response      |
      | "no response" |
      | "no response" |
      | "no response" |
    When the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application closes the client with a timeout of 2 seconds
    Then the application waited less than 3 seconds
