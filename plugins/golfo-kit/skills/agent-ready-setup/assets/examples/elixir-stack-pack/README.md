# Ejemplo de pack con un stack primario propio

Pack mínimo que agrega un stack que golfo-kit no tiene: `beam/elixir`. El contrato completo está en
`references/profiles-and-lockfile.md`, sección «Profile packs». Para usarlo, copiá esta carpeta a un
repositorio propio y declarala en `.agents/agent-ready.json`:

```json
{
  "sources": {
    "packs": [
      { "name": "beam", "source": "path:./agent-packs/beam" }
    ]
  }
}
```

- `beam/elixir` es `kind: stack`: se detecta por `mix.exs` como cualquier stack de golfo-kit, y en un
  repo sin `profiles` la detección lo elige. También se selecciona a mano con `--profiles beam/elixir`.
- Publica sus rules con nombres propios (`elixir-*`) y su sección de `AGENTS.md` en `blocks/AGENTS.md`,
  que va al `AGENTS.md` de la raíz como bloque con id (`<!-- BEGIN AGENT-READY MANAGED: beam/elixir -->`).
- Trae `business-flows` de golfo-kit por `defaults`, y se combina con cualquier capability.
- Si otro stack también coincide (un `package.json` junto a `mix.exs`), la detección pide una selección
  explícita, salvo que uno declare `supersedes` sobre el otro.
