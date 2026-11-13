# Estados del ticket padre en <PROJECT_KEY>

Leer antes de decidir o modificar estado. No trasladar IDs, nombres de transiciones ni rutas de otros proyectos a <PROJECT_KEY>.

## Entradas

- Intención explícita del usuario y modo de tarea.
- Estado y categoría actuales del padre, leídos desde Jira.
- Colección completa `PULL_REQUESTS` y estado de cada PR verificado en GitHub.
- Trazabilidad bidireccional y campos previamente verificados.
- Transiciones disponibles obtenidas con `getTransitionsForJiraIssue` para issue actual.

```text
ALL_PRS_MERGED = PULL_REQUESTS is not empty and every state == "MERGED"
```

No inferir estado PR desde branches, commits, labels, Jira o memoria.

## Sin PR asociados

- Conservar estado inicial en creación; una tarea planificada no implica trabajo iniciado.
- Conservar estado existente durante actualización, salvo cambio de estado explícitamente solicitado.
- No considerar colección vacía como todos fusionados.
- Un cierre manual explícito sin PR puede ejecutarse si usuario confirma que tarea no requiere PR y transiciones reales lo permiten. No afirmar verificación de merge.

## Con PR asociados

- Si alguno está `OPEN` o `CLOSED` sin merge, no completar padre.
- No reabrir ni retroceder automáticamente un padre ya completado; informar inconsistencia.
- Si todos están `MERGED`, intentar cierre mediante transiciones disponibles con destino de categoría `done`.
- Si ya está completado y todos fusionados, no aplicar transición adicional.
- No iniciar ni cambiar estado durante una actualización explícita acotada a otros campos salvo pedido de sincronización completa.

## Descubrimiento y ejecución

1. Releer padre inmediatamente antes de mutarlo.
2. Consultar transiciones del issue actual; usar ID retornado, nunca un ID recordado.
3. Para estado pedido explícitamente, elegir destino exacto; si hay múltiples opciones ambiguas, preguntar.
4. Para cierre por merge, elegir destino de categoría `done`. Si hay varios, pedir destino; categoría sola no autoriza elegir entre resolución satisfactoria y cancelación.
5. Aplicar transición directa solo si Jira la ofrece y requisitos están cubiertos. No exigir estados intermedios de otro proyecto.
6. Si destino no está disponible, informar estado y transiciones disponibles. No recorrer estados intermedios sin conocer ruta válida de <PROJECT_KEY> ni inventar release.
7. Obtener metadata de campos de transición cuando integración lo permita. Si validación exige datos no aportados, informar requisitos y pedirlos; no inventar resolución, versión o fecha.
8. Re-fetch después de transición y verificar destino real. Si no coincide, detener.

PR desconocido, conflicto de padre, trazabilidad incompleta o campos inválidos bloquean transición automática.
Un error de transición no autoriza reintentos ciegos: comprobar estado antes de decidir si quedó pendiente.

## Salida

Devolver estado final verificado, transiciones aplicadas en orden y bloqueo con causa concreta si existe.
Si falta ruta o dato requerido, informar key, estado actual y opciones disponibles sin afirmar sincronización completa.
Gate final no reinicia máquina ni repite transiciones ya verificadas.
