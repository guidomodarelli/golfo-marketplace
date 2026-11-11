# Coding Style Rules — Java

- Follow the formatter and static analysis the build already configures (for example Spotless, Checkstyle, or Error Prone); do not reformat unrelated code.
- Prefer constructor injection with `final` fields; do not use field injection (`@Autowired` on fields).
- Use immutable value types (`record`, `final` fields, unmodifiable collections) for DTOs and domain values.
- Return `Optional` instead of `null` from lookups; never use `Optional` for fields or parameters.
- Throw specific exceptions that carry context and the original cause; do not catch `Exception` or `Throwable` except at the boundary that maps errors to a response.
- Close resources with try-with-resources.
- Keep controllers thin: validate and map the request, delegate to a service, and map the result to the response DTO. Never return JPA entities from an API.
- Declare transaction boundaries (`@Transactional`) on service methods, not on controllers or repositories.
