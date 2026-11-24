# Conflictos estructurales

Los chequeos sin IA de una selección y los que comparan skills:
- qué suma al contexto de cada sesión;
- qué choca con lo instalado en la máquina;
- qué rules contradice el repo, y qué rules deciden la misma `key` de forma distinta;
- qué hooks, permisos o settings chocan;
- la paridad entre providers, variables de entorno y CI;
- qué skills compiten;
- cómo se juntan todos en `agent-ready conflicts`, al iniciar sesión, al editar y para autores de packs.

Leer al explicar un conflicto estructural del plan, de `status` o de `check`. Las revisiones de IA, su caché y
las contradicciones entre rules están en [ai-reviews.md](ai-reviews.md).

## Contenido

1. Presupuesto de contexto
2. Choques con la máquina
3. Rules contra la realidad del repo
4. Hooks, permisos y settings
5. Paridad entre providers, variables de entorno y CI
6. Skills que compiten
7. Todos los conflictos juntos

## 1. Presupuesto de contexto

Cada profile suma texto que el agente carga en todas las sesiones, y con varios profiles juntos el
contexto se llena sin que nadie lo note. `agent-ready plan` informa cuánto suma la selección, sin IA:

```text
Context at the start of a session: AGENTS.md ~3590 bytes; 20 rules without paths: ~84643 bytes; MCP servers: 2
```

- **AGENTS.md**: el archivo como quedaría después del apply, con lo propio del proyecto (o el
  esqueleto de uno nuevo), el bloque gestionado y la sección de cada stack. Codex corta los AGENTS.md
  combinados en `project_doc_max_bytes` (32 KiB por default).
- **Rules sin `paths:`**: Claude carga al inicio de cada sesión toda rule de `.agents/rules/` que no
  declara `paths:` en su frontmatter, gestionada o propia del proyecto. Las que tienen `paths:` se
  cargan solo al tocar esos archivos y no cuentan, y tampoco las de un profile que la selección deja,
  porque el apply las retira.
- **Servidores MCP**: los que el apply registra: los del browser si `tools.enabled` está prendido, y
  los de los packs que la política permite. Cada uno suma la definición de sus herramientas.

Al pasar un umbral, `plan` avisa y nombra los profiles que más suman, para mover contenido a rules
con `paths:` o a skills, que se cargan solo cuando hacen falta. El aviso no frena el apply. Con
`--json`, el detalle va en `context`.

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.contextBudget.enabled` | `true` | `false` no calcula el presupuesto |
| `conflicts.contextBudget.bytes` | `32768` | avisa cuando AGENTS.md pasa esos bytes |
| `conflicts.contextBudget.rulesBytes` | sin valor | avisa cuando las rules sin `paths:` pasan esos bytes; sin valor, solo informa |

## 2. Choques con la máquina

`agent-ready plan` compara la selección con lo que el usuario ya tiene instalado. Solo lee la
configuración del usuario y nunca la escribe.

- **Sombra:** una skill, un subagente o un comando de un profile con el mismo nombre que uno del
  usuario (`~/.claude/skills`, `~/.claude/agents`, `~/.claude/commands`, `~/.agents/skills`,
  `$CODEX_HOME/agents`) o de un
  plugin instalado. Cada provider aplica su precedencia en silencio, y `plan` dice cuál gana:
  - Claude Code usa la skill o el comando del usuario antes que el del proyecto; los de un plugin
    tienen namespace (`/plugin:skill`), así que se cargan los dos.
  - Claude Code usa el subagente del proyecto antes que el del usuario y el de un plugin.
  - Codex lista las dos skills, sin un orden documentado; tampoco documenta cuál gana entre un
    subagente del proyecto (`.codex/agents`) y uno del usuario (`$CODEX_HOME/agents`) del mismo nombre.
- **Servidores MCP del usuario:** un servidor de un pack que el usuario ya registró para todos los
  proyectos (`~/.claude.json`, `config.toml` de Codex), aunque tenga otro nombre. Cuenta como el
  mismo solo si hace exactamente lo mismo: igual URL, paquete (sin contar la versión) o comando con
  su ruta, los mismos argumentos y la misma configuración (`env`, headers, credenciales); ante
  cualquier diferencia se registran los dos. El apply no registra la copia del proyecto en ese
  provider, así el agente no arranca dos veces el mismo servidor, y lo informa. Codex necesita Python 3.11 para leer su
  configuración; con uno anterior no se compara.

```text
  ~ skill component-creation (react) has the same name as ~/.claude/skills/component-creation: Claude Code uses the user's
  ~ MCP server acme-docs (acme/kafka-interno) is the user's my-docs in ~/.claude.json: not registered for claude (conflicts.userServers.register: true registers it)
