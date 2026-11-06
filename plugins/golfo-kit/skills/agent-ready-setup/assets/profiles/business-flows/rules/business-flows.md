# Business Flow Rules

A business flow is the sequence of steps a user goes through to reach a business outcome, such as a checkout, an onboarding, or a claim. These rules apply to every client: web, Android, or any other. They do not apply to copy or styling changes that leave the steps untouched.

- Before adding a flow or changing its steps, follow `.agents/skills/business-flow-design/SKILL.md`, so the flow has a written definition.
- Keep steps, transitions, and outcomes in one definition. A screen reports what happened and the flow decides what comes next; if each screen picks the next one, nobody can see the whole flow or change it safely.
- Name every way a flow can end (completed, abandoned, failed, blocked) and what the user sees in each. A failure with no next step is a dead end, and a defect.
- Enforce eligibility, business rules, and progress on the server when they matter beyond one session or device. A check in the client only shapes the UX, because the client can be stale or modified.
- Make every step safe to enter from anywhere: a deep link, a shared URL, the back button, a reload, or a restored process. Check the step's prerequisites and send the user to the right step instead of assuming the previous one ran.
- Mark each irreversible step (a payment, a submission, a confirmation) and make it idempotent, so a retry or a double tap cannot run it twice. Define what back does after it, because going back must not repeat it.
- Keep the business definition identical across clients. Platform differences belong to presentation and navigation: web needs a URL per step and has to survive a reload; Android has to survive process death and handle system back.
- Keep users already inside a flow working when it changes. They can finish on the version they started, or move to a step that still exists. Old app versions stay installed for months, so a client that receives a step it does not know needs a safe fallback.
- Emit an event when a user enters, completes, or leaves a step, with flow, step, and version identifiers and no personal data, so drop-off can be measured per step.
- Test the transitions, not only the happy path: each failure, resuming midway, entering directly, and going back after an irreversible step.
- Keep anything specific to an internal flow engine in a project rule under `.agents/rules/`, not in this file. Use the engine the project already has rather than adding a new one.
