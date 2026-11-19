---
name: improve-spec
description: >-
  Mejora specs de docs/specs/: resuelve ambigüedades, completa secciones, infiere
  constraints, explora el codebase para Current State y deja tasks ejecutables con
  Verify. Usar con /improve-spec o al pedir mejorar, revisar, completar o dejar
  listo un spec o requirement para implementar, aunque no se nombre la skill.
license: MIT
metadata:
  version: "1.1.0"
  author: "Guido Modarelli"
  category: "spec-driven-development"
  tags: "spec, requirements, tasks, constraints, current-state, planning, context-optimized-v1.20.1"
  command: "/improve-spec"
---

# Improve Spec

## Objetivo

Transformar un spec escrito por una persona (a veces un requirement narrativo, a veces un template a medio llenar) en un spec que otro agente pueda implementar en sesiones de contexto limpio sin volver a preguntar. El resultado sobrescribe el archivo original solo después de aprobación explícita.

Un spec mejorado no es un spec más largo: es uno donde cada afirmación tiene una sola interpretación, cada dato sale de una fuente verificable (el spec original, el codebase o el usuario) y cada task termina con un criterio de verificación ejecutable.

## Principios

- **No inventar.** Todo lo que se agregue tiene que venir del spec original, del codebase (con path concreto) o de una respuesta del usuario. Lo que no se puede confirmar se pregunta o queda como supuesto explícito. Un spec con datos inventados es peor que uno incompleto, porque el implementador confía en él.
- **Preservar intención y contenido de dominio.** Conservar flujos, diagramas, catálogos de endpoints, payloads de ejemplo e identificadores (p. ej. `E1`, `C2`, `N1`) del original. Reorganizarlos está bien; perder información no. Los payloads de ejemplo largos pueden resumirse a los campos que el flujo usa, dejando claro de dónde salen.
- **Fuente de cada dato sensible.** Para IDs, versiones, requester/actor, permisos y montos, el spec tiene que decir de dónde sale el valor (objeto server-side, respuesta de otro servicio, input del usuario). Esto previene bugs de autorización y es lo que más suele faltar.
- **Orden y fallos explícitos.** Cuando un flujo encadena llamadas, dejar escrito el orden, qué pasa si una falla (se propaga, se compensa, se reintenta) y qué no debe ejecutarse después del fallo.
- **Límites de validación.** Validar input no confiable del consumer una sola vez en el boundary de entrada; no inferir constraints que revaliden por completo respuestas de backends/upstream: consumirlas según contrato con el narrowing mínimo que el flujo necesite (status, discriminadores como `FINISHED`).
- **Idioma.** Mantener el idioma del spec original salvo que el usuario pida otro. Código, paths, identificadores y literales quedan tal cual.

## Compatibilidad entre agentes

Las preguntas de los pasos 1, 5 y 7 usan la herramienta de preguntas con opciones que exista en la sesión, según [`agent-capabilities.md`](../../references/agent-capabilities.md): `AskUserQuestion` en Claude Code, `clarify` en Hermes (hasta 4 `choices` por pregunta) o `request_user_input` solo si Codex está en modo Plan. Si no hay ninguna, o `clarify` devuelve `undelivered`, `timed_out` o `cancelled`, hacé la misma pregunta en texto con opciones numeradas y **detenete**: no generes, apruebes ni guardes el spec hasta recibir la respuesta, porque el paso 8 sobrescribe el archivo del usuario. En el cierre, reportá el fallback en `Limitaciones del agente`.

## Flujo

### Paso 1: Resolver el spec

1. Si el usuario pasó un nombre o path (argumento de `/improve-spec`, mención en el mensaje), usarlo. Aceptar `nombre`, `nombre.md` o path relativo/absoluto.
2. Si no, listar `docs/specs/*.md` y preguntar cuál mejorar (con `AskUserQuestion` si está disponible, ofreciendo hasta 4 specs como opciones; si no, en texto).
3. Si `docs/specs/` no existe, buscar ubicaciones equivalentes (`specs/`, `docs/`) y confirmar con el usuario antes de seguir.
4. Si el archivo no existe, informarlo con el path buscado y terminar.

### Paso 2: Leer y clasificar

Leer el spec completo. Identificar su forma:

- **Requirement narrativo** (flujo actual vs. propuesto, endpoints listados, prosa): hay que extraer Why/What/Constraints/Tasks de la prosa.
- **Template parcial** (ya tiene `## Why`, `## Tasks`, etc.): hay que completar y endurecer.
- **Demasiado vacío** (no se entiende qué problema resuelve ni qué se entrega): informar y pedir al menos el problema y el entregable. No inventarlos.

### Paso 3: Analizar

Evaluar cuatro dimensiones y anotar hallazgos concretos (cita o sección de origen + problema):

