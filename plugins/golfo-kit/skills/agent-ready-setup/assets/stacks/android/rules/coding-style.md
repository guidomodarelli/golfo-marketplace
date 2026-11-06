# Coding Style Rules — Android

- Follow the formatter and static analysis the build already configures (for example ktlint, detekt, or Android Lint); do not reformat unrelated code or add a baseline to hide new lint errors.
- Write new code in Kotlin unless the module is still Java only.
- Keep business logic out of Activities, Fragments, and composables: they render state and forward events. A ViewModel exposes one immutable `StateFlow` of UI state and calls the data layer.
- Do not hold an Activity, Fragment, View, or their `Context` in a ViewModel, a singleton, or a static field; it leaks the whole screen. Use the application context when a context must outlive a screen.
- Keep state that must survive process death in `SavedStateHandle` or persistent storage; surviving a rotation is not enough.
- Launch coroutines from `viewModelScope` or `lifecycleScope`, never `GlobalScope`. Collect flows with lifecycle awareness (`collectAsStateWithLifecycle` or `repeatOnLifecycle`), so nothing keeps collecting in the background.
- Do blocking I/O off the main thread. Make suspending functions main-safe, and inject dispatchers instead of hardcoding `Dispatchers.IO`, so tests can control them. Rethrow `CancellationException` when catching broad exceptions.
- In Compose, hoist state to the caller and pass values and lambdas instead of a ViewModel. Keep composables free of side effects outside `LaunchedEffect` and its siblings, and give lazy list items a stable `key`.
- Put user-visible text in string resources, with plurals where needed, and give interactive elements without visible text a content description.
- Declare dependencies in the version catalog when the project has one, and raise `minSdk` or `targetSdk` only as a deliberate change.
