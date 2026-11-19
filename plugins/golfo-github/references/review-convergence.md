# Política de convergencia de loops de review

Leer este archivo antes de operar un loop review → fix → review: `review-fix-loop` (reviewer local o CLI) y `codex-autofix-loop` (reviewer Codex en el PR). Un loop entre un agente autor y un agente revisor puede no terminar nunca: cada ronda encuentra pocos bugs nuevos y cada vez más bugs viejos o de borde. Estas reglas lo hacen converger.

## Tope de rondas

- Una ronda es una review completa seguida de sus fixes.
- Tope por defecto: **3 rondas** por target. Cada skill lo expone como variable propia.
- Al alcanzar el tope con findings `Important` todavía abiertos, no lanzar otra ronda ni mergear. Reportar que el loop no convergió, listar lo pendiente y recomendar **reconsiderar el enfoque** del cambio en vez de seguir parchando.
- Excepción: `codex-autofix-loop` termina la última ronda (fixea sus findings) y mergea sin preguntar tras el gate de CI, en vez de cortar sin mergear. Ver su «Tope de rondas».
- El tope no se resetea por cambiar de provider ni por reiniciar la sesión: el contador vive en el estado del loop.

## Re-review solo del delta

- La ronda 1 revisa el target completo.
- Desde la ronda 2, revisar solo lo que cambió desde el inicio de la ronda anterior: commits posteriores más el working tree. Guardar el sha de referencia al empezar cada ronda.
- Si el reviewer no acepta un delta, revisar el target completo y descartar los findings que caen fuera del delta y ya están en el registro. Codex en GitHub es uno de esos reviewers: `@codex review for …` no limita la review, así que `codex-autofix-loop` pide siempre `@codex review` liso.

## Registro de findings

Mantener un registro por target con una entrada por finding: clase de bug, `archivo:línea`, etiqueta, severidad, ronda y resultado.

Resultados posibles:

- `fixed`: corregido; anotar el sha del fix.
- `rejected`: evaluado e inválido; anotar el motivo en una línea.
- `pre-existing`: defecto anterior al target, no bloqueante.
- `nit-skipped`: nit que se decidió no aplicar.
- `edge-case`: borde rebuscado, cerrado sin cambios.
- `failed`: el fix no se pudo aplicar por una falla del flujo, no de la sugerencia.

Reglas:

- **No repetir.** Un finding que ya está en el registro con resultado `rejected`, `pre-existing`, `nit-skipped` o `edge-case` no abre una ronda nueva. Se cierra con el mismo motivo, salvo que el código de esas líneas haya cambiado desde que se registró.
- Pasar el registro al reviewer cuando lo acepte (por ejemplo `--known-findings` en `review-fix-loop`) para que no reporte de nuevo lo ya triado.
- El registro también sirve como métrica: cuántas rondas llevó cada target y qué fracción de findings terminó en `fixed` contra `rejected`. Esa fracción mide el ruido del reviewer y es la materia prima de las evals.

## Clase de bug, no solo la línea

Al corregir un finding, corregir todas las apariciones del mismo patrón **dentro del target revisado**, no solo la línea señalada. No extender el fix a código fuera del target ni a casos de borde vecinos hipotéticos: eso agrega complejidad y genera más findings en la ronda siguiente.

## Qué bloquea y qué no

| Etiqueta | ¿Se corrige? | ¿Abre otra ronda? |
|---|---|---|
| `Important` | Sí | Sí, si hubo fix |
| `Nit` | Solo si es barato y local | No por sí solo |
| `Pre-existing` | Solo si es seguridad o pérdida de datos, o una línea que el target ya toca y el fix es trivial | No |

Las skills que reciben severidad del reviewer en vez de etiquetas (por ejemplo los badges `P0`–`P3` de Codex) mapean así: `P0`/`P1` → `Important`, `P3` → `Nit`. `P2` es `Important` salvo que el triage lo clasifique como borde.

## Criterio de cierre

El loop queda limpio cuando la última ronda no deja ningún finding `Important` abierto. Los `Nit` y `Pre-existing` pendientes se listan en el reporte final como follow-up, sin bloquear.
