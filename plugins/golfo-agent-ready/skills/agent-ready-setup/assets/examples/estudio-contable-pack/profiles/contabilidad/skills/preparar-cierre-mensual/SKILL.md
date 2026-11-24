---
name: preparar-cierre-mensual
description: Arma el cierre mensual de un cliente con los saldos conciliados, los vencimientos impositivos del mes siguiente y los pendientes. Usar cuando se pida preparar, armar o redactar el cierre del mes de un cliente.
---

# Preparar el cierre mensual

1. Verificá que exista la conciliación del mes (`cierres/<cliente>/<año>-<mes>-conciliacion.md`). Si no existe, corré antes la skill `conciliar-extracto`.
2. Creá `cierres/<cliente>/<año>-<mes>.md` con estas secciones, en este orden: `## Saldos`, `## Diferencias de la conciliación`, `## Vencimientos del mes siguiente` y `## Pendientes`.
3. Copiá los saldos y las diferencias de la conciliación; no los recalcules con otro criterio.
4. Un vencimiento o una alícuota que no figura en los registros del cliente queda `[a verificar]` (`.agents/rules/contable-formato-reportes.md`): no lo completes de memoria.
5. Revisá los datos personales según `.agents/rules/contable-datos-personales.md`.
6. Respondé con la ruta del cierre y sugerí revisarlo con la skill `revisar-cierre` antes de entregarlo.