```

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.shadowing.enabled` | `true` | `false` no busca sombras con la máquina |
| `conflicts.userServers.enabled` | `true` | `false` no compara con los servidores del usuario y registra todos |
| `conflicts.userServers.register` | `false` | `true` registra igual la copia del proyecto; `plan` lo sigue informando |

## 3. Rules contra la realidad del repo

Una rule declara en su frontmatter lo que da por sentado, y `agent-ready plan` lo compara con las
señales estáticas del repo, sin IA y sin ejecutar nada:

```markdown
---
assumes:
  testRunner: vitest
---
```

| Dato | Valores | Qué mira |
|---|---|---|
| `testRunner` | `vitest`, `jest`, `mocha` | dependencias de `package.json`, su clave `jest` y los archivos de configuración |
| `packageManager` | `pnpm`, `npm`, `yarn`, `bun` | lockfiles y el campo `packageManager` de `package.json` |
| `indentation` | `tabs`, `spaces` | `indent_style` de `[*]` en `.editorconfig` y `useTabs` de Prettier en JSON |

La rule contradice al repo cuando este muestra otro valor del mismo dato y ninguno del que la rule
asume. El agente que obedece la rule rompe el proyecto, y el que obedece al proyecto ignora la rule:

```text
  ! .agents/rules/react-testing.md (react) assumes test runner vitest, but the repository uses jest (package.json)
```

Las rules del contenido que solo valen con una herramienta lo declaran, como las de testing de
`react` con Vitest. Un dato o un valor que el catálogo (`assets/repo-facts.json`) no conoce se
informa como no chequeado. Una contradicción escrita en prosa, sin `assumes`, la busca la revisión
semántica. Para reemplazar la rule del contenido por la del proyecto, `overrides`
([profiles.md](profiles.md)).

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.repoReality.enabled` | `true` | `false` no compara las rules con el repo |

### Rules que deciden lo mismo distinto

Una rule atómica puede declarar la decisión que resuelve con `key` ([atomic-rules.md](atomic-rules.md)).
Dos rules con la misma `key` y distinto statement o excepciones son un conflicto, sin llamar a ningún
modelo. Pasa, por ejemplo, con una rule gestionada que dice Vitest y una propia del proyecto que dice Jest.

- **Qué rules entran:** las que quedan en `.agents/rules/` después del apply, las gestionadas (ya sin las que
  reemplaza un `overrides`) y las propias del proyecto.
- **Workspaces:** una rule de un workspace se compara con las de la raíz, que valen para todo el repo, y nunca con
  las de otro workspace: en un monorepo, `apps/web` puede usar Jest y `apps/admin` Vitest.
- **Dónde aparece:** `plan`, `agent-ready conflicts` (sale con 6) y `check` con `ci.conflicts.structural`
  muestran `! <key> is decided differently by <id> (<profile>, <archivo>:<línea>) and …`. En el JSON está bajo
  `ruleKeys`.
- **No es conflicto:** dos rules con la misma `key` y el mismo contenido. Eso es un duplicado, y lo reporta
  `agent-ready rules lint`.
- **Cómo resolverlo:** dejar una de las dos, o que la rule propia reemplace la gestionada con
  `overrides=<fuente>:<id>` ([atomic-rules.md](atomic-rules.md), sección 5). Una rule del núcleo no se reemplaza.
- **Cómo apagarlo:** `rules.enabled: false` lo apaga, junto con el lint.

## 4. Hooks, permisos y settings

`agent-ready plan` compara las capas que lee cada provider: lo que mergea golfo-agent-ready
(`.claude/settings.json (golfo-agent-ready)`, `.codex/hooks.json (golfo-agent-ready)`), el resto de esos archivos
del proyecto, `.claude/settings.local.json` y la configuración del usuario (`~/.claude/settings.json`,
`$CODEX_HOME/hooks.json`). Solo lee; nunca escribe la configuración del usuario.

- **Permisos:** un patrón que una capa permite (`allow`) y otra prohíbe (`deny`) se informa con las
  dos capas. Claude Code aplica el `deny`.
- **Hooks repetidos:** el mismo comando en el mismo evento en dos capas corre una vez por cada
  registro.
- **Formateadores que compiten:** dos formateadores distintos (`assets/formatters.json`: Prettier,
  Biome, `eslint --fix`, dprint, Black, `ruff format`, gofmt, rustfmt) en el mismo evento, con matchers
  que se pisan, pueden reescribir el mismo archivo. Si los dos nombran rutas y no comparten ninguna
  (`black backend/` y `prettier --write frontend/`), no se informa. Solo cuenta el modo que reescribe:
  `prettier --check` o `black --check` no compiten.

```text
  ! permission Bash(npm run *): allowed in .claude/settings.json and denied in ~/.claude/settings.json; Claude Code applies the deny
  ~ claude PostToolUse runs two formatters that can rewrite the same files: prettier (.claude/settings.json) and biome (.claude/settings.local.json)
