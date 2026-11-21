# Ejemplo de pack para un estudio jurídico

Pack para un repositorio sin código: escritos y actas de infracción en Markdown. Muestra que
agent-ready-setup sirve también fuera del software. El contrato completo está en
`references/profile-packs.md`. Para usarlo, copiá esta carpeta a un
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
- Trae también por `defaults` la capability `learning` del contenido: lo que el abogado pide que dure
  («de ahora en más, el número de expediente va en el encabezado») queda como rule del repo, sin que nadie
  la escriba. Solo aprende de los mensajes del usuario, nunca del texto de un expediente
  (`references/learning.md`). Su configuración va en el mismo manifest; por ejemplo, para que el agente
  no avise lo que guarda ni pregunte el alcance de una instrucción ambigua:

  ```json
  {
    "learning": { "notify": false, "clarify": "off" }
  }
  ```

  Un repo que no la quiere la deja afuera con `"excludedDefaults": ["learning"]`.
- El mismo caso funciona sin el stack, eligiendo solo la capability
  (`--profiles estudio-juridico/actas-infraccion`).
- Un `AGENTS.md` anidado en `actas/` se suma cuando agent-ready-setup soporte instrucciones por carpeta
  (#61); este ejemplo todavía no lo trae.
