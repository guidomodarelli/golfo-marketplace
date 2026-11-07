# Ejemplo de profile pack

Pack mínimo para probar `profileSources` de `agent-ready-setup`. El contrato completo está en
`references/profiles-and-lockfile.md`, sección «Profile packs». Para usarlo, copiá esta carpeta a un
repositorio propio y declarala en `.agents/agent-ready.json`:

```json
{
  "profiles": ["acme/kafka-interno"],
  "profileSources": [
    { "name": "acme", "source": "path:./agent-packs/acme" }
  ]
}
```

- `acme/kafka-interno` requiere `node` y `acme/base`, y se sugiere si `package.json` declara `@acme/kafka`.
- Sus assets usan nombres propios (`acme-*`): un destino que ya publica Golfo u otro pack hace fallar la resolución.