```

Que un hook `PreToolUse` bloquee lo que pide una rule o una skill gestionada lo cubre la revisión de IA de
los conflictos, con la misma clave (dirección `hooks`, [ai-reviews.md](ai-reviews.md), sección 7).

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.hooks.enabled` | `true` | `false` no compara los hooks ni los revisa con IA |
| `conflicts.permissions.enabled` | `true` | `false` no compara los permisos |

## 5. Paridad entre providers, variables de entorno y CI

Tres chequeos más de `agent-ready plan`, sin IA y sin escribir nada.

- **Paridad entre providers** (con dos o más en `providers`): `plan` dice qué ve cada uno. Claude Code
  lee las rules como `.claude/rules` y carga las que tienen `paths:` solo al tocar esos archivos;
  Codex lista todas en `AGENTS.md`, y Antigravity (si está entre los providers) también; la línea
  nombra solo los providers del repositorio y aparece con dos o más. Los subagentes le llegan a Codex como subagentes nativos
  (`.codex/agents/<nombre>.toml`) y los comandos como skills del mismo nombre. Avisa de un hook que corre en un provider y no en otro: los de golfo-agent-ready (salvo
  los declarados propios de uno, como el relink de las vistas de `.claude`, y los de aprendizaje,
  que Antigravity todavía no recibe) y los del proyecto en `.claude/settings.json`,
  `.codex/hooks.json` y `.agents/hooks.json` (este último con `antigravity` entre los providers;
  sus hooks se leen por evento y comando, como los de los otros dos).
- **Variables de entorno:** una variable que piden los servidores MCP de dos fuentes distintas, o
  que el proyecto ya lista en `.env.example` (o `.env.sample`, `.env.template`, `.env.dist`), se
  informa con los profiles que la piden, para confirmar que significa lo mismo.
- **Jobs de CI duplicados:** con el CI gestionado (`ci.provider`), un workflow propio del repo que
  ya corre el chequeo de Agent Ready se informa, para no correrlo dos veces.

```text
Providers: Claude Code sees 20 rules (0 only for their paths), 5 skills, 5 subagents and 1 commands; Codex sees 20 rules in AGENTS.md, 6 skills and 5 subagents
  ~ claude runs the PostToolUse hook `npm run lint` (.claude/settings.json) and codex does not
  ~ .github/workflows/own.yml already runs the Agent Ready check; the managed .github/workflows/agent-ready.yml runs it again
```

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.providerParity.enabled` | `true` | `false` no compara los providers |
| `conflicts.environment.enabled` | `true` | `false` no compara las variables de entorno |
| `conflicts.ciJobs.enabled` | `true` | `false` no busca jobs de CI duplicados |

## 6. Skills que compiten

Dos skills que hacen el mismo trabajo, con descripciones que se pisan («crear un endpoint»),
parten la activación: el agente usa una u otra según cómo se pida. Que dos skills se activen ante
el mismo pedido no es un problema si cada una resuelve una parte distinta: son complementarias (una
mide, la otra arregla).

`agent-ready plan` revisa con IA cada skill de un pack contra cada skill de otro profile y avisa
solo de las que compiten, con el pedido en común y en qué difieren:

```text
  ! [a1b2c3] .agents/skills/pr-review-workflow/SKILL.md <-> .agents/skills/team-review/SKILL.md: Both review pull requests; one follows the team checklist. (competing skills: "review this pull request")
```

- **Qué pares.** Solo los de profiles distintos con una skill de un pack: las del contenido no se
  revisan entre sí. Un par que un profile declara en `complements`
  (`"software-development:skills/pr-review-workflow"`) no se revisa.
- **Misma infraestructura.** Usa la llamada al provider, la caché y las decisiones de las demás
  revisiones (secciones 3 a 6 de [ai-reviews.md](ai-reviews.md)), bajo su propio chequeo, `skill-overlap`: un par sin cambios no se
  paga de nuevo, y sin red ni provider queda sin revisar, nunca limpio. Solo avisa: no frena el
  apply.

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.competingSkills.enabled` | `true` | `false` no revisa las skills; `reviews.enabled: false` también la apaga |

## 7. Todos los conflictos juntos

