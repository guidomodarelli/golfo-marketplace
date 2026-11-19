---
name: device-visual-bug-repro
description: "Reproduce y arregla en la causa raíz bugs visuales que el usuario ve en su teléfono (sobre todo iOS Safari) a partir de una captura: mide la captura en píxeles antes de opinar, intenta reproducir con Playwright WebKit y escala de dispositivo, prueba en el dispositivo real por LAN cuando la emulación no alcanza, fija el fix con un test de navegador y responde preguntas sobre una pantalla verificando la semántica en el código. Usar siempre que el usuario mande una captura del teléfono con algo desalineado, descentrado, desbordado o de distinto tamaño, diga que en el celular se ve mal pero en la compu no, o pregunte qué hace una pantalla de su app a partir de una captura."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "web"
  tags: "ios-safari, mobile, visual-bug, screenshot, playwright, webkit, probe"
  command: "/device-visual-bug-repro"
  plugin-dependencies: "golfo-github, golfo-frontend"
---

# Reproducir bugs visuales del dispositivo real

## When to Use

- El usuario manda una captura del teléfono con algo desalineado, descentrado, desbordado o de tamaño distinto.
- El bug no aparece (o no seguro) en el navegador de escritorio / emulación.
- Hay que verificar visualmente páginas con sesión o pantallas de carga en local.

Para bugs que el usuario ve en su teléfono (sobre todo iOS Safari) a partir de una captura (desalineado, desborde,
descentrado) y que hay que arreglar en la causa raíz (p. ej. en la librería de componentes, no en el consumidor).

## Procedimiento

1. **Medí la captura antes de opinar.** Con PIL, escaneá columnas/filas de píxeles para obtener los bordes del
   elemento (track, thumb, input) y convertí a px CSS con la escala (`ancho medido / ancho CSS conocido`, ~3 en
   iPhone). Compará gaps opuestos (arriba/abajo, izq/der). Una asimetría de ~1px CSS es real; un 1px de dispositivo
   es antialias/JPEG. Si hay capturas del mismo elemento en estados distintos (activo/inactivo), comparalas: la
   diferencia entre estados suele señalar la causa (p. ej. solo el estado con `transform` falla).
