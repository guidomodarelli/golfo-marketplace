---
name: review-security
description: Review security vulnerabilities in HEAD, uncommitted changes, changed code against develop/main/master, and agent instructions. Use when the user asks for a security review, Review Security HEAD, review including uncommitted changes, vulnerability review, AppSec review, or focused detection of SQL injection, XSS, command injection, path traversal, SSRF, auth bypass, authorization gaps, data exposure, secret leakage, insecure deserialization, unsafe redirects, CSRF, insecure crypto, dependency risk, prompt injection, tool injection, instruction hierarchy bypass, or untrusted content handling in AI skills and agents.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "code-review"
  tags: "code-review, security, appsec, prompt-injection"
  command: "/review-security"
---

# Review Security

## Goal

Review changed code for vulnerabilities that can expose the system, users, data, credentials, infrastructure, or agent/tool execution. Prioritize exploitable issues over generic hardening advice, and report findings in Spanish with precise file and line references.

## Shared Contract

Read [contrato compartido de review](../../references/review-contract.md) before reviewing. It defines scope presets and the non-interactive default, base selection, repository context (`REVIEW.md`, `CLAUDE.md`, `AGENTS.md`, PR intent, root cause), effort level by risk, adversarial verification, finding labels (`Important`, `Nit`, `Pre-existing`), bug class, and the summary format. This skill adds only its focus, severity guidance, and report fields. If the relative link does not resolve because the skill is installed as a symlink, resolve the skill directory's real path first (`realpath`/`Get-Item .Target`).

Security changes usually touch sensitive paths, so most of them use the **Deep** effort level from the contract. A `Pre-existing` vulnerability with `P0` or `P1` severity is still blocking.

## Review Approach

A vulnerability exists where untrusted input reaches a sensitive sink without a control, so orient the review around the security boundaries the change touches: request input, auth/authz, database query, template/rendering, shell/process execution, filesystem, network call, secrets/config, dependency, logging/telemetry, AI prompt, skill, agent instruction, or tool invocation.

- Start from the diff and widen to surrounding code as far as needed to trace untrusted input from source to sink.
- A finding is solid when you can name the attacker-controlled input, the vulnerable sink, the missing control, and the impact; concrete exploit paths are more useful than speculative concerns. When exploitability depends on deployment, permissions, or upstream validation, state that assumption.
- Count tests as evidence only when they exercise behavior at the security boundary; snapshots and import-only tests say nothing about exploitability.

## Focus Areas

### Injection

Look for:

- SQL, NoSQL, LDAP, XPath, ORM, or query-builder injection from string interpolation or unsafe dynamic clauses.
- XSS from unescaped HTML, unsafe markdown rendering, template injection, DOM sinks, unsafe URL handling, or bypassed sanitization.
- Command injection from shell execution, process arguments composed from user input, or unsafe environment variables.
- Path traversal and file inclusion from untrusted paths, filenames, archive extraction, or download/upload handling.
- SSRF or open redirect from untrusted URLs, redirects, callbacks, webhooks, proxies, or fetch targets.
- Header, log, CSV, formula, or response-splitting injection in generated output.

### Auth, Authorization, And Data Exposure

Look for:

- Missing authentication, auth bypass, confused identity, trusting client-provided user IDs, or relying on UI-only checks.
- Missing object-level, tenant-level, role-level, site-level, or scope-level authorization.
- Insecure direct object references where changed code fetches or mutates resources without ownership checks.
- Sensitive data returned, logged, cached, embedded in HTML, included in errors, exposed to analytics, or sent to third parties.
- Secrets, tokens, API keys, cookies, authorization headers, session IDs, or credentials committed, logged, or exposed in config.
- CSRF, CORS, cookie, redirect, or session changes that weaken browser security.

### AI, Skills, And Agent Instructions

Look for:

- Prompt injection paths where untrusted content is treated as instructions for an AI model, agent, or tool executor.
- Skill or agent instructions that tell the model to obey page content, repository files, external documents, tool output, or user data above system/developer/user intent.
- Missing separation between trusted instructions and untrusted retrieved content.
- Tool invocation based on untrusted model output without validation, allowlisting, confirmation, or least privilege.
- Instructions that encourage exposing secrets, hidden prompts, credentials, internal paths, private data, or tool outputs.
- Unsafe autonomous behavior such as executing commands, modifying files, making network calls, merging, or publishing data from untrusted prompt content, or without a human gate where the change is high risk.

### Crypto, Dependencies, And Platform Controls

Look for:

- Weak randomness, hashing, encryption modes, key handling, token generation, signature validation, or certificate checks.
- New dependencies or version changes that expand attack surface, run install scripts, parse untrusted input, or handle auth/crypto/networking.
- Disabled validation, lint, sandbox, CSP, CSRF, schema checks, TLS verification, or permission controls.
- Security-sensitive defaults changed from deny-by-default to allow-by-default.

## Severity Guidance

- `P0`: Direct unauthenticated compromise, credential exposure, remote code execution, broad data breach, or agent/tool takeover.
- `P1`: Auth bypass, cross-tenant/user data access, stored XSS, exploitable injection, secret leak, SSRF to sensitive networks, or high-impact prompt/tool injection.
- `P2`: Reflected XSS, missing authorization on narrower scope, sensitive logging, unsafe redirects, weak validation, or exploitable issue requiring specific privileges.
- `P3`: Defense-in-depth gap or low-impact issue with a credible abuse path and clear fix.

## Report Fields

Besides the shared fields, each finding includes:

- Attacker-controlled input or untrusted source.
- Vulnerable sink or trust boundary.
- Concrete impact.
- Why the changed code introduced or exposed the issue.
- A remediation direction such as parameterized queries, output encoding, schema validation, authorization checks, allowlists, secret redaction, or isolating untrusted AI context.

When there are no findings, the residual risk also mentions unknown upstream validation or dependencies not scanned.

## Boundaries

- Do not report generic security best practices without a plausible exploit path.
- Do not assume middleware, gateways, or platform controls exist unless the repository shows them or the user provided that context.
- Do not reveal secret values in the response. Refer to secret names, locations, or patterns without copying credentials.
- Do not provide step-by-step exploit instructions beyond what is needed to prove impact and guide remediation.