`agent-ready conflicts` corre los chequeos de la sección 7 de [ai-reviews.md](ai-reviews.md) y de las secciones 1 a 6 de esta referencia sobre la selección y muestra solo
los conflictos, sin escribir nada:

```text
Structural conflicts:
  ! .agents/rules/react-testing.md (react) assumes test runner vitest, but the repository uses jest (package.json)
AI review findings:
  ! [a1b2c3] .agents/rules/acme-team.md <-> .agents/rules/verify-changes.md: … 
```

- **Estructurales:** sin IA, los de las secciones 2 a 5 y las herramientas que compiten. Lo que solo
  informa (el presupuesto de contexto, qué ve cada provider, los servidores que quedan para el usuario,
  un dato que el catálogo no conoce) no cuenta como conflicto.
- **De IA:** las contradicciones entre rules ([ai-reviews.md](ai-reviews.md), sección 7) y las skills que compiten (sección 6), de
  la caché o con el provider. `--offline` responde solo de la caché y dice cuántos pares quedaron sin
  revisar.
- **Código de salida:** `0` sin conflictos, `6` con alguno. `--json` deja el detalle de cada chequeo.

En CI, `agent-ready check` corre los mismos chequeos con `ci.conflicts` (`ci-check.md`).

### Al iniciar sesión y al editar

Los conflictos estructurales también aparecen sin pedirlos, en dos momentos. Cada uno se apaga por
separado:

- **Al iniciar sesión:** el hook de `SessionStart` (`sync-marketplace.sh`) los lista con el prefijo
  `[conflicts]`, cualquiera sea `updates.mode`. Los hallazgos de IA salen de la caché, en la línea
  `AI reviews:` de `status`, y las desactualizadas se revisan en segundo plano ([ai-reviews.md](ai-reviews.md), sección 5).
- **Al editar:** el hook de `PostToolUse` (`check-harness-consistency.sh`) le pasa los archivos
  editados a `.agents/hooks/check-conflicts.sh`, que los recalcula si alguno es una de sus entradas:
  `AGENTS.md`, `CLAUDE.md`, lo que hay bajo `.agents/`, `.claude/` y `.codex/`, `.mcp.json`,
  los archivos de CI y de ejemplo de `.env` que lee la paridad (sección 5) y los que leen los `assumes` (`package.json`, `.editorconfig`,
  Prettier y los de `assets/repo-facts.json`, como lockfiles o `jest.config.js`). Corre sin red y sin
  la CLI del provider. La revisión de IA de rules, skills y `AGENTS.md` sigue aparte ([ai-reviews.md](ai-reviews.md), sección 1).

```text
[conflicts] ! .agents/rules/ours.md (project) assumes test runner vitest, but the repository uses jest (package.json)
[conflicts] Each one with its fix: agent-ready conflicts
```

`agent-ready status` los lista siempre, bajo `Conflicts between the profiles:`.

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.sessionStart.enabled` | `true` | `false` no los calcula al iniciar sesión |
| `conflicts.onEdit.enabled` | `true` | `false` no los recalcula al editar |

### Para autores de packs

Un pack detecta sus contradicciones en su propio CI, antes de publicarse, sin un repo consumidor:

```bash
agent-ready conflicts --pack .            # desde la raíz del pack (su agent-ready-pack.json)
agent-ready conflicts --pack . --offline  # sin llamar a la IA: solo lo estructural y la caché
```

El chequeo copia el pack a un repo consumidor temporal y evalúa cada profile que publica, por separado,
con la base del contenido (`golfo`) y los profiles que declara en `requires`, como lo vería un repo que lo
selecciona. Corre los mismos chequeos que `agent-ready conflicts`, salvo los de la máquina del autor (las
sombras con lo instalado, los servidores MCP y los settings y hooks del usuario), que no son los del
consumidor. El repo temporal está vacío, así que tampoco hay nada que contradiga un `assumes`. La copia
conserva los symlinks, así que un pack que publica uno falla igual que en un consumidor. `--provider`
elige la CLI de la revisión de IA.

```text
Pack acme: 3 profile(s) checked against the golfo base and their requires
acme/base: no conflicts
acme/kafka-interno:
  ~ MCP server base-docs (acme/base) and MCP server acme-docs (acme/kafka-interno) both provide docs-search: …
```

- **Código de salida:** `0` sin conflictos, `6` con alguno y `2` si un profile no resuelve (por ejemplo, un
  `requires` que no existe). `--json` deja el resultado de cada profile.
- **Revisión de IA:** sin `--offline` usa la CLI del provider de la sesión (`AGENT_READY_SETUP_ACTIVE_PROVIDER`
  en CI). El repo temporal no conserva la caché entre corridas, así que cada corrida revisa de nuevo.
