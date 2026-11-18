# Modelo de flujo (`flow-graph.json`)

Contrato del modelo intermedio. `scripts/lib/validate-flow-graph.mjs` lo valida y `scripts/lib/flow-graph-constants.mjs` es la fuente de los valores permitidos; si este documento y el validador difieren, gana el validador.

## Estructura

```json
{
  "schemaVersion": 1,
  "pullRequest": { "title": "…", "url": "https://github.com/<owner>/<repo>/pull/<n>", "baseRef": "main", "headRef": "feature/x" },
  "architecture": "flux-unidirectional",
  "groups": [{ "id": "ui", "label": "UI" }],
  "nodes": [],
  "edges": [],
  "businessFlow": { "summary": "…", "states": [], "transitions": [] },
  "outOfScope": [{ "path": "docs/", "reason": "Documentación, sin flujo." }]
}
```

- `pullRequest.url` es opcional. Con una URL de GitHub, cada evidencia del grafo enlaza a esa línea en «Files changed».
- `architecture` es texto libre: el nombre del perfil de `architecture-profiles.md` o una descripción corta.
- `groups`, `edges`, `businessFlow` y `outOfScope` son opcionales.
- Los `id` van en kebab-case y son únicos dentro de su lista.

## Nodos

```json
{
  "id": "favorites-store",
  "label": "FavoritesStore",
  "kind": "store",
  "group": "flux",
  "change": "added",
  "summary": "Guarda qué productos son favoritos.",
  "evidence": [{ "path": "app/src/main/java/shop/favorites/FavoritesStore.kt", "line": 21 }]
}
```

| Campo | Valores |
|---|---|
| `label` | El nombre que tiene en el código (clase, función, endpoint). |
| `symbol` | Cómo lo nombra el código cuando difiere de `label` (opcional). Se usa para comprobar que una relación verificada lo nombra. |
| `kind` | `view`, `action`, `dispatcher`, `store`, `state`, `effect`, `service`, `external`, `data`, `other` |
| `change` | `added`, `modified`, `removed`, `unchanged` |
| `group` | `id` de un grupo declarado (opcional). |
| `summary` | Una frase sobre qué hace (opcional). |

## Relaciones (`edges`)

```json
{
  "id": "dispatcher-notifies-store",
  "source": "dispatcher",
  "target": "favorites-store",
  "kind": "updates",
  "label": "entrega la acción",
  "change": "added",
  "confidence": "inferred",
  "reason": "El store se registra en el dispatcher por inyección de dependencias.",
  "evidence": [{ "path": "app/src/main/java/shop/di/StoreModule.kt", "line": 33 }]
}
```

| Campo | Valores |
|---|---|
| `kind` | `calls`, `dispatches`, `updates`, `observes`, `navigates`, `requests`, `other` |
| `label` | Texto de la flecha (opcional; por defecto, el nombre del `kind`). |
| `confidence` | `verified`: hay una línea que escribe la relación. `inferred`: la dedujiste. |
| `reason` | Obligatorio con `inferred`: qué te hace pensar que la relación existe. |

La flecha va en el sentido en que viaja el dato o el control: de quien despacha a lo despachado, del store a la vista que lo observa.

## Evidencia

```json
{ "path": "ruta/relativa/al/repo.kt", "line": 83, "side": "base" }
```

- `path` es relativo a la raíz del repo, con `/`.
- `line` es la línea del archivo en esa versión, desde 1.
- `side` es `head` (después del PR, por defecto) o `base` (antes). Usá `base` para lo eliminado: esa línea ya no existe en `head`.

Es obligatoria en todo elemento con `change` distinto de `unchanged` y en toda relación `verified`.

## Fuera del grafo (`outOfScope`)

```json
{ "path": "app/src/test/", "reason": "Tests de las piezas del grafo; no agregan flujo." }
```

Cada archivo que el PR cambió tiene que aparecer como evidencia de algún elemento o coincidir con una entrada de `outOfScope`. `path` es una ruta exacta, una carpeta terminada en `/` o un patrón: `*` vale por parte de un nombre y `**/` por cualquier cantidad de carpetas (`**/*.md`). `reason` dice por qué no forma parte del flujo; el reporte la cita.

## Flujo de negocio

```json
{
  "summary": "Desde el detalle se puede marcar un producto como favorito.",
  "states": [
    { "id": "not-favorite", "label": "No es favorito", "kind": "initial", "change": "unchanged", "nodeIds": ["product-detail-screen"] }
  ],
  "transitions": [
    {
      "id": "tap-favorite",
      "source": "not-favorite",
      "target": "saving",
      "trigger": "Tocar el corazón",
      "guard": "con sesión iniciada",
      "change": "added",
      "confidence": "verified",
      "evidence": [{ "path": "…", "line": 91 }]
    }
  ]
}
```

| Campo | Valores |
|---|---|
| `summary` | Una frase, con palabras de producto, sobre qué cambia para el usuario. El reporte la cita tal cual. |
| estado `kind` | `initial`, `normal`, `success`, `error`, `terminal` |
| estado `nodeIds` | Nodos que implementan ese estado (opcional). |
| `trigger` | La acción del usuario o el evento que dispara la transición. |
| `guard` | Condición para que ocurra (opcional). |

Los `label` y `trigger` se escriben como los diría alguien de producto, sin nombres de clases.

## Reglas que el validador exige

Errores (bloquean el render):

- Identificadores duplicados, mal formados o referencias a nodos, grupos o estados que no existen.
- Un elemento cambiado, o una relación `verified`, sin evidencia.
- Una relación `inferred` sin `reason`.
- Ningún elemento marcado como agregado, modificado o eliminado.
- Un flujo de negocio sin `summary`, o sin exactamente un estado `initial` vigente después del PR.
- Una relación cuyo `change` contradice a sus extremos: si toca algo agregado es `added`; si toca algo eliminado, `removed`.
- Dos relaciones con el mismo origen, destino y `kind`, o dos transiciones con el mismo origen, `trigger` y `guard`.
- Una entrada de `outOfScope` sin `path` o sin `reason`.

Con `--repo <dir>` el modelo se compara con el código y con el diff del PR. El lado `base` se lee en el commit donde el PR se separó de la base (el merge base), así que no importa si la base siguió avanzando. Es error:

- Una evidencia cuyo archivo no existe en su lado, o cuya línea pasa el final del archivo.
- Un elemento `added` sin evidencia en una línea que el diff agrega, uno `removed` sin evidencia en una línea que el diff quita, o uno `modified` sin evidencia en un archivo que el PR cambió.
- Una relación `verified` cuya evidencia, con dos líneas de contexto arriba y abajo, no nombra al otro extremo (por `symbol` o por `label`).
- Un archivo cambiado por el PR que no es evidencia de nada ni figura en `outOfScope`.

Avisos (se informan y no bloquean):

- Un nodo sin ninguna relación.
- Un estado de negocio al que no se llega desde el inicial.
- Una entrada de `outOfScope` que no coincide con ningún archivo del PR.
