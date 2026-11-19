# Contrato de error

## Campos y responsabilidades

| Campo | Propósito | Regla |
|---|---|---|
| `code` | Identificador estable para consumers | No depender de copy ni de strings upstream |
| Categoría | Semántica (`invalid-input`, `dependency-unavailable`, etc.) | No confundir con HTTP status |
| `cause` | Diagnóstico al envolver | `unknown`, interno, nunca serializar raw |
| `metadata` | Contexto mínimo allowlisted | Campos explícitos, tipos acotados y sin PII |
| `retryable` | Decisión operativa | Solo si existe consumer y regla clara |
| Mensaje interno | Diagnóstico/log | No usar como API pública |
| Mensaje público | Copy seguro/localizable | Derivar desde `code` y contexto seguro |

El contrato de dominio no debe exigir un número HTTP. El boundary de transporte puede mapear una categoría/código a status y DTO:

```ts
const transport = {
	status: error.code === 'invalid-input' ? 400 : 502,
	body: { code: toPublicCode(error), message: toPublicMessage(error) },
};
```

El mapping real debe respetar convenciones existentes y conservar contratos legacy durante la migración.

## TypeScript

Usar `catch (error: unknown)` y guards/factories. Elegir una union discriminada o una clase cuando el repositorio ya use ese patrón:

```ts
type DomainError =
	| { code: 'invalid-input'; field: 'email'; cause?: unknown }
	| { code: 'dependency-unavailable'; retryable: boolean; cause?: unknown };

const isDomainError = (value: unknown): value is DomainError =>
	typeof value === 'object' && value !== null &&
		(value as { code?: unknown }).code === 'invalid-input';
```

Si se usa `Error` subclass, conservar `name`, `code` y `cause` según el contrato del runtime. No depender únicamente de `instanceof` para objetos que cruzan bundles, realms o procesos.

## JavaScript y otros lenguajes

En JavaScript sin tipos estáticos, usar factory, JSDoc y runtime guard. En otros lenguajes, preferir el error/result idiomático del repositorio. No introducir clases, `Result` o una jerarquía nueva si un discriminated object, enum existente o error type local resuelve el contrato.

Nunca lanzar strings ni objetos sin contrato deliberadamente. El normalizer debe aceptar valores legacy porque terceros pueden lanzar cualquier cosa:

```ts
const normalizeUnknown = (value: unknown): NormalizedError => {
	if (isDomainError(value)) return value;
	if (value instanceof Error) return { code: 'unexpected', cause: value };
	return { code: 'unexpected', cause: value };
};
```

El `cause` del ejemplo solo puede permanecer en contexto interno. No devolver `NormalizedError` directamente al browser.

## Metadata allowlisted

Definir metadata por código, no aceptar el objeto raw de un proveedor:

```ts
type SafeMetadata =
	| { code: 'invalid-input'; field: string }
	| { code: 'dependency-unavailable'; dependency: string; requestId?: string };
```

Permitir únicamente IDs estables, nombres de campo ya validados, contadores, límites y correlation IDs aprobados. Rechazar o eliminar tokens, credenciales, headers, cookies, URLs con secretos, payloads, nombres completos, emails y valores enviados sin truncar.

No mutar el error original para quitar `response`, `stack` o `cause`; construir DTO/log metadata nuevos.

## Legacy bridge

Cuando existe código legacy:

1. Preservar código, status y retry observables.
2. Normalizar el error en un único borde.
3. Mantener alias/códigos legacy durante transición.
4. Migrar consumers a `code`/guard.
5. Retirar bridge después de tests y búsqueda de usos restantes.

No cambiar `message` visible, status o shape público como efecto incidental. Si hay filtración sensible, corregir el leak explícitamente y agregar una aserción negativa.
