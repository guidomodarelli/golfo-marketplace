# Contrato compartido de review

Leer este archivo antes de revisar con `review-maintainability`, `review-performance` o `review-security`. Cada skill define su foco y su guía de severidad; este contrato define alcance, contexto, esfuerzo, verificación y formato, iguales para las tres.

## Alcance

Si el usuario no eligió el alcance y la review es interactiva, preguntar en español:

> Seleccioná un preset de review
> 1. Review contra develop (PR Style)
> 2. Review contra main/master (PR Style)
> 3. Review cambios no commiteados
> 4. Review con instrucciones personalizadas

Pedir que responda solo `1`, `2`, `3` o `4`:

- `1`: HEAD contra `develop`, incluyendo cambios no commiteados. Preferir `origin/develop`; si no existe, `develop` local.
- `2`: HEAD contra `main`/`master`, incluyendo cambios no commiteados. Orden: `origin/main`, `origin/master`, `main` local, `master` local.
- `3`: solo cambios staged, unstaged y untracked contra `HEAD`. No necesita base.
- `4`: pedir las instrucciones, el alcance y el foco antes de leer diffs, y aplicar el preset más cercano.

**Invocación no interactiva.** Si otra skill, un loop o un subagente invoca la review, no preguntar:

1. Usar el target que pasó el invocador.
2. Sin target: si hay PR abierto, usar su base (`gh pr view --json baseRefName`). Si no, usar `develop` cuando exista y, si no, `main`/`master`. Incluir siempre los cambios no commiteados.

Las ramas remotas van primero porque reflejan mejor la base compartida. Antes de resolver ramas o leer diffs, hacer fetch con prune: una base vieja produce un diff distinto del que mergeará el PR. Si el fetch falla, detenerse y reportar el error en vez de revisar contra refs viejos.

Revisar desde el merge base con la base elegida hasta `HEAD`. Cuando el alcance incluye cambios no commiteados, decirlo en el reporte.

## Contexto antes de revisar

1. **Reglas del repo.** Leer `REVIEW.md`, `CLAUDE.md` y `AGENTS.md` de la raíz y del directorio de los archivos cambiados, si existen; en `AGENTS.md`, prestar atención a la sección «Review guidelines», que también usa Codex. Aplicar lo que definen como fallo, las rutas a omitir y los límites de nits. Si una regla del repo choca con este contrato, gana la del repo.
2. **Intención del cambio.** Con un PR abierto, leer título y body (`gh pr view --json title,body`) y verificar que el diff haga lo que declara. Una diferencia entre lo declarado y lo implementado es un finding.
3. **Causa raíz.** Si el cambio es un bug fix, verificar que ataque la causa y no solo el síntoma. Un fix que tapa el síntoma es un finding `Important`.

## Nivel de esfuerzo según riesgo

El riesgo lo define el cambio, no el autor. Elegir el nivel antes de revisar y declararlo en el reporte.

| Nivel | Cuándo | Cómo |
|---|---|---|
| Quick | Diff de menos de 50 líneas, solo docs, tests o textos, sin rutas sensibles | Una pasada. Reportar solo `Important`. |
| Standard | Cualquier cambio que no sea Quick ni Deep | Flujo completo de la skill. |
| Deep | Toca rutas sensibles o el diff supera las 1000 líneas | Seguir el flujo entre módulos, verificación adversarial de todos los findings y lista explícita de lo que no se pudo cubrir. |

Rutas sensibles: autenticación, autorización y permisos; billing; workflows de CI (`.github/workflows/**`); release, instaladores y scripts de setup; manejo de secretos; migraciones de datos; configuración de agentes, skills, hooks y MCP.

## Verificación antes de reportar

- Cada finding necesita evidencia `archivo:línea` y un escenario concreto que falla. No inferir comportamiento por nombres.
- **Verificación adversarial.** Si el runtime soporta subagentes, pasar los findings `Important` a un verificador read-only con contexto nuevo que intente refutarlos leyendo el código. Reportar solo los que sobreviven. En nivel Deep, verificar también los `Nit`. Sin subagentes, hacer la refutación en una pasada separada y explícita antes de escribir el reporte.
- Si un finding depende de un supuesto, explicitarlo. Si el supuesto es débil, descartarlo.
- Descartar comentarios de estilo, formato o solo diagnóstico, salvo que causen un defecto del foco de la skill.

## Formato de findings

Primero los findings, ordenados por severidad y en español.

Cada finding lleva:

- **Severidad**: `P0`, `P1`, `P2` o `P3`, según la guía de la skill.
- **Etiqueta**:
  - `Important`: hay que corregirlo antes de mergear.
  - `Nit`: opcional, nunca bloquea.
  - `Pre-existing`: el defecto ya existía antes del cambio; el diff solo lo expone o lo toca. Se reporta para dar visibilidad sin atribuírselo al autor, y no bloquea salvo seguridad o pérdida de datos.
- Título breve y referencia `archivo:línea`.
- Los campos propios de la skill (modo de falla, carga de trabajo, input del atacante, etc.).
- **Clase de bug**: el patrón general y todas las demás ubicaciones del mismo patrón dentro del alcance revisado, para que el fix cubra todas las instancias en una sola pasada.
- Dirección de remediación breve.

Para clasificar `Pre-existing`, comparar las líneas señaladas contra el merge base (`git blame <merge-base> -- <archivo>` o `git show <merge-base>:<archivo>`).

Si el entorno soporta comentarios inline, emitir una directiva `::code-comment{...}` por finding, con un rango de líneas acotado y el título y el cuerpo en español.

**Resumen.** Empieza con el conteo por etiqueta, por ejemplo «3 findings: 1 Important, 1 Nit, 1 Pre-existing». Si no hay findings, empieza con «0 findings: nada que corregir» y menciona el riesgo residual: tests no ejecutados, áreas que el diff no deja inspeccionar o contexto de runtime faltante. Declarar también el nivel de esfuerzo usado.

## Límites comunes

- No revisar código sin cambios como objetivo de limpieza; ese código solo entra como `Pre-existing` si el diff lo expone o lo toca.
- No pedir reescrituras amplias cuando un fix acotado elimina el riesgo.
- No asumir que los tests pasan. Si los relevantes son conocidos y baratos, ejecutarlos; si no, decir qué no se validó.
