# Bloques gestionados

El bloque de `AGENTS.md`, que se arma con un template y las rules, la sección de cada stack (sección
«Secciones de los stacks») y los bloques con id que un profile publica en otros archivos compartidos con
el proyecto (sección final, «Bloques en otros archivos»).


Un único template (`assets/common/agents-template.md`) define el esqueleto del proyecto y el bloque
entre `<!-- BEGIN AGENT-READY MANAGED -->` y `<!-- END AGENT-READY MANAGED -->`; el bloque es el mismo
en cualquier repo. Su esqueleto es neutro (propósito, estructura y convenciones), para un repo sin
código. `software-development`, que requiere cualquier stack, publica otro esqueleto
(`assets/profiles/software-development/agents-skeleton.md`, con `Stack`, `Commands` y `Architecture`)
que reemplaza al del template (`--skeleton` del renderer). El esqueleto solo se usa al crear
`AGENTS.md`.
`scripts/render-instruction-template.sh` lo materializa:

- `{{AGENT_READY_RULE_REFERENCES}}`: una referencia portable
  `- Read and follow \`.agents/rules/<relative-path>\`.` por cada rule del
  template (del núcleo en `assets/common/rules/`, de `software-development` y del stack, en orden
  alfabético)
  y, bajo `### Project rules`, por cada rule propia del proyecto. Las rules de
  `rules/workspaces/` son de un workspace de un monorepo: las lista el `AGENTS.md` de su carpeta, no
  este bloque ([profiles-and-lockfile.md](profiles-and-lockfile.md), «Workspaces»).

Una rule propia es cualquier archivo `.md` regular bajo `.agents/rules/` (incluidos
subdirectorios) sin equivalente en las rules del template; los symlinks se
ignoran. Además de listarse en el bloque, el sync le crea su vista en
`.claude/rules/` para que Claude la cargue de forma nativa, la incluye en la
revisión de redundancias y elimina las vistas gestionadas de rules borradas.
Si el template deja de publicar una rule, la copia local que quede en
`.agents/rules/` pasa a tratarse como rule propia hasta que se borre.
- `{{AGENT_READY_CENTRALIZATION}}`: copia literal de
  `assets/instruction-centralization.md`.

El contenido fuera del bloque (descripción, stack, comandos, arquitectura,
ownership) pertenece al proyecto; el scaffold del template solo se usa al crear
un `AGENTS.md` nuevo.

`scripts/merge-instructions.sh`, que el hook lanza en segundo plano en cada sync
después de aplicar el bloque literal con `scripts/apply-managed-block.sh` (un
`AGENTS.md` legacy sin marcadores queda para esta revisión):

1. Reemplaza el bloque por copia literal del template renderizado. Cualquier
   edición manual dentro de los marcadores se pierde; instrucciones propias van
   fuera del bloque.
2. Envía al provider activo el bloque, el contenido completo de cada rule y el
   contenido del proyecto (con el bloque sustituido por
   `<!-- AGENT-READY MANAGED BLOCK -->`), todo como datos no confiables. La IA
   solo puede borrar líneas redundantes fuera del bloque: repetidas en el propio
   contenido o ya cubiertas por el bloque o por una rule.
3. Rechaza la revisión si agrega, reescribe o reordena líneas, pierde el
   placeholder, devuelve bloques cercados o reintroduce marcadores. En ese caso,
   o si el provider falla, aplica solo el bloque literal sin tocar el contenido
   del proyecto y reintenta la revisión en el siguiente sync.
4. Reporta las líneas borradas y, por separado, las inconsistencias: líneas del
   proyecto que contradicen el bloque o una rule. Las inconsistencias nunca se
   borran; quedan para revisión manual.
5. En un `AGENTS.md` legacy sin marcadores, la IA elimina secciones que el
   bloque reemplaza (lista de rules, centralización) y la lista de skills
   escrita a mano, porque Claude y Codex descubren skills de forma nativa; y ubica
   el placeholder. Si la revisión falla, el bloque se agrega al final sin tocar
   el contenido del proyecto.
