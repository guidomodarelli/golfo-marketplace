# Estructura del spec mejorado

Secciones obligatorias en este orden. Las secciones de dominio del original (flujos actual/propuesto, catálogo de endpoints expuestos/consumidos/nuevos, payloads, diagramas) se conservan después de `Current State` y antes de `Tasks`, reorganizadas si hace falta.

```markdown
# {Título que describe el cambio, no el ticket}

## Why
{Problema actual y su consecuencia concreta. Qué se rompe o queda inconsistente hoy.}

## What
{Entregable concreto: qué flujos/endpoints/componentes cambian y cómo.
Referenciar los identificadores del original (E1, C2, N1...) si existen.
Aclarar qué NO se agrega (p. ej. "no se exponen endpoints nuevos").}

## Constraints

### Must
- {Fuente de cada dato sensible: IDs, versiones, requester/actor, permisos.}
- {Orden entre llamadas y qué pasa si una falla.}
- {Error esperado ante cada rechazo: tipo/status y qué incluye el mensaje.}
- {Patrón existente a respetar: pool, config, manejo de errores, convención de tests.}

### Must Not
- {Operaciones que no deben ocurrir en cierto flujo.}
- {Valores que no deben tomarse de input del usuario.}
- {Guards o comportamiento existente que no debe tocarse.}

### Out of Scope
- {Casos que siguen igual (p. ej. entidades sin el dato opcional).}
- {Supuestos de diseño explícitos que no se implementan ahora.}

## Current State
**Archivos relevantes:**
- `{path}[:línea]` — {qué hace hoy y qué cambia}

**Patrón a seguir:** {método/clase existente y qué tomar de él}

## {Secciones de dominio del original: Flows, Endpoints, etc.}
{Flujos propuestos como pasos numerados, con la llamada, el gate y el error de cada rama.
Endpoints nuevos con método, path parametrizado, headers y solo los campos de respuesta que se usan.}

## Tasks

### T1: {título concreto}
**What:** {qué implementar exactamente; snippet corto solo si elimina ambigüedad}
**Files:** {archivos a crear o modificar}
**Verify:** {comando o test con casos concretos y resultado esperado}

## Open Questions
{Solo si quedaron decisiones sin resolver. Omitir la sección si no hay.}
```

## Reglas para tasks

- Ordenar por dependencia: DTOs/modelos y clientes antes que los servicios que los usan.
- Cada task tiene que poder ejecutarse en una sesión de contexto limpio: nombra archivos, métodos y el patrón a copiar, sin depender de "lo que se habló".
- Tamaño: una responsabilidad por task (un método nuevo, una modificación de flujo). Si `Files` supera 3–4 archivos no relacionados, dividir.
- `Verify` ejecutable y específico: comando real del stack (`mvn test -Dtest=...`, `npm test -- path`, `go test ./pkg/...`) y los casos que el test cubre (éxito, cada rama de error, caso sin dato opcional). Nada subjetivo.
- Si el proyecto separa implementación y tests (TDD o convención del repo), separar tasks; si no, incluir los tests en la misma task que el cambio.
- Usar la convención de tests detectada en el repo (anotaciones, naming, ubicación).
