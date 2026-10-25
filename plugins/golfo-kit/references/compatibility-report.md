# Reporte de compatibilidad entre agentes: golfo-kit

<!-- Generado desde compatibility-report.json con `pnpm compat:render`. No editar a mano: editá el JSON y regenerá. -->

> Este reporte **describe** la compatibilidad verificada; no es la fuente de verdad para decidir qué ejecutar.
> Cada skill verifica en runtime las herramientas realmente disponibles en la sesión, según [`agent-capabilities.md`](agent-capabilities.md).

## A. Resumen ejecutivo

- **Fecha de auditoría:** 2026-10-23 (generado 2026-10-23T21:00:00Z).
- **Total de skills analizadas:** 43.
- **Funcionalidades deshabilitadas:** 0.
- **Adaptaciones implementadas:** 42; verificadas: 20.
- **Problemas críticos pendientes:** ninguno.
- **Funcionalidades que dejaron de estar deshabilitadas en esta revisión:** 0 (respecto de `1e937e0 (golfo-kit 0.11.0, PR #23, schema 1.1.0)`).

### Cambios de esta revisión

Dependencias implícitas de navegador de measured-performance-optimization, prevent-ssr-hydration-mismatches y ui-ux-flow-patterns: se agregó la funcionalidad opcional browser-verification por agente, con la fila «Verificar en un navegador» y la sección «Verificación en navegador por terminal» de agent-capabilities.md como fuente única. Codex usa el plugin Chrome (consola con tab.dev.logs y clics, verificado; su evaluate no expone performance, así que las métricas van por terminal) y Hermes usa browser_exec si arranca o Lighthouse, Chrome headless con log y Playwright por terminal (verificados; browser_exec falló 7 de 9 veces). En Claude Code el camino nativo (Claude in Chrome) queda unverified porque no estaba conectado; el fallback por terminal sí corrió. Ninguna funcionalidad se deshabilitó.

| Skill | Agente | Funcionalidad | Antes | Ahora | Resolución | Motivo |
|---|---|---|---|---|---|---|
| `measured-performance-optimization` | `codex` | `browser-verification` | `unverified` | `adapted` | `alternative` | El plugin Chrome reproduce el flujo en el Chrome real pero su evaluate no expone performance; Lighthouse y Playwright por terminal dan las mismas métricas de laboratorio. |
| `measured-performance-optimization` | `hermes` | `browser-verification` | `unverified` | `adapted` | `alternative` | Lighthouse, Chrome headless con log y Playwright por terminal, verificados en Hermes; browser_exec queda como primera opción si arranca. |
| `prevent-ssr-hydration-mismatches` | `codex` | `browser-verification` | `unverified` | `adapted` | `alternative` | El plugin Chrome captura la consola de la carga en el Chrome real con tab.dev.logs, igual que la consola de Claude in Chrome. |
| `prevent-ssr-hydration-mismatches` | `hermes` | `browser-verification` | `unverified` | `adapted` | `alternative` | Lighthouse, Chrome headless con log y Playwright por terminal, verificados en Hermes; browser_exec queda como primera opción si arranca. |
| `ui-ux-flow-patterns` | `codex` | `browser-verification` | `unverified` | `adapted` | `alternative` | El plugin Chrome hace clic y lee la consola en el Chrome real del usuario, igual que Claude in Chrome. |
| `ui-ux-flow-patterns` | `hermes` | `browser-verification` | `unverified` | `adapted` | `alternative` | Lighthouse, Chrome headless con log y Playwright por terminal, verificados en Hermes; browser_exec queda como primera opción si arranca. |

### Agentes evaluados

| Agente | Versión | Comando | Señales de detección |
|---|---|---|---|
| Claude Code (`claude_code`) | 2.1.309 | `claude --version` | CLAUDECODE=1; CLAUDE_CODE_ENTRYPOINT; CLAUDE_CODE_SESSION_ID; herramientas Skill/ToolSearch |
| Codex CLI (`codex`) | codex-cli 0.162.1 | `codex --version` | CODEX_SESSION_ID; CODEX_THREAD_ID; CODEX_VERSION; CODEX_CI=1 en codex exec; herramientas exec_command/apply_patch; plugins habilitados en $CODEX_HOME/config.toml (visualize, chrome, browser, computer-use, codex-app-tools) |
| Hermes Agent (`hermes`) | v0.22.4 (2026.9.24) | `hermes --version` | HERMES_AGENT=true; AI_AGENT=hermes-agent; HERMES_SESSION_ID; HERMES_HOME; herramientas terminal/clarify/delegate_task |

### Skills por estado y agente

| Estado | `claude_code` | `codex` | `hermes` |
|---|---|---|---|
| `compatible` | 4 | 0 | 0 |
| `adapted` | 0 | 1 | 1 |
| `partial` | 0 | 0 | 0 |
| `incompatible` | 0 | 0 | 0 |
| `unverified` | 39 | 42 | 42 |

### Regla de derivación del estado

El estado de una skill en un agente se deriva de sus funcionalidades, en este orden:

1. `unverified` si alguna funcionalidad **obligatoria** está `unverified`.
2. `incompatible` si todas las obligatorias están `disabled` y ninguna funcionalidad (obligatoria u opcional) está `enabled` o `adapted`.
3. `partial` si alguna funcionalidad (obligatoria u opcional) está `disabled`.
4. `adapted` si alguna funcionalidad está `adapted`.
5. `compatible` en otro caso (todas las obligatorias `enabled`).

Las funcionalidades opcionales `unverified` no cambian el estado global, pero se listan como pendientes de verificar.
Una funcionalidad solo puede estar `enabled` o `adapted` si la respalda al menos una prueba `eval` o `real_run` ejecutada **en ese agente** con resultado `passed`; las pruebas `simulated_eval` (otro agente simulando este), `bats` (scripts) y `static` (inspección) no alcanzan.
Toda funcionalidad `disabled` tiene una entrada en el registro de incompatibilidades con ID `INC-<skill>--<agente>--<funcionalidad>`.

La **resolución** de cada funcionalidad dice cómo se entrega en ese agente, independientemente de cuánto se verificó: `native` (la misma funcionalidad que el original), `alternative` (un mecanismo equivalente con otra implementación) o `disabled` (sin solución directa ni alternativa viable).
Una funcionalidad `disabled` lista las alternativas investigadas y ninguna es viable; una `alternative` lista al menos una alternativa viable.

## B. Matriz global

| Skill | `claude_code` | `codex` | `hermes` |
|---|---|---|---|
| `agent-ready-setup` | `unverified` | `unverified` | `unverified` |
| `async-operation-error-handling` | `unverified` | `unverified` | `unverified` |
| `codex-autofix-loop` | `unverified` | `unverified` | `unverified` |
| `codex-comment-closeout` | `compatible` | `unverified` | `unverified` |
| `constants-refactor` | `unverified` | `unverified` | `unverified` |
| `create-issue` | `unverified` | `unverified` | `unverified` |
| `enforce-jsdoc-tsdoc` | `unverified` | `unverified` | `unverified` |
| `error-observability-diagnostics` | `unverified` | `unverified` | `unverified` |
| `feature-branch-pr` | `unverified` | `unverified` | `unverified` |
| `fix-in-ephemeral-clone` | `compatible` | `unverified` | `unverified` |
| `fix-tests-intelligently` | `unverified` | `unverified` | `unverified` |
| `functionality-check` | `unverified` | `unverified` | `unverified` |
| `generate-commit-messages` | `unverified` | `unverified` | `unverified` |
| `improve-spec` | `unverified` | `unverified` | `unverified` |
| `inline-thread-autofix` | `unverified` | `unverified` | `unverified` |
| `measured-performance-optimization` | `unverified` | `unverified` | `unverified` |
| `mobile-first-responsive-layout` | `unverified` | `unverified` | `unverified` |
| `mock-first-testing-design` | `unverified` | `unverified` | `unverified` |
| `nextjs-route-ui-boundaries` | `unverified` | `unverified` | `unverified` |
| `node-runtime-debugging` | `unverified` | `unverified` | `unverified` |
| `optimistic-action-mutations` | `unverified` | `unverified` | `unverified` |
| `pr-description-template` | `compatible` | `unverified` | `unverified` |
| `pr-inline-comment-template` | `unverified` | `unverified` | `unverified` |
| `prevent-ssr-hydration-mismatches` | `unverified` | `unverified` | `unverified` |
| `react-data-fetching-best-practices` | `unverified` | `unverified` | `unverified` |
| `react-render-performance-patterns` | `unverified` | `unverified` | `unverified` |
| `refactor-modularize-code` | `unverified` | `unverified` | `unverified` |
| `refactor-ssr-data-fetching` | `unverified` | `unverified` | `unverified` |
| `review-fix-loop` | `unverified` | `unverified` | `unverified` |
| `review-maintainability` | `unverified` | `unverified` | `unverified` |
| `review-performance` | `unverified` | `unverified` | `unverified` |
| `review-security` | `unverified` | `unverified` | `unverified` |
| `semantic-html-a11y` | `unverified` | `unverified` | `unverified` |
| `sibling-worktree` | `unverified` | `unverified` | `unverified` |
| `simplify-code` | `unverified` | `unverified` | `unverified` |
| `skill-optimizer` | `compatible` | `unverified` | `unverified` |
| `stacked-pr` | `unverified` | `unverified` | `unverified` |
| `test-best-practices` | `unverified` | `unverified` | `unverified` |
| `test-planning` | `unverified` | `unverified` | `unverified` |
| `typed-errors-refactor` | `unverified` | `unverified` | `unverified` |
| `ui-ux-flow-patterns` | `unverified` | `unverified` | `unverified` |
| `user-manual` | `unverified` | `unverified` | `unverified` |
| `widget-ui-proposals` | `unverified` | `adapted` | `adapted` |

## C. Análisis por skill

### `agent-ready-setup`

**Identificación**

- Nombre: Agent Ready Setup; versión: 1.5.0; SKILL.md: `plugins/golfo-kit/skills/agent-ready-setup/SKILL.md`.
- Propósito: Prepara la configuración multi-provider (Claude Code y Codex) de un repo: .claude/, .agents/, .codex/, AGENTS.md y hooks.
- Funcionalidades principales: detección de stack; bootstrap de assets; bloque gestionado de AGENTS.md; hooks y sync.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Rutas de instalación (~/.claude, $CODEX_HOME, CLAUDE_PLUGIN_ROOT, $HERMES_HOME) | path | sí | `claude_code`; `codex`; `hermes` |
| `bash`, `git`, `node`, `python` en PATH | command | sí | `claude_code`; `codex`; `hermes` |
| CLI `claude` (revisión de hooks) | command | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### agent-ready-setup / `claude_code`: `unverified`

Provider de destino soportado. No ejecutada en esta auditoría (las suites bats de los scripts pasan).

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `bootstrap-config` | sí | `unverified` | `native` | bootstrap.sh genera la configuración de Claude Code y Codex. | — | No ejecutada en Claude Code en esta auditoría. | Suites bats (prueba agent-ready-bats).; prueba `agent-ready-bats` |
| `provider-autodetect` | no | `unverified` | `native` | resolve-provider.sh por ruta. | — | No ejecutada en Claude Code en esta auditoría. | — |

#### agent-ready-setup / `codex`: `unverified`

Provider de destino soportado. No ejecutada en esta auditoría.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `bootstrap-config` | sí | `unverified` | `native` | bootstrap.sh genera la configuración de Claude Code y Codex. | — | No ejecutada en Codex CLI en esta auditoría. | Suites bats (prueba agent-ready-bats).; prueba `agent-ready-bats` |
| `provider-autodetect` | no | `unverified` | `native` | resolve-provider.sh por ruta. | — | No ejecutada en Codex CLI en esta auditoría. | — |

#### agent-ready-setup / `hermes`: `unverified`

Hermes no es provider de destino; desde su instalación, resolve-provider.sh elige el único CLI de provider presente o pide elegir si hay dos (verificado en Hermes).

- Capacidades faltantes: Inferencia de provider desde $HERMES_HOME; Generación de configuración para Hermes.
- Alternativas investigadas: reconocer $HERMES_HOME y usar el CLI presente (adoptado); Hermes como provider de destino (fuera de alcance).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `bootstrap-config` | sí | `unverified` | `native` | bootstrap.sh genera la configuración de Claude Code y Codex. | — | No ejecutada en Hermes Agent en esta auditoría. | Suites bats (prueba agent-ready-bats).; prueba `agent-ready-bats` |
| `provider-autodetect` | no | `adapted` | `alternative` | resolve-provider.sh reconoce $HERMES_HOME, ~/.hermes y %LOCALAPPDATA%\hermes; usa el único CLI de provider en PATH y, con dos, pide elegir (clarify). | AGENT_READY_SETUP_ACTIVE_PROVIDER elegido por el usuario. | Hermes no es provider de destino, pero desde su instalación el provider que hace el upgrade y la revisión es el CLI presente; con dos, decide el usuario. | Corrida real en Hermes; bats del resolver; prueba `hermes-real-resolve-provider`; prueba `resolve-provider-hermes-bats`; prueba `eval-sim-hermes-provider-choice` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `provider-autodetect` | Reconocer $HERMES_HOME y elegir el único CLI presente | corrida real + bats | sí | Determinista; no adivina cuando hay dos. |
| `provider-autodetect` | Agregar Hermes como provider de destino | SKILL.md (paridad de providers) | no | Fuera de alcance: no genera configuración de Hermes. |

**Implementación**

- Adaptaciones: Sección «Compatibilidad entre agentes»: Hermes como excepción explícita y override manual; resolve-provider.sh reconoce instalaciones de Hermes (incluido HERMES_HOME en formato Windows).
- Archivos modificados: `plugins/golfo-kit/skills/agent-ready-setup/SKILL.md`, `plugins/golfo-kit/skills/agent-ready-setup/scripts/resolve-provider.sh`, `plugins/golfo-kit/skills/agent-ready-setup/tests/bootstrap.bats`, `plugins/golfo-kit/skills/agent-ready-setup/evals/eval-config.json`.
- Fallback: Override manual del provider..
- Cambios de comportamiento respecto del original: Ninguno..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `agent-ready-bats` | `any` | bats | `bats plugins/golfo-kit/skills/agent-ready-setup/tests/merge-instructions.bats` | `passed` | Suite de merge de instrucciones (agnóstica de agente). |
| `hermes-real-resolve-provider` | `hermes` | real_run | `hermes chat -Q -q "<correr resolve-provider.sh --skill-dir $HERMES_HOME/plugins/golfo-kit/skills/agent-ready-setup con PATH completo y con solo codex>"` | `passed` | Con HERMES_HOME=C:\Users\guido\AppData\Local\hermes (formato Windows) y ambos CLIs: exit 1 'belongs to Hermes and both claude and codex are in PATH; ask the user …'. Con PATH reducido a codex: exit 0, stdout 'codex'. |
| `resolve-provider-hermes-bats` | `any` | bats | `bats -f 'resolve-provider' plugins/golfo-kit/skills/agent-ready-setup/tests/bootstrap.bats` | `passed` | 4 casos: un solo CLI → ese provider; ambos → error que pide elegir; ninguno → error; HERMES_HOME en formato Windows reconocido. |
| `eval-sim-hermes-provider-choice` | `hermes` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/agent-ready-setup --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: hermes-install-asks-provider-when-both-clis: pregunta con clarify y relanza con AGENT_READY_SETUP_ACTIVE_PROVIDER. |

Pendiente de verificar:

- Ejecutar bootstrap real desde los tres agentes.

### `async-operation-error-handling`

**Identificación**

- Nombre: Async Operation Error Handling; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/async-operation-error-handling/SKILL.md`.
- Propósito: Diseña, implementa y revisa manejo de errores en operaciones asíncronas distribuidas (batch, jobs, polling, retries, estados terminales).
- Funcionalidades principales: clasificación de fallos parciales y upstream; preservación de progreso y reintentos; traducción de errores a copy localizado.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### async-operation-error-handling / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### async-operation-error-handling / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### async-operation-error-handling / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `codex-autofix-loop`

**Identificación**

- Nombre: Codex auto-fix loop (local, vía Claude Code); versión: 1.4.0; SKILL.md: `plugins/golfo-kit/skills/codex-autofix-loop/SKILL.md`.
- Propósito: Opera el loop que auto-fixea los comentarios de Codex en un PR hasta converger y mergear con gates.
- Funcionalidades principales: escucha de eventos del PR; triage y fix en clones efímeros; closeout de hilos; dedup y topes de rondas; merge con gates de CI y review limpia; auto-cancelación.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Monitor | monitor | no | `claude_code` |
| CronCreate / CronList / CronDelete (/loop) | scheduler | no | `claude_code` |
| TaskStop | tool | no | `claude_code` |
| terminal(background, notify) + process wait/kill | monitor | no | `hermes` |
| Subagentes (Agent / spawn_agent / delegate_task) | subagent | no | `claude_code`; `codex`; `hermes` |
| PushNotification | tool | no | `claude_code` |
| `gh` y `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |
| fix-in-ephemeral-clone, codex-comment-closeout | skill | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### codex-autofix-loop / `claude_code`: `unverified`