6. Si los marcadores están duplicados o desordenados, no modifica el archivo y
   termina con código `2` para revisión humana.
7. Las secciones de los stacks tampoco son del proyecto: en el contenido que revisa
   la IA, cada una es una línea `<!-- AGENT-READY MANAGED SECTION: <id> -->`, y su
   texto viaja como parte del bloque, de solo lectura. La revisión se rechaza si pierde
   o repite esa línea, si escribe un marcador de sección o si los marcadores de una
   sección no aparean (así no puede borrarlos como si fueran líneas redundantes).

La revisión completada se guarda, con sus inconsistencias, en la caché de revisiones
de IA, cuya clave incluye `AGENTS.md`, las rules del template y propias, el provider y
el modelo. Mientras ninguno cambie, el sync no vuelve a invocar IA y repite las
inconsistencias desde la caché. `agent-ready apply --recheck` fuerza la revisión y
`reviews.enabled: false` la apaga. Unidad, clave, opciones y dónde vive la caché:
[ai-reviews.md](ai-reviews.md). La escritura de `AGENTS.md` es atómica y se cancela si
el archivo cambia durante el proceso.

El modelo y el nivel de razonamiento de la revisión se pueden cambiar con
`AGENT_READY_SETUP_MERGE_MODEL` y `AGENT_READY_SETUP_MERGE_REASONING_EFFORT`.
Los valores por defecto viven solo en `PROVIDER_DEFAULTS` de
`assets/common/hooks/review-cache.py`, que también usa el hook de consistencia. El
valor se pasa tal cual al CLI del provider (`claude --model/--effort`, `codex
--model` y `model_reasoning_effort`).

Los hooks generados no pasan flags de confirmación durante `SessionStart`.
`CLAUDE.md` nunca se modifica durante este paso.

## Secciones de los stacks

Cada stack publica su sección en `assets/stacks/<stack>/blocks/AGENTS.md`: un bloque con id (sección
siguiente) en el `AGENTS.md` de la raíz, con el nombre del stack como id
(`<!-- BEGIN AGENT-READY MANAGED: node -->`). Con `--profiles react,node`, el `AGENTS.md` lleva el
template base, el bloque de rules y una sección `## React` y otra `## Node.js`; una sección nueva
se agrega al final del archivo. El stack primario solo desempata la detección; no aporta el template.

- Solo un profile `stack` agrega una sección, y solo al `AGENTS.md` de la raíz: un profile `capability`
  o `bundle`, o un `AGENTS.md` de otro directorio, hacen fallar el plan. El stack de un pack también
  agrega la suya, con su nombre con namespace como id (`<!-- BEGIN AGENT-READY MANAGED: beam/elixir -->`).
- Cada sección tiene su drift en el lock: `plan` muestra la edición local de una sola sección, y el
  apply la restaura sin tocar las demás ni el contenido del proyecto.
- El apply crea `AGENTS.md` o vuelve a renderizar su bloque antes de `finalize`: las secciones se
  clasifican de nuevo contra el archivo que dejó el propio apply, no contra el del plan.
- Un `AGENTS.md` del proyecto que todavía no tiene el bloque (legacy) no recibe secciones: sigue
  siendo del proyecto hasta que la revisión ubica el bloque. Mientras el `CLAUDE.md` de la raíz tenga
  instrucciones propias distintas de `AGENTS.md`, el apply tampoco agrega, actualiza ni saca secciones:
  el agente une los dos archivos primero. En los dos casos las secciones se ponen al día en el apply
  siguiente, y mientras tanto el lock conserva las que ya conocía.
- Un stack que sale de la selección se lleva su sección. `agent-ready remove` saca las secciones junto
  con el bloque de rules, y borra `AGENTS.md` si solo queda el esqueleto del template. Si alguna sección
  queda en el archivo (marcadores rotos, un symlink o un cambio durante la remoción), el lock se
  conserva para que el próximo `remove` la encuentre.
