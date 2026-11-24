# Profile packs

Profiles de otros repositorios o carpetas: cómo se declara una fuente, qué puede publicar un pack, su
compatibilidad con el motor, las colisiones y cómo se actualiza. Leer para declarar una fuente, explicar
una colisión o un `Evaluation incomplete`. Es parte del contrato de [profiles-and-lockfile.md](profiles-and-lockfile.md).

Una empresa mantiene sus profiles en un repositorio propio y los reutiliza con versiones
fijadas. `scripts/agent_ready_packs.py` carga los packs y `assets/examples/acme-profile-pack/` es un
pack mínimo de ejemplo. Un pack con herramientas (CLIs, servidores MCP o scripts) se publica como dice
[publishing-packs-with-tools.md](publishing-packs-with-tools.md), con un ejemplo personal y otro
corporativo firmado. No hay stacks primarios externos, profiles por carpeta, distribución por
npm ni instaladores propios de un pack.

**Fuentes.** `.agents/agent-ready.json` las declara en `sources.packs`:

```json
{
  "profiles": ["node", "acme/kafka-interno"],
  "sources": {
    "packs": [
      { "name": "acme", "source": "git+https://github.com/acme/agent-profiles", "ref": "main" },
      { "name": "seguridad", "source": "git+ssh://git@github.com/acme/security-profiles#<commit-completo>" },
      { "name": "local", "source": "path:./agent-packs/local", "updates": "pinned" }
    ]
  }
}
```

`agent-ready sources add <nombre> <fuente> [--ref r] [--updates m]` la declara (validada antes de
escribir) y la trae a la caché; `agent-ready sources remove` la saca si ningún profile seleccionado la usa, y
`agent-ready profiles add acme/kafka-interno` selecciona un profile suyo.

`sources.enabled: false` (por ejemplo, desde la organización) apaga los packs: no se descargan ni se leen, y
seleccionar uno de sus profiles falla antes de escribir.

| Forma | Significado |
|---|---|
| `git+https://…#<commit-completo>`, `git+ssh://…#<commit-completo>` | revisión fija: nunca se mueve |
| `git+https://…` con `"ref": "<rama-o-tag>"` (o `#<rama-o-tag>` en la URL) | se resuelve a un commit, que el lock registra; en `auto` sigue a la `ref`, en `pinned` espera una actualización explícita |
| `path:<ruta relativa>` | carpeta local, relativa a la raíz del repo consumidor |

Las credenciales no van en el manifest, el lockfile ni los logs: una URL con usuario de HTTPS,
contraseña o query se rechaza, y Git usa la autenticación ya configurada, sin prompts. Una ruta
absoluta se rechaza porque no existiría en otra máquina. Agregar una fuente hace disponibles sus
profiles, pero no selecciona ninguno ni proyecta sus assets.

**Pack.** Tiene `agent-ready-pack.json` en la raíz, con `schemaVersion`, `name` y `profiles`. `name`
debe ser igual al de la fuente en el manifest, porque los profiles se referencian por él. Cada
profile acepta `kind`, `description`, `assets`, `requires`, `conflicts`, `defaults`, `tools`, `detect` y `nested`,
con el significado de [profiles.md](profiles.md), más `clis`, `mcpServers` y `scripts` ([pack-tools.md](pack-tools.md)), y
estos límites:

- `kind` es `capability`, `bundle` o `stack`. Un profile que necesita un stack lo declara en `requires`;
  un pack publica un `stack` propio para una tecnología que el contenido no tiene (ver «Stacks de un pack»).
- `tools` solo acepta herramientas que el motor ya conoce (`browser`).
- Un pack no declara otras fuentes ni redefine un profile de Golfo. Tampoco declara `baseAssets`: la base y el
  template de `AGENTS.md` vienen solo de la fuente de contenido (ver «El contenido», en
  [updates.md](updates.md)), y un pack de `sources.packs` que la declara falla antes de escribir. Los assets compartidos van en un
  profile propio, como `acme/base`, que los demás requieren.
