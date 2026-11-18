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
  "businessFlow": { "states": [], "transitions": [] }
}
```

- `pullRequest.url` es opcional. Con una URL de GitHub, cada evidencia del grafo enlaza a esa línea en «Files changed».
- `architecture` es texto libre: el nombre del perfil de `architecture-profiles.md` o una descripción corta.
- `groups`, `edges` y `businessFlow` son opcionales.
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

## Flujo de negocio

```json
{
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
- Un flujo de negocio sin exactamente un estado `initial` vigente después del PR.

Con `--repo <dir>`, además, es error una evidencia cuyo archivo no existe en la ref de su lado (`baseRef` o `headRef`, también buscadas como `origin/<ref>`), o cuya línea pasa el final del archivo.

Avisos (se informan y no bloquean):

- Un nodo sin ninguna relación.
- Un estado de negocio al que no se llega desde el inicial.
