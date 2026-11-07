---
name: acme-kafka-consumer
description: Adds a Kafka consumer to a Node service with the internal client. Use when a service must read a new topic.
---

# Acme Kafka consumer

1. Declare the topic in the service configuration.
2. Create the handler with `@acme/kafka` and make it idempotent.
3. Add a test that replays the same message twice.
