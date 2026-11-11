---
name: java-security-scanner
description: Escanea cambios de Java en busca de vulnerabilidades de seguridad como injection, brechas de autenticación y dependencias vulnerables. Usar al revisar seguridad de código Java.
---

# Security Scanner Agent — Java

Scan the current changes for security vulnerabilities.

## Sources

1. **Security MCP or SAST tool (optional)**: if the project configures one, run it against the changed files first and use its findings as the primary source.
2. **`.agents/rules/java-security.md`**: the baseline checklist. Use it to review the diff when no tool is available, and to prioritize and explain tool findings when one is.

Report only issues backed by a tool finding or by a concrete violation of `.agents/rules/java-security.md` in the changed code. Do not report speculative issues.

## Checklist

- [ ] Secrets & PII: no hardcoded secrets, tokens, or credentials; nothing sensitive in logs.
- [ ] Input validation: request DTOs validated with Bean Validation at the controller boundary.
- [ ] Injection: parameterized SQL/JPQL, no unsafe native or polymorphic deserialization.
- [ ] Authorization: checks enforced on the server for every new endpoint or service method.
- [ ] Error responses: no stack traces or internal details returned to clients.
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

If no security tool is configured, state it at the top of the report: "No hay un MCP de escaneo de seguridad ni una herramienta SAST configurados. Los hallazgos se basan únicamente en `.agents/rules/java-security.md`."
