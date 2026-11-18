---
name: constants-refactor
description: Analiza y refactoriza constantes, literales funcionales y contratos cross-layer en cualquier repositorio y lenguaje. Invocar siempre que se cree, modifique, elimine, mueva o revise una constante, aunque el cambio parezca puntual; también cuando usuario pida revisar constantes, mover valores a constants/ o al archivo de configuración, limpiar hardcodes, responder comentarios de PR sobre constantes, centralizar límites/códigos/rutas/regex/timeouts o reducir duplicación entre capas, aunque no mencione una carpeta constants. Da a cada valor estático una fuente canónica fuera del módulo consumidor, incluso con un solo consumidor; usa constants/ para invariantes y contratos, y el archivo de configuración del proyecto (application.yml o .properties en Kotlin y Java, appsettings.json, settings) para valores operativos o ajustables, según lenguaje y convención del repo. Distingue variables calculadas, estado mutable y resultados runtime, que no son constantes. Preserva comportamiento y valida cada cambio.
license: MIT
metadata:
  version: "1.1.0"
  author: "Guido Modarelli"
  category: "refactor"
  tags: "refactor, constants, configuration, literals, cross-layer"
  command: "/constants-refactor"
---

# Constants Refactor

## Objetivo

Dar a toda constante estática con significado de dominio o contrato una fuente canónica fuera del módulo consumidor, aunque exista un solo consumidor actual. La cantidad de usos no decide la ubicación; la naturaleza del valor decide el destino: `constants/` para invariantes y contratos, y el archivo de configuración del proyecto para valores operativos o ajustables cuando el lenguaje y el repositorio tienen esa convención, como en Kotlin y Java (ver "Mover al archivo de configuración"). No confundir constantes con variables calculadas en runtime, estado mutable o resultados de llamadas, y no extraer literales triviales ni vocabulario estándar del lenguaje o plataforma (ver "Mantener fuera de `constants/`").

Las rules del proyecto (`AGENTS.md`, `.agents/rules/` o equivalentes) prevalecen sobre esta skill: aplicar sus convenciones de ubicación de módulos, naming, comentarios, configuración por entorno y secretos.

Aplicar workflow completo cuando usuario pida implementar. Entregar solo análisis cuando usuario pida review o informe sin cambios.

## Modos

Elegir el modo antes de inventariar; el alcance y la base de comparación dependen de él.

| Modo | Cuándo | Alcance | Base |
|---|---|---|---|
| **PR / diff** | Revisar o ajustar un PR, una rama o cambios locales | Archivos del diff y sus consumers directos | `git diff BASE...HEAD` separado de cambios no commiteados |
| **Auditoría de repo** | Revisar o refactorizar el repositorio completo | Todo el código de producción y el tooling versionado | Estado actual de la rama; no requiere diff |

En ambos modos, aplicar al alcance esta regla por tipo de código:

- **Producción** (lo que se publica, despliega o ejecuta en runtime): aplicar la skill completa.
- **Tooling** (`scripts/`, `benchmarks/`, build, release): misma regla, con su propio `constants/` junto al tooling (por ejemplo `scripts/constants/`); no importar constantes de tooling desde producción ni al revés salvo contrato compartido real.
- **Tests**: los inputs y fixtures que representan datos de prueba se quedan en el test. Los valores esperados de un contrato **público u observable** (messageIds, códigos de error, textos de diagnóstico, rutas publicadas) se escriben como literales en el test: son el oráculo y deben fallar si la constante cambia por accidente. Los valores internos que el test solo usa como configuración o setup (límites, timeouts) se importan desde `constants/` en vez de duplicarse. No crear `constants/` dentro de tests salvo fixtures compartidos entre varios archivos de test.
- **Código generado** (catálogos, clientes generados, `dist/`): no tocar.

## Quick start

