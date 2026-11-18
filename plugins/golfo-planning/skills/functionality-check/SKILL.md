---
name: functionality-check
description: "Determine whether capabilities from a spec, draft, mockup, issue, or feature description are implemented and reachable in the current codebase, even when UI, UX, naming, or structure differ. Use when asked what is missing, whether a feature exists, what still needs to be built, or how a specification maps to existing behavior. Produce evidence-backed coverage, distinguish complete, partial, missing, unverified, ambiguous, and unreachable behavior, and identify exact gaps without inferring implementation from isolated types, endpoints, or services."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "spec-driven-development"
  tags: "spec, coverage, gap-analysis, reachability, evidence"
  command: "/functionality-check"
---

# Functionality Check

Compare requested behavior with observable, reachable behavior in the codebase. Treat UI and UX differences as irrelevant only when they do not change an explicit requirement, safety gate, accessibility need, validation rule, or business outcome.

## Core rules

- Functionality is not a component name, file path, or visual pattern.
- Static capability is not necessarily user-available functionality.
- An endpoint, payload type, service method, component, or test alone does not prove an end-to-end flow exists.
- Lack of evidence means `Unverified`, not `Missing`.
- Declare `Implemented` only when every mandatory acceptance criterion is covered through a reachable path.
- Preserve spec intent: confirmation steps, permissions, accessibility behavior, validation, and error prevention may be functional requirements.

## Workflow

### 1. Establish scope and evidence baseline

Identify:

- specification source and version
- repository, branch, and relevant diff or working tree state
- target users, roles, sites, tenants, environments, and feature flags
- whether runtime verification is possible

State material assumptions. Ask a focused question only when ambiguity would change a verdict; otherwise classify the item as `Ambiguous` and explain both interpretations.

### 2. Convert the spec into atomic acceptance criteria

Describe observable behaviors, not proposed components. Split each capability into independently verifiable criteria:

- data displayed and its source
- user action and entry point
- preconditions, permissions, role, site, and tenant scope
- accepted inputs and validation
- state transitions and persistence
- API or service interaction
- business rules and side effects
- loading, empty, success, and controlled failure behavior when required
- single-item versus bulk semantics
- confirmation, cancellation, undo, or other safety gates
- accessibility or UX behavior when explicitly required for successful use

Example: replace “checkbox list for bulk assignment” with “select multiple representatives, submit one assignment for all selected IDs, prevent empty submission, show controlled success/failure feedback, and persist the assignment.”

Mark each criterion as mandatory, optional, or ambiguous. Never lower a mandatory criterion because an alternative implementation looks similar.

### 3. Search for functional equivalents

Search by domain entities, actions, payload fields, routes, permissions, flags, and business outcomes rather than component names.

Inspect relevant layers:

1. user entry point or public caller
2. component, command, controller, or route handler
3. state, hook, use case, or orchestration
4. API route, service, adapter, or client
5. persistence or external side effect when applicable
6. response handling and observable result
7. relevant tests, flags, routing, authorization, and configuration

Follow imports and call sites in both directions. Confirm code is connected, reachable, and enabled for target scope. Check for dead code, missing route registration, disconnected handlers, permanently disabled flags, unsupported sites, and callers that only exercise a narrower payload.

Do not infer:

- frontend trigger from backend support
- working flow from a type or interface
- reachability from component existence
- persistence from local state changes
- bulk behavior from an array-shaped payload
- authorization from hidden UI controls
- runtime correctness from compilation or isolated unit tests

### 4. Build an end-to-end evidence chain

For each criterion, trace the shortest relevant chain:

`entry point -> handler/state -> API/service -> result/side effect`

Attach concrete evidence using repository-relative `file:line` references and symbol names. Distinguish:

- static evidence: code path exists
- test evidence: behavior has automated coverage
- runtime evidence: behavior was executed successfully

Do not invent missing links. Record them as gaps.

### 5. Validate functional security conditions

When capability reads or mutates protected data, verify conditions required for correct behavior:

- authentication and server-side authorization
- role, permission, ownership, tenant, and site scope
- validated and bounded inputs
- absence of client-only enforcement for protected actions
- safe handling of user-controlled rendered content when relevant