- `merge-instructions.sh`, `apply-managed-block.sh` y la normalización solo tocan el bloque de rules:
  las secciones quedan literales (paso 7 de la revisión).
- El motor suma una sección más, `agent-ready:nested-index`, que lista los `AGENTS.md` anidados para Codex.
  No viene de un stack y sigue el mismo contrato ([nested-instructions.md](nested-instructions.md),
  «Índice para Codex»).

## Bloques en otros archivos

Un profile, de golfo-kit o de un pack, publica la parte que le toca de un archivo compartido con el
proyecto como `blocks/<ruta en el repo>` en su árbol de assets. Por ejemplo, `software-development`
publica `assets/profiles/software-development/blocks/.github/pull_request_template.md`, y el profile
`common` publica `assets/common/blocks/.gitignore`, que ignora
el estado local de agent-ready-setup: el lock de una sincronización en curso
(`.agents/.agent-ready-assets.lock/`), la metadata del navegador (`.agents/browser-tools.json`) y el
manifest de vistas por hard link (`.claude/.agent-ready-hard-link-views`). `scripts/agent_ready_blocks.py` lo aplica en
`finalize`, después de la proyección; bootstrap y el hook de sync no copian `blocks/`.

- **Marcadores.** El bloque va entre dos líneas con el id, que es el nombre del profile, y la sintaxis de
  comentario del archivo:
  - Markdown (`.md`, `.markdown`): `<!-- BEGIN AGENT-READY MANAGED: common -->` y
    `<!-- END AGENT-READY MANAGED: common -->`;
  - `.gitignore`, `.gitattributes`, `.dockerignore`, YAML, TOML y shell: `# BEGIN AGENT-READY MANAGED: common`.

  Otro tipo de archivo, un `CLAUDE.md` o un `AGENTS.md` fuera de la raíz (sin importar mayúsculas) y
  lo que está bajo `.git/`, `.agents/`, `.claude/` o `.codex/` no admiten bloques de `blocks/`: el plan falla y
  nombra el profile. El `AGENTS.md` de la raíz solo admite la sección de un stack («Secciones de los stacks»),
  y el de una carpeta, el bloque de un destino anidado, que el profile publica en `nested/` y el repo ubica
  ([nested-instructions.md](nested-instructions.md)).
- **Contrato.** Es el mismo del bloque de `AGENTS.md`:
  - lo que está entre los marcadores se pisa en cada apply, y lo de afuera es del proyecto;
  - un bloque nuevo se agrega al final, separado por una línea en blanco;
  - un profile que sale de la selección se lleva su bloque, y un archivo que queda vacío se borra;
  - reescribir el archivo conserva sus permisos, así que un script ejecutable lo sigue siendo.
- **Varios profiles en un archivo.** Cada profile tiene su bloque, con su id. Un archivo no puede ser a la
  vez un asset entero de un profile y tener bloques de otro. Si un asset entero sale de la selección y su
  ruta pasa a tener bloques, el apply lo retira como a cualquier asset y crea el archivo con los bloques.
- **Marcadores rotos.** Si un marcador se repite, aparece fuera de orden o queda adentro de otro bloque, el
  archivo no se toca. Lo mismo pasa si el archivo es un symlink o lo es un directorio de su ruta. El plan
  lo muestra como `conflict` y el apply como `managed block kept`. El lock conserva la base anterior.
- **Lock, plan y status.** El lock guarda en `blocks` el sha256 de cada bloque por archivo e id. `plan`
  muestra cada bloque que cambia con su diff, y `status` reporta como `modified` un bloque editado a mano
  y como conflicto uno que el apply no puede escribir, aunque nunca se haya aplicado. `apply --from-lock`
  también compara los bloques con el lock, y el `contentDigest` de golfo-kit incluye los suyos.
- **`agent-ready remove`.** Saca cada bloque del lock y deja el resto del archivo; si no queda nada, lo borra.
- **JSON.** `settings.json`, `hooks.json` y `.mcp.json` no admiten comentarios, así que siguen con merge por
  claves.
