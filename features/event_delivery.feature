@events
Feature: Deliver events
  An SDK delivers events despite transient failures of the events API, without ever failing
  the application.

  - A request that times out, loses its connection, or gets a 408, 429, 500, 502, 503 or 504
    is retried: 3 attempts, backing off from 1 second, doubling, with full jitter. Any other
    status drops the batch.
  - Each request times out after 3 seconds.
  - A batch that still fails stays buffered, ahead of newer events, for the next flush, unless
    its last attempt got a 500: then it is dropped. The buffer holds 1000 events, and drops the
    oldest when full. One batch is in flight at a time.
  - A 401 or 403 drops the buffer, stops sending, and makes tracking a no-op.

  Background:
    Given a Flagsmith environment
    And the SDK sends events to Flagsmith

  Scenario: A batch is retried until the events API accepts it
    Given the events API responds to the next requests with:
      | response             |
      | 503                  |
      | "dropped connection" |
    When the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    Then the SDK has sent the following events to the events API:
      | response             | event    |
      | 503                  | checkout |
      | "dropped connection" | checkout |
      | "passed through"     | checkout |
    And Flagsmith has received the following events:
      | event    | identifier | value |
      | checkout | user_123   | "42"  |

  Scenario: A request the events API does not answer times out and is retried
    Given the events API responds to the next requests with:
      | response      |
      | "no response" |
    When the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    Then the application waited less than 7 seconds
    And the SDK has sent the following events to the events API:
      | response         | event    |
      | "no response"    | checkout |
      | "passed through" | checkout |
    And Flagsmith has received the following events:
      | event    | identifier | value |
      | checkout | user_123   | "42"  |

  Scenario: A batch that keeps failing is sent with the next flush, ahead of events tracked since
    Given the events API responds to the next requests with:
      | response |
      | 503      |
      | 503      |
      | 503      |
    When the application tracks event "add_to_cart" for identity "user_123" with value 1 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    And the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    Then the SDK has sent the following events to the events API:
      | response         | event       |
      | 503              | add_to_cart |
      | 503              | add_to_cart |
      | 503              | add_to_cart |
      | "passed through" | add_to_cart |
      | "passed through" | checkout    |
    And Flagsmith has received the following events:
      | event       | identifier | value |
      | add_to_cart | user_123   | "1"   |
      | checkout    | user_123   | "42"  |

  Scenario: A full buffer drops its oldest event
    Given the events API responds to the next requests with:
      | response |
      | 503      |
      | 503      |
      | 503      |
    When the application tracks events "event_1" to "event_1000" for identity "user_123"
    And the application flushes events
    And the application tracks events "event_1001" to "event_1001" for identity "user_123"
    And the application flushes events
    Then Flagsmith has received exactly events "event_2" to "event_1001"

  Scenario: A batch the events API rejects is dropped
    Given the events API responds to the next requests with:
      | response |
      | 400      |
    When the application tracks event "add_to_cart" for identity "user_123" with value 1 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    And the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    Then the SDK has sent the following events to the events API:
      | response         | event       |
      | 400              | add_to_cart |
      | "passed through" | checkout    |
    And Flagsmith has received the following events:
      | event    | identifier | value |
      | checkout | user_123   | "42"  |

  Scenario: A batch that keeps failing with a server error is dropped after its retries
    Given the events API responds to the next requests with:
      | response |
      | 500      |
      | 500      |
      | 500      |
    When the application tracks event "add_to_cart" for identity "user_123" with value 1 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    And the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    Then the SDK has sent the following events to the events API:
      | response         | event       |
      | 500              | add_to_cart |
      | 500              | add_to_cart |
      | 500              | add_to_cart |
      | "passed through" | checkout    |
    And Flagsmith has received the following events:
      | event    | identifier | value |
      | checkout | user_123   | "42"  |

  Scenario Outline: An events API refusing the environment key stops event tracking
    Given the events API responds to the next requests with:
      | response |
      | <status> |
    When the application tracks event "add_to_cart" for identity "user_123" with value 1 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    And the application tracks event "checkout" for identity "user_123" with value 42 and metadata:
      | key      | value |
      | currency | "GBP" |
    And the application flushes events
    Then the SDK has sent the following events to the events API:
      | response | event       |
      | <status> | add_to_cart |

    Examples:
      | status |
      | 401    |
      | 403    |