- `assets` publica solo `rules/`, `skills/`, `agents/`, `commands/`, `blocks/`, los bloques gestionados
  de archivos compartidos con el proyecto ([managed-agents-block.md](managed-agents-block.md), sección
  «Bloques en otros archivos»), y `nested/`, el bloque de cada destino anidado que declara
  ([nested-instructions.md](nested-instructions.md)). Puede traer además `evals/`, los evals de sus rules, que
  `run-evals <carpeta>` corre y el motor nunca proyecta (los `evals/` de una skill sí viajan con ella). No puede traer hooks, settings, el template de
  `AGENTS.md` ni archivos `AGENTS.md` o `CLAUDE.md`; solo un profile `stack` publica su sección de `AGENTS.md`
  (`blocks/AGENTS.md`).
- Las rules de un pack entran en la lista del bloque gestionado de `AGENTS.md`, como las de cualquier
  profile. Un pack no cambia el template ni las instrucciones propias del proyecto.

**Cómo declarar un subagente.** `agents/<nombre>.md` lleva en su frontmatter `name` (igual al nombre del
archivo) y `description`, que Codex exige, y el cuerpo con sus instrucciones. Lo que lo distingue de una
skill (contexto aislado, herramientas restringidas, otro modelo) se declara con dos claves portables, porque
cada provider nombra sus herramientas y modelos distinto:

| Clave | Valores | Claude Code | Antigravity | Codex |
|---|---|---|---|---|
| `access` | `read-only` | `tools: Read, Grep, Glob` | `tools` de lectura (`view_file`, `list_dir`, `find_by_name`, `grep_search`) | `[features] shell_tool = false` |
| | `edit` | `tools: Read, Grep, Glob, Edit, Write` | lectura y escritura (`write_to_file`, `replace_file_content`, `multi_replace_file_content`) | `[features] shell_tool = false` |
| | `full` | todas (sin `tools`) | escritura y `run_command` | sin restricción |
| `model-tier` | `fast` / `balanced` / `deep` | `model: haiku` / `sonnet` / `opus` | `model: flash` / `inherit` / `pro` | `model_reasoning_effort = "low"` / `"medium"` / `"high"` |

Con alguna de las dos, el motor renderiza una vista por provider: `.agents/agents/<nombre>.md` (la que lee
Antigravity) con sus `tools` y `model`, `.claude/agents/<nombre>.md` como archivo propio en lugar de una vista
de la anterior, y `.codex/agents/<nombre>.toml`. El mapeo vive en `assets/providers.json`
(`agentMetadata`), no en el código. Cada clave reemplaza solo su campo: con `model-tier` solo, el `tools`
que ya tenga el template queda, y con `access` solo, su `model`. Sin ninguna de las dos, el subagente se proyecta como siempre: copia,
vista de Claude y TOML. Un valor fuera de su lista frena el apply antes de escribir, nombrando el archivo, y
`plan` avisa lo que un provider no puede cumplir: Codex mantiene el sandbox de la sesión que arranca al
subagente, así que uno `read-only` puede igual editar archivos.

**Subagente o skill.** Un rol de oficina (abogado, contador, ventas) o una forma de trabajar es un profile con
rules y skills: corre en la sesión principal, con su contexto y sus herramientas. Un subagente se justifica solo
por una de estas razones:

- **Contexto aislado:** la tarea lee mucho (un diff grande, un expediente) y solo tiene que devolver la conclusión.
- **Permisos restringidos:** tiene que poder leer sin poder escribir (`access: read-only`).
- **Revisión independiente:** su juicio no debe arrastrar el razonamiento de quien hizo el trabajo.
- **Paralelismo o modelo distinto:** varias revisiones a la vez, o una barata (`model-tier: fast`) junto a una
  profunda.