Modo A, comportamiento original sin cambios. La elección del modo pasó un eval en Claude Code; el loop completo se verifica al operarlo sobre un PR real.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `mode-selection` | sí | `enabled` | `native` | Elige el modo A cuando están Monitor, CronCreate/List/Delete y TaskStop. | — | Con las herramientas presentes, conserva el comportamiento original. | Eval en Claude Code.; prueba `eval-claude-mode-a` |
| `pr-event-watch` | sí | `enabled` | `native` | `Monitor` del PR (paso 0 del prompt). | — | El Monitor del PR detectó y entregó los eventos del PR #22 y se rearmó al vencer. | Corrida real del loop en el PR #22.; prueba `claude-real-loop-pr22`; prueba `eval-claude-mode-a` |
| `backup-schedule` | no | `unverified` | `native` | Cron de sesión vía `/loop`. | — | CronCreate creó el job de respaldo, pero no se observó un disparo del cron durante la corrida porque los eventos del Monitor llegaron antes. | Job f5c08f73 creado.; prueba `claude-real-loop-pr22` |
| `fix-round` | sí | `enabled` | `native` | Triage, agrupación, fix, closeout y dedup (pasos 1 a 6). | — | Triage, inFlight, fix, closeout y dedup ejecutados sobre un hallazgo real. | Corrida real del loop en el PR #22.; prueba `claude-real-loop-pr22` |
| `parallel-subagents` | no | `enabled` | `native` | Subagentes `Agent` en background por grupo de archivo. | Fix en contexto, grupo por grupo. | Un subagente Agent en background resolvió el grupo y devolvió el sha. | Corrida real del loop en el PR #22.; prueba `claude-real-loop-pr22` |
| `merge-gates` | sí | `unverified` | `native` | Review limpia del head + GATE DE CI antes de cualquier merge. | — | No ejecutada en Claude Code en esta auditoría. | — |
| `round-caps` | sí | `unverified` | `native` | Topes de rondas y de rondas de solo tests persistidos. | — | No ejecutada en Claude Code en esta auditoría. | — |
| `auto-cancel` | sí | `unverified` | `native` | Borra el cron y detiene el Monitor. | — | No ejecutada en Claude Code en esta auditoría. | — |
| `notifications` | no | `unverified` | `native` | `PushNotification` de una línea. | Línea en el chat. | No ejecutada en Claude Code en esta auditoría. | — |

#### codex-autofix-loop / `codex`: `unverified`

Modo C: watcher en foreground dentro del turno que cubre la escucha del PR, el respaldo por timeout y el relanzado tras @codex review. Verificados la elección del modo y el watcher; la ronda completa no se ejecutó en Codex.

- Capacidades faltantes: Monitor; CronCreate; procesos en background con aviso.
- Alternativas investigadas: watcher en foreground con exec_command/write_stdin (adoptado); automatizaciones de la app codex_app (solo app, no verificadas); codex exec resume + cron del SO (solo a pedido); codex-autofix.yml en GitHub Actions (complemento).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `mode-selection` | sí | `enabled` | `native` | Elige el modo C (watcher en foreground dentro del turno); el modo D solo si el usuario pide una ronda o el shell no sostiene comandos largos. | — | Codex eligió el modo C con sus herramientas reales. | Corrida real en Codex.; codex-real-inturn-watcher: eligió el modo C; prueba `codex-real-mode-selection`; prueba `codex-real-inturn-watcher` |
| `pr-event-watch` | sí | `adapted` | `alternative` | Modo C: scripts/wait-for-pr-event.sh en foreground dentro del turno, ciclo por ciclo hasta MAX_INTURN_CYCLES (36). | Modo D (una ronda por invocación) si el usuario lo pide o el shell no sostiene comandos largos. | Sin Monitor, el mismo watcher acotado esperado dentro del turno detecta los eventos del PR; se pierde solo la supervisión después del turno. | Corrida real codex-real-inturn-watcher; watcher-bats; prueba `codex-real-inturn-watcher`; prueba `watcher-bats`; prueba `eval-sim-codex-inturn-watcher` |
| `backup-schedule` | no | `adapted` | `alternative` | El timeout del watcher (exit 3) dispara la vuelta que evalúa TTLs y reintentos de merge, igual que en el modo B. | Modo D: la próxima invocación evalúa los TTLs. | El timeout acotado cumple el rol del cron de respaldo mientras dura el turno. | Exit 3 observado en codex-real-inturn-watcher; prueba `codex-real-inturn-watcher` |
| `single-round` | no | `unverified` | `alternative` | Modo D: una vuelta del prompt sin pasos 0 y 7; termina indicando cómo relanzar. | — | Queda como modo opcional a pedido del usuario. | Eval simulado (no cuenta como evidencia en Codex).; prueba `eval-sim-codex-single-round`; prueba `eval-codex-provider`; prueba `eval-sim-codex-inturn-watcher` |
| `fix-round` | sí | `unverified` | `native` | Pasos 1 a 6 del prompt, igual que el original. | — | No ejecutada en Codex CLI en esta auditoría. | — |
| `parallel-subagents` | no | `unverified` | `alternative` | `collaboration.spawn_agent` + `wait_agent` esperando dentro del turno. | Fix en contexto, grupo por grupo. | Herramientas presentes en la sesión; no se ejecutaron. | — |
| `merge-gates` | sí | `unverified` | `native` | Mismos gates; con checks pendientes espera al ciclo siguiente del watcher (modo C) o a la próxima invocación (modo D). | — | Eval simulado aprobado; no ejecutado en Codex. | prueba `eval-sim-codex-merge-gates`; prueba `eval-sim-codex-inturn-watcher` |
| `round-caps` | sí | `unverified` | `native` | Topes persistidos entre invocaciones. | — | No ejecutada en Codex CLI en esta auditoría. | — |
| `auto-cancel` | sí | `unverified` | `alternative` | Exit 5 del watcher o GUARD: termina el turno; nada queda vivo. | — | No ejecutada en Codex CLI en esta auditoría. | — |
| `notifications` | no | `unverified` | `alternative` | Línea en el mensaje final. | — | No ejecutada en Codex CLI en esta auditoría. | — |
| `auto-relaunch` | no | `unverified` | `alternative` | Tras @codex review, el ciclo siguiente del watcher en foreground detecta la respuesta de Codex y sigue sin intervención. | Modo D: relanzar a mano o el workflow codex-autofix.yml. | El mecanismo es el mismo watcher verificado, pero no se observó una respuesta real de Codex disparando la siguiente iteración. | agent-modes.md, modo C; prueba `codex-real-inturn-watcher` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `pr-event-watch` | wait-for-pr-event.sh en foreground (exec_command + write_stdin) | corrida real en codex exec | sí | Exit 3 y 5 observados y manejados según el modo. |
| `pr-event-watch` | Automatizaciones de la app (codex_app, automation_update) | codex-app-tools 0.1.6: .mcp.json + server.mjs | no | Solo en la app de escritorio (herramientas servidas por CODEX_APP_TOOLS_PIPE_PATH); no disponibles en el CLI ni verificadas. |
| `pr-event-watch` | codex exec resume desde cron del SO / Task Scheduler | codex exec --help | no | Viable técnicamente pero crea un scheduler persistente fuera de la sesión; solo a pedido del usuario. |
| `pr-event-watch` | Workflow codex-autofix.yml (GitHub Actions) | SKILL.md | sí | Persistencia 24/7 fuera de la sesión; complemento, no reemplazo de la escucha local. |
| `backup-schedule` | Timeout del watcher como respaldo | corrida real | sí | Exit 3 observado. |
| `backup-schedule` | Automatizaciones de la app (codex_app) | codex-app-tools | no | Solo app de escritorio; no verificadas. |
| `single-round` | Modo D: una vuelta del prompt sin pasos 0 y 7; termina indicando cómo relanzar. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | Queda como modo opcional a pedido del usuario. |
| `parallel-subagents` | `collaboration.spawn_agent` + `wait_agent` esperando dentro del turno. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | Herramientas presentes en la sesión; no se ejecutaron. |
| `auto-cancel` | Exit 5 del watcher o GUARD: termina el turno; nada queda vivo. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Codex CLI en esta auditoría. |
| `notifications` | Línea en el mensaje final | agent-modes.md | sí | Siempre disponible. |
| `notifications` | notify de config.toml | $CODEX_HOME/config.toml | no | Se dispara al terminar cada turno, no a pedido de la skill. |
| `auto-relaunch` | Watcher en foreground dentro del turno | agent-modes.md | sí | Cubre la espera de la respuesta mientras dura el turno. |
| `auto-relaunch` | codex exec resume programado | codex exec --help | no | Scheduler persistente fuera de la sesión; solo a pedido. |
| `auto-relaunch` | handoff_thread / send_message_to_thread de la app | codex-app-tools/.mcp.json | no | Solo app de escritorio; no verificados. |

#### codex-autofix-loop / `hermes`: `unverified`

Modo B (watcher en background). El watcher y la elección del modo funcionaron en Hermes; el loop completo (fixes, closeout, merge) no se ejecutó.

- Capacidades faltantes: Monitor; CronCreate/CronList/CronDelete de sesión; TaskStop; PushNotification.
- Alternativas investigadas: terminal(background, notify) + process_manage (adoptado); cronjob_manage con repeat (descartado: sesión nueva sin contexto ni subagentes); hermes send para avisos (no aplica a sesiones CLI).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `mode-selection` | sí | `enabled` | `native` | Elige el modo B (watcher en background). | — | Hermes eligió el modo B con sus herramientas reales. | Corrida real en Hermes.; prueba `hermes-real-mode-selection` |
| `pr-event-watch` | sí | `adapted` | `alternative` | `scripts/wait-for-pr-event.sh` en background con aviso, rearmado hasta MAX_WATCH_CYCLES. | Modo C si falta alguna herramienta. | Reemplaza a Monitor con un proceso acotado y supervisado. | Watcher ejecutado en Hermes con aviso y wait.; Tests bats del watcher.; prueba `hermes-real-watcher`; prueba `watcher-bats` |
| `backup-schedule` | no | `adapted` | `alternative` | El timeout del watcher (exit 3) dispara la vuelta que evalúa TTLs y reintentos de merge. | — | cronjob_manage corre en sesiones nuevas sin acceso a subagentes ni al watcher, así que no puede reconciliar inFlight; se descartó. | Exit 3 observado en Hermes.; prueba `hermes-real-watcher` |
| `fix-round` | sí | `unverified` | `native` | Pasos 1 a 6 del prompt. | — | No ejecutada en Hermes Agent en esta auditoría. | — |
| `parallel-subagents` | no | `unverified` | `alternative` | `delegate_task` con `tasks[]`; los hijos mueren con la sesión. | Fix en contexto. | Herramienta presente; no ejecutada. | — |
| `merge-gates` | sí | `unverified` | `native` | Mismos gates. | — | No ejecutada en Hermes Agent en esta auditoría. | — |
| `round-caps` | sí | `unverified` | `native` | Topes persistidos. | — | No ejecutada en Hermes Agent en esta auditoría. | — |
| `auto-cancel` | sí | `unverified` | `alternative` | Mata el watcher vivo. | — | kill no se ejercitó en la prueba real (el watcher terminó por timeout). | — |
| `notifications` | no | `unverified` | `alternative` | Línea en el chat (en el gateway llega a Telegram); opcional hermes send --to <destino> desde el shell. | — | No ejecutada en Hermes Agent en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `pr-event-watch` | `scripts/wait-for-pr-event.sh` en background con aviso, rearmado hasta MAX_WATCH_CYCLES. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | Reemplaza a Monitor con un proceso acotado y supervisado. |
| `backup-schedule` | El timeout del watcher (exit 3) dispara la vuelta que evalúa TTLs y reintentos de merge. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | cronjob_manage corre en sesiones nuevas sin acceso a subagentes ni al watcher, así que no puede reconciliar inFlight; se descartó. |
| `parallel-subagents` | `delegate_task` con `tasks[]`; los hijos mueren con la sesión. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | Herramienta presente; no ejecutada. |
| `auto-cancel` | Mata el watcher vivo. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | kill no se ejercitó en la prueba real (el watcher terminó por timeout). |
| `notifications` | Mensaje en el chat del gateway | variables HERMES_SESSION_PLATFORM=telegram | sí | En el gateway el propio mensaje es el aviso. |
| `notifications` | hermes send --to telegram | hermes send --help y --list | sí | Envía sin agente; no se envió nada en la auditoría. |

**Implementación**

- Adaptaciones: Selección de modo por capacidades (A/B/C); Script portable `wait-for-pr-event.sh` con timeout, tope de polls y códigos de salida; Modo B para Hermes con rearmado acotado (MAX_WATCH_CYCLES); Modo C de una ronda por invocación; Casos de eval por agente; Modo C para Codex: wait-for-pr-event.sh en foreground dentro del turno con tope MAX_INTURN_CYCLES; la ronda única pasa a modo D.
- Archivos modificados: `plugins/golfo-kit/skills/codex-autofix-loop/SKILL.md`, `plugins/golfo-kit/skills/codex-autofix-loop/references/agent-modes.md`, `plugins/golfo-kit/skills/codex-autofix-loop/scripts/wait-for-pr-event.sh`, `plugins/golfo-kit/skills/codex-autofix-loop/tests/wait-for-pr-event.bats`, `plugins/golfo-kit/skills/codex-autofix-loop/evals/eval-config.json`.
- Fallback: Modo C: una ronda por invocación, sin esperas, con instrucciones para relanzar..
- Cambios de comportamiento respecto del original: Ninguno en Claude Code (modo A). En Hermes la espera usa el watcher y no hay cron; en Codex no hay escucha continua ni relanzado automático..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `watcher-bats` | `any` | bats | `bats plugins/golfo-kit/skills/codex-autofix-loop/tests/wait-for-pr-event.bats` | `passed` | 14/14: evento por head, comentario, review y checks (exit 0), tope de polls y timeout (exit 3), deadline respetado con gh lento, en el baseline y sin el ejecutable timeout (exit 3), GitHub caído (exit 4), PR cerrado (exit 5), argumentos inválidos (exit 2). |
| `eval-claude-mode-a` | `claude_code` | eval | `run-evals <copia con solo claude-with-monitor-keeps-original-mode> --provider claude` | `passed` | Con Monitor y cron en la sesión elige el modo A: Monitor como disparador y /loop como respaldo (3/3 aserciones). |
| `eval-sim-hermes-mode-b` | `hermes` | simulated_eval | `run-evals <copia con solo hermes-without-monitor-uses-background-watcher> --provider claude` | `passed` | Claude simulando una sesión Hermes: usa wait-for-pr-event.sh en background con aviso, tope de ciclos y kill; no planea Monitor ni CronCreate (6/6). No cuenta como evidencia en Hermes. |
| `eval-sim-codex-single-round` | `codex` | simulated_eval | `run-evals <copia con solo codex-runs-single-round-without-waiting> --provider claude` | `passed` | Claude simulando Codex: una ronda, sin esperar y con instrucciones para relanzar (4/4). No cuenta como evidencia en Codex. |
| `eval-sim-codex-merge-gates` | `codex` | simulated_eval | `run-evals <copia con solo codex-single-round-keeps-merge-gates> --provider claude` | `passed` | Claude simulando Codex: con CI pendiente no mergea ni espera y deja el merge para la próxima invocación (3/3). |
| `eval-codex-provider` | `codex` | eval | `run-evals <copia con los 4 casos nuevos> --provider codex` | `blocked` | Los 4 casos fallaron por infraestructura: `codex exec --sandbox read-only` en Windows no puede leer archivos («el acceso al archivo fue bloqueado por la política del entorno»; en la sonda directa, `CreateProcessAsUserW failed: 5 (Access is denied.)`). |
| `codex-real-mode-selection` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<leer SKILL.md y referencias; describir modo, herramientas y cierre sin tocar GitHub>"` | `passed` | Codex 0.162.1 leyó SKILL.md, agent-modes.md y agent-capabilities.md, eligió el modo C porque faltan Monitor/Cron/TaskStop y background con aviso, propuso collaboration.spawn_agent/wait_agent esperando dentro del turno, interrupt_agent para cancelar, notificación en el mensaje final y cierre con instrucción de relanzar. No ejecutó gh ni procesos. |
| `hermes-real-watcher` | `hermes` | real_run | `hermes chat -Q -q "<terminal(background=true, notify=true) sobre wait-for-pr-event.sh --pr 20 --poll-seconds 10 --timeout-seconds 40; process_manage wait timeout=120>"` | `passed` | Hermes 0.22.4 lanzó el watcher con mcp__terminal background=true notify=true (session_id proc_49b329b77739, notify_on_complete: true) y process_manage wait devolvió status exited, exit_code 3, stdout «TIMEOUT no event on PR #20 after 3 polls». Solo lecturas a GitHub. |
| `hermes-real-mode-selection` | `hermes` | real_run | `hermes chat -Q -q "<leer SKILL.md y referencias; describir modo y herramientas sin tocar GitHub>"` | `passed` | Hermes eligió el modo B (mcp__terminal background+notify, process_manage diferido), propuso delegate_task con tasks[], kill del watcher y delegate_task stop para cancelar, avisos en el chat, sin cronjob_manage; no mencionó invocar Monitor ni CronCreate. |
| `claude-real-loop-pr22` | `claude_code` | real_run | `Loop en modo A sobre el PR #22 (Monitor + CronCreate */3 + Agent + codex-comment-closeout)` | `passed` | Claude Code 2.1.309 operó el loop sobre el PR #22: el Monitor entregó 8 eventos (checks, comentario y review de Codex, head nuevo) y se rearmó al vencer; CronCreate creó el job f5c08f73 (*/3); el inline 4362278361 (P2) se clasificó como realista, se registró en inFlight y lo fixeó un subagente Agent con fix-in-ephemeral-clone (commit f0bd513, 14/14 bats); el closeout publicó 👍, reply con plantilla (4362346998) verificado y resolvió el hilo; la review 5631925162 se minimizó como RESOLVED; processed-22.json registró el id y el outcome fixed. |
| `codex-real-inturn-watcher` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<leer agent-modes.md, elegir modo y correr solo wait-for-pr-event.sh en foreground sobre #21 y #22>"` | `passed` | Codex eligió el modo C por tener exec_command + write_stdin, corrió el watcher en foreground siguiendo la salida con write_stdin: PR #21 → exit 3 'TIMEOUT no event on PR #21 after 3 polls' (dispararía la iteración de respaldo), PR #22 → exit 5 'PR_NOT_OPEN MERGED' (auto-cancelar). No ejecutó iteraciones, comentarios ni merges. |
| `eval-sim-codex-inturn-watcher` | `codex` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/codex-autofix-loop --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: codex-in-turn-foreground-watcher, codex-runs-single-round-without-waiting y codex-single-round-keeps-merge-gates (modos C y D). |

