# Flipper (flipper-server) protocol notes

These notes describe the last published npm version, 0.273.0, which is what `npx flipper-server`
runs. The repo is archived. On HEAD, `flipper-server-core` was merged into `desktop/flipper-server`
and `flipper-frontend-core` into `desktop/flipper-ui`. The SDK side lives in `xplat/Flipper/FlipperClient.cpp`.

## Transport
- The URL is `ws://localhost:52342/?token=<JWT>` (default port 52342, changed with `--port`, upgrade path `/`). Instead of the query parameter you can send the `x-access-token` header.
- The token is read from `~/.flipper/certs/auth.token`. It is an RS256 JWT valid for 21 days, so re-read it on reconnect. Setting the server env var `SKIP_TOKEN_VERIFICATION` disables the check.
- HEAD, which is unpublished, uses cookie `flipper_auth` plus loopback and Host-header checks instead.
- `flipper-server-client`'s `createFlipperServer(host, port, tokenProvider, onState)` needs a global WebSocket. On Node versions without one, use `createFlipperServerWithSocket(new ReconnectingWebSocket(urlFn, [], {WebSocket: ws}), ...)`.
- In that client the exec timeout uses `setInterval` and never clears it after it fires, so it leaks a timer on each timed-out exec.

## Envelopes
- Client to server: `{event:'exec', payload:{id, command, args:[]}}`.
- Server to client: `exec-response {id, data}`, `exec-response-error {id, data: string}`, `server-event {event, data}` and `error {message}`.
- `server-event` is broadcast to every WS client.

## Commands and events
- Commands: `device-list`, `client-list`, `client-request(clientId, payload)` (fire and forget), `client-request-response(clientId, payload)` (returns `{success}` or `{error:{message, stacktrace, name}}`), plus `device-take-screenshot`, `device-shell-exec` and `get-config`.
- Events: `device-connected`, `device-disconnected`, `device-log {serial, entry:{date, type, message, pid, tid, tag}}` (logcat starts automatically when the device connects), `client-connected`, `client-disconnected {id}`, `client-message {id, message: JSON string}` and `client-setup-error`.
- The clientId has the form `escape(app)#os#device#device_id`.

## App protocol (payload inside client-request)
- `getPlugins` and `getBackgroundPlugins` return `{plugins:[...]}`.
- `init` and `deinit` take `{plugin}` and carry no id. `init` is idempotent.
- `execute` takes `{api, method, params}` and fails with `ConnectionNotFound` if the plugin was not initialised.
- `isMethodSupported` returns `{isSupported}`.
- In the app-to-desktop direction the app sends `execute` pushes, `refreshPlugins` and `{error}`.

## Hazards when sharing the app with the web UI
- The server keys pending responses by `id` per app connection, shared across all WS clients, and the UI counts from 0. Use ids from 2^40 or higher; the SDK parses the id as int64.
- A `deinit` from the UI disconnects the plugin for everyone. Send `init` before each `execute` and re-init periodically.
- On `init`, `BufferingFlipperPlugin` replays its buffer, so dedupe by request id.
- The server accepts app connections only while at least one WS client is connected, and exits after 5 h with no clients. With no UI open, your client must do the handshake itself: `getPlugins`, then `getBackgroundPlugins`, then `init`.

## Plugin payloads
- **Network** (background plugin):
  - `newRequest {id, timestamp, method, url, headers:[{key, value}], data: base64}`.
  - `newResponse {id, timestamp, status, reason, headers, data, isMock, insights}`.
  - `partialResponse` messages arrive as chunks `{id, totalChunks, index, data}`, in no guaranteed order.
  - To read a body: base64-decode it, then inflate it according to `Content-Encoding` (gzip or br). If inflating fails with "incorrect header check", the body was already inflated.
- **Databases**:
  - `databaseList` returns `[{id, name, tables}]`.
  - `execute {databaseId, value: sql}` returns `{type: select|insert|update_delete, columns, values, insertedId, affectedCount}`.
  - Also available: `getTableData`, `getTableStructure` and `getTableInfo`.
