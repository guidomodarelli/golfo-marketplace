# Matriz de testing para operaciones async

Los tests deben demostrar comportamiento observable por boundary. Adaptar nombres y herramientas al repositorio; no imponer clases, Jest, React ni mocks de plataforma.

| Escenario | Boundary | Aserciones mínimas |
|---|---|---|
| Éxito completo | service/client/UI | todos los items terminales, side effects y copy esperado |
| Rechazo estructurado | adapter/service/API | código estable, status público correcto, sin retry incorrecto |
| 4xx con texto timeout | classifier | prevalece rechazo/autorización sobre heurística de mensaje |
| Rate limit | API/client/UI | razón rate-limit, espera/retry según contrato, feedback accionable |
| Timeout sin certeza | service/client | estado indeterminado o unresolved; no repetir mutación confirmada |
| DTO middleend no utilizable / mismatch upstream observado | route/client/adapter | validar DTO middleend; mapear mismatch upstream sin revalidarlo, fallback controlado, no éxito inventado ni raw response |
| Todos chunks aceptados | orchestrator | runs completos y orden/identidad preservados |
| Algunos chunks rechazados | orchestrator/API | accepted runs + contadores + razón; chunks aceptados no se repiten |
| Preflight + partial | client/UI | combinación sin duplicados y feedback parcial |
| Run terminal con fallas | polling/UI | termina polling, conserva fallas por item, no clasifica como polling timeout |
| Polling incompleto | client | resultados completados + unresolved; resume sin nuevo job |
| Deadline | client/UI | error recuperable, acción de reconcile/resume, no afirmar no-mutación |
| Abort antes/durante | async/UI | no toast/error visible, listeners/timers limpios, sin estado stale |
| Reintento visible | client/UI | intento, máximo y deadline del DTO salen de la política que ejecuta el retry (configurada con un máximo distinto del default); sin máximo o sin deadline, el campo no viene; al agotarse, error recuperable |
| DTO/log sensible | API/log | ausencia de stack, cause, headers, tokens, cookies, PII y payload raw |
| Unknown throw | normalizer | `null`, string, objeto y `Error` no rompen ni se exponen |
| i18n | UI | copy derivado de código/razón y catálogos fuente consistentes |

## Guía de aserciones

- Verificar status, códigos, resultados, cantidad de requests, IDs y side effects observables; no verificar imports ni contenido textual de archivos fuente.
- En un test de partial, usar respuestas sintéticas con al menos un chunk aceptado y uno rechazado; comprobar que resume opera sobre unresolved y que retry solo incluye fallas terminales elegibles, nunca éxitos confirmados.
- En polling, cubrir procesamiento, terminal success, terminal item failures, invalid shape, deadline y cancelación.
- En sanitización, inyectar `stack`, `cause`, `response`, `headers`, `authorization`, token y PII en error upstream; afirmar que no aparecen en DTO ni log.
- En clasificación, probar igual mensaje con statuses/códigos diferentes para demostrar precedencia estructurada.
- En UI, probar acción disponible según estado: resume de unresolved, retry de fallas terminales elegibles, consulta/reconciliación en estado indeterminado y ausencia de feedback por abort.
- Para concurrente, verificar límites y cleanup con APIs reales del proyecto; no reemplazar SDK/framework interno por mocks si el entorno permite integración.

## Validación mínima

Ejecutar, según scripts del repositorio:

1. tests focales de classifier/service/route/client/UI;
2. tests de integración de transporte o fixtures reales cuando correspondan;
3. typecheck;
4. lint;
5. suite completa/build/runtime si el cambio afecta esos contratos;
6. `git diff --check`.

Reportar cada comando y resultado. Si una validación no puede ejecutarse, explicar bloqueo concreto; no afirmar cobertura por inspección estática.