Si ninguna aplica, es una skill. La orquestación (partir la tarea, despachar a cada subagente, consolidar y
resolver contradicciones) corre en la sesión principal, porque en Claude Code, Codex y Antigravity un subagente no
lanza otros por defecto. En el pack oficial la aporta la capability `orchestration` (skill `orchestrate-agents`) y
cada profile aporta solo su roster: una tabla con el archivo `.agents/agents/<nombre>.md` de cada subagente.
`plan`, `conflicts`, `check` y `conflicts --pack` marcan un archivo de `.agents/` que nombra un subagente que
ningún profile seleccionado publica y el proyecto no tiene ([structural-conflicts.md](structural-conflicts.md),
sección 5). `assets/examples/estudio-contable-pack/` es el caso completo fuera del software: un auditor
`read-only` para la revisión independiente, un investigador con contexto aislado y la skill `revisar-cierre`
como roster, con la capability `orchestration` en `requires`.

**Stacks de un pack.** Un profile `kind: stack` de un pack es un stack primario como los del contenido,
para una tecnología que el contenido no tiene (un lenguaje, un DSL propio). `assets/examples/elixir-stack-pack/`
publica `beam/elixir`:

- Se detecta por sus señales (`detect`) en cuanto el manifest declara la fuente: sin `profiles`, la
  detección inicial lo elige como a cualquier stack. También se elige con `--profiles beam/elixir` o
  `--stack beam/elixir`.
- Declara sus `defaults` y su sección de `AGENTS.md`, y se combina con las capabilities del contenido.
  Puede requerir un stack del contenido (una capa, como en «Capas» de [profiles.md](profiles.md)) o no requerir ninguno.
- **Precedencia entre fuentes:** ninguna fuente gana por ser del contenido o de un pack. Si un stack de un
  pack y otro (del contenido u otra fuente) coinciden en la detección, se pide una selección explícita,
  salvo que uno declare `supersedes` sobre el otro. Un stack de un pack solo puede reemplazar a uno de
  del contenido o de su mismo pack; el contenido no conoce los de los packs, y dos packs no se reemplazan entre
  sí: sus stacks que coinciden piden una selección explícita.
- Dos stacks que publican el mismo destino fallan antes de escribir, como cualquier par de profiles.
- Un stack de un pack no tiene que ser de software: `assets/examples/estudio-juridico-pack/` publica
  `estudio-juridico/estudio`, que se detecta por la estructura de carpetas (`actas/**/*.md`), no requiere
  `software-development` y trae por `defaults` la capability `actas-infraccion` y la capability `learning`
  del contenido. El mismo caso funciona con la capability sola.

**Compatibilidad declarada.** El catálogo de un pack, y el del contenido (`agent-ready-pack.json`),
pueden declarar tres campos opcionales (en el contenido, `version` es obligatoria):

```json
{
  "schemaVersion": 1,
  "name": "acme",
  "version": "2.0.0",
  "minEngine": "0.46.0",
  "changes": [
    { "version": "2.0.0", "summary": "Los topics de Kafka cambian de nombre", "breaking": true },
    { "version": "1.1.0", "summary": "Rule nueva para el cliente interno" }
  ],
  "profiles": {}
}
```

- `version` es la versión semver del contenido.
- `minEngine` es la versión más vieja del motor (el plugin golfo-agent-ready que corre agent-ready-setup)
  que tiene lo que el contenido usa. No hay tope: el motor nunca se fija y un motor más nuevo sigue
  aplicando. Con un motor más viejo, el apply, el plan o el status fallan antes de escribir y dicen
  qué versión del plugin instalar. `agent-ready doctor` lo avisa antes, para el contenido y para cada
  pack, con el comando que actualiza el plugin en cada provider.
- `schemaVersion` sube solo si el formato del catálogo cambia de forma incompatible. Un motor que
  no conoce ese `schemaVersion` falla con el mismo pedido de actualizar el plugin.
- `changes` es el changelog: `version`, `summary` y `breaking` opcional.

