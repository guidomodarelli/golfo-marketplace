---
trigger: always_on
---

# Datos personales de los clientes

- CUIT, CBU, número de cuenta y domicilio de un cliente solo van en el encabezado de un reporte, nunca en el cuerpo, en los nombres de archivo ni en los mensajes de commit.
- En el cuerpo de un reporte, una cuenta se nombra por sus últimos cuatro dígitos (`cuenta ****1234`).
- En ejemplos, borradores y pruebas, usar datos ficticios (`Cliente A`, `CUIT 00-00000000-0`).
- No copiar datos de un cliente a la carpeta, el reporte o el mensaje de otro.
