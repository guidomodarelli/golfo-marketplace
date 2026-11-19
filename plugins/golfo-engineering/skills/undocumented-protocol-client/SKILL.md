---
name: undocumented-protocol-client
description: "Builds a client, MCP server or bridge for an internal, undocumented or unmaintained protocol by working it out from the source: sparse-clones the repo, compares it with the published package, reads both ends of every channel, finds shared-connection hazards (shared request ids, lifecycle commands, replayed buffers, push-only events), writes PROTOCOL.md before any code, records live frames as fixtures and validates end to end against the real peer. Use whenever someone asks to build an MCP server, client, bridge or integration that talks to another program's internal WebSocket or RPC protocol, reverse-engineer how a dev tool's UI talks to its server, or integrate with an archived or undocumented upstream."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "integration"
  tags: "protocol, reverse-engineering, mcp, websocket, integration, fixtures"
  command: "/undocumented-protocol-client"
---

# Building a client for an undocumented protocol

## When to Use

Use this skill when the protocol is internal, undocumented or unmaintained and you have to work it out from the source code. It applies to MCP servers, bridges or tools that talk to another program's internal
protocol, such as a dev-tool server whose UI talks to it over WebSocket. It matters most
when the upstream project is archived or no longer maintained. Order: research the source
and the published packages, write PROTOCOL.md, plan, and only then write code.

## Procedure

1. **Get the source cheaply.** Make a blobless sparse clone and add paths as you discover them:
   `git clone --depth 1 --filter=blob:none --sparse <repo> && git sparse-checkout set --no-cone '/dir/a/' '/dir/b/'`
   - Use `--no-cone` with leading-slash patterns when you mix files and dirs, because cone mode rejects file paths.
   - Run `git ls-tree -r --name-only HEAD <dir>` to find files before you add them. Monorepos move and merge packages, so the paths named in the brief may no longer exist.
2. **Pull the published artifacts as well:** `npm pack <pkg>@<latest> --silent && tar xzf` (or the matching command for your ecosystem). What the user actually runs, such as `npx <pkg>`, is the published version, and it can differ from the repo HEAD. Examples are auth schemes and argument signatures. **When the two differ, the published version decides**, and you note the HEAD difference as a future risk.
3. **Read both ends of every channel.** On the server side, read the socket handler, the auth/verify code and the command/event type map. On the client side, read the official UI client, which shows the handshake order and which methods it calls. If the protocol continues to a third party (for example the device SDK), read that end too, because it shows id types, idempotency and error names.
4. **Look for shared-connection hazards.** Your client is often just another consumer of a resource that the official UI also uses. Check:
   - Request-id maps shared between consumers. If they are shared, use a disjoint id range that fits the peer's integer type.
   - Lifecycle commands sent by one consumer that affect everyone (init/deinit, subscribe/unsubscribe). If they exist, re-assert state idempotently before each call and retry on the "not connected" error.
   - Buffers replayed on re-subscribe. If they exist, dedupe by event id.
   - Server behaviour that depends on how many clients are connected, such as accepting peers only while one is connected or shutting down when idle.
   - Push-only events. If the protocol pushes, buffer events from connect time, because anything missed is gone.
   - Whether the official client library works in your runtime (for example, does it need a global WebSocket in Node 18?), plus timer or leak bugs to wrap.
5. **Write PROTOCOL.md before any code.** Cover the transport (URL, port, auth token location and expiry), the message envelopes, the commands and events you will use with their payload shapes, the hazards from step 4 with their mitigations, and a section "to capture live" listing what the code cannot tell you.
6. **Propose how to capture the missing parts.** Prefer a `--record <file.jsonl>` mode in your own client that dumps every raw frame with a timestamp. It can be repeated, and it produces the fixtures for the mock-server integration test. Inspecting the WebSocket in browser DevTools is the fallback.
7. **Present the plan and stop** whenever the brief says no code before approval. Show the findings that change the brief, the hazards, the small verifiable steps and the open questions. In a chat gateway (Discord, Telegram) ask the questions in plain text with numbered options, because option buttons do not read well there. Keep the PROTOCOL.md draft in a scratch location and share it as a file until the repo location is agreed.
8. **After approval, implement in small verified steps**: transport + reconnection first, verified against the real server (good token, bad token, kill and relaunch the server) before any feature tools; then buffers/filters with unit tests; then a fake server that speaks the published envelopes and mirrors the peer SDK's handshake, driven through a real protocol client (e.g. MCP `InMemoryTransport`).
9. **Validate end to end against the real peer, not only the fake.** If the third party is an app/device, install the platform and build a minimal sample app that uses every plugin in scope; write a `scripts/live.*` scenario with explicit `CHECK` assertions (correlation ids, rendered text, state round trips) and a script that reproduces each shared-connection hazard (e.g. a second client sending `deinit`). Fixtures shaped from source code miss real-payload differences that only a capture reveals, so record the live session with `--record` and commit it as a replay fixture.
Pitfalls when fixing bugs found in review or live runs:
- Prove each regression test fails without the fix (`git stash push -- <prod files>`, run, `git stash pop`). Assert through existing observables (e.g. `emitter.listenerCount`), not a getter you add with the fix, because the old code returns `undefined` for the new getter and the test passes anyway.
- Re-run the live scenario after every fix batch; unit tests with fake payloads stay green while the real path regresses.

## Rules

- Pin exact versions of unmaintained dependencies, and pin the version the user actually runs.
- Don't trust package READMEs of internal packages, which are often just "TBD". The type definitions (`.d.ts`) of the published package are the contract.
- Re-read auth tokens from disk on every reconnect, because servers rotate them.
- When the user says "install and test whatever you need", install the full platform (JDK, SDK, emulator, a sample app) and verify for real instead of stopping at a blocker list; report the setup you installed.

## References

- `references/flipper.md` covers the Flipper desktop server protocol (WS envelopes, auth, app/plugin messages, shared-connection hazards, plugin payloads) plus the Windows emulator setup and real-payload quirks found on a device (OpenSSL 1.1.1 requirement, ui-debugger attribute shapes).
