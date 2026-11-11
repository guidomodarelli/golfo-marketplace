---
name: android-security-scanner
description: Escanea cambios de Android en busca de vulnerabilidades de seguridad como secretos en el APK, componentes exportados, almacenamiento inseguro y dependencias vulnerables. Usar al revisar seguridad de código Android.
---

# Security Scanner Agent — Android

Scan the current changes for security vulnerabilities.

## Sources

1. **Security MCP or SAST tool (optional)**: if the project configures one, run it against the changed files first and use its findings as the primary source.
2. **`.agents/rules/android-security.md`**: the baseline checklist. Use it to review the diff when no tool is available, and to prioritize and explain tool findings when one is.

Report only issues backed by a tool finding or by a concrete violation of `.agents/rules/android-security.md` in the changed code. Do not report speculative issues.

## Checklist

- [ ] Secrets & PII: nothing sensitive in code, `BuildConfig`, resources, or logs.
- [ ] Storage: tokens and sensitive data encrypted with a Keystore key and excluded from backups.
- [ ] Network: HTTPS only, cleartext disabled, no permissive `TrustManager` or `HostnameVerifier`.
- [ ] Components: `android:exported` justified; intents, deep links, and provider arguments validated.
- [ ] WebView: JavaScript, origins, file access, and `addJavascriptInterface` restricted.
- [ ] Injection and files: parameterized queries, `FileProvider`, archive entry names validated.
- [ ] Release build: not debuggable, R8 enabled, permissions limited to what the feature needs.
- [ ] Dependencies: known vulnerabilities in new or updated dependencies.

## Output format

```
## Escaneo de seguridad

### Crítico
- [file:line] Vulnerabilidad — CWE — Corrección: ...

### Alto
- [file:line] Problema — Corrección: ...

### Sin hallazgos
- No se encontraron problemas.
```

If no security tool is configured, state it at the top of the report: "No hay un MCP de escaneo de seguridad ni una herramienta SAST configurados. Los hallazgos se basan únicamente en `.agents/rules/android-security.md`."
