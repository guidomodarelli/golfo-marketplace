---
name: installed-pwa-platform-quirks
description: "Diagnoses and fixes features that work in a browser tab but fail in the installed PWA (iPhone/iPad home-screen app added from Safari, Android installed app): download links (the a download attribute), navigator.share with files, window.open, clipboard, target=_blank and display-mode standalone gaps. Gates fallbacks on capability plus display mode, never on user agent, with the detection in a unit-tested pure helper. Use whenever a bug report says something does not work from the PWA, the installed app, the home-screen app or standalone mode, or a download, share or link works in Safari or Chrome but not in the installed app."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "web"
  tags: "pwa, ios, safari, standalone, web-share, download, display-mode, android"
  command: "/installed-pwa-platform-quirks"
---

# Installed PWA platform quirks

Use this when something works in the browser tab but fails in the installed app: an iPhone/iPad home-screen app added from Safari, or an Android installed app. A bug reported as "doesn't work from the PWA" almost always comes from a platform gap of the installed app's display mode. The code itself is usually fine. Ask, or infer from the report, which device and which browser installed the app: the fix differs.

## Procedure

1. **Pin down the environment**: OS, which browser installed the app (Safari vs Chrome on iOS, Chrome/Samsung on Android) and the manifest `display` mode. Only Safari can add a home-screen app on iOS, and that app runs in WebKit `standalone` with its own gaps.
2. **Find the feature in code** (`grep -rniE` for the visible label and the API: `download`, `window.open`, `clipboard`, `share`, `target="_blank"`), and check it against the quirks below.
3. **Gate the fallback on capability plus mode**, never on user agent: `navigator.standalone === true` is WebKit-only and true only inside an app added from Safari; `matchMedia('(display-mode: standalone)')` covers other platforms. Leave the normal path untouched in browser tabs.
4. **Put the detection in a pure helper** in `src/lib/` (input: a minimal navigator shape) so it can be unit-tested in a Node test env without a DOM. Test: standalone + capable → fallback; browser tab → normal; standalone without capability or `canShare` throwing → normal.
5. Say in the report that it was not tested on a real device, and give the exact manual check for the user.

## Quirks

- **`<a download>` does nothing in iOS standalone** (neither data: nor blob: URLs). Fallback: `navigator.share({ files: [file] })` when `navigator.canShare({ files: [file] })` is true. The share sheet offers "Save Image" and "Save to Files". Call `preventDefault()` on the link only when you take the share path.
- **`navigator.share` needs transient user activation**: iOS rejects a share started after an `await` in the click handler (`fetch(dataUrl)`, encoding). Build the `File` beforehand, for example when the image is generated, and call `share()` synchronously inside the handler. To convert a data URL synchronously, use `Uint8Array.from(atob(payload), (c) => c.codePointAt(0) ?? 0)` and then `new File([bytes], name, { type })`.
- **`AbortError` from `share()` means the user closed the sheet**: ignore it, and show an error only for other rejections.
