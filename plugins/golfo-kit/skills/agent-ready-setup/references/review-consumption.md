# Consumo en reviews automatizadas

Contrato para que un reviewer automatizado (Codex GitHub Review, un job de CI
con Claude Code o Codex, el `<stack>-review-pr` de cada stack) use las reglas de agent-ready-setup sin
sincronizarlas. Es distinto del setup interactivo. Leer al configurar un
reviewer o al explicar qué reglas usó una review.

## Reglas del contrato

1. **Todo sale del checkout.** El reviewer lee `AGENTS.md` (y los `AGENTS.md`
   anidados que su provider soporte), las rules bajo `.agents/rules/` y las
   skills bajo `.agents/skills/` del commit revisado. No hace falta red, ni
   marketplace, ni MCP para las reglas básicas.
2. **Nada se sincroniza durante la review.** Definir
   `AGENT_READY_SETUP_REVIEW_MODE=1` en el entorno del reviewer: el hook de
   SessionStart solo informa el estado, sin refrescar el marketplace ni llamar a
   la CLI del provider. Un repositorio con `updates.mode: pinned` tampoco escribe, pero
   la variable cubre los repos en `auto` y evita el refresh del marketplace.
3. **La versión del contexto queda identificada.** `.agents/agent-ready.lock.json`
   del mismo commit dice qué source (`source.version`, `source.revision`,
   `source.contentDigest`) y qué profiles estaban aplicados. El reporte de
   review la cita (ver `pr-review-workflow`, paso «Record the review context»).
4. **Presencia no es uso.** Que un archivo exista no prueba que el reviewer lo
   cargó. Para confirmar que un entorno descubre las skills y reglas, revisar
   un PR de prueba con un problema que solo una regla específica detecta y
   comprobar que el reporte lo marca y cita esa regla.
5. **MCP es enriquecimiento.** Un MCP caído no puede dejar a la review sin sus
   criterios básicos; las rules no dependen de él.

## Qué no cubre todavía

El piloto en dos repositorios reales y las métricas de detección y falsos
positivos (fases 5 y 6 de la propuesta de mejoras) no están implementados: este
documento fija el contrato que ese piloto tiene que verificar.
