# Bloque gestionado de `AGENTS.md`


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