Pendiente de verificar:

- Claude Code: merge con gates, topes de rondas, auto-cancelación y disparo del cron de respaldo (ocurren después de congelar este reporte en el PR #22).
- Codex: una ronda completa con fixes, closeout y merge gates.
- Hermes: loop completo con delegate_task, kill del watcher y merge gates.
- Codex: ronda completa en modo C sobre un PR de prueba, con respuesta real de Codex disparando la iteración siguiente.

### `codex-comment-closeout`

**Identificación**

- Nombre: Cierre de comentarios de Codex; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/codex-comment-closeout/SKILL.md`.
- Propósito: Plantilla y checklist para responder, reaccionar y resolver comentarios de Codex en un PR.
- Funcionalidades principales: variantes Resuelto / Sin cambios / No pude aplicar; reacción y resolución del hilo; verificación del body publicado.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `gh` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### codex-comment-closeout / `claude_code`: `compatible`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `enabled` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Closeout real con plantilla, reacción, resolución y verificación. | Closeout del inline 4362278361.; prueba `claude-real-closeout-pr22` |

#### codex-comment-closeout / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### codex-comment-closeout / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `claude-real-closeout-pr22` | `claude_code` | real_run | `Closeout del inline 4362278361 del PR #22` | `passed` | Reacción +1, reply ✅ Resuelto con sha corto f0bd513 verificado contra el head remoto, pie de la plantilla y body releído; hilo resuelto (isResolved: true). |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `constants-refactor`

**Identificación**

- Nombre: Constants Refactor; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/constants-refactor/SKILL.md`.
- Propósito: Analiza y refactoriza constantes, literales funcionales y contratos cross-layer.
- Funcionalidades principales: detección de hardcodes; movimiento a constants/; validación del refactor.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### constants-refactor / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### constants-refactor / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### constants-refactor / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `create-issue`

**Identificación**

- Nombre: Create Issue; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/create-issue/SKILL.md`.
- Propósito: Genera la descripción estructurada de una issue a partir de la explicación del usuario.
- Funcionalidades principales: estructura de issue de planificación.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### create-issue / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### create-issue / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### create-issue / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `enforce-jsdoc-tsdoc`

**Identificación**

- Nombre: enforce-jsdoc-tsdoc; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/enforce-jsdoc-tsdoc/SKILL.md`.
- Propósito: Agrega o actualiza JSDoc/TSDoc donde aporta a la lectura.
- Funcionalidades principales: reglas de ubicación y tags; omisión de documentación redundante.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### enforce-jsdoc-tsdoc / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### enforce-jsdoc-tsdoc / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### enforce-jsdoc-tsdoc / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `error-observability-diagnostics`

**Identificación**

- Nombre: Error Observability Diagnostics; versión: sin versión declarada; SKILL.md: `plugins/golfo-kit/skills/error-observability-diagnostics/SKILL.md`.
- Propósito: Diseña y revisa trazabilidad operativa de errores (logs estructurados, sinks, correlación).
- Funcionalidades principales: detección de sinks reales; feedback con reporte; redacción segura.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### error-observability-diagnostics / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### error-observability-diagnostics / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### error-observability-diagnostics / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `feature-branch-pr`

**Identificación**

- Nombre: Feature Branch + Commit + Push + PR; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/feature-branch-pr/SKILL.md`.
- Propósito: Lleva los cambios de la rama a un PR: rama feature/*, commit, push, PR y resumen.
- Funcionalidades principales: creación de rama; commit y push; apertura del PR con pr-description-template.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |
| `gh` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### feature-branch-pr / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### feature-branch-pr / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### feature-branch-pr / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `fix-in-ephemeral-clone`

**Identificación**

- Nombre: Fix Issue Efímero Clone; versión: 1.1.0; SKILL.md: `plugins/golfo-kit/skills/fix-in-ephemeral-clone/SKILL.md`.
- Propósito: Ejecuta fixes en un clone efímero depth-1 y publica la rama autorizada sin hacer closeout.
- Funcionalidades principales: clone efímero; fix y validación; commit y push con reintegración; cleanup.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` y `gh` en PATH | command | sí | `claude_code`; `codex`; `hermes` |
| Subagente con handle (modo background) | subagent | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### fix-in-ephemeral-clone / `claude_code`: `compatible`

Clone, validación y push usan solo git y shell; el modo background depende de un subagente con handle. No ejecutada en Claude Code en esta auditoría.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `in-context-fix` | sí | `enabled` | `native` | Workflow completo en el contexto actual. | — | Fix real en clone efímero con push verificado y cleanup. | Commit f0bd513.; prueba `claude-real-fix-pr22` |
| `background-mode` | no | `unverified` | `native` | `Agent` con handle. | in_context o HANDOFF_EXECUTOR_MISSING. | No ejecutada en Claude Code en esta auditoría. | — |

#### fix-in-ephemeral-clone / `codex`: `unverified`

Clone, validación y push usan solo git y shell; el modo background depende de un subagente con handle. No ejecutada en Codex CLI en esta auditoría.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: spawn_agent.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `in-context-fix` | sí | `unverified` | `native` | Workflow completo en el contexto actual. | — | No ejecutada en Codex CLI en esta auditoría. | — |
| `background-mode` | no | `unverified` | `alternative` | `spawn_agent` + `wait_agent`. | in_context o HANDOFF_EXECUTOR_MISSING. | No ejecutada en Codex CLI en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `background-mode` | `spawn_agent` + `wait_agent`. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Codex CLI en esta auditoría. |

#### fix-in-ephemeral-clone / `hermes`: `unverified`

Clone, validación y push usan solo git y shell; el modo background depende de un subagente con handle. No ejecutada en Hermes Agent en esta auditoría.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: delegate_task.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `in-context-fix` | sí | `unverified` | `native` | Workflow completo en el contexto actual. | — | No ejecutada en Hermes Agent en esta auditoría. | — |
| `background-mode` | no | `unverified` | `alternative` | `delegate_task`. | in_context o HANDOFF_EXECUTOR_MISSING. | No ejecutada en Hermes Agent en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `background-mode` | `delegate_task`. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Hermes Agent en esta auditoría. |

**Implementación**

- Adaptaciones: Sección «Compatibilidad entre agentes» para el modo background.
- Archivos modificados: `plugins/golfo-kit/skills/fix-in-ephemeral-clone/SKILL.md`.
- Fallback: Modo in_context..
- Cambios de comportamiento respecto del original: Ninguno..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `claude-real-fix-pr22` | `claude_code` | real_run | `Subagente del loop con fix-in-ephemeral-clone en modo in_context sobre el PR #22` | `passed` | Clone efímero en un tempdir, fix del watcher, 14/14 bats, commit f0bd513 pusheado (verificado con git ls-remote y la API del PR), clone borrado y sin closeout en GitHub. |

Pendiente de verificar:

- Ejecutar un fix real en Claude Code.
- Ejecutar un fix real en Codex CLI.
- Ejecutar un fix real en Hermes Agent.

### `fix-tests-intelligently`

**Identificación**

- Nombre: fix-tests-intelligently; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/fix-tests-intelligently/SKILL.md`.
- Propósito: Diagnostica tests rotos o flaky sin ajustar aserciones a ciegas.
- Funcionalidades principales: decidir si el fix va en el test o en la implementación.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### fix-tests-intelligently / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### fix-tests-intelligently / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### fix-tests-intelligently / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `functionality-check`

**Identificación**

- Nombre: Functionality Check; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/functionality-check/SKILL.md`.
- Propósito: Determina si las capacidades de una spec están implementadas y alcanzables en el código.
- Funcionalidades principales: cobertura con evidencia; gaps exactos.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### functionality-check / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### functionality-check / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### functionality-check / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `generate-commit-messages`

**Identificación**

- Nombre: Generate Commit Messages; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/generate-commit-messages/SKILL.md`.
- Propósito: Reúne contexto, redacta y aplica el mensaje de commit.
- Funcionalidades principales: análisis del diff; commit.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### generate-commit-messages / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### generate-commit-messages / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### generate-commit-messages / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `improve-spec`

**Identificación**

- Nombre: Improve Spec; versión: 1.1.0; SKILL.md: `plugins/golfo-kit/skills/improve-spec/SKILL.md`.
- Propósito: Mejora specs de docs/specs/ resolviendo ambigüedades, completando secciones y dejando tasks ejecutables.
- Funcionalidades principales: selección del spec; preguntas de ambigüedad; exploración del codebase; aprobación y guardado.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Herramienta de preguntas (AskUserQuestion / clarify / request_user_input en modo Plan) | tool | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### improve-spec / `claude_code`: `unverified`

La pregunta en texto se verificó en una sesión headless sin AskUserQuestion; la ruta nativa con AskUserQuestion y el flujo completo no se ejecutaron.

- Capacidades faltantes: AskUserQuestion en sesiones headless (claude -p, sdk-cli).
- Alternativas investigadas: AskUserQuestion (sesiones interactivas).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-user-choices` | sí | `adapted` | `alternative` | Fallback en texto en sesión headless; AskUserQuestion en sesiones interactivas. | Pregunta en texto con opciones numeradas y detenerse. | Verificado el fallback; la ruta nativa no. | Ver pruebas.; prueba `eval-claude-no-question-tool` |
| `spec-improvement` | sí | `unverified` | `native` | Pasos 2 a 8: análisis, exploración, generación y guardado. | — | No ejecutada en Claude Code en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ask-user-choices` | Fallback en texto en sesión headless; AskUserQuestion en sesiones interactivas. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | Verificado el fallback; la ruta nativa no. |

#### improve-spec / `codex`: `unverified`

Pregunta en texto y se detiene (request_user_input solo existe en modo Plan); verificado en una corrida real. El flujo completo no se ejecutó.

- Capacidades faltantes: request_user_input fuera del modo Plan.
- Alternativas investigadas: request_user_input en modo Plan.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-user-choices` | sí | `adapted` | `alternative` | Pregunta en texto y detenerse; request_user_input solo en modo Plan. | Pregunta en texto con opciones numeradas y detenerse. | Verificado en Codex real. | Ver pruebas.; prueba `codex-real-ask-fallback` |
| `spec-improvement` | sí | `unverified` | `native` | Pasos 2 a 8: análisis, exploración, generación y guardado. | — | No ejecutada en Codex CLI en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ask-user-choices` | Pregunta en texto y detenerse; request_user_input solo en modo Plan. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | Verificado en Codex real. |

#### improve-spec / `hermes`: `unverified`

Usa clarify; si devuelve undelivered (por ejemplo en `hermes chat -Q -q`) pregunta en texto y se detiene. Verificado en una corrida real; el flujo completo no se ejecutó.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: clarify (máx. 4 choices).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-user-choices` | sí | `adapted` | `alternative` | `clarify`; fallback en texto ante undelivered/timed_out/cancelled. | Pregunta en texto con opciones numeradas y detenerse. | Verificado en Hermes real. | Ver pruebas.; prueba `hermes-real-clarify-fallback` |
| `spec-improvement` | sí | `unverified` | `native` | Pasos 2 a 8: análisis, exploración, generación y guardado. | — | No ejecutada en Hermes Agent en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ask-user-choices` | `clarify`; fallback en texto ante undelivered/timed_out/cancelled. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | Verificado en Hermes real. |

**Implementación**

- Adaptaciones: Sección «Compatibilidad entre agentes»: herramienta de preguntas por agente y fallback en texto con detención.
- Archivos modificados: `plugins/golfo-kit/skills/improve-spec/SKILL.md`, `plugins/golfo-kit/skills/improve-spec/evals/eval-config.json`.
- Fallback: Pregunta en texto con opciones numeradas y detención hasta la respuesta..
- Cambios de comportamiento respecto del original: Antes, sin AskUserQuestion la skill preguntaba en texto pero no exigía detenerse; ahora no avanza ni guarda hasta la respuesta..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `eval-claude-no-question-tool` | `claude_code` | eval | `run-evals <copia con no-question-tool-asks-in-text-and-stops> --provider claude` | `passed` | Sesión headless de Claude Code (claude -p, sin AskUserQuestion): pregunta en texto con opciones numeradas y se detiene sin generar el spec (5/5). |
| `eval-claude-clarify-undelivered` | `hermes` | simulated_eval | `run-evals <copia con hermes-clarify-undelivered-falls-back-to-text> --provider claude` | `passed` | Claude simulando Hermes con clarify undelivered: repite en texto, no guarda y reporta la limitación (3/3). |
| `eval-codex-provider` | `codex` | eval | `run-evals <copia con los 2 casos nuevos> --provider codex` | `blocked` | Fallo de infraestructura: el sandbox read-only de Codex en Windows no permite leer SKILL.md. |
| `codex-real-ask-fallback` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox -C <repo temporal con 3 specs> "<seguir SKILL.md y correr /improve-spec sin argumento>"` | `passed` | Codex listó docs/specs, preguntó en texto con 3 opciones numeradas y se detuvo; reportó que request_user_input requiere modo Plan. Los specs quedaron sin cambios. |
| `hermes-real-clarify-fallback` | `hermes` | real_run | `hermes chat -Q --in <repo temporal con 3 specs> -q "<seguir SKILL.md y correr /improve-spec sin argumento>"` | `passed` | Hermes llamó a clarify, que devolvió outcome "undelivered" con la sugerencia de elegir por su cuenta; siguiendo la sección de compatibilidad preguntó en texto con 3 opciones y se detuvo. `git status` limpio. |

Pendiente de verificar:

- Flujo completo (pasos 2 a 8) en los tres agentes.
- Ruta nativa con AskUserQuestion en Claude Code interactivo.

### `inline-thread-autofix`

**Identificación**

- Nombre: Inline Thread Autofix; versión: 1.1.0; SKILL.md: `plugins/golfo-kit/skills/inline-thread-autofix/SKILL.md`.
- Propósito: Orquesta el feedback de un hilo o review de PR: pregunta el entorno, aplica el fix y hace el closeout.
- Funcionalidades principales: pregunta del entorno; preflight y stack; handoff a fix-in-ephemeral-clone o sibling-worktree; closeout del hilo.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Herramienta de preguntas | tool | no | `claude_code`; `codex`; `hermes` |
| Subagente con handle (modo background) | subagent | no | `claude_code`; `codex`; `hermes` |
| `gh` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### inline-thread-autofix / `claude_code`: `unverified`

Adaptaciones documentadas para la pregunta del entorno y el modo background; no ejecutada en Claude Code en esta auditoría.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-environment` | sí | `unverified` | `native` | `AskUserQuestion`. | Pregunta en texto y detención. | No ejecutada en Claude Code en esta auditoría. | — |
| `background-handoff` | no | `unverified` | `native` | `Agent` con handle. | Modo in_context. | No ejecutada en Claude Code en esta auditoría. | — |
| `pr-closeout` | sí | `unverified` | `native` | Reply, reacción y resolución del hilo con gh. | — | No ejecutada en Claude Code en esta auditoría. | — |

#### inline-thread-autofix / `codex`: `unverified`

Adaptaciones documentadas para la pregunta del entorno y el modo background; no ejecutada en Codex CLI en esta auditoría.

- Capacidades faltantes: request_user_input fuera del modo Plan.
- Alternativas investigadas: request_user_input en modo Plan; spawn_agent.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-environment` | sí | `unverified` | `alternative` | Texto y detención; `request_user_input` solo en modo Plan. | Pregunta en texto y detención. | No ejecutada en Codex CLI en esta auditoría. | — |
| `background-handoff` | no | `unverified` | `alternative` | `spawn_agent` + `wait_agent`. | Modo in_context. | No ejecutada en Codex CLI en esta auditoría. | — |
| `pr-closeout` | sí | `unverified` | `native` | Reply, reacción y resolución del hilo con gh. | — | No ejecutada en Codex CLI en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ask-environment` | Texto y detención; `request_user_input` solo en modo Plan. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Codex CLI en esta auditoría. |
| `background-handoff` | `spawn_agent` + `wait_agent`. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Codex CLI en esta auditoría. |

#### inline-thread-autofix / `hermes`: `unverified`

Adaptaciones documentadas para la pregunta del entorno y el modo background; no ejecutada en Hermes Agent en esta auditoría.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: clarify; delegate_task.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-environment` | sí | `unverified` | `alternative` | `clarify`; texto ante undelivered/timed_out/cancelled. | Pregunta en texto y detención. | No ejecutada en Hermes Agent en esta auditoría. | — |
| `background-handoff` | no | `unverified` | `alternative` | `delegate_task`. | Modo in_context. | No ejecutada en Hermes Agent en esta auditoría. | — |
| `pr-closeout` | sí | `unverified` | `native` | Reply, reacción y resolución del hilo con gh. | — | No ejecutada en Hermes Agent en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ask-environment` | `clarify`; texto ante undelivered/timed_out/cancelled. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Hermes Agent en esta auditoría. |
| `background-handoff` | `delegate_task`. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Hermes Agent en esta auditoría. |

**Implementación**

- Adaptaciones: Sección «Compatibilidad entre agentes»: pregunta por agente con fallback en texto; background solo con handle real.
- Archivos modificados: `plugins/golfo-kit/skills/inline-thread-autofix/SKILL.md`.
- Fallback: Pregunta en texto con detención; modo in_context..
- Cambios de comportamiento respecto del original: Ninguno en Claude Code; en otros agentes la pregunta puede ser en texto..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar con una URL de hilo real en Claude Code.
- Ejecutar con una URL de hilo real en Codex CLI.
- Ejecutar con una URL de hilo real en Hermes Agent.

### `measured-performance-optimization`

**Identificación**

- Nombre: Measured Performance Optimization; versión: 1.3.0; SKILL.md: `plugins/golfo-kit/skills/measured-performance-optimization/SKILL.md`.
- Propósito: Mide y optimiza rendimiento web con evidencia.
- Funcionalidades principales: medición antes/después; optimizaciones de bundle, renders, caching, N+1, memoria y leaks, SSR/TTFB y streaming, main thread y long tasks, y listas/DOM grande.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Verificación en navegador: Claude in Chrome o MCP de DevTools/Playwright / plugin chrome@openai-bundled (flujo) + Lighthouse o Playwright por terminal (métricas) / browser_exec o Lighthouse y Playwright por terminal | tool | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### measured-performance-optimization / `claude_code`: `unverified`

Sin dependencias obligatorias de agente. La verificación en navegador usa Claude in Chrome o un MCP de navegador (no conectados en la auditoría); el fallback por terminal sí corrió. La skill completa no se ejecutó en Claude Code.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `unverified` | `native` | Claude in Chrome o un MCP de navegador para medir Web Vitals, interacciones y renders antes y después, y recorrer el flujo (pasos 3, 5 y 6); si no están, el fallback por terminal de agent-capabilities.md. | Lighthouse, Chrome headless con log y Playwright por terminal (verificados desde Claude Code). | Claude in Chrome no estaba conectado en la sesión de esta auditoría: el camino nativo no se ejecutó. El fallback por terminal sí corrió desde Claude Code. | Corrida real claude-real-terminal-browser (fallback por terminal); prueba `claude-real-terminal-browser` |

#### measured-performance-optimization / `codex`: `unverified`

Verificación en navegador adaptada y verificada: Métricas con Lighthouse o Playwright por terminal (el plugin Chrome no expone performance); el plugin Chrome solo confirma el flujo del paso 5. La skill completa no se ejecutó en Codex CLI.

- Capacidades faltantes: Claude in Chrome.
- Alternativas investigadas: Plugin chrome@openai-bundled (viable); Lighthouse, Chrome headless con log y Playwright por terminal (viable); Plugin browser@openai-bundled / browser-use (iab) (viable); computer-use@openai-bundled (descartado).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `adapted` | `alternative` | Métricas con Lighthouse o Playwright por terminal (el plugin Chrome no expone performance); el plugin Chrome solo confirma el flujo del paso 5. | Sin ningún mecanismo, la verificación queda BLOCKED (nunca PASS) y se reporta en Limitaciones del agente. | El plugin Chrome reproduce el flujo en el Chrome real pero su evaluate no expone performance; Lighthouse y Playwright por terminal dan las mismas métricas de laboratorio. | Corrida real codex-real-terminal-metrics; Corrida real codex-real-chrome-console-states; Eval simulada eval-sim-codex-metrics-via-terminal-not-chrome-plugin; prueba `codex-real-terminal-metrics`; prueba `codex-real-chrome-console-states`; prueba `eval-sim-codex-metrics-via-terminal-not-chrome-plugin` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `browser-verification` | Plugin chrome@openai-bundled | docs/api.json del plugin + corrida real codex-real-chrome-console-states | sí | Sirve para confirmar el flujo; no para medir, porque su evaluate no expone performance. |
| `browser-verification` | Lighthouse, Chrome headless con log y Playwright por terminal | plugins/golfo-kit/references/agent-capabilities.md#verificación-en-navegador-por-terminal + corridas reales | sí | Agnóstico del agente; verificado desde los tres agentes. Sin sesión del usuario: solo localhost/staging sin login o con credenciales de prueba. |
| `browser-verification` | Plugin browser@openai-bundled / browser-use (iab) | plugin.json y docs del plugin | sí | Navegador in-app para localhost; solo en la app de escritorio, no probado desde el CLI. |
| `browser-verification` | computer-use@openai-bundled | plugin.json | no | Toma el escritorio; el plugin Chrome cubre el mismo caso sin hacerlo. |

#### measured-performance-optimization / `hermes`: `unverified`

Verificación en navegador adaptada y verificada por terminal: browser_exec si arranca (localhost sin login); si falla dos veces, Lighthouse y Playwright por terminal con el Chrome instalado. La skill completa no se ejecutó en Hermes Agent.

- Capacidades faltantes: Claude in Chrome.
- Alternativas investigadas: browser_exec (Chromium headless, perfil descartable) (viable); Lighthouse, Chrome headless con log y Playwright por terminal (viable); computer_use sobre el Chrome real (viable).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `adapted` | `alternative` | browser_exec si arranca (localhost sin login); si falla dos veces, Lighthouse y Playwright por terminal con el Chrome instalado. | Sin ningún mecanismo, la verificación queda BLOCKED (nunca PASS) y se reporta en Limitaciones del agente. | browser_exec es inestable en esta máquina; Lighthouse, Chrome headless con log y Playwright por terminal logran la misma verificación y corrieron desde Hermes. | Corrida real hermes-real-terminal-console-metrics; Corrida real hermes-real-playwright-states; Corrida real hermes-real-browser-exec-probe; Eval simulada eval-sim-hermes-browser-exec-fails-terminal-fallback; prueba `hermes-real-terminal-console-metrics`; prueba `hermes-real-playwright-states`; prueba `hermes-real-browser-exec-probe`; prueba `eval-sim-hermes-browser-exec-fails-terminal-fallback` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `browser-verification` | browser_exec (Chromium headless, perfil descartable) | corrida real hermes-real-browser-exec-probe + doc browser | sí | Sirve para localhost sin login cuando arranca; en esta máquina falló 7 de 9 veces, así que la skill pasa a terminal tras dos fallos. |
| `browser-verification` | Lighthouse, Chrome headless con log y Playwright por terminal | plugins/golfo-kit/references/agent-capabilities.md#verificación-en-navegador-por-terminal + corridas reales | sí | Agnóstico del agente; verificado desde los tres agentes. Sin sesión del usuario: solo localhost/staging sin login o con credenciales de prueba. |
| `browser-verification` | computer_use sobre el Chrome real | lista de herramientas + doc computer-use | sí | Único camino para pantallas que necesitan la sesión del usuario; requiere aviso y consentimiento. No ejecutado. |

**Implementación**

- Adaptaciones: Sección «Compatibilidad entre agentes»: mecanismo por métrica según agent-capabilities.md (Lighthouse por terminal en cualquier agente; el plugin Chrome de Codex no mide), mismo mecanismo antes y después, y Limitaciones del agente en el reporte; Fila «Verificar en un navegador» y sección «Verificación en navegador por terminal» en plugins/golfo-kit/references/agent-capabilities.md (fuente única compartida).
- Archivos modificados: `plugins/golfo-kit/skills/measured-performance-optimization/SKILL.md`, `plugins/golfo-kit/skills/measured-performance-optimization/references/measurement-tools.md`, `plugins/golfo-kit/skills/measured-performance-optimization/evals/eval-config.json`, `plugins/golfo-kit/references/agent-capabilities.md`.
- Fallback: Sin ningún mecanismo de navegador, la verificación queda BLOCKED y se reporta en Limitaciones del agente..
- Cambios de comportamiento respecto del original: Codex mide por terminal en lugar de intentar medir con el plugin Chrome; Hermes pasa a terminal si browser_exec no arranca. Sin ningún mecanismo aplica la detención del paso 3..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `claude-real-terminal-browser` | `claude_code` | real_run | `npx -y lighthouse@12 http://127.0.0.1:8793/ --output=json --only-categories=performance --chrome-flags=--headless=new; chrome.exe --headless=new --enable-logging --log-file=<log> --v=0 --virtual-time-budget=3000 --dump-dom http://127.0.0.1:8793/ (Start-Process -Wait); node walk-states.mjs (playwright-core 1.64.1, channel chrome)` | `passed` | Desde la Bash de Claude Code sobre una página local servida con python -m http.server: Lighthouse 12.8.2 devolvió LCP 1.1 s, CLS 0, TBT 0 ms, FCP 1.1 s; el log de Chrome headless tuvo la línea CONSOLE con el warning de hidratación simulado; Playwright con el Chrome instalado capturó el console.error, la navegación (169 ms) y los cuatro estados (loading, empty, data, error). Claude in Chrome no estaba conectado en la sesión, así que el camino nativo no se ejecutó. |
| `codex-real-chrome-console-states` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<abrir http://127.0.0.1:8793/ en una pestaña nueva del Chrome real con el plugin Chrome, tab.reload(), tab.dev.logs, tab.playwright.evaluate de performance y clic en cada estado>"` | `passed` | agent.browsers.list() → {type: extension, family: chrome, profileName: Guido}; tab.dev.logs devolvió el console.error de hidratación simulado (una entrada por carga); getByRole(...).click() recorrió Carga, Vacío, Con datos y Error con data-current loading/empty/data/error; la pestaña propia se cerró. tab.playwright.evaluate no expone performance ni PerformanceObserver (scope de solo lectura): las métricas no salen del plugin. |
| `codex-real-terminal-metrics` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<npx -y lighthouse@12 … y node walk-states.mjs por exec_command>"` | `passed` | Lighthouse 12.8.2 desde Codex: LCP 1125 ms, CLS 0, TBT 0, FCP 1125 ms. Playwright con el Chrome instalado: console.error de hidratación, navegación 176 ms y los cuatro estados recorridos. |
| `hermes-real-browser-exec-probe` | `hermes` | real_run | `hermes chat -Q -q "<browser_exec: listener de consola antes de navegar, recarga, performance y clic en cada estado de http://127.0.0.1:8793/>"` | `failed` | browser_exec falló al arrancar 7 de 9 veces ('Chrome exited early … without writing DevToolsActivePort'); las dos que arrancaron eran HeadlessChrome/145 sobre about:blank. Había unos 24 Chromium huérfanos con user-data-dir agent-browser-chrome-<uuid> en Temp, que no se mataron. Ninguna verificación de la página se completó con browser_exec. |
| `hermes-real-terminal-console-metrics` | `hermes` | real_run | `hermes chat -Q -q "<solo terminal: Chrome headless con --enable-logging --log-file y npx -y lighthouse@12 sobre http://127.0.0.1:8793/>"` | `passed` | Hermes encontró Chrome y npx; el log tuvo la línea CONSOLE del warning de hidratación simulado; Lighthouse 12.8.2: LCP 1.1 s, CLS 0, TBT 0 ms, FCP 1.1 s (hermes-lh.json de 192 KB). |
| `hermes-real-playwright-states` | `hermes` | real_run | `hermes chat -Q -q "<solo terminal: node walk-states.mjs http://127.0.0.1:8793/ (playwright-core, channel chrome, headless)>"` | `passed` | Salida del script desde Hermes: console.error de hidratación simulado, navegación 175 ms y data-current loading/empty/data/error tras cada clic; exitCode 0. |
| `eval-sim-codex-metrics-via-terminal-not-chrome-plugin` | `codex` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/measured-performance-optimization --provider claude (solo los casos nuevos)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: codex-metrics-via-terminal-not-chrome-plugin: mide LCP con Lighthouse por terminal, explica que el plugin Chrome no expone performance, mismo mecanismo antes y después y reserva el plugin para confirmar el flujo. |
| `eval-sim-hermes-browser-exec-fails-terminal-fallback` | `hermes` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/measured-performance-optimization --provider claude (solo los casos nuevos)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: hermes-browser-exec-fails-terminal-fallback: tras dos fallos de browser_exec mide la interacción con Playwright por terminal y el Chrome instalado, con performance.mark/measure, y declara Limitaciones del agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.
- Claude Code: verificación en navegador con Claude in Chrome conectado (camino nativo).
- Hermes: pantallas que requieren la sesión del usuario con computer_use (con consentimiento) o browser_exec con perfil real.

### `mobile-first-responsive-layout`

**Identificación**

- Nombre: Mobile First Responsive Units; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/mobile-first-responsive-layout/SKILL.md`.
- Propósito: Guía de unidades y patrones mobile-first en CSS/SCSS.
- Funcionalidades principales: unidades fluidas; breakpoints.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### mobile-first-responsive-layout / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### mobile-first-responsive-layout / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### mobile-first-responsive-layout / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `mock-first-testing-design`

**Identificación**

- Nombre: Mock First Testing Design; versión: 2.0.0; SKILL.md: `plugins/golfo-kit/skills/mock-first-testing-design/SKILL.md`.
- Propósito: Decide cómo aislar dependencias en tests sin contaminar el código de producción.
- Funcionalidades principales: integración real primero; dobles solo en puertos de dominio.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### mock-first-testing-design / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### mock-first-testing-design / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### mock-first-testing-design / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `nextjs-route-ui-boundaries`

**Identificación**

- Nombre: Next.js: boundaries de UI por ruta; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/nextjs-route-ui-boundaries/SKILL.md`.
- Propósito: Decide loading, error, layouts, Suspense y server/client en Next.js App Router.
- Funcionalidades principales: boundaries por ruta; APIs de Next.js.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### nextjs-route-ui-boundaries / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### nextjs-route-ui-boundaries / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### nextjs-route-ui-boundaries / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `node-runtime-debugging`

**Identificación**

- Nombre: Debugging runtime de Node.js; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/node-runtime-debugging/SKILL.md`.
- Propósito: Depura servidores Node.js/BFF con node --inspect y requests reales.
- Funcionalidades principales: inspección de valores runtime.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `node` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### node-runtime-debugging / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### node-runtime-debugging / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### node-runtime-debugging / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `optimistic-action-mutations`

**Identificación**

- Nombre: Optimistic Action Mutations; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/optimistic-action-mutations/SKILL.md`.
- Propósito: Patrones de mutaciones optimistas con reconciliación y rollback.
- Funcionalidades principales: debounce y coalescing; rollback seguro.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### optimistic-action-mutations / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### optimistic-action-mutations / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### optimistic-action-mutations / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `pr-description-template`

**Identificación**

- Nombre: PR Description Template; versión: 1.2.0; SKILL.md: `plugins/golfo-kit/skills/pr-description-template/SKILL.md`.
- Propósito: Define el título y la descripción estándar de PR (y el modo traceability-only), incluidas capturas de UI.
- Funcionalidades principales: título y body con plantilla; conteo de archivos; capturas de UI desde el navegador del usuario; modo traceability-only.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `gh` en PATH | command | sí | `claude_code`; `codex`; `hermes` |
| Navegador real del usuario: Claude in Chrome / plugin chrome@openai-bundled / computer_use o browser_exec con perfil real | tool | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### pr-description-template / `claude_code`: `compatible`

Plantilla y body por gh; capturas con Claude in Chrome. No ejecutada todavía en esta auditoría.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `pr-body` | sí | `enabled` | `native` | Plantilla y gh pr create/edit. | — | PR real creado con la plantilla y verificado. | PR #22.; prueba `claude-real-pr22` |
| `ui-screenshots` | no | `unverified` | `native` | Capturas desde Claude in Chrome. | Omitir capturas. | Requiere un cambio de UI y la extensión conectada; no ejecutado. | — |

#### pr-description-template / `codex`: `unverified`

Plantilla y body por gh; capturas desde el Chrome real del usuario con el plugin Chrome de Codex (capacidad verificada). El body completo no se ejecutó en Codex.

- Capacidades faltantes: Claude in Chrome.
- Alternativas investigadas: plugin chrome@openai-bundled (adoptado); navegador in-app (descartado); computer-use (último recurso).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `pr-body` | sí | `unverified` | `native` | Plantilla y gh pr create/edit. | — | No ejecutada en Codex CLI en esta auditoría. | — |
| `ui-screenshots` | no | `adapted` | `alternative` | Capturas en el Chrome real del usuario vía la extensión: agent.browsers.list() → type extension / family chrome, pestaña nueva, captura y cierre de las pestañas propias. | Sin navegador aceptado, omitir la captura con el motivo en Notas para el Revisor. | El plugin Chrome de Codex controla el mismo navegador real del usuario (sesiones, fuentes, extensiones) que Claude in Chrome. | plugin.json de chrome@openai-bundled; Corrida real codex-real-chrome-capture; prueba `codex-real-chrome-capture`; prueba `eval-sim-codex-chrome-capture` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ui-screenshots` | Plugin chrome@openai-bundled | plugin.json + corrida real en codex exec | sí | Chrome real del usuario, perfil Guido, webdriver=false. |
| `ui-screenshots` | Plugin browser (navegador in-app, iab) | plugin.json del plugin browser | no | No es el navegador del usuario; no tiene sus sesiones ni extensiones. |
| `ui-screenshots` | computer-use@openai-bundled | plugin.json | sí | Viable como último recurso, pero toma el escritorio; se prefiere el plugin Chrome. |

#### pr-description-template / `hermes`: `unverified`

Plantilla y body por gh; capturas con computer_use sobre el Chrome real o browser_exec con perfil real (implementado, no verificado). El browser_exec por defecto no se acepta.

- Capacidades faltantes: Claude in Chrome.
- Alternativas investigadas: computer_use (adoptado, no verificado); browser_exec con use_real_profile + headed (adoptado, no verificado); browser_exec por defecto (descartado: headless); /browser connect (descartado: perfil dedicado).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `pr-body` | sí | `unverified` | `native` | Plantilla y gh pr create/edit. | — | No ejecutada en Hermes Agent en esta auditoría. | — |
| `ui-screenshots` | no | `unverified` | `alternative` | computer_use sobre la ventana real de Chrome del usuario, avisando antes de tomar el escritorio; o browser_exec solo con use_real_profile + headed. | Omitir la captura con el motivo y los navegadores revisados. | Hay alternativas que usan el navegador real del usuario, pero ninguna se ejecutó: computer_use tomaría el escritorio del usuario y la config de perfil real no está activa. | Doc de Hermes (browser y computer-use); Corrida real: browser_exec por defecto es headless y falló; prueba `hermes-real-browser-probe`; prueba `eval-sim-hermes-browser-choice` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ui-screenshots` | computer_use sobre la ventana real de Chrome | lista de herramientas + doc computer-use | sí | Usa el navegador real; requiere aviso porque mueve mouse y teclado. |
| `ui-screenshots` | browser_exec con browser.use_real_profile: true + browser.headed: true | doc user-guide/features/browser | sí | Binario real sobre una copia del perfil; requiere cambiar config.yaml. |
| `ui-screenshots` | browser_exec por defecto | corrida real hermes-real-browser-probe | no | Chromium headless con perfil descartable; además inestable en esta máquina. |
| `ui-screenshots` | /browser connect (CDP) | doc browser | no | Exige un perfil dedicado sin sesiones (Chrome 136+): no es el navegador tal como lo usa el usuario. |

**Implementación**

- Adaptaciones: Sección «Capture browser»: los navegadores aceptados viven en agent-capabilities.md (fuente única); la skill solo agrega las reglas propias de las capturas publicadas (pestaña nueva, aviso antes de tomar el escritorio).
- Archivos modificados: `plugins/golfo-kit/skills/pr-description-template/SKILL.md`, `plugins/golfo-kit/skills/pr-description-template/evals/eval-config.json`.
- Fallback: Sin navegador aceptado, omitir la captura con el motivo..
- Cambios de comportamiento respecto del original: Codex ya no omite las capturas: usa el Chrome real del usuario. Hermes las toma solo con navegador real y aviso previo..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `claude-real-pr22` | `claude_code` | real_run | `gh pr create --body-file <plantilla> (PR #22)` | `passed` | Conteo con count-reviewable-files.sh (4), plantilla completa en español, verificado con gh pr view (https://github.com/guidomodarelli/golfo-marketplace/pull/22). |
| `codex-real-chrome-capture` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<abrir http://127.0.0.1:8791/ en el Chrome del usuario vía mcp__cua_repl.js, capturar y cerrar la pestaña>"` | `passed` | agent.browsers.list() devolvió {type: extension, family: chrome, profileName: Guido}; abrió la página local en una pestaña nueva del Chrome real (webdriver=false, Chrome/156), guardó chrome-shot.jpg (28 101 bytes, revisada: página completa con estilos) y cerró la pestaña. Prueba de la capacidad de captura que usa la skill; el flujo completo de antes/después y subida a pr-assets no se ejecutó en Codex. |
| `hermes-real-browser-probe` | `hermes` | real_run | `hermes chat -Q -q "<abrir http://127.0.0.1:8791/ con browser_exec, capturar e identificar el navegador>"` | `failed` | browser_exec lanzó el Chromium propio de Hermes con --headless=new y --user-data-dir en Temp (perfil descartable, sin sesiones ni extensiones) y falló al arrancar 4 de 5 veces ('Chrome exited early … without writing DevToolsActivePort'); no produjo captura. Confirma que el navegador por defecto no sirve para capturas publicadas. |
| `eval-sim-codex-chrome-capture` | `codex` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/pr-description-template --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: codex-chrome-plugin-screenshots: usa el Chrome real vía plugin, pestaña nueva, descarta el navegador in-app. |
| `eval-sim-hermes-browser-choice` | `hermes` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/pr-description-template --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: hermes-default-browser-not-accepted: propone computer_use con aviso y rechaza browser_exec headless por defecto. |

Pendiente de verificar:

- Codex: flujo completo antes/después + subida a pr-assets.
- Hermes: captura con computer_use o con use_real_profile + headed.

### `pr-inline-comment-template`

**Identificación**

- Nombre: PR Inline Comment Template; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/pr-inline-comment-template/SKILL.md`.
- Propósito: Crea, formatea y publica comentarios inline de review en PRs de GitHub.
- Funcionalidades principales: plantilla de comentario; publicación inline.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `gh` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### pr-inline-comment-template / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### pr-inline-comment-template / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### pr-inline-comment-template / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `prevent-ssr-hydration-mismatches`

**Identificación**

- Nombre: React SSR Hydration Consistency; versión: 1.1.0; SKILL.md: `plugins/golfo-kit/skills/prevent-ssr-hydration-mismatches/SKILL.md`.
- Propósito: Previene y diagnostica mismatches de hidratación SSR en React.
- Funcionalidades principales: render inicial determinista.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Verificación en navegador: Claude in Chrome o MCP de navegador / plugin chrome@openai-bundled (tab.dev.logs) / browser_exec o Chrome headless con log y Playwright por terminal | tool | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### prevent-ssr-hydration-mismatches / `claude_code`: `unverified`

Sin dependencias obligatorias de agente. La verificación en navegador usa Claude in Chrome o un MCP de navegador (no conectados en la auditoría); el fallback por terminal sí corrió. La skill completa no se ejecutó en Claude Code.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `unverified` | `native` | Claude in Chrome o un MCP de navegador para hard reload de la ruta afectada y lectura de los warnings de hidratación en la consola (pasos 6 a 8 de la validación); si no están, el fallback por terminal de agent-capabilities.md. | Lighthouse, Chrome headless con log y Playwright por terminal (verificados desde Claude Code). | Claude in Chrome no estaba conectado en la sesión de esta auditoría: el camino nativo no se ejecutó. El fallback por terminal sí corrió desde Claude Code. | Corrida real claude-real-terminal-browser (fallback por terminal); prueba `claude-real-terminal-browser` |

#### prevent-ssr-hydration-mismatches / `codex`: `unverified`

Verificación en navegador adaptada y verificada: tab.reload() y tab.dev.logs({ levels: ["error", "warn"] }) del plugin Chrome sobre el Chrome real del usuario. La skill completa no se ejecutó en Codex CLI.

- Capacidades faltantes: Claude in Chrome.
- Alternativas investigadas: Plugin chrome@openai-bundled (viable); Lighthouse, Chrome headless con log y Playwright por terminal (viable); Plugin browser@openai-bundled / browser-use (iab) (viable); computer-use@openai-bundled (descartado).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `adapted` | `alternative` | tab.reload() y tab.dev.logs({ levels: ["error", "warn"] }) del plugin Chrome sobre el Chrome real del usuario. | Sin ningún mecanismo, la verificación queda BLOCKED (nunca PASS) y se reporta en Limitaciones del agente. | El plugin Chrome captura la consola de la carga en el Chrome real con tab.dev.logs, igual que la consola de Claude in Chrome. | Corrida real codex-real-chrome-console-states; Corrida real codex-real-terminal-metrics; Eval simulada eval-sim-codex-hydration-console-via-dev-logs; prueba `codex-real-chrome-console-states`; prueba `codex-real-terminal-metrics`; prueba `eval-sim-codex-hydration-console-via-dev-logs` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `browser-verification` | Plugin chrome@openai-bundled | docs/api.json del plugin + corrida real codex-real-chrome-console-states | sí | Chrome real del usuario: tab.dev.logs lee la consola de la carga y getByRole().click() recorre estados. |
| `browser-verification` | Lighthouse, Chrome headless con log y Playwright por terminal | plugins/golfo-kit/references/agent-capabilities.md#verificación-en-navegador-por-terminal + corridas reales | sí | Agnóstico del agente; verificado desde los tres agentes. Sin sesión del usuario: solo localhost/staging sin login o con credenciales de prueba. |
| `browser-verification` | Plugin browser@openai-bundled / browser-use (iab) | plugin.json y docs del plugin | sí | Navegador in-app para localhost; solo en la app de escritorio, no probado desde el CLI. |
| `browser-verification` | computer-use@openai-bundled | plugin.json | no | Toma el escritorio; el plugin Chrome cubre el mismo caso sin hacerlo. |

#### prevent-ssr-hydration-mismatches / `hermes`: `unverified`

Verificación en navegador adaptada y verificada por terminal: browser_exec con listener registrado antes de navegar si arranca; si no, Chrome headless con --enable-logging --log-file o Playwright con page.on("console") por terminal. Rutas con sesión sin credenciales de prueba: BLOCKED. La skill completa no se ejecutó en Hermes Agent.

- Capacidades faltantes: Claude in Chrome.
- Alternativas investigadas: browser_exec (Chromium headless, perfil descartable) (viable); Lighthouse, Chrome headless con log y Playwright por terminal (viable); computer_use sobre el Chrome real (viable).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `adapted` | `alternative` | browser_exec con listener registrado antes de navegar si arranca; si no, Chrome headless con --enable-logging --log-file o Playwright con page.on("console") por terminal. Rutas con sesión sin credenciales de prueba: BLOCKED. | Sin ningún mecanismo, la verificación queda BLOCKED (nunca PASS) y se reporta en Limitaciones del agente. | browser_exec es inestable en esta máquina; Lighthouse, Chrome headless con log y Playwright por terminal logran la misma verificación y corrieron desde Hermes. | Corrida real hermes-real-terminal-console-metrics; Corrida real hermes-real-playwright-states; Corrida real hermes-real-browser-exec-probe; Eval simulada eval-sim-hermes-session-route-blocked; prueba `hermes-real-terminal-console-metrics`; prueba `hermes-real-playwright-states`; prueba `hermes-real-browser-exec-probe`; prueba `eval-sim-hermes-session-route-blocked` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `browser-verification` | browser_exec (Chromium headless, perfil descartable) | corrida real hermes-real-browser-exec-probe + doc browser | sí | Sirve para localhost sin login cuando arranca; en esta máquina falló 7 de 9 veces, así que la skill pasa a terminal tras dos fallos. |
| `browser-verification` | Lighthouse, Chrome headless con log y Playwright por terminal | plugins/golfo-kit/references/agent-capabilities.md#verificación-en-navegador-por-terminal + corridas reales | sí | Agnóstico del agente; verificado desde los tres agentes. Sin sesión del usuario: solo localhost/staging sin login o con credenciales de prueba. |
| `browser-verification` | computer_use sobre el Chrome real | lista de herramientas + doc computer-use | sí | Único camino para pantallas que necesitan la sesión del usuario; requiere aviso y consentimiento. No ejecutado. |

**Implementación**

- Adaptaciones: Sección «Agent compatibility»: captura de la consola desde la carga según el mecanismo presente (Claude in Chrome, tab.dev.logs, browser_exec con listener previo o terminal), BLOCKED si la ruta exige sesión y no hay navegador real, y Agent limitations en el reporte; Fila «Verificar en un navegador» y sección «Verificación en navegador por terminal» en plugins/golfo-kit/references/agent-capabilities.md (fuente única compartida).
- Archivos modificados: `plugins/golfo-kit/skills/prevent-ssr-hydration-mismatches/SKILL.md`, `plugins/golfo-kit/skills/prevent-ssr-hydration-mismatches/evals/eval-config.json`, `plugins/golfo-kit/references/agent-capabilities.md`.
- Fallback: Sin ningún mecanismo de navegador, la verificación queda BLOCKED y se reporta en Limitaciones del agente..
- Cambios de comportamiento respecto del original: Codex lee la consola con tab.dev.logs; Hermes usa la terminal si browser_exec no arranca. Rutas con sesión sin navegador real quedan BLOCKED en lugar de omitirse..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `claude-real-terminal-browser` | `claude_code` | real_run | `npx -y lighthouse@12 http://127.0.0.1:8793/ --output=json --only-categories=performance --chrome-flags=--headless=new; chrome.exe --headless=new --enable-logging --log-file=<log> --v=0 --virtual-time-budget=3000 --dump-dom http://127.0.0.1:8793/ (Start-Process -Wait); node walk-states.mjs (playwright-core 1.64.1, channel chrome)` | `passed` | Desde la Bash de Claude Code sobre una página local servida con python -m http.server: Lighthouse 12.8.2 devolvió LCP 1.1 s, CLS 0, TBT 0 ms, FCP 1.1 s; el log de Chrome headless tuvo la línea CONSOLE con el warning de hidratación simulado; Playwright con el Chrome instalado capturó el console.error, la navegación (169 ms) y los cuatro estados (loading, empty, data, error). Claude in Chrome no estaba conectado en la sesión, así que el camino nativo no se ejecutó. |
| `codex-real-chrome-console-states` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<abrir http://127.0.0.1:8793/ en una pestaña nueva del Chrome real con el plugin Chrome, tab.reload(), tab.dev.logs, tab.playwright.evaluate de performance y clic en cada estado>"` | `passed` | agent.browsers.list() → {type: extension, family: chrome, profileName: Guido}; tab.dev.logs devolvió el console.error de hidratación simulado (una entrada por carga); getByRole(...).click() recorrió Carga, Vacío, Con datos y Error con data-current loading/empty/data/error; la pestaña propia se cerró. tab.playwright.evaluate no expone performance ni PerformanceObserver (scope de solo lectura): las métricas no salen del plugin. |
| `codex-real-terminal-metrics` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<npx -y lighthouse@12 … y node walk-states.mjs por exec_command>"` | `passed` | Lighthouse 12.8.2 desde Codex: LCP 1125 ms, CLS 0, TBT 0, FCP 1125 ms. Playwright con el Chrome instalado: console.error de hidratación, navegación 176 ms y los cuatro estados recorridos. |
| `hermes-real-browser-exec-probe` | `hermes` | real_run | `hermes chat -Q -q "<browser_exec: listener de consola antes de navegar, recarga, performance y clic en cada estado de http://127.0.0.1:8793/>"` | `failed` | browser_exec falló al arrancar 7 de 9 veces ('Chrome exited early … without writing DevToolsActivePort'); las dos que arrancaron eran HeadlessChrome/145 sobre about:blank. Había unos 24 Chromium huérfanos con user-data-dir agent-browser-chrome-<uuid> en Temp, que no se mataron. Ninguna verificación de la página se completó con browser_exec. |
| `hermes-real-terminal-console-metrics` | `hermes` | real_run | `hermes chat -Q -q "<solo terminal: Chrome headless con --enable-logging --log-file y npx -y lighthouse@12 sobre http://127.0.0.1:8793/>"` | `passed` | Hermes encontró Chrome y npx; el log tuvo la línea CONSOLE del warning de hidratación simulado; Lighthouse 12.8.2: LCP 1.1 s, CLS 0, TBT 0 ms, FCP 1.1 s (hermes-lh.json de 192 KB). |
| `hermes-real-playwright-states` | `hermes` | real_run | `hermes chat -Q -q "<solo terminal: node walk-states.mjs http://127.0.0.1:8793/ (playwright-core, channel chrome, headless)>"` | `passed` | Salida del script desde Hermes: console.error de hidratación simulado, navegación 175 ms y data-current loading/empty/data/error tras cada clic; exitCode 0. |
| `eval-sim-codex-hydration-console-via-dev-logs` | `codex` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/prevent-ssr-hydration-mismatches --provider claude (solo los casos nuevos)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: codex-hydration-console-via-dev-logs: recarga la pestaña y lee los warnings de hidratación con tab.dev.logs, con resultado PASS/FAIL/BLOCKED. |
| `eval-sim-hermes-session-route-blocked` | `hermes` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/prevent-ssr-hydration-mismatches --provider claude (solo los casos nuevos)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: hermes-session-route-blocked: ruta con sesión, sin credenciales de prueba ni consentimiento para computer_use: reporta BLOCKED con Agent limitations y nunca PASS. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.
- Claude Code: verificación en navegador con Claude in Chrome conectado (camino nativo).
- Hermes: pantallas que requieren la sesión del usuario con computer_use (con consentimiento) o browser_exec con perfil real.

### `react-data-fetching-best-practices`

**Identificación**

- Nombre: React Data Fetching Best Practices; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/react-data-fetching-best-practices/SKILL.md`.
- Propósito: Buenas prácticas de data fetching en React, server-first.
- Funcionalidades principales: fetch en servidor; cancelación con AbortController.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### react-data-fetching-best-practices / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### react-data-fetching-best-practices / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### react-data-fetching-best-practices / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `react-render-performance-patterns`

**Identificación**

- Nombre: React Render Performance Patterns; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/react-render-performance-patterns/SKILL.md`.
- Propósito: Patrones de rendimiento de render y prioridad de updates en React.
- Funcionalidades principales: memoización; transiciones.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### react-render-performance-patterns / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### react-render-performance-patterns / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### react-render-performance-patterns / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `refactor-modularize-code`

**Identificación**

- Nombre: Refactor Modularity Cohesion Deduplication; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/refactor-modularize-code/SKILL.md`.
- Propósito: Refactoriza límites de módulos, cohesión y duplicación sin cambiar comportamiento.
- Funcionalidades principales: extracción de módulos; reorganización de imports.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### refactor-modularize-code / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### refactor-modularize-code / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### refactor-modularize-code / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `refactor-ssr-data-fetching`

**Identificación**

- Nombre: React SSR y BFF Data Fetching; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/refactor-ssr-data-fetching/SKILL.md`.
- Propósito: Prioriza el acceso a upstream desde el servidor y el BFF same-origin en React SSR.
- Funcionalidades principales: decisión de arquitectura de red.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### refactor-ssr-data-fetching / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### refactor-ssr-data-fetching / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### refactor-ssr-data-fetching / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `review-fix-loop`

**Identificación**

- Nombre: Review Fix Loop; versión: 1.2.0; SKILL.md: `plugins/golfo-kit/skills/review-fix-loop/SKILL.md`.
- Propósito: Loop de review y fix multi-provider (Claude Code y Codex como reviewers CLI) sobre cambios locales o PRs.
- Funcionalidades principales: selección de provider con fallback; rondas de review y fix; filtro adversarial; reporte final.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| CLIs `claude` y/o `codex` en PATH | command | sí | `claude_code`; `codex`; `hermes` |
| Revisor aislado read-only: Agent (Claude Code) o proceso externo claude -p --tools Read,Grep,Glob | subagent | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### review-fix-loop / `claude_code`: `unverified`

Filtro adversarial con Agent; providers por CLI. No ejecutada en esta auditoría.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `provider-review` | sí | `unverified` | `native` | Helper `scripts/review-fix-loop` con providers CLI. | — | No ejecutada en Claude Code en esta auditoría. | Suite shell del helper (prueba review-fix-loop-shell-suite).; prueba `review-fix-loop-shell-suite` |
| `isolated-filter` | no | `unverified` | `native` | Filtro adversarial en subagente aislado. | Filtro inline. | No ejecutada en Claude Code en esta auditoría. | — |

#### review-fix-loop / `codex`: `unverified`

Providers por CLI; filtro adversarial aislado con un proceso claude -p de solo lectura (verificado en Codex).

- Capacidades faltantes: Subagente read-only verificado.
- Alternativas investigadas: claude -p de solo lectura (adoptado); codex exec -s read-only (descartado en Windows); subagentes nativos (sin modo de solo lectura).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `provider-review` | sí | `unverified` | `native` | Helper `scripts/review-fix-loop` con providers CLI. | — | No ejecutada en Codex CLI en esta auditoría. | Suite shell del helper (prueba review-fix-loop-shell-suite).; prueba `review-fix-loop-shell-suite` |
| `isolated-filter` | no | `adapted` | `alternative` | Proceso externo claude -p "<prompt del filtro>" --tools "Read,Grep,Glob" --permission-mode dontAsk < /dev/null acotado con timeout/gtimeout o, sin ellos, con un wrapper de Python (verificado en Windows). | Filtro inline con Limitaciones del agente. | Codex no tiene subagentes de solo lectura, pero un proceso claude -p limitado a lectura da el mismo aislamiento. | Corrida real del filtro externo; Prueba de aislamiento: no pudo escribir; prueba `codex-real-claude-filter`; prueba `claude-cli-read-only-filter-probe`; prueba `eval-sim-codex-windows-inline` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `isolated-filter` | claude -p --tools Read,Grep,Glob | corridas reales en Codex y Hermes | sí | Aislado y de solo lectura (verificado). |
| `isolated-filter` | codex exec -s read-only | codex-read-only-sandbox-probe | no | En Windows el sandbox bloquea todo proceso, incluso leer; en Linux/macOS no verificado. |
| `isolated-filter` | spawn_agent | lista de herramientas | no | No tiene modo de solo lectura. |

#### review-fix-loop / `hermes`: `unverified`

Providers por CLI; filtro adversarial aislado con un proceso claude -p de solo lectura (verificado en Hermes).

- Capacidades faltantes: Subagente read-only (delegate_task hereda toolsets).
- Alternativas investigadas: claude -p de solo lectura (adoptado); codex exec -s read-only (descartado en Windows); subagentes nativos (sin modo de solo lectura).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `provider-review` | sí | `unverified` | `native` | Helper `scripts/review-fix-loop` con providers CLI. | — | No ejecutada en Hermes Agent en esta auditoría. | Suite shell del helper (prueba review-fix-loop-shell-suite).; prueba `review-fix-loop-shell-suite` |
| `isolated-filter` | no | `adapted` | `alternative` | Proceso externo claude -p "<prompt del filtro>" --tools "Read,Grep,Glob" --permission-mode dontAsk < /dev/null acotado con timeout/gtimeout o, sin ellos, con un wrapper de Python (verificado en Windows). | Filtro inline con Limitaciones del agente. | Hermes no tiene subagentes de solo lectura, pero un proceso claude -p limitado a lectura da el mismo aislamiento. | Corrida real del filtro externo; Prueba de aislamiento: no pudo escribir; prueba `hermes-real-claude-filter`; prueba `claude-cli-read-only-filter-probe`; prueba `eval-sim-hermes-claude-filter` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `isolated-filter` | claude -p --tools Read,Grep,Glob | corridas reales en Codex y Hermes | sí | Aislado y de solo lectura (verificado). |
| `isolated-filter` | codex exec -s read-only | codex-read-only-sandbox-probe | no | En Windows el sandbox bloquea todo proceso, incluso leer; en Linux/macOS no verificado. |
| `isolated-filter` | delegate_task | lista de herramientas | no | Los hijos heredan los toolsets del padre. |

**Implementación**

- Adaptaciones: Runners del filtro aislado por capacidad: Agent, claude -p de solo lectura, codex exec -s read-only donde lea, o inline.
- Archivos modificados: `plugins/golfo-kit/skills/review-fix-loop/SKILL.md`, `plugins/golfo-kit/skills/review-fix-loop/evals/eval-config.json`.
- Fallback: Filtro inline..
- Cambios de comportamiento respecto del original: Codex y Hermes recuperan el filtro aislado cuando claude está en PATH..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `review-fix-loop-shell-suite` | `any` | bats | `pnpm run test:review-fix-loop` | `passed` | Suite shell del helper de providers (agnóstica de agente). |
| `claude-cli-read-only-filter-probe` | `any` | static | `claude -p "<filtro adversarial + intentar crear pwned.txt>" --tools "Read,Grep,Glob" --permission-mode dontAsk` | `passed` | Desde una terminal: aceptó el off-by-one, rechazó el renombrado sin guía y no pudo crear pwned.txt (solo tenía Read/Glob/Grep). Comprueba el aislamiento del mecanismo, independiente del agente que lo invoque. |
| `codex-read-only-sandbox-probe` | `codex` | real_run | `codex exec -s read-only [-c 'windows.sandbox="elevated"'] "<leer sum.js e intentar escribir pwned.txt>"` | `failed` | En Windows el sandbox read-only no deja crear ningún proceso: 'CreateProcessAsUserW failed: 5 (Access is denied.)'; con elevated: 'helper_unknown_error: setup refresh had errors'. No pudo ni leer los archivos, así que no sirve como filtro en esta máquina. |
| `hermes-real-claude-filter` | `hermes` | real_run | `hermes chat -Q -q "<leer Agent compatibility de review-fix-loop y correr solo el filtro aislado sobre findings.md>"` | `passed` | Hermes eligió el runner 2, descartó delegate_task por heredar toolsets y corrió timeout 600 claude -p … --tools "Read,Grep,Glob" --permission-mode dontAsk < /dev/null (exit 0): aceptó 2 findings, rechazó 1 y el directorio quedó idéntico (ls antes/después). |
| `codex-real-claude-filter` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<leer Agent compatibility de review-fix-loop y correr solo el filtro aislado sobre findings.md>"` | `passed` | Codex corrió claude.exe -p … --tools Read,Grep,Glob --permission-mode dontAsk con timeout de 600 s y stdin cerrado (exit 0): aceptó 1 finding y rechazó 2; git status igual antes y después. |
| `eval-sim-hermes-claude-filter` | `hermes` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/review-fix-loop --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: hermes-filter-via-claude-cli-read-only: claude -p --tools Read,Grep,Glob con timeout; descarta delegate_task. |
| `eval-sim-codex-windows-inline` | `codex` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/review-fix-loop --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: windows-codex-only-filter-inline: sin claude en Windows filtra inline y lo reporta. |

Pendiente de verificar:

- Ejecutar una ronda real en Claude Code.
- Ejecutar una ronda real en Codex CLI.
- Ejecutar una ronda real en Hermes Agent.

### `review-maintainability`

**Identificación**

- Nombre: Review Maintainability; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/review-maintainability/SKILL.md`.
- Propósito: Revisa riesgos de mantenibilidad en el diff contra develop/main/master.
- Funcionalidades principales: concurrencia; leaks; edge cases.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### review-maintainability / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### review-maintainability / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### review-maintainability / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `review-performance`

**Identificación**

- Nombre: Review Performance; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/review-performance/SKILL.md`.
- Propósito: Revisa problemas de rendimiento con impacto en producción en el diff.
- Funcionalidades principales: N+1; complejidad; I/O ineficiente.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### review-performance / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### review-performance / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### review-performance / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `review-security`

**Identificación**

- Nombre: Review Security; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/review-security/SKILL.md`.
- Propósito: Revisa vulnerabilidades en el diff y en instrucciones de agentes.
- Funcionalidades principales: AppSec; instrucciones de IA y skills.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### review-security / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### review-security / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### review-security / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `semantic-html-a11y`

**Identificación**

- Nombre: Semantic HTML and Accessibility; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/semantic-html-a11y/SKILL.md`.
- Propósito: Aplica HTML semántico y accesibilidad en markup frontend.
- Funcionalidades principales: elementos nativos; aria y foco.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### semantic-html-a11y / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### semantic-html-a11y / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### semantic-html-a11y / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `sibling-worktree`

**Identificación**

- Nombre: Worktree hermano; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/sibling-worktree/SKILL.md`.
- Propósito: Gestiona worktrees hermanos persistentes reutilizando ramas existentes.
- Funcionalidades principales: crear, listar, remover y migrar worktrees.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### sibling-worktree / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### sibling-worktree / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### sibling-worktree / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `simplify-code`

**Identificación**

- Nombre: Simplify Code; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/simplify-code/SKILL.md`.
- Propósito: Revisa el diff por reuso, simplificación y eficiencia, y aplica los fixes.
- Funcionalidades principales: limpieza del diff.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### simplify-code / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### simplify-code / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### simplify-code / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `skill-optimizer`

**Identificación**

- Nombre: Skill Optimizer; versión: 1.2.0; SKILL.md: `plugins/golfo-kit/skills/skill-optimizer/SKILL.md`.
- Propósito: Optimiza skills existentes de forma medible: audita, compara baseline contra candidato y aplica solo con evidencia.
- Funcionalidades principales: modo audit; modos quick/full con evaluador held-out aislado; gate held-out.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Subagente con contexto aislado (quick/full) | subagent | no | `claude_code`; `codex`; `hermes` |
| `run-evals` con CLI `claude` o `codex` | command | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### skill-optimizer / `claude_code`: `compatible`

audit no depende del agente; quick/full requieren subagente aislado y run-evals.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `audit` | sí | `enabled` | `native` | Fase 1 read-only y reporte. | — | Audit real ejecutado sobre 10 skills. | Resultado AUDIT_ONLY.; prueba `claude-real-audit` |
| `isolated-evaluation` | no | `unverified` | `native` | `Agent` con handle. | Sin evaluador aislado no se aplica ningún candidato. | No ejecutada en Claude Code en esta auditoría. | — |

#### skill-optimizer / `codex`: `unverified`

audit no depende del agente; quick/full requieren subagente aislado y un CLI de run-evals (claude o codex). No ejecutada en Codex CLI.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: spawn_agent.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `audit` | sí | `unverified` | `native` | Fase 1 read-only y reporte. | — | No ejecutada en Codex CLI en esta auditoría. | — |
| `isolated-evaluation` | no | `unverified` | `alternative` | `spawn_agent` + `wait_agent`. | Sin evaluador aislado no se aplica ningún candidato. | No ejecutada en Codex CLI en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `isolated-evaluation` | `spawn_agent` + `wait_agent`. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Codex CLI en esta auditoría. |

#### skill-optimizer / `hermes`: `unverified`

audit no depende del agente; quick/full requieren subagente aislado y un CLI de run-evals (claude o codex). No ejecutada en Hermes Agent.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: delegate_task (contexto nuevo).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `audit` | sí | `unverified` | `native` | Fase 1 read-only y reporte. | — | No ejecutada en Hermes Agent en esta auditoría. | — |
| `isolated-evaluation` | no | `unverified` | `alternative` | `delegate_task`. | Sin evaluador aislado no se aplica ningún candidato. | No ejecutada en Hermes Agent en esta auditoría. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `isolated-evaluation` | `delegate_task`. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Hermes Agent en esta auditoría. |

**Implementación**

- Adaptaciones: Sección «Compatibilidad entre agentes» para quick/full.
- Archivos modificados: `plugins/golfo-kit/skills/skill-optimizer/SKILL.md`.
- Fallback: Modo diagnóstico sin aplicar candidatos..
- Cambios de comportamiento respecto del original: Ninguno..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `claude-real-audit` | `claude_code` | real_run | `/skill-optimizer mode=audit sobre las 10 skills modificadas` | `passed` | AUDIT_ONLY: quick_validate válido en 9 skills; el error de agent-ready-setup (SKILL.md anidados en assets/) también aparece en origin/main; links relativos resuelven; hallazgo menor en user-manual corregido. |

Pendiente de verificar:

- Ejecutar audit y quick en Claude Code.
- Ejecutar audit y quick en Codex CLI.
- Ejecutar audit y quick en Hermes Agent.

### `stacked-pr`

**Identificación**

- Nombre: Stacked PRs por responsabilidad; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/stacked-pr/SKILL.md`.
- Propósito: Gestiona stacked PRs por responsabilidad con golden diff y CI por capa.
- Funcionalidades principales: división de PRs; rebase de capas.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| `git` en PATH | command | sí | `claude_code`; `codex`; `hermes` |
| `gh` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### stacked-pr / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### stacked-pr / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### stacked-pr / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `test-best-practices`

**Identificación**

- Nombre: test-best-practices; versión: 2.0.0; SKILL.md: `plugins/golfo-kit/skills/test-best-practices/SKILL.md`.
- Propósito: Estandariza tests con Vitest y Testing Library.
- Funcionalidades principales: naming y AAA; aserciones estrictas.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### test-best-practices / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### test-best-practices / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### test-best-practices / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `test-planning`

**Identificación**

- Nombre: Test Planning; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/test-planning/SKILL.md`.
- Propósito: Planifica casos y cobertura de tests antes de escribirlos.
- Funcionalidades principales: modo casos; modo cobertura.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### test-planning / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### test-planning / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### test-planning / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `typed-errors-refactor`

**Identificación**

- Nombre: Typed Errors Refactor; versión: 1.0.0; SKILL.md: `plugins/golfo-kit/skills/typed-errors-refactor/SKILL.md`.
- Propósito: Diseña y ejecuta refactors de errores tipados.
- Funcionalidades principales: jerarquía de errores; normalización.
- Agentes soportados declarados: no declara.

**Dependencias**

Sin dependencias específicas de agente detectadas por inspección.

**Compatibilidad por agente**

#### typed-errors-refactor / `claude_code`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Claude Code durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### typed-errors-refactor / `codex`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Codex CLI durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

#### typed-errors-refactor / `hermes`: `unverified`

Sin dependencias específicas de agente detectadas por inspección. No se ejecutó en Hermes Agent durante esta auditoría, así que su funcionamiento no está verificado.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |

**Implementación**

- Adaptaciones: ninguna.
- Archivos modificados: ninguno.
- Fallback: ninguno.
- Cambios de comportamiento respecto del original: ninguno.

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.

### `ui-ux-flow-patterns`

**Identificación**

- Nombre: UI/UX por flujo: componentes, estados y feedback; versión: 1.2.0; SKILL.md: `plugins/golfo-kit/skills/ui-ux-flow-patterns/SKILL.md`.
- Propósito: Define componentes, estados y feedback por flujo de UI.
- Funcionalidades principales: estados loading/vacío/error; toast, banner, diálogo.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Verificación en navegador: Claude in Chrome o MCP de navegador / plugin chrome@openai-bundled (clics y consola) / browser_exec o Playwright por terminal | tool | no | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### ui-ux-flow-patterns / `claude_code`: `unverified`

Sin dependencias obligatorias de agente. La verificación en navegador usa Claude in Chrome o un MCP de navegador (no conectados en la auditoría); el fallback por terminal sí corrió. La skill completa no se ejecutó en Claude Code.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Claude Code en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `unverified` | `native` | Claude in Chrome o un MCP de navegador para recorrer cada estado de la UI en el browser (paso 5); si no están, el fallback por terminal de agent-capabilities.md. | Lighthouse, Chrome headless con log y Playwright por terminal (verificados desde Claude Code). | Claude in Chrome no estaba conectado en la sesión de esta auditoría: el camino nativo no se ejecutó. El fallback por terminal sí corrió desde Claude Code. | Corrida real claude-real-terminal-browser (fallback por terminal); prueba `claude-real-terminal-browser` |

#### ui-ux-flow-patterns / `codex`: `unverified`

Verificación en navegador adaptada y verificada: Clics por estado con tab.playwright.getByRole(...).click() y consola con tab.dev.logs del plugin Chrome; en la app de escritorio también el navegador in-app. La skill completa no se ejecutó en Codex CLI.

- Capacidades faltantes: Claude in Chrome.
- Alternativas investigadas: Plugin chrome@openai-bundled (viable); Lighthouse, Chrome headless con log y Playwright por terminal (viable); Plugin browser@openai-bundled / browser-use (iab) (viable); computer-use@openai-bundled (descartado).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Codex CLI en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `adapted` | `alternative` | Clics por estado con tab.playwright.getByRole(...).click() y consola con tab.dev.logs del plugin Chrome; en la app de escritorio también el navegador in-app. | Sin ningún mecanismo, la verificación queda BLOCKED (nunca PASS) y se reporta en Limitaciones del agente. | El plugin Chrome hace clic y lee la consola en el Chrome real del usuario, igual que Claude in Chrome. | Corrida real codex-real-chrome-console-states; Corrida real codex-real-terminal-metrics; Eval simulada eval-sim-codex-walk-states-with-chrome-plugin; prueba `codex-real-chrome-console-states`; prueba `codex-real-terminal-metrics`; prueba `eval-sim-codex-walk-states-with-chrome-plugin` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `browser-verification` | Plugin chrome@openai-bundled | docs/api.json del plugin + corrida real codex-real-chrome-console-states | sí | Chrome real del usuario: tab.dev.logs lee la consola de la carga y getByRole().click() recorre estados. |
| `browser-verification` | Lighthouse, Chrome headless con log y Playwright por terminal | plugins/golfo-kit/references/agent-capabilities.md#verificación-en-navegador-por-terminal + corridas reales | sí | Agnóstico del agente; verificado desde los tres agentes. Sin sesión del usuario: solo localhost/staging sin login o con credenciales de prueba. |
| `browser-verification` | Plugin browser@openai-bundled / browser-use (iab) | plugin.json y docs del plugin | sí | Navegador in-app para localhost; solo en la app de escritorio, no probado desde el CLI. |
| `browser-verification` | computer-use@openai-bundled | plugin.json | no | Toma el escritorio; el plugin Chrome cubre el mismo caso sin hacerlo. |

#### ui-ux-flow-patterns / `hermes`: `unverified`

Verificación en navegador adaptada y verificada por terminal: browser_exec para localhost sin login; si falla dos veces, Playwright por terminal con el Chrome instalado. computer_use solo con sesión requerida y consentimiento. La skill completa no se ejecutó en Hermes Agent.

- Capacidades faltantes: Claude in Chrome.
- Alternativas investigadas: browser_exec (Chromium headless, perfil descartable) (viable); Lighthouse, Chrome headless con log y Playwright por terminal (viable); computer_use sobre el Chrome real (viable).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `core-workflow` | sí | `unverified` | `native` | Instrucciones de la skill; no usa herramientas específicas de agente. | — | Sin dependencias específicas detectadas por inspección; no ejecutada en Hermes Agent en esta auditoría. | Inspección estática (prueba static-inspection).; prueba `static-inspection` |
| `browser-verification` | no | `adapted` | `alternative` | browser_exec para localhost sin login; si falla dos veces, Playwright por terminal con el Chrome instalado. computer_use solo con sesión requerida y consentimiento. | Sin ningún mecanismo, la verificación queda BLOCKED (nunca PASS) y se reporta en Limitaciones del agente. | browser_exec es inestable en esta máquina; Lighthouse, Chrome headless con log y Playwright por terminal logran la misma verificación y corrieron desde Hermes. | Corrida real hermes-real-playwright-states; Corrida real hermes-real-browser-exec-probe; Eval simulada eval-sim-hermes-browser-exec-unstable-playwright-fallback; prueba `hermes-real-playwright-states`; prueba `hermes-real-browser-exec-probe`; prueba `eval-sim-hermes-browser-exec-unstable-playwright-fallback` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `browser-verification` | browser_exec (Chromium headless, perfil descartable) | corrida real hermes-real-browser-exec-probe + doc browser | sí | Sirve para localhost sin login cuando arranca; en esta máquina falló 7 de 9 veces, así que la skill pasa a terminal tras dos fallos. |
| `browser-verification` | Lighthouse, Chrome headless con log y Playwright por terminal | plugins/golfo-kit/references/agent-capabilities.md#verificación-en-navegador-por-terminal + corridas reales | sí | Agnóstico del agente; verificado desde los tres agentes. Sin sesión del usuario: solo localhost/staging sin login o con credenciales de prueba. |
| `browser-verification` | computer_use sobre el Chrome real | lista de herramientas + doc computer-use | sí | Único camino para pantallas que necesitan la sesión del usuario; requiere aviso y consentimiento. No ejecutado. |

**Implementación**

- Adaptaciones: Sección «Compatibilidad entre agentes»: navegador según agent-capabilities.md por herramienta presente, aclaración de que headless no reemplaza el lector de pantalla, y Limitaciones del agente en el reporte; Fila «Verificar en un navegador» y sección «Verificación en navegador por terminal» en plugins/golfo-kit/references/agent-capabilities.md (fuente única compartida).
- Archivos modificados: `plugins/golfo-kit/skills/ui-ux-flow-patterns/SKILL.md`, `plugins/golfo-kit/skills/ui-ux-flow-patterns/evals/eval-config.json`, `plugins/golfo-kit/references/agent-capabilities.md`.
- Fallback: Sin ningún mecanismo de navegador, la verificación queda BLOCKED y se reporta en Limitaciones del agente..
- Cambios de comportamiento respecto del original: Codex recorre los estados con el plugin Chrome; Hermes con Playwright por terminal si browser_exec no arranca. La sección Verificación dice con qué herramienta se recorrió..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `claude-real-terminal-browser` | `claude_code` | real_run | `npx -y lighthouse@12 http://127.0.0.1:8793/ --output=json --only-categories=performance --chrome-flags=--headless=new; chrome.exe --headless=new --enable-logging --log-file=<log> --v=0 --virtual-time-budget=3000 --dump-dom http://127.0.0.1:8793/ (Start-Process -Wait); node walk-states.mjs (playwright-core 1.64.1, channel chrome)` | `passed` | Desde la Bash de Claude Code sobre una página local servida con python -m http.server: Lighthouse 12.8.2 devolvió LCP 1.1 s, CLS 0, TBT 0 ms, FCP 1.1 s; el log de Chrome headless tuvo la línea CONSOLE con el warning de hidratación simulado; Playwright con el Chrome instalado capturó el console.error, la navegación (169 ms) y los cuatro estados (loading, empty, data, error). Claude in Chrome no estaba conectado en la sesión, así que el camino nativo no se ejecutó. |
| `codex-real-chrome-console-states` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<abrir http://127.0.0.1:8793/ en una pestaña nueva del Chrome real con el plugin Chrome, tab.reload(), tab.dev.logs, tab.playwright.evaluate de performance y clic en cada estado>"` | `passed` | agent.browsers.list() → {type: extension, family: chrome, profileName: Guido}; tab.dev.logs devolvió el console.error de hidratación simulado (una entrada por carga); getByRole(...).click() recorrió Carga, Vacío, Con datos y Error con data-current loading/empty/data/error; la pestaña propia se cerró. tab.playwright.evaluate no expone performance ni PerformanceObserver (scope de solo lectura): las métricas no salen del plugin. |
| `codex-real-terminal-metrics` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<npx -y lighthouse@12 … y node walk-states.mjs por exec_command>"` | `passed` | Lighthouse 12.8.2 desde Codex: LCP 1125 ms, CLS 0, TBT 0, FCP 1125 ms. Playwright con el Chrome instalado: console.error de hidratación, navegación 176 ms y los cuatro estados recorridos. |
| `hermes-real-browser-exec-probe` | `hermes` | real_run | `hermes chat -Q -q "<browser_exec: listener de consola antes de navegar, recarga, performance y clic en cada estado de http://127.0.0.1:8793/>"` | `failed` | browser_exec falló al arrancar 7 de 9 veces ('Chrome exited early … without writing DevToolsActivePort'); las dos que arrancaron eran HeadlessChrome/145 sobre about:blank. Había unos 24 Chromium huérfanos con user-data-dir agent-browser-chrome-<uuid> en Temp, que no se mataron. Ninguna verificación de la página se completó con browser_exec. |
| `hermes-real-terminal-console-metrics` | `hermes` | real_run | `hermes chat -Q -q "<solo terminal: Chrome headless con --enable-logging --log-file y npx -y lighthouse@12 sobre http://127.0.0.1:8793/>"` | `passed` | Hermes encontró Chrome y npx; el log tuvo la línea CONSOLE del warning de hidratación simulado; Lighthouse 12.8.2: LCP 1.1 s, CLS 0, TBT 0 ms, FCP 1.1 s (hermes-lh.json de 192 KB). |
| `hermes-real-playwright-states` | `hermes` | real_run | `hermes chat -Q -q "<solo terminal: node walk-states.mjs http://127.0.0.1:8793/ (playwright-core, channel chrome, headless)>"` | `passed` | Salida del script desde Hermes: console.error de hidratación simulado, navegación 175 ms y data-current loading/empty/data/error tras cada clic; exitCode 0. |
| `eval-sim-codex-walk-states-with-chrome-plugin` | `codex` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/ui-ux-flow-patterns --provider claude (solo los casos nuevos)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: codex-walk-states-with-chrome-plugin: recorre cada estado con clics del plugin Chrome, revisa la consola y aclara que no hubo lector de pantalla. |
| `eval-sim-hermes-browser-exec-unstable-playwright-fallback` | `hermes` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/ui-ux-flow-patterns --provider claude (solo los casos nuevos)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: hermes-browser-exec-unstable-playwright-fallback: tras dos fallos de browser_exec recorre los estados con Playwright por terminal, descarta computer_use (no hace falta sesión) y verifica el doble clic. |

Pendiente de verificar:

- Ejecutar la skill en Claude Code con un caso real.
- Ejecutar la skill en Codex CLI con un caso real.
- Ejecutar la skill en Hermes Agent con un caso real.
- Claude Code: verificación en navegador con Claude in Chrome conectado (camino nativo).
- Hermes: pantallas que requieren la sesión del usuario con computer_use (con consentimiento) o browser_exec con perfil real.

### `user-manual`

**Identificación**

- Nombre: User Manual Generator; versión: 2.5.0; SKILL.md: `plugins/golfo-kit/skills/user-manual/SKILL.md`.
- Propósito: Genera o actualiza manuales de usuario HTML autocontenidos con capturas reales de la app.
- Funcionalidades principales: preguntas de dispositivo, idiomas y repo; mapa de visibilidad; HTML con DESIGN.md; capturas reales; publicación.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| Herramienta de preguntas | tool | no | `claude_code`; `codex`; `hermes` |
| Herramienta JavaScript de navegador (capturas) | tool | no | `claude_code`; `codex`; `hermes` |
| `node`, `python` en PATH | command | sí | `claude_code`; `codex`; `hermes` |

**Compatibilidad por agente**

#### user-manual / `claude_code`: `unverified`

Preguntas adaptadas por agente con fallback en texto; capturas con la herramienta JavaScript de navegador de cada agente (Claude in Chrome, runtime de navegador de Codex, browser_exec de Hermes) o mockups dibujados. No ejecutada en Claude Code.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-device-languages` | sí | `unverified` | `native` | `AskUserQuestion`. | Pregunta en texto y detención. | No ejecutada en Claude Code en esta auditoría. | — |
| `manual-generation` | sí | `unverified` | `native` | Pasos 1 a 5 con los helpers de scripts/. | — | No ejecutada en Claude Code en esta auditoría. | — |
| `real-app-captures` | no | `unverified` | `native` | frame-driver.js + capture-bridge.py desde el navegador del agente. | Mockups dibujados (mockup-body), declarados en el reporte. | No ejecutada en Claude Code en esta auditoría. | — |

#### user-manual / `codex`: `unverified`

Preguntas adaptadas por agente con fallback en texto; capturas con la herramienta JavaScript de navegador de cada agente (Claude in Chrome, runtime de navegador de Codex, browser_exec de Hermes) o mockups dibujados. No ejecutada en Codex CLI.

- Capacidades faltantes: request_user_input fuera del modo Plan.
- Alternativas investigadas: request_user_input en modo Plan.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-device-languages` | sí | `unverified` | `alternative` | Texto y detención; `request_user_input` solo en modo Plan. | Pregunta en texto y detención. | No ejecutada en Codex CLI en esta auditoría. | — |
| `manual-generation` | sí | `unverified` | `native` | Pasos 1 a 5 con los helpers de scripts/. | — | No ejecutada en Codex CLI en esta auditoría. | — |
| `real-app-captures` | no | `unverified` | `alternative` | capture-snippet.js evaluado en una pestaña del Chrome del usuario (plugin Chrome) o del navegador in-app para un dev server sin login. | Mockups dibujados (mockup-body) y Limitaciones del agente. | El runtime de navegador de Codex evalúa JavaScript en la página (verificado leyendo #ua en codex-real-chrome-capture de pr-description-template); la inyección del snippet no se ejecutó. | Corrida real de captura en Chrome desde codex exec (pr-description-template); prueba `eval-sim-codex-browser-runtime` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ask-device-languages` | Texto y detención; `request_user_input` solo en modo Plan. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Codex CLI en esta auditoría. |
| `real-app-captures` | Plugin chrome@openai-bundled vía mcp__cua_repl.js | corrida real en codex exec | sí | Evalúa JS en el Chrome real del usuario. |
| `real-app-captures` | Navegador in-app (iab) | plugin.json del plugin browser | sí | Sirve para dev servers sin login. |
| `real-app-captures` | computer-use | plugin.json | no | No evalúa scripts en la página. |

#### user-manual / `hermes`: `unverified`

Preguntas adaptadas por agente con fallback en texto; capturas con la herramienta JavaScript de navegador de cada agente (Claude in Chrome, runtime de navegador de Codex, browser_exec de Hermes) o mockups dibujados. No ejecutada en Hermes Agent.

- Capacidades faltantes: ninguna.
- Alternativas investigadas: clarify; toolset browser.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `ask-device-languages` | sí | `unverified` | `alternative` | `clarify`; texto ante undelivered/timed_out/cancelled. | Pregunta en texto y detención. | No ejecutada en Hermes Agent en esta auditoría. | — |
| `manual-generation` | sí | `unverified` | `native` | Pasos 1 a 5 con los helpers de scripts/. | — | No ejecutada en Hermes Agent en esta auditoría. | — |
| `real-app-captures` | no | `unverified` | `alternative` | capture-snippet.js con el helper js() de browser_exec; use_real_profile para pantallas con la sesión del usuario. | Mockups dibujados (mockup-body) y Limitaciones del agente. | browser_exec evalúa JS, pero en esta máquina falló al arrancar 4 de 5 veces; no verificado. | Doc de Hermes (browser); Corrida real hermes-real-browser-probe (pr-description-template); prueba `eval-sim-drawn-mockups-fallback` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `ask-device-languages` | `clarify`; texto ante undelivered/timed_out/cancelled. | Auditoría 1.0.0 (PR #22) y plugins/golfo-kit/references/agent-capabilities.md | sí | No ejecutada en Hermes Agent en esta auditoría. |
| `real-app-captures` | browser_exec + js() | doc browser | sí | Evalúa scripts en la página; headless sirve para clonar DOM y CSS. |
| `real-app-captures` | computer_use | doc computer-use | no | No evalúa scripts en la página. |

**Implementación**

- Adaptaciones: Sección «Agent compatibility»: preguntas por agente con fallback en texto y detención; Tabla de la «herramienta JavaScript de navegador» por agente y fallback explícito a mockups dibujados.
- Archivos modificados: `plugins/golfo-kit/skills/user-manual/SKILL.md`, `plugins/golfo-kit/skills/user-manual/evals/eval-config.json`.
- Fallback: Pregunta en texto con detención..
- Cambios de comportamiento respecto del original: Ninguno en Claude Code..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `design-tokens-bats` | `any` | bats | `bats plugins/golfo-kit/skills/user-manual/tests/check-design-tokens.bats` | `passed` | Suite del chequeo de tokens de DESIGN.md (agnóstica de agente). |
| `eval-sim-codex-browser-runtime` | `codex` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/user-manual --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: codex-browser-runtime-for-captures: inyecta capture-snippet.js con mcp__cua_repl.js en el Chrome del usuario. |
| `eval-sim-drawn-mockups-fallback` | `hermes` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/user-manual --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: no-script-browser-falls-back-to-drawn-mockups: sin navegador que evalúe scripts cae a mockups dibujados. |

Pendiente de verificar:

- Generar un manual real en Claude Code.
- Generar un manual real en Codex CLI.
- Generar un manual real en Hermes Agent.
- Codex: inyectar capture-snippet.js y exportar una captura real.
- Hermes: browser_exec estable para inyectar el snippet.

### `widget-ui-proposals`

**Identificación**

- Nombre: Widget-driven UI/UX proposals & previews; versión: 1.3.0; SKILL.md: `plugins/golfo-kit/skills/widget-ui-proposals/SKILL.md`.
- Propósito: Muestra propuestas y previews de UI como widgets visuales interactivos antes de escribir código.
- Funcionalidades principales: Propuestas de UI como widget interactivo; Preview del cambio antes de aplicarlo; Aplicar las opciones elegidas e iterar.
- Agentes soportados declarados: no declara.

**Dependencias**

| Dependencia | Tipo | Obligatoria | Agentes que la tienen |
|---|---|---|---|
| mcp__visualize__show_widget / read_me | mcp | no | `claude_code` |
| Plugin visualize@openai-bundled (skill visualize) | skill | no | `codex` |
| Shell + navegador headless (chrome --headless --screenshot o browser_exec) para el preview estático | command | no | `claude_code`; `codex`; `hermes` |
| Herramienta de preguntas (clarify) o texto para elegir | tool | no | `hermes` |

**Compatibilidad por agente**

#### widget-ui-proposals / `claude_code`: `unverified`

Modo original con show_widget en sesiones Claude con el conector visualize (no verificado: el conector no está en sesiones headless). En sesiones headless aplica el preview estático.

- Capacidades faltantes: mcp__visualize__show_widget en la sesión probada.
- Alternativas investigadas: ninguna.

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `render-widget` | sí | `unverified` | `native` | Widget interactivo. | — | La herramienta no está en la sesión headless probada; no se probó en una sesión con el conector. | — |
| `apply-proposal` | no | `unverified` | `native` | Botón Aplicar del widget. | — | Depende del widget. | — |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `render-widget` | Preview estático (HTML → PNG) | SKILL.md de la skill | sí | Fallback para sesiones headless sin el conector. |
| `apply-proposal` | Preview estático (HTML → PNG) | SKILL.md de la skill | sí | Fallback para sesiones headless sin el conector. |

#### widget-ui-proposals / `codex`: `adapted`

En la app de escritorio, modo Codex con el plugin visualize (generación verificada; render no observado). En el CLI y codex exec, preview estático HTML → PNG (verificado en codex exec).

- Capacidades faltantes: mcp__visualize__show_widget.
- Alternativas investigadas: plugin visualize@openai-bundled (adoptado); preview estático HTML → PNG (fallback); navegador in-app browser@openai-bundled (descartado).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `render-widget` | sí | `adapted` | `alternative` | App de escritorio (herramientas codex_app en la sesión): modo Codex con el plugin visualize (fragmento + visualize{…}, .viz-carousel). CLI o codex exec: preview estático HTML → PNG con Chrome headless. | Sin ninguna vía de render, detenerse y reportar. | Codex no tiene show_widget, pero su plugin visualize logra el mismo resultado (visual interactivo en la conversación) con otro mecanismo. | $CODEX_HOME/plugins/cache/openai-bundled/visualize/1.0.50/skills/visualize/SKILL.md y tweak.md; La skill visualize:visualize aparece en codex exec; En codex exec la referencia visualize{…} queda como texto: por eso el CLI usa el preview estático (hallazgo de Codex en el PR #23).; prueba `codex-real-visualize-fragment`; prueba `codex-real-cli-static-preview`; prueba `eval-sim-codex-visualize` |
| `apply-proposal` | no | `unverified` | `alternative` | Botón Aplicar dentro de cada variante con window.openai.sendFollowUpMessage({prompt: 'Implementá: …'}); también se acepta que el usuario nombre la opción en el chat. | Elegir en el chat por nombre de variante. | El fragmento con sendFollowUpMessage se generó en una corrida real, pero el clic solo existe en la app de escritorio y no se observó. | skills/visualize/SKILL.md del plugin visualize; prueba `codex-real-visualize-fragment`; prueba `eval-sim-codex-visualize` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `render-widget` | Plugin visualize@openai-bundled | config.toml + skills/visualize/SKILL.md 1.0.50 + codex exec | sí | Mismo resultado: visual interactivo en la conversación con variantes y acciones. |
| `render-widget` | Preview estático (HTML → PNG con navegador headless) | chrome --headless; prueba en Hermes | sí | Funciona, pero pierde interactividad; queda como fallback. |
| `render-widget` | browser@openai-bundled (navegador in-app) | plugin.json del plugin browser | no | Abre páginas para el agente; no muestra un visual dentro del chat. |
| `apply-proposal` | window.openai.sendFollowUpMessage | skills/visualize/SKILL.md | sí | Equivale a sendPrompt: el clic continúa la conversación. |
| `apply-proposal` | Elección por nombre en el chat | SKILL.md de widget-ui-proposals | sí | Siempre disponible como respaldo. |

#### widget-ui-proposals / `hermes`: `adapted`

Adaptada con un preview estático: HTML renderizado a PNG, entregado por ruta o por el gateway, y elección con clarify u opciones numeradas. Se pierde la interactividad dentro del chat.

- Capacidades faltantes: widget interactivo en el chat.
- Alternativas investigadas: preview estático HTML → PNG con Chrome headless (adoptado); browser_exec + capture_screenshot (segunda opción, inestable); clarify / opciones numeradas para elegir (adoptado).

| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |
|---|---|---|---|---|---|---|---|
| `render-widget` | sí | `adapted` | `alternative` | Preview estático: HTML autocontenido renderizado a PNG con chrome --headless (o browser_exec + capture_screenshot), revisado con vision y entregado por ruta (CLI) o subido por el gateway. | Sin shell ni navegador, detenerse y reportar. | Hermes no muestra widgets en el chat, pero puede mostrar una imagen fiel de las propuestas; se pierde la interactividad (documentado en la skill). | Doc de Hermes: deliverable-mode y browser; Sesión real de Hermes; prueba `hermes-real-static-preview`; prueba `eval-sim-hermes-static-preview` |
| `apply-proposal` | no | `adapted` | `alternative` | clarify con multi_select (≤ 4 opciones); ante undelivered/timed_out/cancelled, opciones numeradas en el chat y detenerse. El HTML copia la instrucción Implementá: … al portapapeles. | Opciones numeradas en el chat. | La elección vuelve por clarify o por respuesta en el chat en lugar de un clic; mismo resultado (aplicar solo lo elegido). | Corrida real: clarify sin usuario en -q → opciones numeradas y detención; prueba `hermes-real-static-preview`; prueba `eval-sim-hermes-static-preview` |

| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |
|---|---|---|---|---|
| `render-widget` | HTML → PNG con Chrome headless | corrida real hermes-real-static-preview | sí | Produce la imagen de las variantes; estable. |
| `render-widget` | browser_exec + capture_screenshot() | doc de Hermes y corrida real del 2026-10-23 | sí | Funciona en teoría, pero en esta máquina el Chromium de Hermes falló al arrancar 4 de 5 veces; queda como segunda opción. |
| `render-widget` | Entrega por gateway (Telegram) mencionando la ruta absoluta | doc deliverable-mode | sí | Muestra la imagen inline en mensajería; en el CLI solo se da la ruta. |
| `render-widget` | Widget interactivo | lista de herramientas de Hermes | no | No existe ninguna herramienta de widget en Hermes. |
| `apply-proposal` | clarify (multi_select) | tools-reference de Hermes | sí | Pregunta con opciones componibles. |
| `apply-proposal` | Opciones numeradas en el chat | corrida real | sí | Verificado como fallback en -q. |

**Implementación**

- Adaptaciones: Modo Codex con el plugin visualize (fragmento HTML, visualize{…}, .viz-carousel, sendFollowUpMessage); Modo de preview estático (HTML → PNG con navegador headless, clarify u opciones numeradas) para Hermes y otros agentes con shell; Detención con Limitaciones del agente solo sin ninguna vía de render.
- Archivos modificados: `plugins/golfo-kit/skills/widget-ui-proposals/SKILL.md`, `plugins/golfo-kit/skills/widget-ui-proposals/evals/eval-config.json`.
- Fallback: Preview estático; sin shell ni navegador, detenerse y reportar..
- Cambios de comportamiento respecto del original: Codex: mismo flujo con otro mecanismo de render. Hermes: la vista es una imagen fija y la elección vuelve por pregunta, no por clic..

**Verificación**

| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |
|---|---|---|---|---|---|
| `static-inspection` | `any` | static | `grep -rE "AskUserQuestion\|request_user_input\|Monitor\|Cron(Create\|List\|Delete)\|PushNotification\|TaskStop\|Agent\|subagent\|mcp__\|claude -p\|codex exec\|~/.claude\|~/.codex\|apply_patch\|update_plan" plugins/golfo-kit/skills/<skill>` | `passed` | Inspección de SKILL.md, references y scripts del 2026-10-23; las coincidencias de "hook" son hooks de React o de git, no hooks de agente. |
| `codex-real-visualize-fragment` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<leer y seguir widget-ui-proposals/SKILL.md; dos variantes del botón Guardar cambios>" (en un directorio temporal)` | `passed` | Codex 0.162.1 eligió el modo Codex, escribió guardar-cambios.html (5582 bytes, fragmento sin <html>/<head>/<body>) con un .viz-carousel de dos hijos data-variant="Sólida azul"/"Outline" y botones Aplicar con window.openai.sendFollowUpMessage, y terminó la respuesta con visualize{"path":"C:/Users/guido/AppData/Local/Temp/rt-codex-widget/guardar-cambios.html"} en una línea propia más la recomendación. El render interactivo en la app de escritorio no se observó (codex exec es terminal). |
| `hermes-real-static-preview` | `hermes` | real_run | `hermes chat -Q -q "<leer y seguir widget-ui-proposals/SKILL.md; tres variantes del header de una tabla de pedidos>" (en un directorio temporal)` | `passed` | Hermes 0.22.4 eligió el modo de preview estático: escribió propuestas-header-pedidos.html autocontenido, lo renderizó con chrome --headless y un --user-data-dir temporal a propuestas-header-pedidos.png (tarjetas A/B/C, B recomendada), revisó la imagen, corrigió la fila de filtros recortada y re-renderizó; clarify no tenía usuario (-q), así que pasó a opciones numeradas y se detuvo sin aplicar nada; reportó la pérdida de interactividad en Limitaciones del agente y dio las rutas absolutas. |
| `eval-sim-codex-visualize` | `codex` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/widget-ui-proposals --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: codex-visualize-mode-without-show-widget: modo Codex con visualize{…}, .viz-carousel, sendFollowUpMessage y sin show_widget. codex-cli-falls-back-to-static-preview: en codex exec usa el preview estático. |
| `eval-sim-hermes-static-preview` | `hermes` | simulated_eval | `run-evals <copia filtrada>/plugins/golfo-kit/skills/widget-ui-proposals --provider claude (solo los casos nuevos o modificados)` | `passed` | Claude (claude-sonnet-5-5) simulando el agente: hermes-static-preview-with-clarify: PNG con --screenshot, clarify multi_select y Limitaciones del agente; no-visual-capability-blocks-with-limitations: sin vía de render se detiene sin simular. |
| `codex-real-cli-static-preview` | `codex` | real_run | `codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "<leer y seguir widget-ui-proposals/SKILL.md; dos variantes del botón Guardar cambios>" (en un directorio temporal)` | `passed` | Tras exigir un frontend que renderice: en codex exec (sin herramientas codex_app) eligió el modo de preview estático, escribió guardar-cambios-variantes.html, lo renderizó con Chrome headless y un perfil temporal a guardar-cambios-variantes.png, revisó la imagen, dio la recomendación y reportó la imagen estática en Limitaciones del agente. |

Pendiente de verificar:

- Claude: probar en una sesión con el conector visualize.
- Codex: observar el render y el clic de Aplicar en la app de escritorio.
- Hermes: verificar la entrega inline de la PNG por el gateway de Telegram.

## D. Registro de incompatibilidades

| ID | Skill | Agente | Funcionalidad | Dependencia faltante | Motivo técnico | Alternativas investigadas | Solución o bloqueo | Severidad | Estado |
|---|---|---|---|---|---|---|---|---|---|
| `INC-agent-ready-setup--hermes--provider-autodetect` | `agent-ready-setup` | `hermes` | `provider-autodetect` | Provider Hermes en resolve-provider.sh | La skill genera configuración solo para Claude Code y Codex. | agregar Hermes como provider de destino (fuera de alcance) | Resuelto: resolve-provider.sh reconoce instalaciones de Hermes. | `low` | `resolved` |
| `INC-codex-autofix-loop--codex--pr-event-watch` | `codex-autofix-loop` | `codex` | `pr-event-watch` | Herramienta para esperar eventos después del turno | Codex CLI no expone Monitor, cron ni procesos en background que despierten al agente. | exec_command/write_stdin dentro del turno; codex exec resume desde un watcher externo; automatizaciones de la app de escritorio | Resuelto con el modo C (watcher en foreground dentro del turno). | `medium` | `resolved` |
| `INC-codex-autofix-loop--codex--backup-schedule` | `codex-autofix-loop` | `codex` | `backup-schedule` | Scheduler de sesión | No hay cron en Codex CLI. | automatizaciones de la app (no verificadas) | Resuelto con el modo C (watcher en foreground dentro del turno). | `low` | `resolved` |
| `INC-codex-autofix-loop--codex--auto-relaunch` | `codex-autofix-loop` | `codex` | `auto-relaunch` | Mecanismo para seguir vivo tras `@codex review` | El paso (7) no es ejecutable sin espera supervisada. | ídem pr-event-watch | Resuelto con el modo C (watcher en foreground dentro del turno). | `low` | `resolved` |
| `INC-codex-autofix-loop--codex--fix-round` | `codex-autofix-loop` | `codex` | `fix-round` | Evidencia de ejecución en Codex | La ronda completa no se ejecutó en Codex y `run-evals --provider codex` falla en Windows por el sandbox. | corrida real con --dangerously-bypass-approvals-and-sandbox sobre un PR de prueba | Pendiente: correr una ronda real en un PR de prueba. | `high` | `pending` |
| `INC-codex-autofix-loop--hermes--fix-round` | `codex-autofix-loop` | `hermes` | `fix-round` | Evidencia de ejecución en Hermes | Solo se ejecutaron el watcher y la elección de modo; fixes, closeout y merge no. | loop completo sobre un PR de prueba con delegate_task | Pendiente: correr el loop completo en Hermes sobre un PR de prueba. | `high` | `pending` |
| `INC-measured-performance-optimization--hermes--browser-verification` | `measured-performance-optimization` | `hermes` | `browser-verification` | browser_exec estable | browser_exec falló al arrancar 7 de 9 veces (DevToolsActivePort) con Chromium huérfanos de corridas previas. | Lighthouse, Chrome headless con log y Playwright por terminal; computer_use | Mitigado: la skill pasa a la terminal tras dos fallos; la causa de la inestabilidad sigue abierta (ACT-006). | `low` | `mitigated` |
| `INC-pr-description-template--codex--ui-screenshots` | `pr-description-template` | `codex` | `ui-screenshots` | Claude in Chrome | Las capturas publicadas deben salir del navegador real del usuario. | browser_use de Codex | Resuelto con un navegador real del usuario alternativo; ver «Capture browser» en la skill. | `low` | `resolved` |
| `INC-pr-description-template--hermes--ui-screenshots` | `pr-description-template` | `hermes` | `ui-screenshots` | Claude in Chrome | Las capturas publicadas deben salir del navegador real del usuario. | toolset browser de Hermes | Resuelto con un navegador real del usuario alternativo; ver «Capture browser» en la skill. | `low` | `resolved` |
| `INC-prevent-ssr-hydration-mismatches--hermes--browser-verification` | `prevent-ssr-hydration-mismatches` | `hermes` | `browser-verification` | browser_exec estable | browser_exec falló al arrancar 7 de 9 veces (DevToolsActivePort) con Chromium huérfanos de corridas previas. | Lighthouse, Chrome headless con log y Playwright por terminal; computer_use | Mitigado: la skill pasa a la terminal tras dos fallos; la causa de la inestabilidad sigue abierta (ACT-006). | `low` | `mitigated` |
| `INC-review-fix-loop--codex--isolated-filter` | `review-fix-loop` | `codex` | `isolated-filter` | Subagente aislado read-only | spawn_agent no tiene un modo read-only verificado. | spawn_agent | Resuelto con un proceso externo claude -p limitado a Read/Grep/Glob. | `low` | `resolved` |
| `INC-review-fix-loop--hermes--isolated-filter` | `review-fix-loop` | `hermes` | `isolated-filter` | Subagente aislado read-only | delegate_task hereda los toolsets del padre, incluida la escritura. | delegate_task | Resuelto con un proceso externo claude -p limitado a Read/Grep/Glob. | `low` | `resolved` |
| `INC-ui-ux-flow-patterns--hermes--browser-verification` | `ui-ux-flow-patterns` | `hermes` | `browser-verification` | browser_exec estable | browser_exec falló al arrancar 7 de 9 veces (DevToolsActivePort) con Chromium huérfanos de corridas previas. | Lighthouse, Chrome headless con log y Playwright por terminal; computer_use | Mitigado: la skill pasa a la terminal tras dos fallos; la causa de la inestabilidad sigue abierta (ACT-006). | `low` | `mitigated` |
| `INC-widget-ui-proposals--codex--render-widget` | `widget-ui-proposals` | `codex` | `render-widget` | mcp__visualize__show_widget | El conector visualize solo existe en sesiones Claude. | HTML estático; texto; browser_use | Resuelto con una alternativa equivalente; ver la funcionalidad y la sección «Agent compatibility» de la skill. | `medium` | `resolved` |
| `INC-widget-ui-proposals--codex--apply-proposal` | `widget-ui-proposals` | `codex` | `apply-proposal` | Botón sendPrompt del widget | Depende del render del widget. | elección en texto | Resuelto con una alternativa equivalente; ver la funcionalidad y la sección «Agent compatibility» de la skill. | `low` | `resolved` |
| `INC-widget-ui-proposals--hermes--render-widget` | `widget-ui-proposals` | `hermes` | `render-widget` | mcp__visualize__show_widget | El conector visualize solo existe en sesiones Claude. | HTML estático; texto; toolset browser | Resuelto con una alternativa equivalente; ver la funcionalidad y la sección «Agent compatibility» de la skill. | `medium` | `resolved` |
| `INC-widget-ui-proposals--hermes--apply-proposal` | `widget-ui-proposals` | `hermes` | `apply-proposal` | Botón sendPrompt del widget | Depende del render del widget. | elección en texto | Resuelto con una alternativa equivalente; ver la funcionalidad y la sección «Agent compatibility» de la skill. | `low` | `resolved` |

## E. Plan de acciones pendientes

| Prioridad | ID | Impacto | Acción recomendada | Criterio de resolución | Incompatibilidades |
|---|---|---|---|---|---|
| 1 | `ACT-001` | `high` | Correr codex-autofix-loop completo en Hermes (modo B) sobre un PR de prueba: delegate_task, kill del watcher, closeout y merge gates. | Prueba real_run en Hermes con fix, closeout y gates observados; features fix-round, merge-gates, round-caps y auto-cancel en adapted o enabled. | `INC-codex-autofix-loop--hermes--fix-round` |
| 2 | `ACT-002` | `high` | Correr codex-autofix-loop en Codex (modo C) sobre un PR de prueba hasta que una respuesta real de Codex dispare la iteración siguiente. | Prueba real_run en Codex con auto-relaunch, fix-round y merge-gates observados. | `INC-codex-autofix-loop--codex--fix-round` |
| 3 | `ACT-003` | `medium` | Verificar las alternativas implementadas sin ejecución: capturas de Hermes con computer_use o perfil real, render de visualize y clic de Aplicar en la app de escritorio de Codex, inyección de capture-snippet.js en Codex. | Cada una tiene una prueba real_run aprobada en su agente. | `INC-pr-description-template--hermes--ui-screenshots`; `INC-widget-ui-proposals--codex--apply-proposal` |
| 4 | `ACT-004` | `medium` | Habilitar `run-evals --provider codex` en Windows (sandbox read-only no puede crear procesos) o correr las evals de Codex en Linux/CI. | Los casos nuevos pasan con provider codex. | — |
| 5 | `ACT-005` | `medium` | Ejecutar en Codex y Hermes las skills sin dependencias de agente con un caso real cada una, empezando por las de flujo GitHub (feature-branch-pr, stacked-pr, pr-inline-comment-template). | Cada skill tiene una prueba eval o real_run aprobada por agente y su estado pasa de unverified a compatible. | — |
| 6 | `ACT-006` | `low` | Investigar por qué browser_exec de Hermes no arranca de forma estable en esta máquina (Chromium 145, gateway elevado; falló 4 de 5 y 7 de 9 veces, con unos 24 Chromium huérfanos agent-browser-chrome-<uuid> en Temp). | browser_exec abre y captura una página local en 5 de 5 intentos. | `INC-measured-performance-optimization--hermes--browser-verification`; `INC-prevent-ssr-hydration-mismatches--hermes--browser-verification`; `INC-ui-ux-flow-patterns--hermes--browser-verification` |
| 7 | `ACT-007` | `low` | Verificar el camino nativo de browser-verification en Claude Code con Claude in Chrome conectado, y en Hermes las pantallas con sesión del usuario con computer_use (con consentimiento) en measured-performance-optimization, prevent-ssr-hydration-mismatches y ui-ux-flow-patterns. | Prueba real_run aprobada en Claude Code con Claude in Chrome y en Hermes con computer_use; browser-verification de Claude Code pasa a enabled. | — |
