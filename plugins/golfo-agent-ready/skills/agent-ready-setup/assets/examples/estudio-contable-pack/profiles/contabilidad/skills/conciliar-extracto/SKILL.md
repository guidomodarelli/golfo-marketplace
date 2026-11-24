---
name: conciliar-extracto
description: Concilia el extracto bancario de un cliente con sus registros del mes, movimiento por movimiento, y deja el reporte de diferencias. Usar cuando se pida conciliar un extracto, cuadrar el banco o buscar por qué no cierra el saldo de una cuenta.
---

# Conciliar un extracto

1. Ubicá el extracto en `extractos/<cliente>/<año>-<mes>.csv` y los registros del mes en `liquidaciones/<cliente>/<año>-<mes>/`. Si falta alguno, pedilo; no lo inventes.
2. Emparejá cada movimiento del extracto con un registro por fecha, importe y concepto. Un movimiento sin pareja es una diferencia.
3. Recalculá el saldo final: saldo inicial más créditos menos débitos tiene que dar el saldo del extracto.
4. Escribí `cierres/<cliente>/<año>-<mes>-conciliacion.md` según `.agents/rules/contable-formato-reportes.md`: una tabla de diferencias (fecha, concepto, importe en el extracto, importe en los registros) y la sección `## Pendientes`.
5. Nombrá la cuenta como dice `.agents/rules/contable-datos-personales.md`.
6. Respondé con la ruta del reporte, la cantidad de diferencias y si el saldo cierra.
