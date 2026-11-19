# Provider adapters

Leer esta referencia antes de ejecutar provider manualmente o modificar helper.

## Prompt obligatorio

Incluir target exacto (o delta desde `--since`), modo read-only, prohibición de editar/commit/push, prohibición de invocar otro reviewer, lectura de `REVIEW.md`/`CLAUDE.md`/`AGENTS.md`, chequeo de intención del PR y de causa raíz, y pedido de findings con archivo, línea, escenario, severidad, confianza, etiqueta (`Important`, `Nit`, `Pre-existing`) y clase de bug. El resultado empieza con el conteo por etiqueta. Si hay registro de findings (`--known-findings`), agregarlo para que no se repitan.

## Claude + Copilot API + Luna con esfuerzo max

```bash
env ANTHROPIC_BASE_URL="http://localhost:4141" \
  ANTHROPIC_AUTH_TOKEN="dummy" \
  ANTHROPIC_MODEL="gpt-6-luna[1m]" \
  ANTHROPIC_DEFAULT_OPUS_MODEL="gpt-6-luna[1m]" \
  ANTHROPIC_DEFAULT_SONNET_MODEL="gpt-6-luna[1m]" \
  CLAUDE_CODE_USE_VERTEX=0 \
  CLAUDE_CODE_USE_BEDROCK=0 \
  DISABLE_NON_ESSENTIAL_MODEL_CALLS=1 \
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
  CLAUDE_CODE_ATTRIBUTION_HEADER=0 \
  CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION=false \
  CLAUDE_CODE_ENABLE_AWAY_SUMMARY=0 \
  CLAUDE_CODE_TOTAL_TOKENS_REMINDER=off \
  MCP_CONNECT_TIMEOUT_MS=20000 \
  CLAUDE_CODE_SUBAGENT_MODEL="gpt-6-luna[1m]" \
  CLAUDE_CODE_EFFORT_LEVEL="max" \
  claude \
  --permission-mode plan \
  --tools Read,Grep,Glob,Bash \
  --no-session-persistence \
  --output-format text \
  -p "$REVIEW_PROMPT"
```

No heredar variables de Copilot API desde settings del usuario. Este comando fija perfil completo del provider. Subagentes usan gpt-6-luna con esfuerzo max.

## Claude direct

```bash
env -u ANTHROPIC_BASE_URL \
  -u ANTHROPIC_AUTH_TOKEN \
  -u ANTHROPIC_MODEL \
  -u ANTHROPIC_DEFAULT_HAIKU_MODEL \
  -u ANTHROPIC_DEFAULT_OPUS_MODEL \
  -u ANTHROPIC_DEFAULT_SONNET_MODEL \
  -u CLAUDE_CODE_SUBAGENT_MODEL \
  claude --setting-sources project,local \
  --permission-mode plan \
  --tools Read,Grep,Glob,Bash \
  --no-session-persistence \
  --output-format text \
  -p "$REVIEW_PROMPT"
```

This flow intentionally bypasses user-scoped Copilot API settings.

## Codex

```bash
codex review --uncommitted
codex review --base origin/main
codex review --commit HEAD
```

No combinar prompt inline con `codex review --base`.
