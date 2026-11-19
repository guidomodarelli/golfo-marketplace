---
name: node-runtime-debugging
description: >-
  Depura cambios de servidores Node.js y BFF con node --inspect
  y requests reales antes de asumir valores runtime, elegir fuentes de datos o
  agregar fallbacks. Usar al decidir entre campos de req, sesión, plataforma,
  configuración o respuestas de dependencias, y al depurar diferencias entre
  entornos. No aplica a CSS, documentos ni código que corre únicamente en browser.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "developer-experience"
  tags: "nodejs, debugging, inspector, bff, runtime"
  command: "/node-runtime-debugging"
---

# Debugging runtime de Node.js

## Contrato

Antes de cambiar comportamiento basado en datos runtime, observar el flujo real con `node --inspect`. Código, tipos, nombres de campos, memoria y mocks orientan el breakpoint; no prueban qué valor recibe la aplicación.

No implementar una elección de fuente, `??`, `||`, default o recuperación para compensar un valor supuesto. Primero verificar presencia, tipo, valor mínimo necesario y origen. Un request con un campo ausente tampoco demuestra que ese campo nunca exista.

Esta comprobación complementa tests y revisión. Respetar contratos y validaciones del proyecto; no agregar schemas ni cambiar permisos para conseguir una captura.

## Flujo

1. **Precisar decisión.** Identificar operación, valor del que depende el cambio, fuentes candidatas y escenario real que permite distinguirlas. Separar hechos, contrato documentado e hipótesis. Para campos de request, revisar también qué middleware los crea o reemplaza.
2. **Preparar proceso real.** Leer instrucciones, `package.json` y configuración. Reutilizar servidor y debugger existentes cuando pertenecen al proyecto y hay autorización. Si hay que iniciar uno, conservar entrypoint, transpiler, alias, env y configuración del proyecto; agregar `--inspect` al proceso que ejecuta la aplicación, no a todos los procesos de un wrapper.

   ```bash
   node --inspect=127.0.0.1:9229 <entrypoint-del-proyecto>
   ```

   Adaptar puerto si está ocupado. `--inspect-brk` sirve cuando hay que pausar antes del bootstrap; reanudar antes de probar HTTP. Registrar PID y recursos propios. Nunca matar un listener ajeno ni reemplazar arranque real por un arnés que fabrique `req`.
3. **Comprobar disponibilidad.** Confirmar debugger, listener HTTP y ruta real por separado. Usar host, routing y contexto auténtico del proyecto. En servidores HTTP y BFF, conservar sesión e identidad reales. Conservar autenticación, autorización y TLS. Resolver dependencias faltantes mediante instalación del proyecto dentro del alcance autorizado; no fabricar módulos, cambiar versiones ni tocar configuración global para ocultar errores.
4. **Adjuntar debugger.** Usar cliente Inspector compatible disponible: DevTools, IDE, CLI o Chrome DevTools Protocol. Un MCP que controla páginas no necesariamente controla el debugger de Node. Confirmar PID, script cargado y breakpoint resuelto. Con Babel/TypeScript, usar source maps o ubicación compilada verificada; no asumir que línea original coincide con script ejecutado.
5. **Ejecutar request real.** Desde UI o cliente autorizado con contexto real, disparar operación de lectura o escenario permitido. Pausar en caller/handler/adapter donde se consume el valor. Evaluar únicamente una proyección acotada de campos candidatos y resultado derivado. Si el middleware puede transformar una fuente, capturar antes y después. No evaluar getters o funciones con efectos laterales.
6. **Decidir con evidencia.** Comparar candidatos, identificar propietario y explicar cuál satisface el contrato del producto. Si ambos coinciden, eso no determina prioridad: comprobar origen o un escenario real donde diverjan. Para un fallback, demostrar cuándo falta fuente principal, por qué alternativa es válida y qué debe ocurrir cuando ambas faltan. No inventar identidad, autorización, país, elegibilidad ni éxito.
7. **Aplicar y repetir.** Cambiar únicamente boundary responsable. Repetir mismo flujo y breakpoint sobre código nuevo; verificar valor seleccionado y resultado observable. Actualizar y ejecutar tests de comportamiento pertinentes y lint del proyecto. Tests sintéticos pueden cubrir variantes, pero no reemplazan comprobación runtime que justificó decisión.

## Captura segura y cierre

- Inspector debe escuchar en loopback. No exponerlo en `0.0.0.0` ni abrir acceso externo.
- Nunca volcar `req`, sesión, headers, cookies, tokens, body, response completa ni PII. Proyectar campos concretos autorizados y sanitizar resultados. Evitar heap snapshots o dumps completos para decisiones sobre pocos valores.
- Breakpoints pueden bloquear requests y provocar timeouts: limitar pausa, reanudar incluso si evaluación falla y retirar breakpoints al terminar. No usar tráfico productivo para pausas sin autorización específica.
- Retirar instrumentación temporal. Desconectar debugger y detener únicamente procesos propios, salvo pedido de conservarlos. Preservar servidor, browser y sesión del usuario.

## Bloqueos y evidencia mínima

Si faltan runtime, cliente Inspector, dependencia, autenticación o fixture autorizado, declarar `BLOCKED` con intento realizado y causa concreta. Continuar trabajo independiente; no reemplazar observación por un mock y presentarlo como comprobación real. Pedir únicamente dato o acción indispensable. Si usuario autoriza continuar sin runtime, explicitar limitación y no declarar el fallback verificado.

Cerrar con operación y escenario, proceso/ruta observados, breakpoint efectivo, proyección sanitizada, origen de cada candidato, decisión sustentada, resultado después del cambio y limpieza. Distinguir `PASS`, `FAIL` y `BLOCKED`; incluir alcance y variantes no observadas.

## Fuentes técnicas

- [Debugging Node.js](https://nodejs.org/learn/getting-started/debugging): arranque, conexión de clientes y aislamiento del puerto Inspector.
- [Inspector API](https://nodejs.org/api/inspector.html): API y protocolo disponibles; verificar compatibilidad con versión instalada antes de elegir cliente.