El plan de una actualización (`agent-ready update <fuente> --dry-run` o `--plan --update-source`)
muestra en «Version changes» la versión del lock y la nueva de cada fuente. Debajo lista los cambios
declarados entre las dos, del más nuevo al más viejo, con los `breaking` resaltados. Un salto de
versión mayor (o de minor en `0.x`) se marca aparte. El JSON del plan los trae en `versionChanges`.
Después, «Semantic conflicts» lista lo que la actualización contradice de las rules propias y del
`AGENTS.md` del proyecto ([ai-reviews.md](ai-reviews.md), sección 7).

| Referencia | Significado |
|---|---|
| `node` | profile de Golfo |
| `acme/kafka-interno` | profile de la fuente `acme` |
| `otra-fuente/base` | profile de otra fuente declarada en el manifest; un pack no trae fuentes por su cuenta |

**Validación antes de escribir.** Al resolver se validan el schema, las dependencias, los ciclos, los
conflictos y los nombres de fuente duplicados. También se rechazan estas colisiones de destino:
entre un pack y Golfo, entre dos packs, entre profiles de un mismo pack, en los destinos que generan
los adaptadores (`skills/x.md` y `commands/x.md` producen el mismo `.agents/skills/x/SKILL.md`), en los
subagentes de Codex (`agents/x.md` y `agents/otra/x.md` producen el mismo `.codex/agents/x.toml`) y entre
paths que solo difieren en mayúsculas. El namespace no evita una colisión de archivos. Los assets deben
quedar dentro del pack, sin symlinks, y un destino no puede pasar por un directorio enlazado del
proyecto. Cualquiera de estos errores frena el apply antes de modificar el repositorio.

**Lockfile.** `profileSources` registra por fuente `type`, `origin`, `requestedRef`, `resolvedCommit`
(`null` en una ruta), `catalogDigest`, `contentDigest` (assets de los profiles seleccionados) y
`profiles`. Cada asset guarda su propietario en `profile` y su origen en `source`
(`acme:profiles/kafka-interno/rules/acme-kafka.md`), con su `sha256` y `state`. El resultado es
determinista, sin timestamps ni rutas de la máquina. Un repo sin fuentes no suma ningún campo. `detect`
sí cuenta en `catalogDigest`, pero no en el digest de cada profile. El commit y el digest identifican el
contenido; la confianza en sus instrucciones sigue dependiendo de la fuente y de quien la revisa.

**Actualizaciones.** Un apply descarga lo que falta en
`${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/packs/`. Necesita resolver todas las fuentes declaradas,
también las que no tienen profiles seleccionados: si una falla, frena antes de escribir. Cada actualización
deja un diff revisable de assets y lockfile, y sigue el ownership de [profiles-and-lockfile.md](profiles-and-lockfile.md). Cada repo tiene su lock;
dos repos con el mismo pack pueden usar revisiones distintas. Cómo se actualiza cada fuente: [updates.md](updates.md).

**Rutas locales.** El digest se calcula sobre el contenido real de la carpeta, incluidos cambios sin
commitear, porque el `HEAD` no identifica un árbol modificado. `plan` y `status` muestran el drift, un
apply de `bootstrap.sh` lo adopta y un sync también, salvo con `updates.mode: pinned`. Si la ruta falta, un apply falla sin
escribir y `plan` informa la evaluación incompleta. Una carpeta externa sirve para desarrollo, pero su
digest no garantiza que pueda reconstruirse en otro entorno. Para consumo compartido, usar Git fijado o
un pack versionado dentro del propio repo.

**Modos de consulta.** `--plan`, `--status` y `AGENT_READY_SETUP_REVIEW_MODE=1` no escriben en el repo. Si
falta una fuente que la selección necesita, informan `Evaluation incomplete` y `plan` sale con 5: ese
resultado no es un plan validado. Una fuente sin profiles seleccionados que no está disponible no frena la
evaluación, pero sus sugerencias no aparecen. Cargar un catálogo o evaluar su `detect` nunca ejecuta nada
del pack. Qué refrescan y cuándo: [updates.md](updates.md).
