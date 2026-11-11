# Testing Rules — Android

- Put tests that do not need a device in `src/test` (local JVM) and keep `src/androidTest` for what really needs one: real UI, framework behavior, or the database on a device. Name tests after the behavior they verify.
- Use the test framework and assertion library the project already uses; run the local suite with `./gradlew test` and the device suite with `./gradlew connectedAndroidTest`.
- Test ViewModels by asserting the UI state they expose, with `runTest` and an injected test dispatcher; never use `Thread.sleep`.
- Prefer fakes at the boundaries the project owns (repositories, data sources, outbound clients). Do not mock the Android framework, Kotlin coroutines, or value objects; use Robolectric or a device test when framework behavior matters.
- Test Compose UI through its semantics (`onNodeWithText`, `onNodeWithContentDescription`), and add a `testTag` only when no user-visible property identifies the node. Wait with `waitUntil` or an idling resource, not with a fixed delay.
- Test Room queries against a real in-memory Room database, and every schema change with `MigrationTestHelper`, so a migration that loses data fails before release.
- Do not mock your own database layer in integration tests; see `Data` in `patterns-we-do-not-use.md`.
