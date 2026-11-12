# Ejemplo de profile pack

Pack mínimo para probar `sources.packs` de `agent-ready-setup`. El contrato completo está en
`references/profiles-and-lockfile.md`, sección «Profile packs». Para usarlo, copiá esta carpeta a un
repositorio propio y declarala en `.agents/agent-ready.json`:

```json
{
  "profiles": ["acme/kafka-interno"],
  "sources": {
    "packs": [
      { "name": "acme", "source": "path:./agent-packs/acme" }
    ]
  }
}
```

- `acme/kafka-interno` requiere `node` y `acme/base`, y se sugiere si `package.json` declara `@acme/kafka`.
- `acme/backend` es un bundle: no publica assets y solo agrupa por `requires` lo que elige un backend Node de Acme (`node`, que trae `browser` por defaults, y `acme/kafka-interno`). El manifest guarda `acme/backend` y el lock lo que resolvió.
- Sus assets usan nombres propios (`acme-*`): un destino que ya publica Golfo u otro pack hace fallar la resolución.