Do not turn this check into a full security audit. Treat missing required access control or scope enforcement as a functional gap because the capability is not correctly implemented for intended users. Avoid exposing secrets, tokens, cookies, authorization headers, or complete PII in evidence.

### 6. Verify proportionally

Prefer evidence strength in this order:

1. relevant runtime or integration execution
2. existing behavioral tests
3. complete static call-path analysis
4. isolated declarations or partial code

Run relevant existing tests or validation commands when feasible. Do not add or modify production code or tests during a check unless the user requests implementation. If execution is unavailable, state the limitation and keep confidence proportional to static evidence.

### 7. Classify each capability

| Status | Rule |
|---|---|
| ✅ Implemented | Reachable end-to-end flow covers every mandatory criterion for target scope |
| ⚠️ Partial | Reachable flow exists, but at least one mandatory criterion or layer is incomplete |
| ❌ Missing | Sufficient repository evidence confirms no implementation or equivalent flow exists |
| ❓ Unverified | Available evidence cannot confirm presence or absence |
| 🚫 Unreachable | Relevant code exists but target user or caller cannot execute it because wiring, routing, configuration, flag, or scope blocks it |
| ◻️ Ambiguous | Specification supports materially different interpretations that produce different verdicts |

Status applies to whole capability. List criterion-level results when mixed coverage explains a partial verdict.

Confidence is separate from status:

- High: complete reachable chain plus behavioral or runtime evidence
- Medium: complete static chain without runtime verification
- Low: incomplete static evidence; normally use `Unverified`

### 8. Report auditable results

Start with counts by status. Then report gaps and uncertain items first. Include implemented items in a compact coverage table so readers can audit what was considered; omit that table only when the user explicitly requests missing items only.

Use this shape:

| Capability | Status | Evidence | Exact gap | Confidence |
|---|---|---|---|---|
| Filter by presence status | ✅ Implemented | `path/file.tsx:42` `PresenceFilters`; `path/hook.ts:18` `usePresenceFilters` | — | Medium |
| Bulk assign process | ⚠️ Partial | `path/service.ts:71` accepts multiple IDs; caller sends one ID | Multi-selection entry point and bulk feedback | High |

For every non-implemented status, explain:

- covered portion
- exact missing or blocked criterion
- evidence supporting verdict
- smallest product-level capability still needed, without prescribing UI unless required

For `Unverified`, state what evidence or execution would resolve uncertainty. For `Ambiguous`, state interpretations and focused question.

## Anti-patterns

- Literal file, path, or component-name matching
- Equating visual difference with functionality gap
- Equating endpoint or service existence with user availability
- Treating type definitions as implementation evidence
- Declaring absence after searching only one naming variant or layer
- Ignoring route wiring, feature flags, permissions, sites, tenants, or dead code
- Ignoring required validation, errors, persistence, or side effects
- Calling a destructive direct action equivalent to a required confirmation flow
- Reporting verdicts without file/symbol evidence
- Hiding covered items by default, which prevents audit of false positives
- Using `Depends on intent` instead of `Ambiguous` plus explicit interpretations

## Examples

### Equivalent presentation

Spec: “Segmented control with All/Inside/Outside to filter by presence status.”

Repo: reachable dropdown sends equivalent status values and updates displayed results.

Verdict: `✅ Implemented` if all required values and target scope match. Different control does not create a gap.

### Partial bulk capability

Spec: “Select multiple representatives and assign area/process in one action.”

Repo: service accepts `representativeIds`, but reachable UI always sends `[representativeId]` and provides no multi-selection.

Verdict: `⚠️ Partial`. Static backend capability exists; bulk user flow does not.

### Unreachable implementation

Spec: “Managers can export the filtered report.”

Repo: export component and service exist, but route never renders the component or feature flag is disabled for all target sites.

Verdict: `🚫 Unreachable`.

### Ambiguous safety gate

Spec: “Scan QR, review changes, then confirm or skip each representative.”

Repo: scan applies changes immediately.

Verdict: `◻️ Ambiguous` only if spec does not establish whether review is mandatory. If review prevents unintended mutation or is explicit acceptance criteria, verdict is `⚠️ Partial`; direct apply does not satisfy confirmation behavior.
