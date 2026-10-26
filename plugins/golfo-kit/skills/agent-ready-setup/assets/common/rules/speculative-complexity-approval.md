# Speculative Complexity Approval

Before adding complexity for a speculative case, such as a hypothetical edge case or a remote or unlikely race condition or security advantage, explain it to the user and get their approval. Do not silently widen the scope for theoretical robustness.

- Describe the concrete failure mode: what input, timing, or attacker action triggers it, and what breaks.
- Estimate its probability from the evidence you have (a reproduction, logs, a known exploit, usage patterns), and say when the estimate is a guess.
- State the complexity cost: added code, branches, dependencies, tests, and the maintenance or performance burden.
- Ask whether to add it. Until the user approves, implement the requested change without it and list the deferred hardening in your report, as an item of the list that `user-actions-first.md` defines.
- Avoid generic abstractions with a single implementation, configuration options "just in case", a second implementation left next to the old one, and backward compatibility for internal APIs nobody needs; see `Architecture and dependencies` in `patterns-we-do-not-use.md`.
- This rule does not cover failures that are confirmed or reproduced, or handling that an existing rule or contract of the project already requires: handle those as part of the task.
