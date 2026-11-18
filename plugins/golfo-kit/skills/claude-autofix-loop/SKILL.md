---
name: claude-autofix-loop
description: "Lanza el loop que auto-fixea los hallazgos de Claude (claude[bot], el workflow Claude Code Review de anthropics/claude-code-action con el plugin code-review) en un PR: fix en clone efímero, push, closeout del hilo, nueva ronda con el propio push, timeout y reintento del run, y merge sin preguntar tras el gate de CI. Usa el flujo centralizado de codex-autofix-loop con el perfil de revisor `claude`, sin copiarlo. Usar cuando pidan /claude-autofix-loop, «fixeá los comentarios de Claude en el PR», «loop de Claude para el PR N», un link a un comentario de claude[bot] con `## Code review`, o al abrir un PR en un repo cuyo revisor es ese workflow. Para comentarios de Codex usar codex-autofix-loop; para cerrar un solo comentario, codex-comment-closeout. Use when the user asks to auto-fix or loop over claude[bot] code review comments on a pull request."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "code-review"
  tags: "code-review, claude, pull-request, autofix, convergence"
  command: "/claude-autofix-loop"
---

# Claude auto-fix loop

Punto de entrada para el loop de auto-fix sobre los hallazgos de **Claude** (`claude[bot]`). El loop
no vive acá: es el de [`codex-autofix-loop`](../codex-autofix-loop/SKILL.md) con el **perfil de revisor
`claude`**. Así triage, fan-out, closeout, topes de rondas, gate de CI y merge tienen una sola fuente, y
un cambio al flujo llega a los dos revisores a la vez.

## Flujo

1. **Identificá el PR.** Del pedido (número, URL del PR o de un comentario como
   `…/pull/211#issuecomment-…`) o, si no hay, del PR abierto de la rama actual
   (`gh pr view --json number,headRefName,baseRefName,isDraft,url`). Un link a un comentario solo
   identifica el PR: el loop procesa todos los hallazgos pendientes de Claude, no solo ese.
2. **Confirmá que Claude es el revisor.** Buscá en `.github/workflows/` del head el workflow que
   corre `anthropics/claude-code-action` con un `prompt` que invoca `code-review`, y tomá su `name:`
   como `{{CLAUDE_REVIEW_WORKFLOW}}`. Si no existe, decilo en una línea y no lances el loop: sin ese
   workflow no hay reviews que esperar ni rondas que pedir.
3. **Leé el loop y el perfil**, en este orden y enteros: `SKILL.md` de `codex-autofix-loop` y su
   `references/reviewers/claude.md`. El perfil reemplaza los puntos de variación (pedido de review,
   ack, review terminada, fallida y limpia, fuentes de hallazgos, severidad, modos de fix) y gana
   sobre el texto de Codex en esos puntos; todo lo demás se sigue como dice el loop.
4. **Lanzalo** con «Cómo relanzarlo» de `codex-autofix-loop`, fijando `{{REVIEWER}}` = `claude` en el
   paso 0-ter, sin preguntar el tope ni el método de merge (pasos 0 y 0-bis). Con el perfil `claude`:
   - Estado en `.codex-autofix/processed-claude-<PR>.json` y monitor `Monitor claude-autofix PR #<PR>`.
   - `{{FIX_MODE}}` = `local`.
   - Cierre de cada hallazgo con `closeout.sh … --reviewer claude` (skill `codex-comment-closeout`).
5. **Reportá** en una línea: «Loop de Claude lanzado para el PR #N (tope R rondas, workflow
   `<nombre>`)». Si ya hay un loop vivo para ese PR, de este perfil o de Codex, no armes otro y decilo.

## Notas

- Desde la segunda ronda, el plugin `code-review` suele cortar sin publicar nada porque Claude ya
  comentó en el PR. El perfil trata ese run `success` sin comentarios nuevos como «review limpia
  silenciosa» y lo dice en el aviso del merge; ver «Review limpia» en `reviewers/claude.md`.
- No edites el workflow del repo ni respondas con menciones `@claude` para delegar fixes: el perfil
  `claude` solo admite fixes locales.
