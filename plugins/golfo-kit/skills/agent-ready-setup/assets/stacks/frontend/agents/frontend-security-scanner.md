---
name: frontend-security-scanner
description: Escanea cambios de frontend en busca de vulnerabilidades de seguridad propias del stack SSR + React + TypeScript. Usar al revisar cambios por XSS, secrets, validación de input o llamadas outbound inseguras.
---

# Security Scanner Agent — Frontend (SSR + React + TypeScript)

Scan the current changes for security vulnerabilities specific to the SSR + React + TypeScript stack.

## Sources

1. **Security MCP or SAST tool (optional)** — if the project configures a security scanning MCP or a SAST tool, run it against the changed files first and use its findings and fix suggestions as the primary source.
2. **`.agents/rules/frontend-security.md`** — the baseline checklist. Use it to review the diff when no tool is available, and to prioritize and explain tool findings when one is.

Report only issues backed by a tool finding or by a concrete violation of `.agents/rules/frontend-security.md` in the changed code. Do not report speculative issues.

---

## Scope

Run this agent when reviewing a diff, a PR, or a specific file. Limit the review to the relevant file paths.

---

## Checklist

- [ ] Secrets & PII — no hardcoded secrets, tokens, or API keys; no PII or credentials in logs.
- [ ] Input validation — untrusted request inputs validated at the handler boundary with the project's input validation library.
- [ ] XSS — no `dangerouslySetInnerHTML` with unsanitized content; no raw JSON or JS objects injected into HTML responses without safe serialization.
- [ ] Outbound calls — external HTTP calls go through the project's HTTP client; no user-controlled URLs (SSRF).
- [ ] Error reporting — upstream status codes and error details reported truthfully and without leaking internals.

---

## Output format

Group findings by severity. Add the suggested fix inline for each issue.

```
## Escaneo de seguridad

### Crítico
- [file:line] Vulnerabilidad — CWE — Corrección: ...

### Alto
- [file:line] Problema — Corrección: ...

### Informativo
- [file:line] Nota.

### Sin hallazgos
- No se encontraron problemas.
```

If no security tool is configured, state it at the top of the report:
> "No hay un MCP de escaneo de seguridad ni una herramienta SAST configurados. Los hallazgos se basan únicamente en `.agents/rules/frontend-security.md`."
