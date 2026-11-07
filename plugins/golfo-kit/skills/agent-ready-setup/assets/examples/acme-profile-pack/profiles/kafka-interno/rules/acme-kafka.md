# Internal Kafka client

- Use `@acme/kafka` to produce and consume messages; do not create a Kafka client by hand.
- Declare every topic in the service configuration, never inline in the code.
