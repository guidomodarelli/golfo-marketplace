# Testing Rules — Java

- Use JUnit 5 and the assertion library the project already uses (for example AssertJ); name tests after the behavior they verify.
- Prefer slice tests (`@WebMvcTest`, `@DataJpaTest`) over `@SpringBootTest` when a single layer is under test.
- Run repository and SQL tests against a real database through Testcontainers or the project's test database, not an in-memory substitute with a different dialect.
- Use Mockito only at the boundaries the project owns (repositories, outbound clients); do not mock the JDK, the framework, or value objects.
- Test controllers through MockMvc or `WebTestClient` and assert status, headers, and body as the client sees them.
- Do not mock your own database layer in integration tests; see `Data` in `patterns-we-do-not-use.md`.
