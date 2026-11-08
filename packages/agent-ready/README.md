# @golfo/agent-ready

`agent-ready` en el PATH de una persona: corre el CLI de
[agent-ready-setup](https://github.com/guidomodarelli/golfo-marketplace/tree/main/plugins/golfo-kit/skills/agent-ready-setup)
que ya instaló tu agente, con los mismos subcomandos, flags, salida y códigos de salida.

```bash
npm install --global @golfo/agent-ready
agent-ready init
agent-ready doctor
agent-ready --help
```

## Qué motor usa

El paquete no trae una copia del motor: usa el del plugin golfo-kit instalado, así vos y tus
agentes corren la misma versión. Lo busca en este orden:

1. `AGENT_READY_SETUP_SKILL_DIR`, si está definida (por ejemplo, un checkout para desarrollo).
2. La versión más nueva entre las que instalaron Claude Code (cache y snapshot del marketplace,
   bajo `CLAUDE_CONFIG_DIR` o `~/.claude`), Codex (bajo `CODEX_HOME` o `~/.codex`) y Hermes
   (`HERMES_HOME`, `~/.hermes` o `%LOCALAPPDATA%\hermes` en Windows).

Si no encuentra ninguno, sale con 1 y dice cómo instalar el plugin; si el instalado es anterior
al CLI (golfo-kit 0.38.0), dice cómo actualizarlo.

## Requisitos

- Node.js 18 o más nuevo, para el launcher.
- Python 3.8 o más nuevo, como `python3` en el PATH (en Windows también sirven `py -3` y `python`),
  para el motor.
- El plugin golfo-kit instalado en Claude Code, Codex o Hermes.

## Licencia

MIT
