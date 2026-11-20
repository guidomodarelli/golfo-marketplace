# Hook de respuestas de PR

Hook `PreToolUse` de Claude Code que se instala con el plugin `golfo-github`. Frena un comando que publica una respuesta en un PR de GitHub cuando el body no usa ninguno de los templates de las skills:

- `codex-comment-closeout` (`skills/codex-comment-closeout/templates/`), para comentarios de Codex o de Claude;
- `inline-thread-autofix` (`skills/inline-thread-autofix/references/closeout-template.md`), para comentarios de personas.

Existe porque la regla de usar el template depende de que el agente cargue la skill. En un flujo que trae sus propias instrucciones (por ejemplo, el Auto-fix de la app de escritorio con eventos `ci-monitor-event`) el agente a veces responde directo con texto libre. El hook no depende de eso.

## Qué revisa

Solo corre cuando el tool `Bash` o `PowerShell` ejecuta `gh` (campo `if` de `hooks.json`).

| Comando | Se revisa |
|---|---|
| Respuesta en un hilo de review: `pulls/<n>/comments/<id>/replies`, `pulls/<n>/comments` con `in_reply_to`, `addPullRequestReviewThreadReply` | Siempre |
| Comentario general, edición de un comentario o de una review: `issues/<n>/comments`, `issues/comments/<id>`, `pulls/comments/<id>`, `pulls/<n>/reviews/<id>`, `gh pr comment`, `gh issue comment` y sus mutations de GraphQL | Solo si responde a otro: lleva la línea `Addressed by [Claude Code]` del Auto-fix, un link a `#discussion_r…`, `#issuecomment-…` o `#pullrequestreview-…`, o `in_reply_to` |
| Lecturas (`gh api` sin `-f`, `-F`, `--input` ni método de escritura) y cualquier otro comando | No |

Un comentario que no responde a nadie (por ejemplo, el que pide una review a Codex) pasa sin revisar.

Cada invocación de `gh` se revisa por separado: en un comando que publica dos respuestas (`gh api … && gh api …`), las dos tienen que cumplir. El comando se parte respetando comillas, heredocs y here-strings, así que un body que menciona `gh api` no abre otra invocación. Los flags de `gh` pueden ir antes o entre los subcomandos (`gh --repo o/r pr comment`).

El body de cada invocación se busca en su propio texto, en los archivos que lee y en las variables que usa, si el mismo comando las asigna (`body=$(cat <<'EOF' … EOF)` en Bash, `$body = @' … '@` en PowerShell). Los archivos se leen de `-F body=@<ruta>` (también `-F "body=@<ruta con espacios>"`), `--input <ruta>` (JSON con escapes `\uXXXX` incluido), `--body-file <ruta>`, `-F <ruta>` de `gh pr comment`, `$(cat <ruta>)` y `Get-Content <ruta>`. Una ruta con variables (`$SCRATCH/reply.md`) o una variable que el comando no asigna no se pueden leer sin ejecutarlo: el hook las frena y pide una ruta literal.

## Cuándo deja pasar

El body tiene que contener el encabezado de alguna variante, por ejemplo `✅ **Resuelto**` o `💬 **Respuesta**`. También tiene que llevar el pie `<sub>🤖 …</sub>`, salvo en las variantes que no lo tienen. Los encabezados no están copiados en el hook: los saca de los templates cada vez que corre, así que una variante nueva o cambiada vale sin tocar el hook. La comparación ignora el selector de variación U+FE0F de emojis como «ℹ️».

Cuando frena, el agente recibe el motivo: qué skill cargar, los encabezados válidos y que edite con `PATCH` una respuesta libre ya publicada en lugar de publicar otra.

## Apagarlo

Definí `GOLFO_PR_REPLY_TEMPLATE_CHECK=off` en el `env` de la configuración de Claude Code (`settings.json`). El hook lee el entorno de Claude Code, no el del comando, así que el agente no lo puede apagar desde un comando.

## Límites

- Solo Claude Code: los plugins de Codex no pueden traer hooks, y el paquete portable que usa Hermes tampoco.
- Necesita `node` en el `PATH`. Sin `node`, o si el hook falla, Claude Code sigue con el comando: el hook nunca traba un comando por un error propio, y avisa con `systemMessage` cuando no pudo revisar.
- No ve lo que corre adentro de un script: `bash scripts/closeout.sh …` no se revisa, porque ese script ya arma la respuesta con los templates.
- Es una revisión de texto: no ejecuta ni expande el comando.

## Tests

`pnpm run test:pr-reply-hook` ejecuta el hook como proceso, igual que Claude Code, contra los templates reales del plugin.
