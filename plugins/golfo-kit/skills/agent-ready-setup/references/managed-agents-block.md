# Bloques gestionados

El bloque de `AGENTS.md`, que se arma con un template y las rules, y los bloques con id que un profile
publica en otros archivos compartidos con el proyecto (sección final, «Bloques en otros archivos»).


Cada template de stack (`assets/stacks/<stack>/agents-template.md`) define el bloque
entre `<!-- BEGIN AGENT-READY MANAGED -->` y `<!-- END AGENT-READY MANAGED -->`.
`scripts/render-instruction-template.sh` lo materializa:

- `{{AGENT_READY_RULE_REFERENCES}}`: una referencia portable
  `- Read and follow \`.agents/rules/<relative-path>\`.` por cada rule del
  template (comunes de `assets/common/rules/` y del stack, en orden alfabético)
  y, bajo `### Project rules`, por cada rule propia del proyecto.

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

## Bloques en otros archivos

Un profile, de golfo-kit o de un pack, publica la parte que le toca de un archivo compartido con el
proyecto como `blocks/<ruta en el repo>` en su árbol de assets. Por ejemplo, el profile `common` publica
`assets/common/blocks/.github/pull_request_template.md`. `scripts/agent_ready_blocks.py` lo aplica en
`finalize`, después de la proyección; bootstrap y el hook de sync no copian `blocks/`.

- **Marcadores.** El bloque va entre dos líneas con el id, que es el nombre del profile, y la sintaxis de
  comentario del archivo:
  - Markdown (`.md`, `.markdown`): `<!-- BEGIN AGENT-READY MANAGED: common -->` y
    `<!-- END AGENT-READY MANAGED: common -->`;
  - `.gitignore`, `.gitattributes`, `.dockerignore`, YAML, TOML y shell: `# BEGIN AGENT-READY MANAGED: common`.

  Otro tipo de archivo, un `AGENTS.md` o `CLAUDE.md` en cualquier directorio (sin importar mayúsculas) y
  lo que está bajo `.git/`, `.agents/`, `.claude/` o `.codex/` no admiten bloques: el plan falla y nombra
  el profile.
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
