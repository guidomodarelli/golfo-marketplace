# Ejemplo de pack para un estudio jurídico

Pack para un repositorio sin código: escritos y actas de infracción en Markdown. Muestra que
agent-ready-setup sirve también fuera del software. El contrato completo está en
`references/profiles-and-lockfile.md`, sección «Profile packs». Para usarlo, copiá esta carpeta a un
repositorio propio y declarala en `.agents/agent-ready.json`:

```json
{
  "sources": {
    "packs": [
      { "name": "estudio-juridico", "source": "path:./agent-packs/estudio-juridico" }
    ]
  }
}
```

- `estudio-juridico/estudio` es un stack de dominio: se detecta por la estructura de carpetas
  (`actas/**/*.md` o `expedientes/**/*.md`), así que en un repo con esas carpetas la detección lo elige
  solo. No requiere `software-development`: el repo recibe el núcleo y el `AGENTS.md` neutro
  (propósito, estructura, convenciones), más su sección `## Estudio jurídico`.
- Trae por `defaults` la capability `estudio-juridico/actas-infraccion`: rules de formato, citas
  normativas y datos personales (`actas-*`), y la skill `redactar-acta` con su plantilla en
  `templates/acta.md`.
- El mismo caso funciona sin el stack, eligiendo solo la capability
  (`--profiles estudio-juridico/actas-infraccion`).
- Un `AGENTS.md` anidado en `actas/` se suma cuando agent-ready-setup soporte instrucciones por carpeta
  (#61); este ejemplo todavía no lo trae.
