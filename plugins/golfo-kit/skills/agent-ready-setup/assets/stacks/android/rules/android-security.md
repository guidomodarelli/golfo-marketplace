# Security Rules — Android

- Treat everything in the APK as public: `BuildConfig` fields, resources, assets, and code can all be extracted, and R8 does not hide them. Keep secrets on a server the app authenticates against. Keep build-time keys in `local.properties` or the CI secret store, never in the repository.
- Store tokens and other sensitive data encrypted with a key held in the Android Keystore; never in plain `SharedPreferences`, external storage, or logs. Exclude that data from backups (`android:dataExtractionRules`, `android:fullBackupContent`).
- Use HTTPS only and keep cleartext traffic disabled in the network security config. Never ship a custom `TrustManager` or `HostnameVerifier` that accepts everything, not even behind a debug flag that could reach a release build.
- Set `android:exported="false"` on every component that other apps do not need. Treat every `Intent` extra, deep link, and `ContentProvider` argument as untrusted input: validate it before using it to navigate, load a URL, or open a file.
- Use explicit intents for internal communication, and `FLAG_IMMUTABLE` on a `PendingIntent` unless it must be mutable.
- Keep JavaScript disabled in a `WebView` unless the screen needs it, load only allowlisted origins, disable file access, and expose `addJavascriptInterface` only to content you control.
- Use parameterized queries (Room `@Query` parameters, selection arguments); never concatenate user input into SQL.
- Share files through `FileProvider`, never `file://` URIs, and validate entry names when extracting an archive so a path cannot escape the target directory.
- Request only the runtime permissions a feature needs, at the moment it needs them, and keep the feature usable or clearly degraded when the user denies them.
- Enforce authorization on the server. A check in the app only shapes the UI, because a modified client can skip it.
- Keep release builds non-debuggable and with R8 enabled. Show safe error messages to users, and log failures as `error-handling.md` › `Diagnosable failures` defines; never log tokens, personal data, or full request bodies.
- Scan dependencies when they change (for example with Dependabot or OWASP Dependency-Check, whichever the project uses) and resolve reported vulnerabilities.