1. **Ambigüedades**: afirmaciones con más de una lectura. Típicas: respuesta ante errores (¿400, 404, 409, 503?), quién puede ejecutar la operación, soft vs. hard delete, tipo/formato de campos, de dónde sale un valor, qué pasa con entidades sin el dato opcional, orden entre llamadas.
2. **Secciones incompletas**: ver estructura en `references/spec-structure.md`. Faltantes o vacías: `Why`, `What`, `Constraints` (`Must`, `Must Not`, `Out of Scope`), `Current State`, `Tasks`.
3. **Tasks no ejecutables**: cada task necesita `What` concreto, `Files` con paths (del `Current State`; si el path exacto no se conoce, el patrón del repo, p. ej. `src/main/java/.../ContextService.java`) y `Verify` ejecutable: comando del stack apuntando al test concreto (`-Dtest=ClaseTest`, `npm test -- path`) más los casos que cubre, uno por rama. "Funciona bien", "revisar que ande" o un `mvn test` genérico no son verificables.
4. **Constraints faltantes**: inferidos del `What`: existencia de entidades, casos borde (vacío, último elemento, duplicados, dato opcional ausente), autorización y fuente confiable de identificadores, comportamiento ante error de dependencias, compatibilidad con el flujo actual para casos no alcanzados.

### Paso 4: Explorar el codebase

Objetivo: llenar `Current State` con evidencia y encontrar el patrón existente que el nuevo código debe seguir. Detectar el stack primero (`pom.xml`/`build.gradle`, `package.json`, `go.mod`, `pyproject.toml`) y adaptar las búsquedas; no asumir un lenguaje.

1. Extraer palabras clave del spec: entidades, métodos/clases nombrados (p. ej. `com.acme.service.FooService.bar` → buscar `FooService` y `bar`), paths de endpoints, nombres de config.
2. Buscar con `rg` (o `grep -rn` si no está) excluyendo dependencias y build (`node_modules`, `target`, `build`, `dist`, `vendor`):
   - definiciones de las clases/métodos mencionados y sus llamadores;
   - la operación hermana o inversa ya implementada (si el spec agrega un promote, buscar el validate o create existente del mismo cliente);
   - cliente/adapter del servicio externo que se va a consumir, su config (pool, base path, scope) y su manejo de errores;
   - tests existentes de esas piezas, para saber convención y comando de ejecución.
3. Leer los archivos relevantes, no solo listarlos: `Current State` tiene que decir qué hace cada uno hoy y qué cambia, con `path:línea` cuando ayude.
4. Si el spec contradice el código (un método que no existe, una firma distinta), registrarlo como hallazgo; no reescribir el spec para que coincida en silencio.
5. Si no se encuentra nada relacionado, dejar en `Current State`: "No se encontraron archivos relacionados — completar manualmente" e indicar qué se buscó.

### Paso 5: Resolver lo que el codebase no responde

Juntar las ambigüedades que no se resolvieron con evidencia y preguntarlas al usuario antes de generar (con `AskUserQuestion` si está disponible, hasta 4 por ronda, cada una con opciones concretas y la recomendada primero). Si el usuario prefiere no decidir, dejar la decisión como supuesto explícito en `Out of Scope` o en una sección `## Open Questions`, nunca como hecho.

### Paso 6: Generar el spec mejorado

Seguir la estructura y las reglas de tasks de `references/spec-structure.md`. Para ver el tipo de transformación esperado (qué se agrega y por qué), leer `references/improvement-patterns.md`. Son guías de forma: el contenido sale del spec y del codebase del usuario, nunca de esos ejemplos.

### Paso 7: Mostrar resumen y pedir aprobación

Antes de escribir, mostrar:

```
Mejoras encontradas en {spec}:

Ambigüedades resueltas:
  → {ambigüedad} — {cómo se resolvió: evidencia en path | decisión del usuario}
Secciones completadas:
  → {sección}
Constraints agregados:
  → {constraint}
Current State:
  → {N} archivos relevantes
  → Patrón a seguir: {descripción breve}
Tasks:
  → {N} tasks ({agregadas / completadas})
Pendiente / supuestos:
  → {open question o supuesto explícito, si hay}
```

Preguntar (con `AskUserQuestion` si está disponible): "¿Aprobás estas mejoras?"

1. **Aprobar y guardar** — sobrescribe el spec.
2. **Ver spec completo** — mostrar el spec generado y volver a preguntar.
3. **Modificar algo** — pedir qué cambiar, regenerar y volver a este paso.
4. **Cancelar** — terminar sin escribir.

### Paso 8: Guardar y confirmar

Sobrescribir el archivo original con el spec aprobado. Confirmar:

```
Spec mejorado y guardado.

Archivo : {path}
Tasks   : {N} tasks ejecutables
Pendiente: {open questions, o "ninguno"}
```

## Manejo de casos

| Situación | Acción |
| :-- | :-- |
| Archivo no existe | Informar path buscado y terminar |
| Spec vacío o sin problema/entregable | Pedir al menos Why y What; no inventarlos |
| Spec contradice el código | Reportarlo como hallazgo y preguntar cuál es la intención |
| Sin archivos relacionados en el codebase | Current State con nota "completar manualmente" + qué se buscó |
| Spec ya completo | Informar que está bien definido y listar qué se verificó; no sobrescribir |
| Usuario cancela | No escribir nada |
