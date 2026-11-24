# Ejemplo de pack para un estudio contable

Pack para un repositorio sin código: extractos, liquidaciones y cierres mensuales en Markdown y CSV. A
diferencia de `estudio-juridico-pack`, que solo trae rules y una skill, este muestra subagentes y
orquestación fuera del software. El contrato completo está en `references/profile-packs.md` («Cómo declarar
un subagente» y «Subagente o skill»). Para usarlo, copiá esta carpeta a un repositorio propio y declarala en
`.agents/agent-ready.json`:

```json
{
  "providers": ["claude", "codex", "antigravity"],
  "sources": {
    "packs": [
      { "name": "estudio-contable", "source": "path:./agent-packs/estudio-contable" }
    ]
  }
}
```

## Qué trae

- `estudio-contable/estudio` es un stack de dominio: se detecta por las carpetas `liquidaciones/**` o
  `extractos/**`, no requiere `software-development` y publica la sección `## Estudio contable` de
  `AGENTS.md`. Trae por `defaults` la capability `estudio-contable/contabilidad` y la capability `learning`
  del contenido; un repo que no quiere `learning` la deja afuera con `"excludedDefaults": ["learning"]`.
- `estudio-contable/contabilidad` trae:
  - las rules `contable-datos-personales` (CUIT, CBU y cuentas solo en el encabezado) y
    `contable-formato-reportes` (importes, fechas, `## Pendientes` y `[a verificar]`);
  - las skills `conciliar-extracto` y `preparar-cierre-mensual`, que corren en la sesión principal;
  - los subagentes `auditor-contable` e `investigador-normativo`;
  - la skill `revisar-cierre`, que es solo el roster: sigue `orchestrate-agents`, la skill de la capability
    `orchestration` del contenido, que `contabilidad` declara en `requires`.

## Por qué cada pieza es una skill o un subagente

El rol del contador no es un subagente: es este pack, con sus rules y skills, en la sesión principal.
Conciliar y preparar el cierre son skills porque trabajan con lo que la persona ve y corrige en la conversación.
Los dos subagentes existen por una razón concreta:

| Subagente | Razón | Metadatos |
|---|---|---|
| `auditor-contable` | Revisión independiente con permisos restringidos: no arrastra el razonamiento de quien armó el cierre y no puede editarlo | `access: read-only`, `model-tier: deep` |
| `investigador-normativo` | Contexto aislado: lee normativa larga y devuelve solo la conclusión | `model-tier: balanced`, sin `access` porque necesita buscar en la web |

La orquestación corre en la sesión principal, porque en los tres providers un subagente no lanza otros por
defecto. `revisar-cierre` despacha siempre al auditor y al investigador solo cuando el cierre tiene algo
`[a verificar]`.

## Qué ve cada provider

`agent-ready apply` proyecta los mismos archivos de `.agents/` para todos y renderiza una vista de cada
subagente por provider:

| | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Rules | `.claude/rules/` (vistas de `.agents/rules/`) y `CLAUDE.md` (proxy de `AGENTS.md`) | `AGENTS.md` | `AGENTS.md` y `.agents/rules/` (`trigger: always_on`) |
| Skills | `.claude/skills/` (vistas de `.agents/skills/`) | `.agents/skills/` | `.agents/skills/` |
| `auditor-contable` | `.claude/agents/auditor-contable.md` con `tools: Read, Grep, Glob` y `model: opus` | `.codex/agents/auditor-contable.toml` con `model_reasoning_effort = "high"` | `.agents/agents/auditor-contable.md` con `tools` de lectura y `model: pro` |
| `investigador-normativo` | `.claude/agents/investigador-normativo.md` con `model: sonnet` | `.codex/agents/investigador-normativo.toml` con `model_reasoning_effort = "medium"` | `.agents/agents/investigador-normativo.md` con `model: inherit` |

Codex mantiene el sandbox de la sesión que arranca al subagente, así que el auditor `read-only` puede igual
editar archivos ahí: `agent-ready plan` lo avisa como límite del provider, no como conflicto.

## Evals

Cada skill trae `evals/eval-config.json`, que viaja con ella al proyecto. Desde el repo que adopta el pack:

```bash
run-evals .agents/skills/conciliar-extracto
run-evals .agents/skills/revisar-cierre --baseline --repeat 3
```