- **Preferences**:
  - `getAllSharedPreferences`, `setSharedPreference {sharedPreferencesName, preferenceName, preferenceValue}` and `deleteSharedPreference`.
  - Change pushes arrive as the event `sharedPreferencesChange`.
- **ui-debugger** (push):
  - Events: `init {rootId}`, `metadataUpdate {attributeMetadata}`, `subtreeUpdate {txId, rootId, nodes: ClientNode[]}`.
  - Node `attributes` are keyed by metadataId, so values such as text can only be read once you resolve them through `metadataUpdate`. Keep the latest frame.
  - The legacy `Inspector` plugin is pull-based instead (`getRoot`, `getNodes`). Confirm which one the app has via `getPlugins`.
  - Android SDK details (`plugins/uidebugger/descriptors`): each frame carries all nodes (replace, don't merge); `bounds` are relative to the parent (sum ancestors for screen coords); `inlineAttributes.id` is the resource id name; `hiddenAttributes.invisible = true` when not VISIBLE; `attributes` are sections keyed by the namespace metadataId (e.g. `TextView`) whose `fields` hold `text`; `runInBackground()` is false, so the web UI deinits it when the user switches tabs.

## Verifying against a real server (no device needed)
- `npx -y flipper-server@0.273.0 --no-open --port 52342` works on Windows without an Android SDK (it logs an ADB error and keeps serving). It creates `~/.flipper/certs/auth.token` on first start, and `device-list` returns the host desktop device.
- That is enough to verify auth (good and bad token → 401), the envelopes, `device-list`/`client-list` and reconnection. To test reconnection, kill the server's node PID (find it with `netstat -ano | grep :52342`), not the shell wrapper the background tool started.
- MCP SDK `StdioClientTransport` does NOT inherit the parent env (only a safe default set). Pass `env: {...process.env}` in smoke scripts, and tell users to put FLIPPER_* vars in the MCP client config.
- On this Windows host the pnpm `node` shim fails in background processes with "stdin is not a tty"; call `node.exe` directly there.
- Commit at least one real recording under `fixtures/recordings/` and assert it exists in the replay test: a root-relative ignore (`/recordings/`) is needed, because `recordings/` also ignores `fixtures/recordings/`.

## Real device on Windows (verified with SDK 0.273.0, Android 14 emulator)
- Setup that works: winget `Microsoft.OpenJDK.17`; cmdline-tools unzipped to `%LOCALAPPDATA%\Android\Sdk\cmdline-tools\latest` (the default path flipper-server uses for adb); `sdkmanager platform-tools emulator platforms;android-34 build-tools;34.0.0 system-images;android-34;google_apis;x86_64`; `emulator -avd X -no-window -gpu swiftshader_indirect` (WHPX). AGP 8.5.2 + Gradle 8.9 + Kotlin 1.9.24 build Flipper 0.273.0 fine.
- **OpenSSL is the blocker**: flipper-server signs the app CSR with `openssl` from PATH. Git for Windows ships OpenSSL 3.5, which fails with `X509_REQ_verify_ex:unsupported version`; the app logs "Certificate exchange complete with required files: 0" in a loop and never shows in `client-list`. Fix: FireDaemon OpenSSL 1.1.1w zip first in the server's PATH plus `OPENSSL_CONF=<dir>/ssl/openssl.cnf` (without it: "Can't open ...FireDaemon SSL/openssl.cnf").
- ui-debugger on Android sends `frameScan` (frameTime = epoch ms), a few hundred ms after a change: wait for a view instead of reading right after an action. Namespace sections in `attributes` are `{fields}` WITHOUT `type`; `visibility` is an enum attribute in the View section.
- `SharedPreferencesFlipperPlugin(context)` only lists files existing at startup; pass `SharedPreferencesDescriptor`s.
- `FlipperObject.getArray(key)` never returns null (missing key -> empty array); use `contains(key)` for optional params.
- A ThreadLocal trace id is lost when the dispatcher `post`s to the main thread: restore it inside the posted runnable.
- To test the web-UI `deinit` hazard for real, open a second WS client with the token and `exec client-request [clientId, {method:'deinit', params:{plugin}}]`.