1. Resolver repositorio, lenguaje/framework, modo y alcance exacto. Detectar el archivo de configuración del proyecto y su binding tipado ([references/config-destinations.md](references/config-destinations.md)).
2. Modo PR: separar `git diff BASE...HEAD` de cambios no commiteados. Modo auditoría: listar archivos de producción y tooling versionados.
3. Medir línea base (ver "Métrica objetiva").
4. Inventariar declaraciones `const`, atoms escalares, objetos/arrays de valores fijos, enums/union literals, regex, límites, códigos, paths, timeouts y strings repetidos.
5. Comparar inventario con `constants/`, `config/`, `permissions/`, `utils/`, tipos/interfaces, schemas y módulos de dominio existentes.
6. Clasificar cada candidato: `mover a constants/`, `mover a configuración`, `mantener como variable runtime` o `no tocar` (trivial, vocabulario estándar, copy).
7. Implementar fuentes canónicas, migrar consumers y tests.
8. Ejecutar validaciones, repetir la métrica y reportar bloqueos reales sin ocultarlos.

## Alcance y exclusiones

- Interpretar `@constants/` como carpeta `constants/` salvo que el repositorio ya defina otro alias explícito.
- En lenguajes que organizan por package o namespace (Kotlin, Java, C#, Go), `constants/` es el package o namespace de constantes equivalente; los ejemplos en TypeScript de esta skill se trasladan a esa forma según [references/config-destinations.md](references/config-destinations.md).
- Preferir aliases e imports existentes; no crear un alias nuevo solo para este refactor.
- Respetar exclusiones explícitas del usuario por dominio, módulo, ruta o PR. Si el usuario excluye un dominio, no modificar servicios, rutas, permisos, guards ni tests de ese dominio, aunque compartan strings con otro flujo.
- No editar manualmente catálogos generados de traducciones salvo pedido explícito y workflow del repositorio.
- No hacer commit, push, comentarios de PR ni cambios externos sin autorización explícita.

## Inventario

### Fuentes que revisar

Adaptar al layout del repositorio:

- `constants/`, `config/`, `settings/`;
- `interfaces/`, `types/` y exports runtime dentro de módulos de tipos;
- API, backend, frontend, servicios, adapters, middlewares y utilidades;
- schemas y validadores;
- hooks, loaders, SSR y clientes backend-for-frontend cuando existan;
- tests y mocks;
- comentarios inline y reviews del PR, cuando exista PR.

### Búsquedas mínimas

Adaptar comandos al shell, lenguaje y layout:

```bash
rg -n "export const|const [A-Z][A-Z0-9_]+|as const|enum " .
rg -n "['\"](status|reason|error|code|path|timeout|limit)" src api app lib utils tests
rg -n "timeout|max\(|min\(|regex\(|allowlist" src api app lib utils
rg -n "from ['\"].*/(interfaces|types|constants)/" src api app lib utils tests
```

En modo PR:

- determinar base y HEAD desde GitHub/git;
- leer comentarios inline, threads y estado `resolved/outdated`;
- separar comentarios abiertos aplicables de comentarios ya resueltos u obsoletos;
- no tratar boilerplate de bots como hallazgo.

## Organización física por dominio

Cuando `constants/` contenga varios módulos relacionados, agruparlos por dominio funcional y boundary, no solo por tipo primitivo o por orden de creación:

```text
constants/
├── <domain-a>/
│   ├── index.ts
│   ├── <domain-a>.ts
│   └── <domain-a>-errors.ts
├── <domain-b>/
│   └── index.ts
└── <shared-concern>.ts
```

Aplicar estas reglas:

- Mover juntas las constantes que representan el mismo dominio o contrato —por ejemplo códigos, rutas, límites, estados y tipos de un flujo— y mantener separadas las preocupaciones transversales realmente reutilizadas.
- Usar `index.ts` (o el entrypoint equivalente del lenguaje) como fachada del dominio cuando haya varios módulos. Reexportar desde allí sin redeclarar valores; una sola definición evita divergencias.
- Evitar colisiones entre un archivo y una carpeta con el mismo basename (`constants/<domain>.ts` y `constants/<domain>/`). Si se conserva el specifier público, mover la implementación al directorio y usar `index.ts` como fachada.
- Conservar shims legacy como archivos que solo reexportan la ubicación canónica cuando el path profundo no colisiona con una carpeta nueva. Mantener imports públicos existentes cuando la resolución siga siendo válida y migrarlos por boundary cuando no lo sea.
- Representar rutas o paths relacionados como un objeto con propiedades semánticas; evitar constantes escalares sueltas para fragmentos del mismo boundary. Derivar rutas compuestas desde ese objeto y preservar la separación entre rutas de boundaries distintos.
- Preservar el alias soportado por runtime y evitar cambiar imports masivamente solo por uniformidad. Verificar compilador, test runner, bundler y runtime por separado cuando sus resolvers difieran.
- No colocar en `constants/` expresiones cuyo valor se obtiene o cambia durante runtime.
- Revisar el boundary de cada constante: no exponer en código cliente o paquetes públicos valores server-only, detalles internos de servicios externos o metadata sensible.
- Mantener constantes puras y sin side effects. Evitar que los barrels importen servicios u otros módulos que introduzcan ciclos; los módulos de dominio pueden depender de constantes compartidas, no al revés.
- Tras mover constantes, validar valores, referencias, tipos, identidad de objetos cuando importe y resolución de barrels/shims mediante tests de comportamiento o typecheck; no testear strings del archivo fuente.

## Pedidos explícitos de reubicación

Cuando usuario pida mover constantes de módulo o feature hacia `constants/`:

1. Buscar primero archivo de dominio existente, por ejemplo `constants/<domain>/<feature>.ts`; no crear `constants.ts` genérico.
2. Mover cada constante estática según "Clasificación": el destino lo decide la naturaleza del valor, no la cantidad de consumidores.
3. Mantener fuera de `constants/` lo que no es constante, lo trivial, el vocabulario estándar y los valores con destino propio de "Mover al archivo de configuración" y "Separar destinos". Si el pedido nombra `constants/` para un valor que corresponde a configuración, moverlo a configuración y decirlo en el reporte.
4. Separar tipos runtime de UI: constants no deben importar valores desde capas de presentación ni desde módulos que dependan de constants.
5. Mantener specifiers públicos existentes solo cuando el barrel los soporte; no introducir un alias nuevo por uniformidad.

### Barrels y contratos públicos

Antes de migrar consumers, recorrer destino y todos sus barrels ascendentes. Si un barrel usa lista explícita de exports, agregar el nuevo símbolo allí; `export *` en barrel interno no implica exposición desde entrypoint raíz. Ejecutar typecheck después de actualizar barrels y antes de cerrar refactor.

### Atoms escalares y agregados

- Cuando un literal tenga significado unitario y estable, definirlo una sola vez como atom escalar en `constants/`, aunque hoy tenga un solo consumidor: `const SEMANTIC_ATOM = 'value' as const`.
- Construir arrays y agregados contractuales desde atoms: `const CONTRACT_VALUES = [SEMANTIC_ATOM, OTHER_ATOM] as const`.
- Nombrar atoms por rol semántico y dominio (`PAYMENT_SOURCE_CARD`), no por valor genérico (`VALUE`, `ITEM`, `TYPE`).
- Mantener arrays distintos cuando tengan semánticas distintas aunque compartan atoms (`mixed` no pertenece a una lista de valores individuales).
- Compartir atom después de comprobar equivalencia de significado, boundary, serialización y consumers. La coincidencia textual aislada no justifica reutilizar un atom existente, pero tampoco justifica mantenerlo en el consumidor. Dos conceptos distintos con el mismo valor (por ejemplo dos severidades por defecto que hoy valen `"warn"`) quedan como constantes separadas.
- Mantener atoms puros, sin servicios, permisos, imports server-only ni side effects.
- Preservar orden, identidad y forma observable al componer arrays desde atoms. No reemplazar referencias canónicas por `Array.from`, spread, `Object.freeze` o composición dinámica cuando eso cambie identidad, mutabilidad, flags o serialización requerida por consumers; si se usan, validarlo explícitamente.
- Un refactor de constants debe limitarse a extracción, composición y migración de referencias; no agregar condicionales, guards, normalización ni cambios de validación salvo pedido explícito separado.
- Priorizar composición simple y legible. Mantener regex literales cuando derivarlas dinámicamente agregue helpers, escapes o complejidad sin reducir un drift comprobado; en ese caso cubrir sincronización con tests.
- Si un patrón canónico ya existe como string, reutilizarlo mediante `new RegExp(CANONICAL_PATTERN)` cuando el consumidor requiera `RegExp`; no duplicar un equivalente literal solo para evitar una advertencia de lint. Si una regla de lint marca esa conversión segura, usar un suppress puntual y documentado, limitado a esa línea.

### Tipos y constantes

- No derivar tipos desde constantes con `typeof X[number]`, `(typeof X)[keyof typeof X]` ni variantes. Declarar el tipo como union literal explícita y legible.
- Verificar la sincronía entre constante y tipo desde la constante: `satisfies` o anotación contra el tipo explícito (`[A, B] as const satisfies readonly MyUnion[]`, `{ ... } satisfies Record<MyUnion, string>`). Así el tipo sigue siendo legible en declaraciones y errores, y un drift falla en typecheck.
- Ubicar el tipo donde corresponda al contrato (módulo de tipos públicos o del dominio); `constants/` puede importarlo solo como type-only.
- Cuando `.includes()` o `.has()` reciben un valor más amplio que la union, anotar la colección como `readonly string[]`/`ReadonlySet<string>` en vez de castear en cada consumer.

## Clasificación

### Mover a `constants/`

Mover siempre toda declaración que represente un valor estático con significado de dominio o contrato, sin exigir reutilización previa:

- constantes de contrato, aunque tengan un solo consumidor;
- límites, estados, códigos, rutas, regex, allowlists, atributos y claves públicas;
- metadata estática que no dependa del entorno (schemas, mapas estáticos, defaults);
- runtime constants ubicadas dentro de `interfaces/` o `types/`;
- literales con significado unitario y elementos de arrays contractuales, aunque hoy no estén repetidos;
- msgids/claves de traducción o de mensajes, estilos, statuses HTTP y nombres de variables de entorno;
- timeouts, paginación y delays cuando son parte fija del contrato o cuando el proyecto no tiene archivo de configuración (ver sección siguiente).

Esta es la regla canónica de ubicación: la cantidad de referencias y la visibilidad no cambian el destino; solo "Mover al archivo de configuración", "Separar destinos" y "Mantener fuera" definen alternativas.

### Mover al archivo de configuración

No toda constante va a `constants/`. En muchos ecosistemas el destino idiomático de un valor operativo es el archivo de configuración del proyecto, leído con binding tipado. En Kotlin y Java es la norma (`application.yml` o `application.properties` más una clase de propiedades): una clase `Constants` con timeouts y URLs va contra la convención, porque obliga a recompilar y redesplegar para ajustar un valor que se espera cambiar por entorno.

Decidir por la naturaleza del valor; el lenguaje define dónde queda cada destino, no cuál corresponde:

| Pregunta | Destino |
|---|---|
| ¿Varía por entorno, deployment, site o brand, o se espera ajustarlo sin tocar la lógica de negocio? | Archivo de configuración |
| ¿Es un invariante: si cambia, cambia el contrato o el código que lo interpreta? | `constants/` |

- **Configuración**: endpoints y hosts, nombres de buckets/topics/colas, app ids, límites y cuotas de servicios externos, timeouts, reintentos y backoff, tamaños de pool, batch o página por defecto, TTL de caché, expresiones cron y feature flags.
- **`constants/`**: códigos de error, estados, nombres de headers, fragmentos de ruta, regex de formato, msgids, valores de protocolo y todo valor que el lenguaje exige como constante de compilación (por ejemplo, argumentos de anotaciones en Java y Kotlin).

Al mover un valor a configuración:

1. Usar el mecanismo que el repositorio ya tiene (archivo, perfiles y clase o módulo de binding), detectado según [references/config-destinations.md](references/config-destinations.md). No sumar un segundo mecanismo ni otra librería.
2. Si el proyecto no tiene archivo de configuración ni convención para leerlo, no crear esa infraestructura como efecto del refactor: el valor va a `constants/` y se reporta como candidato a configuración en "Riesgos o bloqueos".
3. Conservar el valor efectivo: el literal actual pasa a ser el default, con el mismo tipo y la misma unidad. Una clave obligatoria sin default, o un perfil que ya la pisa con otro valor, cambia el comportamiento; revisar los overrides existentes y reportarlos.
4. Leer la clave en un único binding tipado (clase de propiedades, objeto de settings) y pasarlo a los consumers. Repetir el nombre de la clave como string en cada consumer reintroduce el hardcode.
5. En tests, fijar el valor con la configuración de test o construyendo el binding; no depender del archivo de producción.

### Mantener fuera de `constants/`

- **No constantes**: variables calculadas en runtime, estado mutable, resultados de llamadas, respuestas, datos derivados de input, instancias creadas al importar (clientes, segmenters, loggers).
- **Triviales**: `0`, `1`, `-1`, `true`, `false`, `""` y literales mecánicos cuyo nombre sería más ruidoso que el valor (separadores de path `"/"`, un espacio, un salto de línea usado como join).
- **Vocabulario estándar del lenguaje, plataforma o estándar**, autoexplicativo y definido fuera del proyecto: resultados de `typeof`, keywords de JSON Schema (`type: "object"`), selectores o hooks del framework (`"Program:exit"`, nombres de lifecycle), métodos HTTP en la definición de una ruta, encodings (`"utf8"`), nombres de eventos del DOM. Si el valor está disponible como constante exportada por una dependencia de runtime, usar esa fuente; si solo existe en una dependencia de desarrollo, no importarla en producción.
- **Declaraciones locales de montaje**: las que la convención del proyecto exige junto al router o schema que montan (por ejemplo, un subrouter y su schema); los límites y valores de dominio que ese schema usa sí van a `constants/`.
- **Copy user-facing** (mensajes, labels, descripciones): ver "Separar destinos".

### Separar destinos

- autorización → módulo `permissions/`, `auth/` o equivalente del dominio, no `constants` genérico;
- valores por entorno/deployment y valores operativos ajustables → archivo de configuración o settings, no `constants` (ver "Mover al archivo de configuración");
- secretos, credenciales y tokens → variables de entorno o secret manager, nunca hardcodeados en `constants/` ni en `config/` versionado;
- rutas compartidas entre capas propias → `constants/routes.ts` o equivalente;
- paths privados de servicios externos → cliente/adapter;
- copy, labels y mensajes user-facing → i18n/localization cuando el proyecto lo tenga; sus msgids/claves sí van a `constants/`. **Si el proyecto no tiene i18n**, dejar el copy donde lo espera la convención del framework (por ejemplo `meta.messages` de una regla ESLint, textos de un CLI junto a su comando) y mover solo sus identificadores; no crear infraestructura de i18n como efecto del refactor. Con i18n basado en `gettext`, el msgid es el propio texto fuente y queda en el catálogo, no en `constants/`;
- estados internos de un parser sin significado de dominio → módulo del parser; si una regex o estado forma parte de un contrato, va a `constants/`.

## Diseño seguro

### Preservar semántica de validación

Centralizar la fuente de un patrón no debe cambiar el mecanismo de validación.

Preferir:

```ts
export const ACCOUNT_KIND_PATTERN = /^(personal|business)$/;

schema.string().regex(ACCOUNT_KIND_PATTERN)
```

No reemplazar automáticamente por un validador distinto (por ejemplo `enum` en vez de `regex`): puede cambiar sanitización, coerción, clasificación y forma de errores observables.

Para límites compartidos, usar misma constante en schema y validación manual. Mantener separados límites con objetivos distintos, por ejemplo el de un lookup frente al de un payload malformado que solo se registra en logs.

### Seguridad y autorización

- Mantener validación basada en schemas en cada boundary usando el validador aprobado por el proyecto.
- Mantener allowlists; no reemplazarlas por valores derivados de input no confiable.
- No incluir tokens, cookies, headers, secrets, payloads sensibles ni PII en logs.
- No tocar autorización, métodos HTTP, CSRF ni auth como efecto colateral de mover valores.
- No introducir dependencias nuevas para resolver duplicación si utilidades existentes alcanzan.

### Ciclos

- Mantener imports type-only desde `interfaces/` o `types/` hacia `constants/`; nunca imports de valores.
- Preferir dirección unidireccional: `constants → consumers`, con tipos importados type-only.
- No usar `enum` si la configuración TypeScript prohíbe declaraciones no erasables.
- Verificar reglas de ciclo, resolución de imports y aliases configurados por el repositorio.

### Documentación

- Agregar documentación del lenguaje para nuevas constantes, objetos, regex y helpers no obvios.
- Documentar unidades (`_MS`), límites, formato y consumidor esperado.
- Si una constante de tooling o producción depende de su ubicación (paths relativos al módulo), documentarlo.

## Implementación

1. Crear o ampliar archivo de dominio cohesivo en `constants/` y, para los valores de configuración, la sección del archivo de configuración y su binding tipado.
2. Identificar todos los valores estáticos y definirlos allí; crear atoms antes de arrays/agregados contractuales cuando corresponda.
3. Construir arrays/agregados desde atoms y verificarlos con `satisfies` contra tipos explícitos.
4. Mantener nombre semántico; no usar nombres genéricos como `VALUE`, `LIMIT`, `DATA`.
5. Mover valores sin cambiar strings, orden, default, serialización o respuesta.
6. Respetar el orden de declaración: una constante usada por otra del mismo módulo se declara antes (evitar TDZ).
7. Actualizar barrels, imports de producción, tests y valores esperados que reflejan contratos.
8. Revisar diff por dominio excluido antes de continuar.
9. No mezclar refactor de constantes con cambios funcionales no solicitados.

## Verificación

Ejecutar comandos definidos por repo. Como base genérica:

```bash
git diff --check
```

Luego detectar y ejecutar lint, typecheck, tests y build. Ejecutar primero suites focales de los módulos afectados y luego la suite completa. En refactors con atoms, comprobar valores, orden, identidad de arrays/tuplas, serialización y rechazo de valores inválidos.

### Métrica objetiva

Medir antes y después con una herramienta automática en vez de estimar:

- Si el ecosistema tiene un linter de literales mágicos o duplicados (reglas `no-magic-*`, `no-duplicate-string`, equivalentes), correrlo sobre el alcance antes de cambiar y al terminar; reportar el conteo y cada hallazgo remanente con su justificación.
- Si no existe, usar un conteo reproducible con búsquedas (`rg`) sobre literales en comparaciones, `switch`/`case` y argumentos de llamadas, y documentar el comando.
- Un hallazgo remanente es aceptable solo si cae en "Mantener fuera" o es un falso positivo explicado (por ejemplo, dos conceptos con el mismo valor).

### Paridad de comportamiento

Cuando el refactor cambia la forma de la lógica y no solo referencias (condiciones anidadas → tabla de rangos, `replace` → template, objetos literales → objeto compartido), escribir o identificar un test que cubra ese comportamiento y ejecutarlo **también contra el código original** (por ejemplo con `git stash` del código de producción). Si pasa en ambos, la paridad está demostrada; si no existe cobertura previa, agregar el test.

### Contratos públicos de librerías

Si el repositorio publica un paquete o SDK:

- Comparar las declaraciones públicas generadas (`.d.ts`, stubs, headers, docs de API) antes y después; los tipos resueltos deben ser idénticos y legibles (sin `typeof` derivados, ver "Tipos y constantes").
- Verificar que las declaraciones públicas no importen módulos o tipos que el consumidor no tenga instalados (dependencias de desarrollo).
- Ejecutar el typecheck de un consumidor real o del test de empaquetado existente.

No marcar tarea como completa si tests, lint o build fallan. Si falla por cambio preexistente o de entorno, aislarlo, documentar archivo/línea y no modificarlo sin autorización.

## Formato de salida

Usar este formato salvo que usuario pida otro:

```markdown
## Alcance
- Modo, base/HEAD o rama, archivos y cambios locales excluidos.

## Métrica
| Momento | Hallazgos | Herramienta |

## Candidatos movidos
| Archivo/línea | Valor | Destino (`constants/` o configuración) | Motivo |

## Valores fuera de `constants/`
| Archivo/línea | Valor | Motivo: no constante / trivial / vocabulario estándar / copy |

## Cambios aplicados
- Fuentes canónicas.
- Consumers y tests.
- Exclusiones respetadas.

## Validación
| Comando | Resultado |

## Riesgos o bloqueos
- Fallos reales, preexistentes o no ejecutados.
```

Ser explícito cuando cambio es solo estructural y cuando una sustitución puede modificar comportamiento observable. No decir “todo funciona” si suite completa no pasó.
