<div align="right"><sup>📄 Archivos de código modificados: 4</sup></div>

## 📝 Descripción

### ❓ ¿Qué problema resuelve?
Los avisos de facturación se enviaban por un servicio legado y deben usar el nuevo motor de campañas.

### 💡 ¿Cuál fue la solución?
Se envían los tres avisos a sus campañas, preservando destinatario y datos del evento.

### Consolidación de #11

- Incorpora la limpieza de configuración del PR #11.
- Jira asociado a la limpieza: [ACME-7](https://acme.atlassian.net/browse/ACME-7).

## 🚀 Tipo de Cambio

- [ ] 🐛 **Bug Fix** — corrige comportamiento defectuoso
- [x] ✨ **New Feature** — agrega funcionalidad nueva

## 🧪 Pruebas Manuales

1. Disparar el evento de prueba en staging.
2. Verificar la ejecución en el panel de campañas.