2. **Intentá reproducir en emulación**: Playwright `webkit` + `devices["iPhone 13"]` o `deviceScaleFactor: 3`,
   midiendo `getBoundingClientRect()` y screenshots recortados; forzá offsets fraccionarios del contenedor
   (`marginTop: 0.125…0.875px`) porque las filas centradas junto a texto que envuelve caen en medio píxel.
   Si reproduce: test de navegador que falle antes del fix y pase después.
   Si WebKit no está disponible y el síntoma coincide con una [causa conocida](#causas-conocidas-ios-safari),
   aplicá ese fix y fijalo con un test en Chromium a viewport de teléfono (390 px) que mida el invariante
   (`getBoundingClientRect().right` del control ≤ el de su columna y ≤ `innerWidth`) más la propiedad del fix
   (`getComputedStyle(el).appearance === 'none'`): Chromium no reproduce el desborde nativo, así que sin la
   aserción de la propiedad el test pasaría también antes del fix. Decile al usuario que lo confirme en el teléfono.
3. **Si la emulación no reproduce, probá en el dispositivo real por LAN** con una página de variantes A/B/C
   (A = como hoy, B/C = candidatos de fix vía overrides CSS). Ver [references/lan-device-probes.md](references/lan-device-probes.md).
   - **Montá el probe dentro del shell real de la app** (layout, SSR, estilos del módulo de la pantalla), no solo
     en un harness aislado: un harness aislado puede verse bien en todas las variantes y no discrimina nada.
   - Preguntá qué variante se ve bien, ofreciendo también «todas se ven bien» y «otra cosa» (en Discord, opciones
     escritas en el mensaje; ver «Preguntar decisiones»). «Se ve perfecto» sin decir cuál no confirma
     nada: repreguntá.
4. **No shipees un fix que el probe no discriminó.** Si A también se ve bien, la hipótesis no está probada:
   descartá la rama y pedí más datos (captura recién cargada vs. después de interactuar, qué estados fallan).
5. **Con la variante confirmada**: fix en la fuente (librería) con comentario de una línea sobre el mecanismo,
   test que fije el invariante (centrado medido + la propiedad que causaba el bug), entrada en CHANGELOG
   `[Unreleased]`, validación completa del repo (unit + browser en todos los proyectos), PR + loop de Codex.
   Después: release de la librería y bump en el consumidor.
6. **Limpieza siempre**: borrá rutas/páginas de probe temporales, revertí cambios de config (p. ej.
   `allowedDevOrigins`), matá los servidores por PID del puerto y confirmá que el puerto no responde.

## Separar causas

Una captura puede mezclar problemas de dueños distintos (p. ej. inputs que desbordan = componente de la librería;
labels más grandes = el consumidor usa `<label>` suelto en vez de la prop `label` del componente). Nombrá cada uno
con su dueño y arreglalo en su repo. El mismo mensaje puede traer además una pregunta de UX sobre la pantalla
(«¿y si no quiero X?»): respondela con un cambio de flujo (ver `ui-ux-flow-patterns`, ajuste opcional en Settings),
no solo con «ya se puede», en el mismo PR si toca la misma pantalla.

## Causas conocidas (iOS Safari)

- `will-change: transform` permanente en un elemento desplazado con `transform` (thumb de un switch activo): Safari
  lo dibuja en capa propia y puede quedar ~1px CSS arriba o abajo del centro de su contenedor; el estado sin
  transform se ve bien. Fix: quitar `will-change` permanente (las librerías de animación promueven la capa solo
  mientras animan).
- `<input type="date|datetime-local|time">` conserva su ancho nativo e ignora `width: 100%`, desbordando la
  columna. Fix: `appearance: none` acotado a esos tipos (no a range/color).

## Preguntas sobre una pantalla de la app del usuario

Cuando la captura trae una pregunta («¿qué significa cada opción?») o un pedido de cambio de copy/comportamiento:

1. **Ubicá el repo por el texto visible antes de responder**: `rg -l "<frase exacta de la UI>" <carpeta de los repos del usuario, p. ej. ~/ghq/projects> --glob '!node_modules'`
   (aparecen también los worktrees; usá el checkout principal o `origin/main`). Las constantes de copy llevan al
   componente, y de ahí al use case / SQL que define el efecto real.
2. **Verificá la semántica en código y SQL antes de explicarla**: qué estado deja cada opción, qué permisos tiene
   ese estado (p. ej. qué policies exigen `status = 'active'`), si hay acción para revertirlo. Explicar por el nombre
   del estado falla: un estado puede tener efecto inmediato aunque el texto diga «de acá en adelante», o no tener
   vuelta atrás desde la UI. Si respondés sin verificar, decilo explícitamente, y si después encontrás que algo
   era distinto, corregilo de frente en el siguiente mensaje.
3. **Si pide «agregá esa descripción tal cual»**, escribí la versión verificada, no la explicación especulativa, y
   avisá qué cambió. Revisá si el componente compartido ya soporta el campo (p. ej. `description` en las opciones
   de `RadioGroup` de `@golfo/ui`) antes de crear markup propio.
4. **Un pedido de copy puede destapar un cambio de producto** (el usuario repiensa el flujo al leer la explicación).
   Pará antes de codear, explorá cómo está implementado hoy (qué bloquea qué, de dónde salen los estados) y
   llevá las decisiones abiertas al usuario con tu recomendación y los riesgos concretos que encontraste (p. ej.
   filas que comparten estado pero nunca fueron integrantes). Con el plan aprobado, si el cambio es grande (DB,
   migraciones, docs, manuales), trabajalo en un worktree propio y cerralo con PR (`pr-description-template` del plugin `golfo-github`), o delegalo en otra sesión de agente si el agente lo permite.

## Preguntar decisiones

En gateways de chat (Discord, Telegram) las opciones de las herramientas de pregunta (`clarify`) no siempre se leen:
ahí escribí cada pregunta numerada con opciones `a)`, `b)`, `c)` completas en el mensaje, la recomendada primero,
y pedí la respuesta compacta («1a, 2b, 3a»). En una sesión interactiva, usá la herramienta de preguntas del agente.
Si el usuario contesta una opción con otra pregunta («¿cuál es la diferencia?»), respondela con hechos del código
y tu recomendación antes de seguir.

## Previews pedidas por el usuario

Si pide «mostrame cómo quedaría» y la emulación ya reproduce el bug (medición antes = captura del usuario),
alcanza con un antes/después de Playwright WebKit (`devices["iPhone 13"]`) sobre la app local con sesión, recortado
a la zona, con el avatar difuminado, enviado como imagen. Reportar las medidas (superposición, gap, diferencia de
centro) junto a la imagen.

## Verificación local de páginas con sesión o skeletons

Ver [references/lan-device-probes.md](references/lan-device-probes.md), sección «Playwright local».
