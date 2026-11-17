# Rules atómicas

La unidad de una rule es la **entrada**, no el archivo. Un archivo de rules sigue siendo Markdown agrupado
por tema; cada instrucción adentro tiene identidad propia, su hash y sus metadatos. Este formato lo usan los
profiles de un pack y las rules propias del proyecto en `.agents/rules/`. Lo implementa
`scripts/agent_ready_rules.py` y lo revisa `agent-ready rules lint` (#168).

## 1. Formato

```markdown
## Unit tests

<!-- rule id=testing/unit-runner key=testing.unit-runner -->
- Use Vitest for unit tests.
  - Except: keep the runner the project already uses if it is not Vitest.
  - Run them with `pnpm test`.

<!-- rule id=testing/behavior-only requires=testing/unit-runner -->
- Assert observable behavior, not implementation details.
```

- **El comentario** va en su propia línea, justo arriba de la rule. Puede haber líneas en blanco entre los dos.
- **El statement** es el bullet de primer nivel que sigue al comentario: una sola instrucción imperativa.
  Puede seguir en líneas con sangría, sin cambiar de bullet.
- **Los sub-bullets** con sangría son parte de la rule:
  - **Excepciones:** los que empiezan con `Except:`. No son rules aparte, porque una rule sin sus excepciones se
    aplica de más.
  - **Detalles:** el resto, como el motivo o un ejemplo.
- **La rule termina** en la primera línea sin sangría. Una línea en blanco solo es parte de la rule si la sigue
  otra con sangría.
- **No son rules:**
  - los títulos;
  - los párrafos fuera de un bullet;
  - el frontmatter del archivo (por ejemplo, `paths` o `assumes`);
  - lo que está dentro de un bloque de código.

  Los párrafos sirven para dar contexto al tema. Un bullet de primer nivel sin comentario arriba es un error del
  lint (`untagged-rule`): o es una rule y necesita su id, o es prosa y va como párrafo.

### Atributos del comentario

| Atributo | Valor | Para qué |
|---|---|---|
| `id` (obligatorio) | segmentos kebab-case unidos por `/`, como `testing/unit-runner` | Identidad estable de la rule. Otra fuente la nombra como `<fuente>:<id>`, por ejemplo `golfo:testing/unit-runner`. |
| `key` | segmentos kebab-case unidos por `.`, como `testing.unit-runner` | El slot de decisión que resuelve la rule. Dos rules activas con la misma `key` deciden lo mismo. |
| `requires` | ids separados por coma | Rules de las que depende. Un id sin fuente tiene que estar en el mismo conjunto. |
| `paths` | globs separados por coma | Alcance por carpeta de la rule. |
| `overrides` | ids con su fuente (`<fuente>:<id>`), separados por coma | La rule de otra fuente que esta reemplaza. |
| `locked` | flag, sin valor | La rule no se reemplaza. |

Los valores no llevan espacios. El orden de los atributos y los espacios entre ellos no cambian la rule.

### Qué ve cada provider

- **Claude Code** quita los comentarios HTML de `CLAUDE.md` y de `.claude/rules/` antes de cargarlos. Los
  metadatos no le gastan contexto. Se verificó en #168 con una sonda en las dos ubicaciones: la rule se aplicó
  y el modelo no vio el comentario.
- **Codex** lee `AGENTS.md` tal como está: ve el comentario, que cuesta unos pocos tokens por rule y no cambia la
  instrucción.

## 2. Hash e idempotencia

Cada rule tiene un hash `sha256:` de su forma normalizada:

- el id, la `key`, `requires`, `paths` y `overrides` (como conjuntos ordenados) y `locked`;
- el statement, las excepciones y los detalles, cada uno en una línea con espacios simples.

Por eso no cambian el hash:

- los finales de línea CRLF o LF;
- los espacios de más;
- cortar el statement en otra línea;
- el orden de los atributos;
- un cambio en otra rule del mismo archivo.

Cambiar el texto de la rule o sus metadatos, sí. `agent-ready rules show <id>` imprime el hash.

### En el lock y en el plan

- **El lock:** cada archivo gestionado de `.agents/rules/` con rules atómicas guarda, además del hash del
  archivo, el hash de cada rule en `assets.<archivo>.rules` (`{"<id>": "sha256:…"}`). Un archivo solo de prosa
  no tiene ese campo.
- **El plan** (`agent-ready plan`, y también `apply --dry-run` y `update --dry-run`): debajo de cada archivo de rules que se actualiza, adopta, queda en conflicto o se retira,
  `plan` dice qué rules cambian: `~ rule changed: <ids>`, `+ rule added: <ids>` y `- rule removed: <ids>`.
  Para cada rule que cambia o se va, también dice qué depende hoy de ella en el repo, con las mismas
  relaciones que `rules impact` (sección 4):
  `! <id> is required by|replaced by|cited by …`.
  En `plan --json`, cada entrada lleva `ruleChanges` y `ruleImpact`. El archivo se sigue escribiendo
  entero, y el diff del archivo sigue al final del plan.
- **La revisión de IA:** cada rule es un documento propio de la revisión de contradicciones, así que
  cambiar una no vuelve a revisar las demás del archivo ([ai-reviews.md](ai-reviews.md), sección 2).

## 3. Qué revisa el lint

`agent-ready rules lint` sale con `1` cuando hay algún error y con `0` cuando solo hay avisos. Cada hallazgo
nombra el archivo, la línea, el código y la rule:

| Código | Nivel | Cuándo |
|---|---|---|
| `marker-syntax` | error | El comentario no se puede leer: no tiene id, un id o una `key` no siguen el formato, un atributo es desconocido o está dos veces, o un flag lleva valor. |
| `marker-without-rule` | error | Al comentario no le sigue un bullet de primer nivel. |
| `untagged-rule` | error | Un bullet de primer nivel no tiene comentario arriba. |
| `duplicate-id` | error | Dos rules del conjunto tienen el mismo id. |
| `several-decisions` | error | El statement encadena instrucciones: más de una oración, o cláusulas unidas con `;`. No cuentan el código entre backticks, lo que está entre paréntesis ni abreviaturas como `e.g.` o `i.e.`. |
| `statement-too-long` | error | El statement pasa `rules.maxStatementChars` (300 por defecto). |
| `statement-long` | aviso | El statement pasa `rules.statementWarnChars` (200 por defecto). |
| `key-conflict` | error | Dos rules tienen la misma `key` y distinto statement o excepciones. Se detecta sin llamar a ningún modelo. |
| `duplicate-rule` | aviso | Dos rules tienen la misma `key` y el mismo contenido, o el mismo statement. |
| `unknown-requires` | error | `requires` nombra un id sin fuente que no está en el conjunto. |

El largo cuenta solo el statement, no las excepciones ni los detalles: el motivo de una rule va en un sub-bullet.
Los dos límites se configuran en el módulo `rules`, y `rules.enabled: false` apaga el lint
([configuration-keys.md](configuration-keys.md)).

## 4. Comandos

```bash
agent-ready rules list [--path <archivo|carpeta>]... [--json]         # cada rule con su id, key y lugar
agent-ready rules show <id> [--path <archivo|carpeta>]... [--json]    # metadatos, excepciones, detalles y hash
agent-ready rules lint [--path <archivo|carpeta>]... [--json]         # atomicidad, largo y consistencia
agent-ready rules impact <id> [--path <archivo|carpeta>]... [--json]  # qué toca cambiar esa rule
agent-ready rules graph [--path <archivo|carpeta>]... [--json]        # todas las relaciones entre rules
```

- **Sin `--path`:** leen `.agents/rules/` del repositorio.
- **Con `--path`:** leen ese archivo, o cada `.md` bajo una carpeta `rules/` de esa carpeta. Así el autor de un
  pack lo revisa desde su checkout, sin un repositorio que lo consuma:

  ```bash
  agent-ready rules lint --path .
  ```

  En el CI del pack va el mismo comando.

### Impacto y grafo

`rules impact <id>` muestra, antes de cambiar una rule, qué rules la piden con `requires`, cuáles la
reemplazan con `overrides` y qué skills la citan. `rules graph` lista todas esas relaciones, una por línea
(`<desde> requires|overrides|cites <rule>  (<archivo>:<línea>)`).

- **Citar una rule desde una skill:** se escribe `rule:<fuente>:<id>` o `rule:<id>` en el texto de la
  skill, como `rule:golfo:testing/unit-runner`. Se leen los `.md` de `.agents/skills/` o, con `--path`,
  los de cada carpeta `skills/`.
- **El id:** se acepta con o sin la fuente. Dentro de un conjunto de rules los ids no se repiten, así que
  `golfo:testing/unit-runner` y `testing/unit-runner` nombran la misma rule.
- **Una rule reemplazada:** el apply la saca del archivo proyectado, pero `impact` la sigue mostrando
  porque las referencias a ella quedan, y aclara que no está en el conjunto.
- **Un id que nadie usa:** si ninguna rule tiene ese id y nada lo nombra, sale con 1.
- **En `plan`:** las mismas relaciones aparecen debajo de cada rule que una actualización cambia o saca
  (sección 2, «En el lock y en el plan»).
- **Pendiente:** cuántos repos de clientes reemplazan la rule (el `harvest` de #156).

## 5. Reemplazar una sola rule

Una rule reemplaza una rule de un profile de la selección con `overrides=<fuente>:<id>`. La `<fuente>` es el
nombre del pack de un profile con namespace (`acme` para `acme/backend`) o `golfo` para el contenido oficial.
Puede declararlo:

- **una rule de otro profile de la selección:**

  ```markdown
  <!-- rule id=kafka/logger overrides=acme:conventions/logger -->
  - Log Kafka consumers with the structured Kafka logger.
  ```

- **una rule propia del proyecto,** en un archivo de `.agents/rules/` que no escribió ningún apply. Su fuente
  es `project` (`project:team/logger` en los mensajes y en `plan`):

  ```markdown
  <!-- rule id=team/logger overrides=acme:conventions/logger -->
  - Log with pino.
  ```

  El archivo propio no cambia ni entra al lock. Si se borra, el próximo apply vuelve a proyectar la rule
  reemplazada. Un archivo propio bajo `.agents/rules/workspaces/` no reemplaza nada: las instrucciones no
  lo referencian, así que ningún provider cargaría el reemplazo.

- **Qué se proyecta:** el archivo de la rule reemplazada sin esa rule. Las demás rules del archivo, la prosa y
  su hash quedan igual. `plan` lo muestra como `Rule overridden: <fuente>:<id> by <fuente>:<id> of <profile>`.
- **El texto:** el plan y la proyección leen el mismo archivo, guardado en la caché por usuario por su sha256.
  Así el lock registra los mismos bytes que quedaron en el repo.
- **Falla antes de escribir:**
  - un `overrides` sin la fuente;
  - una rule que ningún profile de la selección publica;
  - una rule `locked`, también desde una rule propia del proyecto;
  - una rule del mismo profile;
  - una rule del núcleo;
  - dos rules que reemplazan la misma;
  - una rule que reemplaza otra y a su vez está reemplazada, como dos rules que se reemplazan entre sí:
    se borrarían las dos;
  - un `overrides` de archivo entero del profile sobre un archivo con una rule `locked`;
  - el mismo id publicado dos veces por la misma fuente. Las rules de un archivo que otro profile reemplaza
    entero no cuentan, porque ese archivo no se proyecta.
- **Hoy cubre** las rules de los profiles de la raíz de la selección: los profiles que suma solo un workspace no
  se pueden reemplazar con una rule.

Para reemplazar un archivo entero sigue estando el `overrides` del profile
([profiles.md](profiles.md)).
