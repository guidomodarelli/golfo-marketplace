---
version: alpha
name: Heritage Spec
description: >
  Sistema visual para documentos técnicos y especificaciones internas.
  Estética de "broadsheet contemporáneo": fondo cálido tipo piedra caliza,
  sans neutra para lectura, mono para metadatos y código.
  Inspirado en specs de producto, RFCs y diseño editorial sobrio.
colors:
  # Texto e ink
  primary:           "#1A1A1A"   # Tinta profunda — títulos, énfasis, body fuerte
  body:              "#333333"   # Texto corrido — párrafos, listas, celdas
  muted:             "#555555"   # Sutil — subtítulos, descripciones secundarias
  label:             "#6B6B6B"   # Metadatos, labels mono, números de sección (≥4.5:1 en todas las superficies)
  link:              "#1A4F7A"   # Links en prosa (mismo tono que info-text)
  focus-ring:        "#1A4F7A"   # Outline de :focus-visible (≥3:1 sobre cualquier superficie clara)
  # Superficies neutras
  background:        "#F8F7F4"   # Fondo principal — limestone cálido
  surface-alt:       "#F0EDE6"   # Beige cálido — headers de tabla, code inline, badges neutros
  surface-card:      "#FFFFFF"   # Mockups, example boxes, accordions
  # Bordes
  border:            "#E0DDD6"   # Borde estándar — separadores, tablas
  border-strong:     "#D0CDC6"   # Borde de cards/mockups/pills
  border-neutral:    "#CCCCCC"   # Borde del badge gris
  border-ink:        "#1A1A1A"   # Línea pesada del doc-header y part-header (2px)
  # Superficie oscura (code blocks, step circles)
  surface-dark:      "#1A1A2E"
  on-dark:           "#E2E8F0"
  # Callout — Info (azul broadsheet)
  info-bg:           "#EAF3FB"
  info-border:       "#5A9FD4"
  info-text:         "#1A4F7A"
  # Callout — Warn (amber)
  warn-bg:           "#FDF5E0"
  warn-border:       "#D4A44C"
  warn-text:         "#7A5510"
  # Callout — Ok (verde apagado)
  ok-bg:             "#E8F7F2"
  ok-border:         "#4AAA8C"
  ok-text:           "#1A6B52"
  # Callout — Red/Alert (coral terracota)
  red-bg:            "#FEF8F6"
  red-border:        "#E8917A"
  red-text:          "#9E3D25"
  # Acentos para syntax highlighting (sobre surface-dark)
  syntax-comment:    "#7C8BA1"   # ≥4.5:1 sobre surface-dark
  syntax-keyword:    "#7DD3FC"
  syntax-string:     "#86EFAC"
  syntax-number:     "#FBBF24"
  syntax-function:   "#C084FC"
  syntax-tag:        "#F9A8D4"

typography:
  doc-title:
    fontFamily: DM Sans
    fontSize: 28px
    fontWeight: 600
    lineHeight: 1.2
  doc-sub:
    fontFamily: DM Sans
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  doc-label:
    fontFamily: DM Mono
    fontSize: 11px
    fontWeight: 500
    letterSpacing: 0.14em
    # uso: text-transform: uppercase
  doc-meta:
    fontFamily: DM Mono
    fontSize: 11px
    fontWeight: 400
  part-title:
    fontFamily: DM Sans
    fontSize: 22px
    fontWeight: 600
    lineHeight: 1.2
  section-num:
    fontFamily: DM Mono
    fontSize: 11px
    fontWeight: 500
    letterSpacing: 0.12em
    # uso: text-transform: uppercase, color label
  section-title:
    fontFamily: DM Sans
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.3
  body-md:
    fontFamily: DM Sans
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.7
  body-callout:
    fontFamily: DM Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.6
  table-header:
    fontFamily: DM Mono
    fontSize: 11px
    fontWeight: 500
    letterSpacing: 0.1em
    # uso: text-transform: uppercase
  table-cell:
    fontFamily: DM Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  badge:
    fontFamily: DM Mono
    fontSize: 11px
    fontWeight: 500
    letterSpacing: 0.05em
  code-inline:
    fontFamily: DM Mono
    fontSize: 12px
    fontWeight: 400
  code-block:
    fontFamily: DM Mono
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.7
  step-num:
    fontFamily: DM Mono
    fontSize: 12px
    fontWeight: 500
  step-label:
    fontFamily: DM Sans
    fontSize: 14px
    fontWeight: 600
  step-desc:
    fontFamily: DM Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.6
  accordion-title:
    fontFamily: DM Sans
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.4
  toc-item:
    fontFamily: DM Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  back-to-top:
    fontFamily: DM Mono
    fontSize: 12px
    fontWeight: 500
  rail-preview-title:
    fontFamily: DM Sans
    fontSize: 13px
    fontWeight: 600
    lineHeight: 1.4

rounded:
  xs:   3px     # code inline
  sm:   4px     # badges
  md:   6px     # pills, chips de estado
  lg:   8px     # callouts, code blocks, accordions
  xl:   10px    # mockups, example boxes, cards grandes
  full: 9999px  # circular (step-circle, mockup dots)

spacing:
  # Todo padding, margin y gap sale de esta escala o de las medidas con nombre de
  # `layout`. Excepciones: 1–2px de chips inline (badges, code inline) y geometría que
  # no es espaciado (tamaños, posición de la línea conectora de steps).
  # check-layout-tokens.mjs lo verifica en el CSS y los scripts de assets/.
  xs:   4px
  sm:   6px
  md:   8px
  lg:   10px
  xl:   12px
  2xl:  16px
  3xl:  20px
  4xl:  24px
  5xl:  28px
  6xl:  32px
  7xl:  40px
  8xl:  48px
  9xl:  56px
  10xl: 80px

layout:
  # Medidas que no son de la escala spacing: reservas de layout y alineaciones de alto.
  # check-layout-tokens.mjs acepta en padding, margin y gap solo spacing, estas medidas,
  # 0 y hasta 2px (chips inline).
  stage-menu-reserve:          280px  # menú de etapas 224px + 32px de separación + 24px de borde
  rail-reserve:                96px   # mapa de secciones 48px + 24px a cada lado
  lang-switch-inset:           3px    # aro interno de la píldora segmentada de idioma
  lang-switch-button-y-compact: 5px   # alto del selector de idioma por debajo de mobile
  menu-back-y:                 10.5px # iguala el alto de «Ir al menú» al del selector de idioma
  menu-back-y-compact:         9.5px  # ídem por debajo de mobile

breakpoints:
  # Toda media query de ancho usa estos valores: min-width: <token> o max-width: <token> - 1px.
  mobile:     720px   # por debajo: padding lateral 16px, tablas con scroll horizontal
  stage-menu: 820px   # lectura por etapas: menú derecho desde acá, barra compacta por debajo
  rail:       1024px  # por debajo no hay margen lateral para el mapa de secciones: se oculta
  wide:       1200px  # desde acá «Ir al menú» no cae sobre la columna de texto

motion:
  # Movimiento funcional: solo responde a una acción del lector. Con
  # prefers-reduced-motion: reduce no hay transiciones y el scroll es instantáneo.
  # Variables CSS: --motion-<token> (check-design-tokens.sh las verifica).
  duration-fast:   120ms                          # hover, foco, subrayado de links
  duration-base:   200ms                          # abrir un accordion, aparecer el botón "Inicio"
  easing-standard: "cubic-bezier(0.2, 0, 0, 1)"   # entra rápido y se asienta, sin rebote

components:
  # —— Layout raíz
  page:
    backgroundColor: "{colors.background}"
    textColor:       "{colors.primary}"
    typography:      "{typography.body-md}"
    padding:         "48px 24px 80px"
    # max-width: 860px, centrado horizontalmente; <720px: padding lateral 16px

  # —— Doc header
  doc-header:
    backgroundColor: "{colors.background}"
    padding:         "0 0 20px 0"
    # border-bottom: 2px solid {colors.border-ink}, margin-bottom: 40px
  doc-header-label:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-label}"
  doc-header-title:
    textColor:       "{colors.primary}"
    typography:      "{typography.doc-title}"
    # elemento: <h1> (único por documento)
  doc-header-sub:
    textColor:       "{colors.muted}"
    typography:      "{typography.doc-sub}"
  doc-header-meta:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-meta}"
    # display: flex, flex-wrap: wrap, gap: 24px, margin-top: 16px
  doc-footer:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-meta}"
    # border-top: 1px {colors.border}, margin-top: 40px, padding-top: 16px; datos técnicos del documento

  # —— Part header (separa partes mayores A / B)
  part-header:
    padding:         "32px 0 0 0"
    # border-top: 2px solid {colors.border-ink}, margin-top: 56px, margin-bottom: 40px
  part-header-label:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-label}"
  part-header-title:
    textColor:       "{colors.primary}"
    typography:      "{typography.part-title}"
    # elemento: <h2>

  # —— Section block (bloque numerado)
  section:
    padding:         "0"
    # margin-bottom: 40px; elemento: <section>
  section-num:
    textColor:       "{colors.label}"
    typography:      "{typography.section-num}"
  section-title:
    textColor:       "{colors.primary}"
    typography:      "{typography.section-title}"
    # elemento: <h2>; padding-bottom: 8px, border-bottom: 1px solid {colors.border}

  # —— Índice (TOC) para documentos con 5+ secciones
  toc:
    padding:         "0"
    # elemento: <nav aria-labelledby>, margin-bottom: 40px, lista a 2 columnas (1 en mobile)
  toc-label:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-label}"
  toc-item:
    textColor:       "{colors.primary}"
    typography:      "{typography.toc-item}"
    padding:         "4px 0"
    # link sin subrayado en reposo (navegación, no prosa); hover y foco lo muestran
  toc-num:
    textColor:       "{colors.label}"
    typography:      "{typography.section-num}"
    # mismo número que el section-num de destino

  # —— Links
  link:
    textColor:       "{colors.link}"
    # text-decoration: underline 1px, text-underline-offset: 2px; hover: grosor 2px

  # —— Callouts (4 variantes semánticas)
  callout-info:
    backgroundColor: "{colors.info-bg}"
    textColor:       "{colors.info-text}"
    typography:      "{typography.body-callout}"
    rounded:         "{rounded.lg}"
    padding:         "12px 16px"
    # border-left: 3px solid {colors.info-border}
  callout-warn:
    backgroundColor: "{colors.warn-bg}"
    textColor:       "{colors.warn-text}"
    typography:      "{typography.body-callout}"
    rounded:         "{rounded.lg}"
    padding:         "12px 16px"
    # border-left: 3px solid {colors.warn-border}
  callout-ok:
    backgroundColor: "{colors.ok-bg}"
    textColor:       "{colors.ok-text}"
    typography:      "{typography.body-callout}"
    rounded:         "{rounded.lg}"
    padding:         "12px 16px"
    # border-left: 3px solid {colors.ok-border}
  callout-red:
    backgroundColor: "{colors.red-bg}"
    textColor:       "{colors.red-text}"
    typography:      "{typography.body-callout}"
    rounded:         "{rounded.lg}"
    padding:         "12px 16px"
    # border-left: 3px solid {colors.red-border}

  # —— Table
  table-header:
    backgroundColor: "{colors.surface-alt}"
    textColor:       "{colors.label}"
    typography:      "{typography.table-header}"
    padding:         "8px 12px"
    # text-transform: uppercase, border-bottom: 1px solid {colors.border}
  table-cell:
    textColor:       "{colors.body}"
    typography:      "{typography.table-cell}"
    padding:         "10px 12px"
    # border-bottom: 1px solid {colors.border}, vertical-align: top
  table-wrap:
    padding:         "0"
    # overflow-x: auto — contenedor obligatorio para que la tabla no rompa el layout en mobile

  # —— Badges (pills compactas mono)
  badge-green:
    backgroundColor: "{colors.ok-bg}"
    textColor:       "{colors.ok-text}"
    typography:      "{typography.badge}"
    rounded:         "{rounded.sm}"
    padding:         "2px 8px"
    # border: 1px solid {colors.ok-border}
  badge-amber:
    backgroundColor: "{colors.warn-bg}"
    textColor:       "{colors.warn-text}"
    typography:      "{typography.badge}"
    rounded:         "{rounded.sm}"
    padding:         "2px 8px"
    # border: 1px solid {colors.warn-border}
  badge-red:
    backgroundColor: "{colors.red-bg}"
    textColor:       "{colors.red-text}"
    typography:      "{typography.badge}"
    rounded:         "{rounded.sm}"
    padding:         "2px 8px"
    # border: 1px solid {colors.red-border}
  badge-gray:
    backgroundColor: "{colors.surface-alt}"
    textColor:       "{colors.muted}"
    typography:      "{typography.badge}"
    rounded:         "{rounded.sm}"
    padding:         "2px 8px"
    # border: 1px solid {colors.border-neutral}

  # —— Steps (proceso numerado con línea conectora)
  step-circle:
    backgroundColor: "{colors.surface-dark}"
    textColor:       "{colors.surface-card}"
    typography:      "{typography.step-num}"
    rounded:         "{rounded.full}"
    width:           "32px"
    height:          "32px"
  step-label:
    textColor:       "{colors.primary}"
    typography:      "{typography.step-label}"
  step-desc:
    textColor:       "{colors.muted}"
    typography:      "{typography.step-desc}"
  # Línea conectora: 1px sólido {colors.border}, vertical, entre step-circles

  # —— Code (inline + block)
  code-inline:
    backgroundColor: "{colors.surface-alt}"
    textColor:       "{colors.primary}"
    typography:      "{typography.code-inline}"
    rounded:         "{rounded.xs}"
    padding:         "1px 6px"
  code-block:
    backgroundColor: "{colors.surface-dark}"
    textColor:       "{colors.on-dark}"
    typography:      "{typography.code-block}"
    rounded:         "{rounded.lg}"
    padding:         "20px 24px"

  # —— Mockup (ventana navegador estilizada)
  mockup:
    backgroundColor: "{colors.surface-card}"
    rounded:         "{rounded.xl}"
    # border: 1.5px solid {colors.border-strong}, overflow: hidden
  mockup-bar:
    backgroundColor: "{colors.surface-alt}"
    textColor:       "{colors.label}"
    typography:      "{typography.doc-meta}"
    padding:         "10px 16px"
    # border-bottom: 1px solid {colors.border-strong}
    # dots 10×10px {rounded.full}: {colors.red-border}, {colors.warn-border}, {colors.ok-border}
  mockup-body:
    backgroundColor: "{colors.surface-card}"
    padding:         "20px"
  mockup-mobile:
    # modificador .mockup--mobile: max-width 410px (captura de 375px + 16px de aire por lado + bordes), centrado
  figcap:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-meta}"
    # leyenda bajo el mockup, centrada; margin -8px 0 16px; da el aria-label de la captura

  # —— Example box (cita destacada con label mono)
  example-box:
    backgroundColor: "{colors.surface-card}"
    rounded:         "{rounded.xl}"
    padding:         "16px 20px"
    # border: 1.5px solid {colors.border-strong}
  example-box-label:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-label}"

  # —— Pills (chips de estado para flujos)
  pill-neutral:
    backgroundColor: "{colors.surface-alt}"
    textColor:       "{colors.primary}"
    typography:      "{typography.code-inline}"
    rounded:         "{rounded.md}"
    padding:         "6px 12px"
    # border: 1px solid {colors.border-strong}
  pill-success:
    backgroundColor: "{colors.ok-bg}"
    textColor:       "{colors.ok-text}"
    typography:      "{typography.code-inline}"
    rounded:         "{rounded.md}"
    padding:         "6px 12px"
    # border: 1px solid {colors.ok-border}
  pill-stale:
    backgroundColor: "{colors.surface-alt}"
    textColor:       "{colors.red-text}"
    typography:      "{typography.code-inline}"
    rounded:         "{rounded.md}"
    padding:         "6px 12px"
    # border: 1px solid {colors.border-strong}, text-decoration: line-through

  # —— Divider
  divider:
    backgroundColor: "{colors.border}"
    height:          "1px"
    # margin: 28px 0

  # —— Accordion (bloque colapsable de detalle)
  accordion:
    backgroundColor: "{colors.surface-card}"
    rounded:         "{rounded.lg}"
    # border: 1px solid {colors.border}, margin-bottom: 10px, overflow: hidden
  accordion-summary:
    textColor:       "{colors.primary}"
    typography:      "{typography.accordion-title}"  # un escalón debajo de section-title para no competir con él
    padding:         "12px 16px"
    # cursor: pointer; marcador nativo oculto; glifo +/– (DM Mono, color label) a la derecha
    # [open] agrega border-bottom: 1px solid {colors.border}
  accordion-num:
    textColor:       "{colors.label}"
    typography:      "{typography.section-num}"
    # label mono uppercase opcional dentro del summary (ej. "Reglas", "Checklist")
  accordion-body:
    textColor:       "{colors.body}"
    padding:         "12px 16px 4px"
    # al abrir: fade + translateY(-4px → 0) en {motion.duration-base}

  # —— Botón "Inicio" (volver al inicio, flotante)
  back-to-top:
    backgroundColor: "{colors.surface-dark}"
    textColor:       "{colors.surface-card}"
    typography:      "{typography.back-to-top}"
    rounded:         "{rounded.full}"
    padding:         "8px 16px"
    # position: fixed, right/bottom 24px (16px en mobile); aparece después de 480px de scroll
    # sombra mínima documentada; aparece con fade en {motion.duration-base}; oculto en impresión

  # —— Mapa de secciones (marcas laterales con vista previa)
  section-rail:
    padding:         "0"
    # position: fixed, left 24px, centrado vertical; <1024px e impresión: oculto
  section-rail-tick:
    backgroundColor: "{colors.label}"
    rounded:         "{rounded.full}"
    width:           "12px"
    height:          "2px"
    # área clickeable 48×10px; sección actual (aria-current): 24px y {colors.primary}
    # lupa: bajo el puntero o el foco llega a 40px y las vecinas crecen menos cuanto más lejos (radio 48px)
  section-rail-preview:
    backgroundColor: "{colors.surface-card}"
    rounded:         "{rounded.lg}"
    padding:         "12px 16px"
    # border: 1px solid {colors.border-strong}, width 280px, sombra mínima documentada
  section-rail-preview-num:
    textColor:       "{colors.label}"
    typography:      "{typography.section-num}"
  section-rail-preview-title:
    textColor:       "{colors.primary}"
    typography:      "{typography.rail-preview-title}"
    # una línea, ellipsis
  section-rail-preview-summary:
    textColor:       "{colors.muted}"
    typography:      "{typography.body-callout}"
    # primer párrafo de la sección, máximo 3 líneas
  section-rail-preview-hint:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-meta}"
    # atajos de teclado al pie de la vista previa

  # —— Píldora de sección + índice en hoja inferior (todos los anchos)
  section-pill:
    backgroundColor: "{colors.surface-card}"
    textColor:       "{colors.primary}"
    typography:      "{typography.toc-item}"
    rounded:         "{rounded.full}"
    padding:         "8px 16px"
    # border: 1px solid {colors.border-strong}; fija abajo a la izquierda, 24px (16px en mobile); max-width 360px
  toc-sheet:
    backgroundColor: "{colors.surface-card}"
    padding:         "20px 24px 24px"
    # <dialog> modal pegado abajo, radio 10px arriba, max-height 70vh; fondo surface-dark al 32%

  # —— Copiar enlace a una sección
  section-link:
    textColor:       "{colors.link}"
    typography:      "{typography.doc-meta}"
    # dentro del section-num; visible al pasar por la sección, al enfocarlo y en pantallas táctiles

  # —— Glosario
  term:
    # hereda el color del texto; subrayado punteado 1px {colors.label}, offset 3px
  term-card:
    backgroundColor: "{colors.surface-card}"
    rounded:         "{rounded.lg}"
    padding:         "12px 16px"
    # igual que section-rail-preview: título rail-preview-title, texto body-callout muted

  # —— Puntos sobre capturas
  hotspot:
    backgroundColor: "{colors.surface-dark}"
    textColor:       "{colors.surface-card}"
    typography:      "{typography.step-num}"
    rounded:         "{rounded.full}"
    width:           "24px"
    height:          "24px"
    # border: 2px solid {colors.surface-card} para separarse de cualquier captura
  hotspot-ref:
    backgroundColor: "{colors.surface-dark}"
    textColor:       "{colors.surface-card}"
    typography:      "{typography.badge}"
    rounded:         "{rounded.full}"
    width:           "20px"
    height:          "20px"

  # —— Comparación antes / después
  compare:
    backgroundColor: "{colors.surface-card}"
    rounded:         "{rounded.xl}"
    # border 1.5px {colors.border-strong}; divisor 2px {colors.surface-dark} con perilla circular 32px
  compare-labels:
    textColor:       "{colors.label}"
    typography:      "{typography.doc-label}"
---

## Overview

Minimalismo arquitectónico + gravitas periodística. La interfaz emula un
broadsheet premium o una galería contemporánea: fondo de piedra caliza
cálida, tinta profunda para titulares, y un único acento por familia de
callout en lugar de paletas saturadas.

El sistema fue diseñado para **documentos densos en información**: specs
técnicas, reglas de negocio, RFCs, runbooks. Prioriza legibilidad
prolongada por sobre impacto visual, y conviene leerse impreso o en
pantalla sin perder jerarquía.

**Características clave:**

- Dos familias tipográficas únicas — **DM Sans** para lectura, **DM Mono** para metadatos.
- Fondo `#F8F7F4` (no blanco puro) para reducir fatiga visual.
- Numeración explícita de secciones (`01`, `02`, …) en mono uppercase como guía estructural.
- Cuatro tonos de callout (info, warn, ok, red) que cubren todo el espectro de aviso.
- Ningún componente usa sombras pesadas: la jerarquía se logra con tipografía y bordes finos.
- Todo par texto/fondo cumple **WCAG AA** (≥4.5:1); ver [Accesibilidad](#accesibilidad).

**Fuera de alcance:** modo oscuro. La estética es de papel impreso; el
documento declara `color-scheme: light` y no redefine la paleta.

## Colors

La paleta se construye sobre **neutros cálidos de alto contraste** y cuatro
familias de acento semánticas. Nada de grises azulados ni blancos puros.
Cualquier color que no esté en el front matter está fuera del sistema.

El front matter es la **fuente de verdad**. El `:root` de `assets/boilerplate/base.css` declara
una variable CSS por token, con el mismo nombre (`label` → `--label`) y el
mismo valor. Después de tocar un color en cualquiera de los dos lados, correr:

```bash
bash scripts/check-design-tokens.sh   # desde la carpeta de la skill user-manual
```

Falla (exit `1`) si falta una variable, sobra una o un valor no coincide.

### Tinta y texto

- **primary (`#1A1A1A`)** — Tinta profunda para titulares, énfasis, body en negrita.
- **body (`#333333`)** — Texto corrido en párrafos, listas, celdas de tabla. Es lo que el lector lee por más tiempo; por eso no es negro absoluto.
- **muted (`#555555`)** — Subtítulos, descripciones secundarias de un step. Lo suficientemente legible pero claramente subordinado.
- **label (`#6B6B6B`)** — Metadatos, números de sección, headers de tabla en mono uppercase. Texto que "guía" sin reclamar atención. Es el gris más claro permitido para texto: el anterior `#888888` no llegaba a 4.5:1 en ninguna superficie.
- **link (`#1A4F7A`)** — Links dentro de prosa, siempre subrayados. Comparte tono con `info-text` para no sumar un acento nuevo.

### Superficies

- **background (`#F8F7F4`)** — Limestone cálido. Reemplaza el blanco puro para suavizar la lectura.
- **surface-alt (`#F0EDE6`)** — Beige cálido para headers de tabla, code inline, badges neutros. Diferencia sutil del fondo.
- **surface-card (`#FFFFFF`)** — Único uso del blanco puro: dentro de mockups, example boxes y accordions que necesitan destacarse como "pieza encajada" sobre el fondo.
- **surface-dark (`#1A1A2E`)** — Tinta nocturna para code blocks y step circles. Único elemento muy oscuro de la página: por eso ancla la mirada cuando aparece.

### Acentos semánticos

Cada acento viene en tríada `bg / border / text` y se usa siempre en los mismos roles:

- **Info (azul broadsheet)** — Contexto, aclaraciones, lógica de fondo. Es el callout por defecto cuando hay duda.
- **Warn (amber)** — Advertencias suaves, condicionales, "ojo con esto". No alarmante.
- **Ok (verde apagado)** — Confirmaciones, éxito, "lo que sí queremos".
- **Red (coral terracota, no rojo brillante)** — Alertas críticas, consecuencias, pendientes urgentes. El tono está apagado a propósito para no romper la paleta editorial; transmite seriedad sin gritar.

El uso es consistente: **bg suave** rellena el callout, **border** se aplica como `border-left: 3px solid`, **text** colorea el texto del callout y de los badges asociados. Los `*-border` son decorativos: **nunca usarlos como color de texto** (no alcanzan 3:1).

## Typography

Dos familias, ambas de Google Fonts. Cargarlas con `<link>` + `preconnect`
(más rápido que `@import`, que bloquea el parseo del CSS):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap">
```

Si el documento se abre sin conexión, las fuentes caen a un stack de sistema
de métricas parecidas, no al `sans-serif` genérico:

- Sans: `'DM Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif`
- Mono: `'DM Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace`

### DM Sans — lectura

Geométrica humanista, levemente grotesca. Funciona en titulares y en body
sin cambiar de carácter. Pesos disponibles: 400 (regular), 500 (medium),
600 (semibold). **Nunca usar 700 o más** — rompe la sobriedad editorial.
Ojo: `<h1>`, `<h2>`, `<th>` y `<strong>` son `bold` (700) por defecto en el
navegador; el boilerplate los fija en 600.

| Token | Tamaño | Peso | Uso |
| --- | --- | --- | --- |
| `doc-title` | 28px | 600 | Título de documento (1× por página, `<h1>`) |
| `part-title` | 22px | 600 | División entre partes mayores (Parte A / Parte B) |
| `section-title` | 20px | 600 | Encabezado de sección numerada (`<h2>`) |
| `body-md` | 14px | 400 | Párrafos y listas |
| `body-callout` | 13px | 400 | Texto dentro de callouts (más compacto) |
| `table-cell` | 13px | 400 | Celdas de tabla |
| `step-label` | 14px | 600 | Etiqueta de cada paso |
| `step-desc` | 13px | 400 | Descripción bajo la etiqueta del paso |
| `accordion-title` | 16px | 600 | Título del `summary` de un accordion |
| `toc-item` | 13px | 400 | Entradas del índice |
| `rail-preview-title` | 13px | 600 | Título en la vista previa del mapa de secciones |

Line-height: **1.7** para body, **1.6** para callouts, **1.5** para celdas.
Esto da espacio para leer páginas largas sin agotar la vista.

### DM Mono — estructura

Monoespaciada, geométrica. Es la "voz del sistema": números, IDs, labels,
estados. Siempre indica algo que el lector debería tratar como literal o como
metadato — no como prosa.

| Token | Tamaño | Peso | Tracking | Caja |
| --- | --- | --- | --- | --- |
| `doc-label` | 11px | 500 | 0.14em | UPPERCASE |
| `section-num` | 11px | 500 | 0.12em | UPPERCASE |
| `doc-meta` | 11px | 400 | — | mixed |
| `table-header` | 11px | 500 | 0.10em | UPPERCASE |
| `badge` | 11px | 500 | 0.05em | mixed |

**11px es el piso** del sistema: ningún texto va más chico, ni siquiera en mono.
| `code-inline` | 12px | 400 | — | mixed |
| `code-block` | 12px | 400 | — | mixed |
| `step-num` | 12px | 500 | — | mixed |

**Regla mnemotécnica:** si el contenido es legible como oración, va en **DM Sans**.
Si es un identificador, número, label, código o estado, va en **DM Mono**.

## Layout

### Página

- Ancho máximo: **`860px`**, centrado horizontalmente.
- Padding del body: **`48px`** arriba, **`24px`** a los lados, **`80px`** abajo.
- Fondo `{colors.background}` sólido (no gradientes).
- En mobile (`<720px`) el padding lateral baja a `16px` y las tablas scrollean horizontalmente dentro de `.table-wrap`; la tipografía se mantiene en los mismos tamaños. Nunca debe haber scroll horizontal de la página.
- Toda media query de ancho usa un token `breakpoints` (`min-width: <token>` o `max-width: <token> - 1px`), y toda medida de layout que no está en `spacing` tiene nombre en `layout`. `node scripts/check-layout-tokens.mjs` lo verifica.

### Lectura por etapas

Para manuales extensos cuya lectura lineal abruma, agrupar secciones por objetivo de
aprendizaje en **etapas**. No imponer etapas a documentos breves ni fijar una cantidad
universal. El boilerplate (`assets/boilerplate/`) sigue siendo lineal: esta variante se activa con
los assets de la skill, no agregando clases o escondiendo secciones con CSS a mano.

**Implementación.** Partir de `assets/staged-reading/template.html` (contrato de marcado en su
comentario inicial) y, con el manual armado sobre el boilerplate, incrustar el CSS y el script con
`node scripts/build-manual.mjs <manual.html>` (`--viewer document` suma el
[adaptador de visor](#copiar-enlace-a-una-sección); `--example <out.html>` genera el ejemplo).
Volver a correrlo actualiza los bloques incrustados. El marcado:

- `<meta name="heritage:reading-mode" content="stages">` en el `<head>`.
- Por etapa, en orden: `div.stage-intro` con `id="stage-<id>"` y `data-stage-intro="<id>"`
  (`.stage-label`, `h2.stage-title`, `p.stage-objective` y `p.stage-reading` vacío, que completa el
  script); sus secciones contiguas con `data-stage="<id>"`; y `aside.stage-recap` con
  `data-stage-recap="<id>"`, `ul.stage-concepts` de tres `li` y `p.stage-next`.
- **Capítulos** (opcionales, por etapa): cuando una etapa reúne varios temas, `div.stage-chapter` con
  `id="chapter-<id>"`, `data-chapter="<id>"` y `data-stage="<etapa>"` (`.stage-chapter-label`,
  `h2.stage-chapter-title` y `p.stage-chapter-reading` vacío). Si una etapa los usa, toda sección va
  después de un capítulo y cada capítulo tiene al menos dos secciones; con menos, sobra el capítulo.
  La etapa se sigue mostrando entera: los capítulos ordenan, no ocultan. La recapitulación sigue
  siendo por etapa; el capítulo lleva solo título y lectura estimada.
- El script valida ese marcado antes de ocultar nada, con las reglas de
  `assets/staged-reading/stage-contract.js`, las mismas que aplica `check-manual.mjs` (una sola
  definición: activar y validar no pueden divergir). Si algo falla deja el manual lineal y avisa con
  `console.warn`. Sin índice superior, `Alt`+`I` abre la hoja del índice. Oculta con `hidden` (nunca recrea ni mueve nodos) y avisa con
  `heritage:visibility-change`; el script de navegación reusa su scroll y su URL
  (`window.HeritageNavigation`) y revela destinos con `heritage:before-scroll`, así que no hay una
  segunda navegación. Expone `window.HeritageStages` (estado, secciones y capítulos de cada etapa y
  progreso) para `check-rendered.js` y las pruebas.
- Lo que agrega el script, sin escribirlo a mano:
  - En el menú, debajo de la etapa activa, sus capítulos y secciones como enlaces: se va directo a
    una sección sin abrir la hoja del índice.
  - Progreso de la visita: la etapa cuya recapitulación se leyó dice «leída» en el menú (texto, no
    solo color). No se guarda nada entre visitas.
  - En cada recapitulación, «Etapa N de M · X min» y botones a la etapa anterior y a la siguiente
    (no en la primera ni en la última, respectivamente).
  - En la hoja del índice, etiquetas de etapa y de capítulo antes de su primera sección; en el
    mapa, un respiro entre grupos.
  - La lectura estimada de cada capítulo, con la misma tasa que la etapa.
  - El nivel que anuncian los lectores de pantalla: etapa (`h2`) > capítulo (nivel 3) > sección
    (nivel 3, o 4 con capítulos) vía `aria-level`. Los títulos de sección siguen siendo `h2`.
- Sus textos de interfaz (es/pt) viven en el mismo diccionario que los del script de navegación
  (`UI_TEXT` de `assets/boilerplate/navigation.js`, leído con `HeritageNavigation.text`): un idioma
  nuevo se agrega en un solo lugar.

- Mantener las secciones originales, sus IDs y su orden. Una etapa visible por vez y
  opción **«Ver todo»**; cambiar de etapa no recrea nodos ni reinicia simuladores.
- Usar un único modelo de etapas y secciones para menú, mapa, hoja de índice y enlaces.
  El índice completo incluye también las secciones de etapas ocultas. El mapa representa
  las visibles; cualquier salto a una oculta activa su etapa **antes** de medir o scrollear.
- En escritorio (`≥820px`), menú de etapas fijo a la **derecha** y mapa de marcas a la
  **izquierda**. Para esta variante, ampliar el layout hasta `1180px`, reservar `224px`
  para el menú y `32px` de separación; reservar también espacio para el mapa. El mapa
  conserva su breakpoint `rail`: ocultarlo cuando no haya margen, no forzar su aparición
  desde el breakpoint del menú. Nunca superponer navegación y contenido.
- Por debajo de `820px`, reemplazar el menú fijo por una barra sticky compacta con
  «etapa actual / total · título» y botón **«Etapas»**. El listado no se despliega en el
  flujo superior: abre un sidebar modal desde la **derecha**, de hasta `340px` de ancho
  y como máximo `calc(100vw - 32px)`, con scroll propio y fondo atenuado.
- Implementar el sidebar con `<dialog>` y `showModal()`: nombre accesible, botón «Cerrar»,
  cierre por `Escape`, toque fuera y elección de etapa; foco confinado y fondo inerte.
  Devolver el foco al disparador al cancelar; al navegar, dirigirlo al destino visible.
  Reubicar los mismos controles entre menú y dialog, sin duplicar IDs, listeners ni estado.
  Al cruzar el breakpoint, cerrar el modal y liberar el bloqueo de scroll.
- Usar los tokens de Motion para la entrada lateral; sin animación con reduced motion.
  En impresión mostrar todas las etapas y ocultar barras, menú y dialogs.
- Con etapas y hoja inferior, omitir el índice superior redundante. La hoja sigue siendo
  el índice completo; no confundirla con el selector de etapas. Ver [Píldora de sección](#píldora-de-sección).
- Abrir cada etapa con título, objetivo breve y **lectura estimada**. Calcularla desde
  sus palabras con una tasa explícita de referencia (`200 palabras/minuto`), redondeada
  hacia arriba y con mínimo de un minuto. Aclarar que no incluye ejercicios ni simuladores;
  no presentarla como duración medida de la tarea. Cerrar con tres conceptos clave y
  **«Qué sigue»**; la última etapa propone síntesis o consulta, no una etapa inexistente.
- Al elegir etapa, mostrar su orientación inicial y actualizar el enlace a su primera
  sección. Un enlace directo a una sección, en cambio, lleva a esa sección y no al
  encabezado de etapa. Aplicar el contrato de [Copiar enlace](#copiar-enlace-a-una-sección)
  también a carga inicial, recarga, historial y navegación desde cualquier índice.

### Densidad

- Separación entre secciones: **`40px`**.
- Separación interna de una sección (entre párrafos, listas, tablas, callouts): **`12–16px`**.
- Padding de callouts y example boxes: **`12–20px`**, nunca más.
- **Todo padding, margin y gap sale de la escala `spacing`** (4, 6, 8, 10, 12, 16, 20, 24, 28, 32, 40, 48, 56, 80). Solo quedan fuera los 1–2px de chips inline y la geometría que no es espaciado (tamaños de círculos y dots, posición de la línea conectora).

### Jerarquía estructural

Un documento típico se estructura así, de arriba a abajo:

```
doc-header           ← encabezado completo del documento (<header>, título en <h1>)
[toc]                ← (opcional, 5+ secciones) índice con links a cada sección
[section-rail]       ← (opcional, va con el índice) mapa lateral fijo, lo arma el script
[section-pill]       ← (opcional, va con el mapa) sección actual + índice en hoja
section 01           ← cada sección numerada (<section>, título en <h2>)
section 02
section 03
[part-header]        ← (opcional) separador de partes mayores (título en <h2>)
section 04
section 05
…
```

### Gramática de líneas

Hay dos familias de líneas y no se mezclan:

- **Divisores** (separan bloques del flujo): `2px` sólido tinta en `doc-header` (abajo) y `part-header` (arriba); `1px` `{colors.border}` bajo cada `section-title`, entre filas de tabla y en `.divider`. **Son los únicos divisores del sistema** — no agregar otros.
- **Contornos** (delimitan una pieza encajada): `1px` en accordions y badges, `1.5px` `{colors.border-strong}` en mockups y example boxes, `3px` a la izquierda en callouts para indicar el tono.

## Elevation & Depth

El sistema **no usa sombras**. La profundidad se logra exclusivamente con:

1. **Bordes finos** (`1px` / `1.5px`) en tono cálido `{colors.border}` o `{colors.border-strong}`.
2. **Cambios de superficie** entre `background`, `surface-alt`, `surface-card` y `surface-dark`.
3. **Bordes-izquierdos gruesos** (`3px`) en callouts, que indican el tono del bloque.

Esto mantiene la sensación de papel impreso y evita el aire "interfaz de
software". Si en algún caso muy puntual se necesita sombra, usar
`0 1px 2px rgba(0,0,0,0.04)` — apenas perceptible.

## Shapes

| Token | Valor | Uso |
| --- | --- | --- |
| `rounded.xs` | 3px | Code inline |
| `rounded.sm` | 4px | Badges |
| `rounded.md` | 6px | Pills, chips de estado |
| `rounded.lg` | 8px | Callouts, code blocks, accordions |
| `rounded.xl` | 10px | Mockups, example boxes, cards grandes |
| `rounded.full` | 9999px | Step circles, dots del mockup bar |

**Sin redondeos por encima de `10px`** salvo lo circular puro. Esto preserva
el carácter editorial — nada de bubbles tipo dashboard SaaS.

## Motion

El movimiento sigue la misma regla que la profundidad: **funcional y casi
imperceptible**. Un documento Heritage es papel; lo que se mueve solo confirma
que el lector hizo algo, nunca decora.

| Token | Valor | Uso |
| --- | --- | --- |
| `motion.duration-fast` | 120ms | Hover y foco: color, borde, grosor del subrayado |
| `motion.duration-base` | 200ms | Abrir un accordion, aparecer el botón "Inicio" |
| `motion.easing-standard` | `cubic-bezier(0.2, 0, 0, 1)` | Todas las transiciones: entra rápido y se asienta sin rebote |

**Qué se anima**

- Cambios de estado ante una acción: color, borde, opacidad y grosor del subrayado.
- La apertura y el cierre de un bloque (accordion): el cuerpo se despliega o se recoge (alto,
  padding y opacidad) en `1,5 × motion.duration-base`.
- El scroll dentro de la página: índice, mapa de secciones y botón "Inicio" con scroll suave.
- La vista previa del mapa de secciones: aparece con fade en `motion.duration-fast`.
- La lupa del mapa de secciones cambia el largo de las marcas sin transición: sigue al puntero
  cuadro a cuadro, así que es manipulación directa y no una animación. Lo mismo vale para el
  divisor de la comparación antes / después.
- La hoja del índice sube desde abajo al abrir y baja al cerrar (por "Cerrar", `Escape`, el fondo o
  al elegir una entrada), con el fondo apareciendo y yéndose a la par, en `1,5 × motion.duration-base`.
- **Latido de destino** (única escala del sistema): al tocar un paso, una referencia o un punto
  sobre una captura, el círculo de destino late 3 veces (`scale 1 → 1.25 → 1`, cada latido
  `2 × motion.duration-base`) cuando termina el scroll, para que se vea a qué apunta. Lo pidió el
  lector y termina solo; con "reducir movimiento" queda solo el anillo de resaltado.

**Qué no se anima**

- Nada que el lector no haya pedido: sin entradas al scrollear, sin parallax, sin loops ni autoplay.
- Sin rebotes, escalas, rotaciones ni `box-shadow`: rompen la estética de papel. La excepción es el
  latido de destino, el foco temporal, el crecimiento al pasar el puntero y la manito de los pasos con
  punto.
- Sin `height` o `max-height` animados en contenido largo: provocan saltos de layout. La excepción
  es el accordion, que el lector abre o cierra a propósito.
- Mockups y su contenido quedan quietos: muestran una pantalla, no una demo.

**Reglas**

- Solo `opacity`, `transform: translateY()` de hasta 4px y propiedades de color. Excepciones: el alto
  y el padding del cuerpo del accordion, la escala del latido y la manito, y el foco temporal.
- Ninguna transición supera `motion.duration-base` (200ms). Las excepciones son el latido de destino
  (3 latidos de `2 × motion.duration-base`) y el toque de la manito al pasar el puntero
  (`3 × motion.duration-base` por toque, en loop solo mientras el puntero sigue sobre el paso), el
  foco temporal (que dura lo que el latido) y la apertura y el cierre del accordion
  (`1,5 × motion.duration-base`).
- Todo el movimiento va dentro de `@media (prefers-reduced-motion: no-preference)`: con
  "reducir movimiento" activo no hay transiciones y el scroll es instantáneo.
- En impresión no hay transiciones ni animaciones.

## Components

Los snippets HTML de cada componente están en [Snippets de componentes](#snippets-de-componentes).

### Doc header

El primer bloque de todo documento. Estructura vertical:

```
[doc-label]   ← contexto: proyecto, alcance, área (mono uppercase)
[doc-title]   ← título principal (<h1>) — puede ocupar 2 líneas con <br>
[doc-sub]     ← subtítulo descriptivo (1 línea)
[doc-meta]    ← row horizontal de metadatos (fecha · prioridad · estado · estimado), solo los que
                 informan algo al lector: `Estado` solo si el documento tiene un ciclo real
                 (borrador → aprobado); un manual publicado siempre está vigente y no lo lleva
```

Cierra con `border-bottom: 2px solid {colors.border-ink}` y `margin-bottom: 40px`.
Las fechas de `doc-meta` van en formato absoluto (`2026-09-27`), nunca relativas.
Un documento que describe código lleva, al final y fuera del recorrido del lector, un
`<footer class="doc-footer">` con la línea `Para el equipo técnico · Código: <rama> @ <commit corto>`
(el dato solo le sirve a quien mantiene el documento; en el `doc-meta` distrae), con
`<rama> @ <commit corto>` como link al commit (`https://github.com/<org>/<repo>/commit/<sha>`,
`target="_blank" rel="noopener noreferrer"`), y, en el `<head>`, los metas `heritage:source-repo`,
`heritage:source-ref`, `heritage:source-commit`, `heritage:source-files` (rutas leídas, separadas
por espacio) y `heritage:source-commit-url`. Dicen
contra qué versión del código se escribió y permiten saber qué cambió desde entonces.

### Índice (TOC)

En lectura lineal va **siempre**, aunque el documento tenga pocas secciones, inmediatamente
después del `doc-header` (`check-manual.mjs` lo exige). Con [lectura por etapas](#lectura-por-etapas),
la hoja inferior cumple esta función y se omite el índice superior duplicado. Estructura lineal:

```
[toc-label]   "CONTENIDO" — mono uppercase
[toc-list]    01 Título de la sección   05 Título de la sección
              02 …                      06 …
```

- `<nav class="toc" aria-labelledby="toc-label">` con una `<ol>` a dos columnas (una en mobile).
- Cada entrada es un link al `id` del `section-title`, con el número en `toc-num` (mono, color `label`) y el título en `toc-item`.
- Es navegación, no prosa: el link va sin subrayado en reposo y lo muestra en hover y foco.
- **Scroll suave** hasta la sección con el script de navegación del boilerplate: alinea la
  `<section>` completa (número incluido) 16px debajo del borde, mueve el foco al título y
  actualiza el hash. Si el contenido de arriba cambia de alto mientras scrollea (imágenes o
  capturas diferidas), corrige la posición hasta que el layout se asienta.
- Si el documento tiene `part-header`, la parte se indica como un `toc-label` más dentro de la lista, sin link.
- Sin borde ni fondo: el índice no es una pieza encajada, es parte del flujo.

### Part header

Separa partes mayores de un documento largo (Parte A / Parte B). Abre con
`border-top: 2px solid {colors.border-ink}`, `margin-top: 56px` y
`padding-top: 32px`. Lleva un `part-header-label` mono uppercase
(`PARTE B`) y un `part-header-title` (`<h2>`, 22/600). Si el documento tiene
una sola parte, no usarlo.

### Section

Bloque numerado. Estructura:

```
[section-num]    "01", "02", … (mono uppercase, color label)
[section-title]  Título de la sección (<h2>, DM Sans 20/600)
[contenido]      párrafos, listas, callouts, tablas, code, mockups, steps
```

El `section-title` cierra con `border-bottom: 1px solid {colors.border}` y
`padding-bottom: 8px`. **No agregar `<h3>`+ para sub-jerarquías dentro de
una sección** — preferir prosa con `<strong>`. Si una sección crece
demasiado, dividirla en dos secciones numeradas o colapsar su referencia en
accordions.

### Callouts

Cuatro variantes, cada una con borde-izquierdo de `3px`. Reglas de elección:

- **Info (azul)**: contexto, lógica de fondo, "esto funciona así porque…".
- **Warn (amber)**: precaución, condicionales, restricciones.
- **Ok (verde)**: confirmaciones, "esto sí queremos", éxito.
- **Red (coral)**: consecuencias críticas, pendientes urgentes, errores.

Empezar el callout con una palabra clave en `<strong>` (`Importante:`,
`Ojo:`, `Resultado:`) para que el tono no dependa solo del color.
**Nunca anidar callouts**. Si un callout contiene una lista, usar `<ul>` o
`<ol>` normales — el callout ya provee el énfasis.

### Diagramas y alcance del contenido

- Conservar las representaciones originales cuando ya explican bien el flujo: HTML/CSS
  o SVG semántico, íconos y simuladores incluidos. No agregar Pele u otra biblioteca por
  defecto ni sustituir un diagrama legible por una segunda representación equivalente.
  Si se solicita otra tecnología, justificarla por una necesidad concreta y respetar
  las restricciones del destino y el carácter autocontenido del documento.
- No agregar por defecto «Ampliar diagrama», visor de zoom ni disclosure de una copia
  original. Priorizar lectura inline responsive, texto legible y descripción accesible;
  evitar que un modal clone IDs o pierda listeners y estado de un simulador.
- No repetir badges genéricos **«Modelo conceptual»** por todo el documento. Un aviso
  inicial de alcance basta para el contexto general; no significa certificación contra
  producción. Mantener etiquetas **«Ejemplo didáctico»** para simulaciones y advertencias
  **«Verificar implementación»** donde exista una incertidumbre concreta, explicando qué
  contrato o integración falta contrastar. No borrar avisos específicos para limpiar la UI.

### Tables

- Siempre dentro de `<div class="table-wrap">` para que scrolleen en mobile.
- Header en `{typography.table-header}` (mono, uppercase, tracking), con `scope="col"`.
- Fondo de header en `{colors.surface-alt}`.
- Celdas en `{typography.table-cell}` (13px) con `padding: 10px 12px`, `vertical-align: top`, `line-height: 1.5`.
- Borde inferior `1px solid {colors.border}` entre filas; **sin borde** en la última fila.
- Sin bordes verticales — la separación columna se logra con padding y el cambio tipográfico header/celda.

Usar tablas para comparativas estructuradas (operación / efecto / condición)
o para listas con columnas claras. Si tiene menos de 2 columnas reales,
preferir una lista.

### Badges

Pills compactas para estado. Cuatro variantes:

- `b-green`: ✓, "Sí", "Completado".
- `b-amber`: "Solo como excepción", "Media", "A coordinar".
- `b-red`: "Pendiente", "Bloqueante".
- `b-gray`: "Opcional", neutral.

Siempre en mono, siempre con `padding: 2px 8px`, siempre con borde `1px` del
color de la familia. **El texto del badge debe entenderse sin el color**
(`✓ Sí`, no un badge verde vacío). **No usar emojis dentro de badges** — el
color y el texto ya transmiten estado.

### Steps

Lista vertical numerada con línea conectora. Estructura:

```
[step-circle 1] [step-label] + [step-desc]
       │
[step-circle 2] [step-label] + [step-desc]
       │
[step-circle N] [step-label] + [step-desc]
```

- Se marca como `<ol class="steps">`; el número del `step-circle` es decorativo (`aria-hidden="true"`) porque la lista ordenada ya lo anuncia.
- `step-circle` es un círculo de `32×32px`, fondo `{colors.surface-dark}`, texto blanco mono.
- La línea conectora es `1px solid {colors.border}`, vertical, desde el bottom del circle hasta el siguiente; el último step no la tiene.
- Usar steps para **secuencias temporales o procesos accionables** ("1. cancela → 2. se re-suscribe"). No usar para listas de items independientes — para eso, `<ul>`.

### Code

- **Inline (`<code>`)**: fondo `{colors.surface-alt}`, padding `1px 6px`, radius `3px`. Para nombres de archivo, identificadores, valores literales en prosa.
- **Block (`.code-block`)**: fondo `{colors.surface-dark}`, texto `{colors.on-dark}`, padding `20px 24px`, radius `8px`, `overflow-x: auto`. Para snippets de SQL, HTML, JS, configuración. Escapar `<`, `>` y `&` dentro del `<pre>`.

Sintaxis: usar `<span>` con clases `c-comment`, `c-key`, `c-str`, `c-num`,
`c-fn`, `c-tag` para colorear manualmente. Los colores están en
`colors.syntax-*`. **No incluir números de línea** salvo que sean
referenciados desde el texto.

### Mockup

Ventana de navegador estilizada (tres dots tipo macOS + URL bar). Usar
**solo cuando una pantalla real ayuda más que la descripción**. Estructura:

```
[mockup-bar]   dots rojo/amarillo/verde + texto de URL (mono, color label)
[mockup-body]  contenido real del mockup (puede ser un layout multi-columna)
```

- **Celular:** `.mockup.mockup--mobile` limita el mockup a `410px` y lo centra, para capturas de
  375px. Así los puntos sobre la captura (`hotspot`) quedan en su lugar en cualquier ancho.
- **Leyenda:** `div.figcap` justo después del mockup, en mono 11px color `label`. Describe la
  pantalla con datos de ejemplo; el runtime de capturas la usa como `aria-label`.

Border `1.5px solid {colors.border-strong}`, radius `10px`, fondo
`{colors.surface-card}`. Lleva `isolation: isolate`: las capturas reales traen capas con `z-index`
alto (modales, menús) que, sin aislar, taparían el botón "Inicio", la píldora y el mapa. Los dots usan `red-border`, `warn-border` y
`ok-border` (10×10px) y son decorativos (`aria-hidden="true"`). Agregar
`role="img"` + `aria-label` con una descripción breve de la pantalla cuando
el mockup es un dibujo y no contenido legible.

### Example box

Cita destacada con label mono. Estructura:

```
[example-label]   "EJEMPLO PRÁCTICO" — mono uppercase
[example-body]    el cuerpo del ejemplo
```

Border `1.5px solid {colors.border-strong}`, fondo blanco, radius `10px`.
Equivalente a un callout pero con tono **neutro** — para narrar un caso
concreto sin teñirlo de aviso/éxito/error.

### Pills (chips de estado en flujos)

Útiles para representar transiciones de valor (`$15 → $20`):

- `pill-neutral`: estado actual sin connotación.
- `pill-success`: estado deseado / vigente.
- `pill-stale`: estado viejo (con `text-decoration: line-through`). Para lectores de pantalla, envolver el valor en `<del>` en lugar de depender solo del tachado visual.

Se intercalan con flechas mono (`→`, `aria-hidden="true"`) en color
`{colors.label}`, dentro de un contenedor `.flow` que hace wrap en mobile.

### Link

Color `{colors.link}`, subrayado `1px` con `text-underline-offset: 2px`; en
hover el subrayado pasa a `2px`, con transición de `motion.duration-fast`. Nunca
quitar el subrayado en prosa: el color solo no distingue un link del texto. Única excepción: el índice (TOC), donde
el contexto ya indica que todo es navegable. Links externos con texto descriptivo, no
"click acá".

### Referencias a secciones

Cada vez que el texto menciona otra sección, la mención es un link a esa sección con su **título**, no
con su número: `<a href="#permissions">sección Permisos y prerrequisitos</a>`. El número solo no le dice
nada al lector ("sección 03") y no se puede seguir. Varias secciones: `secciones <a href="#a">Título A</a>
y <a href="#b">Título B</a>` (o `a` para un rango). Sin comillas: «…» y “…” se reservan para textos de la
app. En portugués, el link dice `seção` y el título traducido de la tabla. `check-manual.mjs` marca como
error cualquier "sección NN" que quede sin link.

Un link dentro de un paso con punto (`step-item[data-hotspot]`) o de una referencia va a su destino: el
script de navegación no muestra el punto ni el tooltip "Ver en la captura" al tocarlo.

### Accordion (bloques colapsables)

Bloque de detalle que arranca **cerrado** y se expande al click. Pensado para
**documentos densos**: una sección con muchas reglas, tablas de comportamiento,
casos de error y checklists se vuelve un muro vertical. El accordion deja a la
vista solo los títulos y el lector abre lo que necesita.

Implementación nativa con `<details class="acc">` + `<summary>` (sin JS para
abrir/cerrar). Estructura:

```
[summary]   [accordion-num] (label mono opcional) + título  ···  glifo +/–
[acc-body]  contenido: prosa, listas, tablas, callouts
```

- Borde `1px solid {colors.border}`, radius `8px`, fondo `surface-card`.
- El `summary` usa `accordion-title` (16/600), un escalón por debajo de `section-title` para que el título de la sección siga mandando, y **sin** borde inferior; el marcador nativo se oculta y se reemplaza por un glifo `+` (cerrado) / `–` (abierto) en mono, color `label`, alineado a la derecha.
- Al abrir (`[open]`), el `summary` cierra con `border-bottom: 1px solid {colors.border}` para separar del cuerpo.
- Opcional: un `accordion-num` (mono uppercase, color `label`) al inicio del summary como mini-etiqueta del bloque (`Reglas`, `Comportamiento`, `Checklist`), en el mismo espíritu que `section-num`.
- El `summary` es focuseable con teclado: nunca quitarle el `:focus-visible`.
- **Al abrir y al cerrar**, el `acc-body` se despliega o se recoge (alto, padding y opacidad) en
  `1,5 × motion.duration-base`, con `motion.easing-standard`. Lo hace el script con Web Animations
  sobre el `<details>` nativo: el teclado, el lector de pantalla y la impresión (que abre todo) siguen
  funcionando igual. Tocar de nuevo a mitad de camino invierte el movimiento. Con "reducir
  movimiento", abre y cierra al instante.
- **Nunca dos abiertos:** abrir un accordion, con un clic o con un salto (desde el glosario, un link o una
  referencia), cierra con la misma animación todos los demás abiertos del documento, salvo los que lo
  contienen. La impresión los abre todos igual.

**Regla de uso:** colapsar los bloques de **referencia** (reglas de negocio,
comportamiento esperado, casos de error, checklist) y dejar **siempre abiertos**
los de **acción** (intro/objetivo, flujo en `steps`, mockups). No anidar
accordions ni meter un mockup pesado adentro de uno cerrado. Si una sección no
es densa, no la colapses — el accordion es para domar volumen, no decoración.

### Botón "Inicio" (volver al inicio)

Botón flotante para documentos largos: vuelve al principio sin que el lector
tenga que scrollear todo de nuevo. Usarlo junto con el índice.

- `<a class="back-to-top" href="#top" aria-label="Volver al inicio" hidden>` con `↑` decorativo (`aria-hidden="true"`) y el texto **Inicio**.
- El `doc-header` lleva `id="top"` y `tabindex="-1"` para recibir el foco después del salto.
- Fijo abajo a la derecha (24px; 16px en mobile), fondo `surface-dark`, texto `surface-card`, mono 12/500, radio circular y la sombra mínima documentada.
- Está oculto (`hidden`) hasta los primeros 480px de scroll; aparece con fade en `motion.duration-base`. Al ocultarse desaparece sin transición, para no quedar clickeable mientras se desvanece.
- Scroll suave hasta `0`, no hasta la posición del header, porque el header tiene margen superior.
- Funciona dentro de visores embebidos que scrollean un iframe: usa `window` del propio documento.
- No se imprime.

### Mapa de secciones

Atajo lateral para documentos largos: una marca corta por sección, fija a la
izquierda de la página. Al pasar el mouse o enfocar una marca aparece una vista
previa con el número, el título y el comienzo de la sección; al hacer click,
salta a ella. Complementa al índice completo (superior en lectura lineal o en hoja
inferior con etapas): el mapa queda a mano mientras se lee. Usarlo junto con ese
índice y el botón "Inicio".

```
 ─
 ──
 ───            ┌──────────────────────────────────┐
 ━━━━━  ←────── │ 03                               │
 ───            │ Quién ve qué                     │
 ──             │ La sección muestra a cada        │
 ─              │ operador solo lo que …           │
 ─              └──────────────────────────────────┘
```

- Markup: solo `<nav class="section-rail" aria-label="Mapa de secciones" hidden></nav>` antes de
  `</body>`. El script de navegación del boilerplate lo arma: una marca por cada `section.section`
  con `section-title` e `id`, y lo muestra si hay 2 o más. **No se escribe a mano**, así que no se
  desalinea cuando cambian las secciones.
- La primera marca es el **inicio del documento** (`#top`): un punto de `6px`, separado `8px` de las
  rayas para que la primera raya siga siendo la sección 01. No crece con la lupa. Su vista previa
  muestra el título y el subtítulo, sin número, y su `aria-label` es "Inicio: <título>".
- Cada marca es un link al `id` del `section-title`, con `aria-label` "número + título". Usa el
  mismo scroll que el índice: sección completa 16px debajo del borde, foco en el título, hash
  actualizado y `heritage:before-scroll`.
- Marca en reposo: `12×2px`, color `label`. **Sección actual** (`aria-current="location"`, la
  última cuyo borde superior pasó el 30% de la ventana, o la última al llegar al final): `24px` y
  color `primary`. El largo marca el estado, no solo el color.
- **Lupa:** con el puntero sobre el mapa, la marca más cercana llega a `40px` y color `primary`, y
  las vecinas crecen menos cuanto más lejos están, hasta volver a `12px` a `48px` del puntero (unas
  4 marcas por lado, caída en coseno). Sigue la posición vertical del puntero, no solo la marca
  bajo él. Con el foco del teclado la lupa se centra en la marca enfocada. La sección actual nunca
  baja de `24px`. Al salir del mapa todo vuelve al reposo.
- Vista previa: `surface-card`, borde `1px` `border-strong`, radio `8px`, `280px` de ancho, la
  sombra mínima documentada. Muestra `section-num`, el título en una línea y el primer párrafo de
  la sección (hasta 3 líneas). Es decorativa (`aria-hidden="true"`, sin eventos del puntero): el
  nombre accesible ya está en el link. Se centra en la marca y no se sale de la ventana.
- Se oculta por debajo de `1024px` (breakpoint `rail`), donde no queda margen al costado del
  texto, y en impresión. Sin JavaScript no aparece.
- **Progreso:** la marca de la sección actual se llena de `primary` de izquierda a derecha a medida
  que se lee (`--tick-progress`); lo que falta queda en `label`.
- **Sin estado de lectura:** el mapa no marca secciones como leídas ni guarda nada entre visitas.
  Un documento publicado se actualiza en su lugar, así que una sección "leída" puede haber cambiado
  desde entonces; el progreso de la sección actual alcanza para ubicarse.
- **Atajos:** el pie de la vista previa los recuerda (`⌥ ↑ ↓ secciones · ⌥ I índice`, `Alt` fuera
  de Mac). Ver [Atajos de teclado](#atajos-de-teclado).

### Píldora de sección

Píldora fija abajo a la izquierda con la sección actual (`03 · Quién ve qué`); al tocarla abre el
índice en una hoja inferior. Se ve en todos los anchos: en desktop acompaña al mapa (dice dónde
estás sin pasar el mouse) y por debajo de `1024px`, incluido el iframe angosto de un visor embebido,
conserva el acceso al índice completo aunque el mapa se oculte. Con etapas, convive con
la barra compacta: cada control cumple una función distinta.

- Anclarla al **viewport**, no al contenedor centrado ni al menú: `left:24px; bottom:24px`,
  y `16px` en ambos bordes por debajo de `720px`. Mantener libre el botón «Inicio».
- El título compacto puede truncarse, pero `title` y nombre accesible lo conservan completo.
  En la hoja mostrar **«Sección actual · número · título completo»**, sin ellipsis, y
  exactamente una entrada con `aria-current="location"`, reconocible sin depender del color.
  Al abrir, dejar visible ese encabezado; la lista puede tener scroll propio.

```
┌─────────────────────────────────────┐
│ …                                   │
│ ╭──────────────────╮   ╭──────────╮ │
│ │ 03  Quién ve qué │   │ ↑ Inicio │ │
│ ╰──────────────────╯   ╰──────────╯ │
└─────────────────────────────────────┘
```

- Markup fijo (`button.section-pill` + `dialog.toc-sheet`, ver snippets); el script completa la
  sección actual y copia el índice adentro de la hoja, con sus etiquetas de parte. Si
  no hay índice, arma la lista desde las secciones.
- **Se ve siempre**, también arriba de todo, donde muestra el título del documento sin número. Deja
  lugar para el botón "Inicio" (que sigue apareciendo después de 480px de scroll): el título se
  corta con ellipsis (máximo `360px`).
- La hoja suma, antes de la primera sección, el título del documento como entrada que lleva al
  inicio (`#top`, la URL queda sin hash).
- La hoja es un `<dialog>` modal: atrapa el foco, cierra con `Escape`, con "Cerrar" o tocando el
  fondo, y devuelve el foco a la píldora. La sección actual va en negrita
  (`aria-current="location"`). Al elegir una entrada cierra y scrollea como el índice. Abre subiendo
  desde abajo y cierra bajando (ver Motion).
- `aria-label` de la píldora: "Sección actual: 03 Quién ve qué. Abrir índice".
- No se imprime.

### Copiar enlace a una sección

Cada `section-num` suma un botón "Copiar enlace" a la derecha. Sirve para responder un ticket con
el link directo a la sección. El boilerplate resuelve hashes genéricos; los formatos
específicos de un visor requieren adaptar generación, lectura y sincronización, y probar esa
integración. Declarar `heritage:share-url` no implementa por sí solo un adaptador del host.

- Lo agrega el script; no se escribe a mano. Visible al pasar por la sección o al enfocarlo, y
  siempre en pantallas táctiles (`hover: none`).
- En una página directa copia `<URL base>#<id del section-title>`. En visores embebidos la
  URL del iframe no es la que ve el lector: declarar la pública con
  `<meta name="heritage:share-url" content="…">` y aplicar el formato del host descrito abajo.
- **El id es un slug fijo de la sección**, no su número ni su título: corto, en kebab-case, en
  inglés (el mismo para todos los idiomas) y que diga de qué trata (`permissions`,
  `add-collaborators`). Se elige al crear la sección y no cambia nunca: ni al renumerar, ni al agregar
  secciones en medio, ni al cambiar el título; así un enlace copiado sigue llevando a la misma
  sección. Un id de una sección eliminada no se reusa.
- Confirma con "Enlace copiado" en el botón y en una región `role="status"`. Si el visor bloquea
  el portapapeles, dice "No se pudo copiar" y deja un `console.warn` con el `id` de la sección.
- Al copiar, actualizar también la URL pública visible, sin agregar una entrada al historial.
  No asumir que el visor sincroniza el hash del iframe: comprobar su contrato. Por ejemplo,
  un visor puede usar `/d/<doc_id>/view?href=<id>` en la barra y `/d/<doc_id>/raw#<id>` dentro.
  Adaptar la generación y lectura del enlace a ese formato, sin copiar la URL local de preview.
- Si hace falta sincronizar `parent.history`, hacerlo únicamente tras verificar **mismo origen
  y mismo documento**; no tocar el DOM ni el estado interno del visor. En cross-origin usar
  solo un protocolo documentado del host. Si no existe, conservar la navegación interna y
  comunicar la limitación: no afirmar que la barra externa quedó actualizada.
- Resolver el destino desde la URL pública al cargar y al recibir `popstate` o `hashchange`,
  además del hash propio. Con etapas, revelar el destino antes del scroll. Validar el enlace
  copiado abriéndolo en otra pestaña del visor, recargando y usando Atrás/Adelante.
- **Adaptador de visor.** El script de navegación consulta `window.HeritageViewer` si existe
  (`shareUrl(id)`, `syncLocation(id)`, `initialTargetId()`, `onNavigate(callback)`); sin él conserva
  el comportamiento genérico de hash. Para visores con ese formato,
  `assets/viewer-adapters/document-viewer-adapter.js` (incrustarlo con
  `build-manual.mjs --viewer document`, también en un manual lineal) solo
  sincroniza `?href=` cuando el visor es del mismo origen y su `/d/<doc_id>/view` coincide con el
  `/d/<doc_id>/raw` del iframe y con `heritage:share-url`. Si no, la navegación queda local,
  `HeritageViewer.reason` dice por qué (`cross-origin`, `unrecognized-host`, `different-document`,
  `share-url-mismatch`) y un `console.warn` lo declara la primera vez; el enlace copiado sigue
  usando el formato público de `heritage:share-url`.
- **Abrir el enlace lleva a la sección**, también al recargar: el script lee el hash propio o, en un
  visor embebido del mismo origen (que puede no pasar el hash al iframe), el de la página que lo envuelve,
  y salta como desde el índice, renderizando antes las capturas de arriba. Un hash nuevo pegado en
  la barra del visor también mueve el documento.

### Selector de idioma

Solo en documentos que tienen versión en portugués: un documento **solo en español no lleva
selector**. Cuando la tiene, puede leerse en **español (por defecto) y portugués**. El lector elige con una píldora
segmentada **fija arriba a la derecha** (`Español · Português`), visible en todo el recorrido como el
botón "Inicio" y la píldora de sección; la opción activa lleva fondo `surface-card`, borde `1.5px` `link`
y peso 600, y las demás quedan en `muted`. En pantallas angostas se achica y se acerca al borde
(`top:12px`, `right:16px`), y el `doc-header` suma `28px` arriba para que no tape la etiqueta ni el título.
Cuando el selector cae sobre la columna del texto, los saltos (índice, mapa, enlaces directos, cambio
de idioma) dejan la sección `16px` debajo del selector en lugar de `16px` debajo del borde, así el
número de la sección y su "Copiar enlace" quedan a la vista.

- **Un solo markup, en español, y una tabla de traducciones.** El documento se escribe una vez, en
  español; el portugués es una tabla JSON en `<script type="application/json" id="heritage-translations">`
  con `htmlLang`, `title` y tres partes: `document` (texto en español → texto en portugués, para cada
  texto y cada `aria-label`, `title`, `alt`, `placeholder`, `data-tooltip`, `data-target` y
  `data-target-text` del documento), `captures` (lo mismo para los textos de la app dentro de las
  capturas) y `captureTemplates` (solo para la captura excepcional cuya estructura cambia en
  portugués: su HTML completo, por nombre). No se duplica el markup ni las capturas.
- **Script de idioma** (`window.HeritageLanguage`), justo antes del de navegación: traduce en el lugar
  los textos y atributos que están en la tabla (la clave es el texto sin los espacios de los bordes),
  guarda el español de cada uno para poder volver, ajusta `lang` y el título, y avisa con el evento
  `heritage:language-change`. Nunca toca `code`, `style`, `script` ni el selector. Al cargar, traduce
  solo si la URL lo pide: **siempre abre en español**, la elección no se guarda (ni `localStorage` ni
  cookies) y vive solo en `?lang=pt` (la URL del documento o, dentro de un visor embebido, la del
  visor), así que dura mientras se lee y viaja en un enlace compartido.
- **Al elegir**, el cambio es **en la misma página, sin red ni recarga**: el script de navegación llama
  a `HeritageLanguage.set`, reescribe sus propios textos, las capturas se traducen y vuelven a ubicar
  sus puntos, la URL pasa a `?lang=pt` (o lo pierde) conservando `#sNN`, y **la pantalla queda donde
  estaba**: el primer bloque que se veía arriba (párrafo, paso, fila, captura) sigue a la misma distancia
  del borde. El ancla es ese bloque y no el `scrollY`, porque el texto traducido tiene otro largo; se
  mantiene mientras las capturas se vuelven a acomodar. El navegador funde
  el antes y el después con `document.startViewTransition` en `1,5 × motion.duration-base` (300ms); sin
  soporte o con "reducir movimiento", cambia al instante.
- Los textos de la interfaz que arma el script de navegación (copiar enlace, tooltips, pista de las
  capturas, mapa, píldora, hoja del índice, botón "Inicio") salen de su diccionario `UI_TEXT` y se
  vuelven a escribir con cada cambio de idioma (`whenLanguage`); no van en la tabla.
- `role="radiogroup"` con `aria-label` "Idioma"; cada opción es un `button` con `role="radio"` y
  `aria-checked`. Cada opción se nombra en su propio idioma. No se imprime.
- Sin banderas: un idioma no es un país.

### Ir al menú

En los documentos que se abren desde un **menú de manuales**: un link **fijo arriba a la izquierda**,
espejo del selector de idioma (mismo fondo, borde, radio y alto) y visible en todo
el recorrido: la flecha `←` (en un `span` con `aria-hidden`, como la `↑` del botón "Inicio") y "Ir al menú". Lleva a la URL pública del menú (en un visor, su URL para compartir). Mientras cae sobre la columna del
texto (hasta 1199px), el `doc-header` suma `28px` arriba y los saltos dejan la sección `16px` debajo de
él, como con el selector. No se imprime. Es el primer hijo del `<body>`; el texto va en la tabla de
traducciones ("Ir ao menu").

### Tarjeta destacada en una captura

Cuando una captura muestra varias opciones del mismo tipo (las tarjetas del menú de la app) y el texto
habla de una, el `app-frame` lleva `data-mute="<selector del grupo>"` y `data-mute-except="<selector de la
opción>"`: el runtime de capturas pone en gris (`grayscale`) y al 45% los íconos e imágenes de las demás,
dentro de la captura, también después de cambiar de idioma. Los textos de la app no cambian. Se usa en
"¿Cómo se accede?" para la tarjeta del manual.

### Menú de manuales

Un documento que reúne los manuales de una herramienta es **siempre una réplica del menú real de la
app**: la captura del menú (`app-frame`, como cualquier captura) con un link encima de cada tarjeta,
nunca una grilla dibujada a mano. El lector reconoce la pantalla que ya usa y toca la misma tarjeta.

- Header común (`doc-label`, `doc-title`, `doc-sub` con qué hacer, `doc-meta` con `Fecha` y
  `Capturas`), sin índice, mapa, píldora ni botón "Inicio": es una sola pantalla.
- Se captura con **todas** las tarjetas (un usuario con todos los permisos); el `figcap` dice que cada
  usuario ve solo las que le habilitan sus permisos.
- Cada tarjeta lleva un `a.menu-link` anclado con `data-target` + `data-target-text` (el texto de la
  tarjeta), que cubre la tarjeta después de cada ajuste de la captura y al cambiar de idioma.
  - Con manual: `href` a la URL pública del manual (con `#slug` cuando la tarjeta abre una parte del
    manual); la tarjeta se ve como en la app y, al pasar el puntero o enfocar su link, crece con
    `scale:1.05` en `motion.duration-fast` (la regla la inyecta el script dentro de la captura); con
    teclado suma el anillo `2px` `link` de `:focus-visible`.
  - Sin manual: `aria-disabled="true"`, sin `href`; el script pone su ícono en gris (`grayscale`) y al
    45% de opacidad, dentro de la captura, y no navega. Los textos quedan como en la app.
  - Nada se superpone a los textos de la tarjeta (sin badges encima): los textos de la app cambian de
    largo con el ancho y el idioma. Una leyenda debajo del `figcap` dice qué hace una tarjeta normal y
    qué significa una con el ícono en gris.
- Cada link tiene `aria-label` ("Abrir el manual de …" o "…: manual en preparación").

### Navegación entre documentos

El menú y los manuales se enlazan con `a[data-document-link]` y el script "Navegación entre
documentos" del boilerplate:

- **Abre en la página entera**, también dentro de un visor embebido: el sandbox de su iframe puede no permitir navegar la
  página de arriba (ni con `target="_top"`), así que el script crea el link en el documento del visor,
  que es del mismo origen, y lo activa. Fuera de un visor funciona el `target="_top"` del link.
- **Lleva el idioma:** en portugués agrega `?lang=pt` a la URL de destino. El script de idioma lee
  `?lang` de su propia URL y, dentro de un visor, de la del visor (que puede no pasar la query al iframe).
- **Transición:** el documento se desvanece en `motion.duration-base` antes de irse y el destino aparece
  en lo mismo cuando llega desde otro documento del mismo visor (no al recargar). No es una view
  transition entre documentos: las páginas de un visor pueden no habilitarla y el destino es suyo. Con "reducir
  movimiento", cambia al instante.
- `Cmd`/`Ctrl` + click abre en una pestaña nueva, con el idioma ya en el link.

### Sin marcas de novedad

Los documentos **no marcan secciones nuevas ni actualizadas**: nada de badges "Nuevo" /
"Actualizado", puntos de color en el mapa ni "Novedades: N secciones" en el `doc-meta`. Cada
versión se lee como el documento completo y vigente; el historial de cambios queda en la
herramienta donde se publica (por ejemplo, el historial de versiones del visor).

### Glosario

Términos del dominio con su definición a mano, sin salir del párrafo.

```html
<p>Los usuarios con <a class="term" href="#g-cuenta-externa">cuenta externa</a> no ven …</p>
…
<dl class="glossary">
  <dt id="g-cuenta-externa">Cuenta externa</dt>
  <dd>Cuenta de una persona que no es empleada; empieza con <code>ext_</code>.</dd>
</dl>
```

- La definición vive **una sola vez**, en la `<dl class="glossary">`, en la sección "Glosario"
  (`data-section="glossary"`), siempre la **última** del documento. Un glosario sin términos no se
  muestra: sin sección, sin entrada en el índice y sin `a.term`. El término es un link a su `<dt>`:
  sin JavaScript igual lleva a la definición.
- Con JavaScript, al pasar o enfocar el término aparece una tarjeta con el término y la definición,
  debajo (o arriba si no entra). Se puede recorrer con el puntero sin que se cierre y `Escape` la
  cierra (WCAG 1.4.13). El término recibe `aria-describedby` hacia su `<dd>`.
- Estilo: hereda el color del texto, subrayado punteado `label`; así no se confunde con un link
  común. Marcar solo la primera aparición de cada término por sección.
- Ids con prefijo `g-` en kebab-case.
- **Menciones:** el script de navegación agrega junto a cada `<dt>` un superíndice por cada `a.term` que
  lo menciona en el documento (`1 2 3`, en orden de aparición). Cada número lleva a esa mención y su
  tooltip dice la sección ("Mención en Permisos y prerrequisitos"). No se escriben a mano: salen de los
  `a.term` del texto, así que agregar o quitar una mención actualiza el glosario solo. No se imprimen.
- **Saltos del glosario:** del término a su definición y de un superíndice a su mención, el destino se
  centra y late 3 veces (`scale 1 → 1.08 → 1`) bajo el foco temporal, como un punto de una captura, sin
  fondo de color. El foco se centra en la palabra del destino: no en el ancho de su bloque ni en sus superíndices. Si está dentro de un
  accordion cerrado, el accordion se abre antes. El resaltado se aplica antes de medir, para que la palabra no se mueva
  al empezar a latir. Un destino del final (el glosario) también queda centrado: un espaciador (`.scroll-spacer`)
  agrega lugar al pie durante el salto y se achica solo cuando el lector vuelve a subir. Con "reducir movimiento" no late ni aparece el foco.

### Puntos sobre capturas

Círculos numerados encima de una captura o mockup que conectan la imagen con los pasos.

```
┌ mockup ─────────────────────────┐      ①  Abrí el menú
│  [≡]①        Buscar …   [⚙]②   │      ②  Elegí "Filtrar"
└─────────────────────────────────┘
```

- `div.hotspot-stage` envuelve el contenido de la captura (`app-frame` o `mockup-body`) y lleva
  los `span.hotspot` con `data-hotspot="1"`.
- **Los pasos van antes de la captura:** el `ol.steps` vinculado a una captura se escribe antes de su
  `.mockup` (y del `figcap`), nunca después. El lector lee qué hacer y después ve dónde; los círculos
  grandes de los pasos encabezan el bloque.
- **Los puntos se numeran en orden de lectura:** de arriba hacia abajo y, en la misma fila, de
  izquierda a derecha. Si una sección tiene varias capturas, la numeración sigue de una captura a la
  siguiente. Los pasos y las referencias llevan esos mismos números, así que los pasos se escriben en ese
  orden; si una acción tiene que ir antes que otra que está más arriba, va en otra lista de pasos.
  Las referencias en el texto también se mencionan en orden dentro de cada párrafo, lista o tabla:
  "(5) … (6) … (7)", nunca "(6) … (5)". Si la frase nombra los elementos en otro orden, se reescribe
  siguiendo la captura (de arriba hacia abajo).
- **Las referencias en el texto también van antes:** el párrafo, la lista o la tabla con
  `span.hotspot-ref` se ubica justo antes de la captura que tiene esos puntos, lo más cerca posible:
  pasos → texto con referencias → captura → `figcap`. Si una lista nombra puntos de varias capturas
  seguidas, se parte en una lista por captura, cada una antes de la suya. Un párrafo que presenta varias
  capturas seguidas puede ir antes de la primera, sin otro texto entre ellas.
- **Sobre una captura real, anclar siempre el punto a su elemento:** `data-target` es un selector
  CSS dentro de la captura y `data-target-text`, opcional, el texto exacto cuando el selector
  matchea varios (`data-target="button" data-target-text="Confirmar"`). El runtime de capturas
  ubica el punto 14px a la izquierda del elemento, centrado en alto, después de cada ajuste del
  frame y de cada resize. No se corre con el ancho ni el alto del lector.
- `--x` / `--y` (porcentaje del stage) quedan como posición inicial hasta que el frame renderiza, y
  como única posición sobre un `mockup-body` dibujado a mano. Un porcentaje solo es estable si la
  captura no cambia de alto con la ventana: por eso, sobre capturas, se ancla.
- Los pasos (`li.step-item`) y las referencias en el texto (`span.hotspot-ref`) llevan el mismo
  `data-hotspot`. El número del punto coincide con el del paso.
- **Un número, un punto por sección:** los puntos viven en la misma sección que sus pasos y
  referencias, y cada número aparece en un solo punto de la sección. Dos `1` en una sección (de
  dos listas de pasos distintas) confunden al lector. Si un paso ocurre en una pantalla que ya se
  mostró en otra sección, se repite la captura (mismo `data-cap`) en la sección del paso, con su
  punto; la pantalla original queda sin puntos.
- **Vuelta al paso:** cada punto lleva una burbuja de `16px` en su esquina inferior derecha con la
  flecha curva de "deshacer" (la agrega el script). Aparece al pasar el puntero por el punto y, sola,
  cuando el lector llega al punto desde un paso, hasta el último latido: se va justo con él (con
  "reducir movimiento", al terminar el resaltado). En reposo no se ve y no se imprime.
- **Foco temporal:** al llegar a un salto, la página se oscurece apenas (`surface-dark` al 15%) y se
  desenfoca `6px`, y una burbuja nítida se cierra sobre el destino hasta dejar `44px` libres alrededor
  del círculo (`.hotspot-spotlight`, la agrega el script). Se abre en **500ms** y enseguida se va en
  otros **500ms** (`2,5 × motion.duration-base` cada uno, 1s en total), mientras el
  destino sigue latiendo; también se va apenas el lector scrollea o toca la pantalla. Con "reducir movimiento" no aparece; no se imprime.
- **El destino conserva el resaltado durante el salto**, hasta su último latido: lo que pasa por
  debajo del puntero mientras la página scrollea (otro punto, otro paso) no se lo quita. Con el último
  latido termina el resaltado (con "reducir movimiento", a los 2,6 s) y vuelve a seguir al puntero.
- **Manito en los pasos:** cada `step-item` con punto lleva una manito (la agrega el script) en la
  esquina inferior derecha del círculo, inclinada `-35°` y con el índice adentro. Quieta en reposo;
  mientras el puntero está sobre el paso repite el toque, y para al salir: el índice baja `2px` y destella
  (`3 × motion.duration-base`). Solo en los círculos grandes: sobre los puntos de las capturas
  taparía lo que señalan. Con "reducir movimiento" no se anima.
- **Se nota que se pueden tocar,** sin movimiento que el lector no pidió: el círculo bajo el puntero
  o con foco crece a `1.1` (en `motion.duration-fast`) y se resalta con su par; el tooltip dice qué
  pasa al tocar («Ir al paso 2», «Ver en la captura»), y el pie de la primera captura con puntos de
  cada sección suma «Hacé click en un número para ir a su paso.» con mouse o «Tocá un número para ir
  a su paso.» en pantallas táctiles (`.figcap-hint`, lo agrega el script según el puntero; no se imprime).
- Tocar un paso o una referencia (o `Enter` sobre la referencia) centra su punto en la pantalla,
  siempre, lo resalta y, al llegar, lo hace latir 3 veces. Tocar el punto hace el camino inverso: centra el círculo de su paso (o,
  si la sección no tiene pasos con ese número, la primera referencia).
- Al pasar por un paso, una referencia o un punto, se resaltan los que comparten número (anillo
  `focus-ring`) y todos los demás círculos de la sección (puntos, referencias y pasos) bajan a 40% de
  opacidad, también mientras late el destino de un salto.
- Los puntos son `aria-hidden="true"`: el texto del paso lleva la información. En la referencia,
  el texto oculto `punto` le da contexto al lector de pantalla.
- **Tantos puntos como tenga sentido:** todo elemento que el texto nombra sobre una captura (botón,
  campo, pestaña, mensaje, valor) lleva su punto y su referencia. Máximo 6 por captura; si hacen
  falta más, se divide el texto en dos grupos y se repite la captura.
- Se imprimen.

### Comparación antes / después

Dos capturas superpuestas con un divisor que se arrastra. Para "¿Qué cambió?".

- `div.compare` > `div.compare-stage` con `div.compare-before`, `div.compare-after`,
  `div.compare-handle` y un `input.compare-range` nativo (0–100) que cubre la imagen; debajo,
  `div.compare-labels` con "Antes" y "Después".
- El divisor sigue al puntero o al dedo; con teclado se mueve con las flechas del range, que
  anuncia `aria-valuetext` ("Antes 50%, después 50%"). El foco muestra el anillo alrededor.
- `compare-stage` también lleva `isolation: isolate`, como el mockup.
- Las dos capturas deben tener el mismo ancho y encuadre; si no, no se pueden comparar y van como
  dos mockups.
- Cada `app-frame` dentro de una comparación lleva su `aria-label` ("Captura de pantalla: antes,
  …"), porque no tiene mockup del que tomarlo.
- En impresión se ven lado a lado, sin divisor.

### Atajos de teclado

- `Alt` + `↓` / `↑` (`⌥` en Mac): sección siguiente / anterior. `Alt` + `I`: índice.
- Llevan modificador para no chocar con lectores de pantalla ni con la escritura (WCAG 2.1.4), y
  se ignoran dentro de campos, con la hoja del índice abierta o con otro modificador.
- `Escape` cierra la vista previa del mapa y la tarjeta del glosario.
- Usan el mismo scroll que el índice.

## Accesibilidad

- **Contraste**: todo texto cumple ≥4.5:1 sobre su superficie; bordes con significado y el anillo de foco, ≥3:1. Valores medidos: `label` 4.56–5.33:1, `muted` ≥6.38:1, textos de callout 5.8–7.7:1, `syntax-comment` 4.93:1.
- **Semántica**: `<header>` + `<h1>` para el doc-header, `<section>` + `<h2>` por sección, `<ol>` para steps, `<th scope="col">` en tablas, `<details>/<summary>` para accordions.
- **Foco**: `:focus-visible` con `outline: 2px solid {colors.focus-ring}` y `outline-offset: 2px` en links y summaries. Nunca `outline: none` sin reemplazo.
- **Color no es el único canal**: callouts con palabra clave inicial, badges con texto, links subrayados, estados viejos con `<del>`.
- **Decoración oculta**: dots del mockup, flechas de flujo, números de step-circle, la flecha del botón "Inicio" y la vista previa del mapa de secciones llevan `aria-hidden="true"`.
- **Contenido al pasar el mouse**: la tarjeta del glosario se puede recorrer con el puntero, cierra con `Escape` y su contenido también existe en la página (WCAG 1.4.13). La vista previa del mapa es decorativa y cierra con `Escape`.
- **Atajos**: siempre con modificador (`Alt`/`⌥`), nunca una tecla sola (WCAG 2.1.4).
- **Movimiento**: todo el motion va dentro de `@media (prefers-reduced-motion: no-preference)`; con "reducir movimiento" el scroll es instantáneo y no hay transiciones. Después de un salto por el índice o el botón "Inicio", el foco queda en el destino.
- **Idioma**: `<html lang="es">`; fragmentos en otro idioma con `lang` propio si son prosa (no hace falta para código).

## Impresión

El documento debe imprimirse (o exportarse a PDF) sin perder jerarquía:

- Fondo blanco y sin padding de página: el limestone no se imprime bien y el navegador lo descarta por defecto.
- `break-inside: avoid` en callouts, example boxes, mockups, steps, code blocks y filas de tabla; `break-after: avoid` en títulos.
- Los accordions se abren antes de imprimir (snippet `beforeprint` del boilerplate); el glifo `+/–` se oculta.
- Los links muestran su URL entre paréntesis después del texto.
- Sin transiciones ni animaciones, sin botón "Inicio", mapa de secciones, píldora, botones de copiar enlace ni tarjetas del glosario.
- Las comparaciones antes / después se imprimen lado a lado; los puntos sobre capturas, sí.

## Do's and Don'ts

### Do

- **Numerá las secciones** (`01`, `02`, …). Da una sensación de spec serio. Para referenciar una sección en el texto, usá su nombre como link, nunca solo el número (ver "Referencias a secciones").
- **Usá `doc-label` y `section-num` en mono uppercase**. Es la firma visual del sistema.
- **Elegí callouts conscientemente**: cada uno tiene un significado, no son intercambiables.
- **Mantené párrafos cortos** (3–5 líneas máximo). El line-height generoso es para escanear, no para muros de texto.
- **Usá `<strong>` para énfasis dentro de prosa**, no `<b>` ni colores arbitrarios.
- **Tipografiá las celdas de tabla con `table-cell`** (DM Sans 13px) — los headers van en mono, las celdas no.
- **Envolvé toda tabla en `.table-wrap`** para que no desborde en mobile.
- **Colapsá los bloques de referencia en docs densos** con `accordion` (reglas, comportamiento, errores, checklist) y dejá abiertos intro, flujo y mockups. Convertí listas largas de "comportamiento" en tablas `situación → comportamiento`.
- **Referenciá colores por variable CSS** (`var(--label)`), no por hex suelto: así el documento sigue a la paleta si cambia.
- **Animá solo respuestas a una acción del lector** (hover, foco, abrir, navegar), con los tokens `motion` y dentro de `prefers-reduced-motion: no-preference`.

### Don't

- **No uses sombras pesadas.** Bordes finos y cambios de superficie son suficientes.
- **No mezcles paletas de color** (verde brillante, rojo Material, azul Bootstrap). El sistema tiene cuatro acentos apagados; cualquier color fuera de la paleta rompe la estética.
- **No uses pesos `700+` de DM Sans**, ni cursivas marcadas. La sobriedad se rompe rápido con tipografía dramática.
- **No anides callouts dentro de callouts** ni callouts dentro de tablas.
- **No uses iconos decorativos** (emojis, lucide a granel). El sistema confía en tipografía y color. Excepción: un emoji muy puntual dentro de un title de step (📦, 🎯) si suma información concreta.
- **No agregues efectos hover llamativos** en documentos estáticos. Si el doc es interactivo, los hovers deben ser cambios sutiles de borde o fondo, nunca elevación dramática.
- **No animes la entrada de contenido al scrollear**, ni uses rebotes, escalas, parallax o duraciones de más de 200ms.
- **No uses fondos blancos puros para el body** en pantalla. El `#F8F7F4` está calibrado para que `surface-card` (blanco) destaque por encima. (En impresión sí se usa blanco.)
- **No uses más de un `doc-title` por archivo.** Para sub-documentos, usar `part-header`.
- **No uses grises más claros que `label`** para texto, ni los `*-border` como color de texto.

## Checklist de conformidad

Antes de entregar o aprobar un documento con este sistema. Cada ítem remite a la sección que define
la regla (no la repite); entre paréntesis, el script que la verifica cuando hay uno.

- [ ] Estructura: un solo `doc-title`; secciones numeradas con `section-title` ([Jerarquía estructural](#jerarquía-estructural)).
- [ ] Tokens: colores, tipografía, espaciados, medidas de layout y breakpoints del front matter ([Colors](#colors), [Typography](#typography), [Layout](#layout); `check-design-tokens.sh`, `check-layout-tokens.mjs`).
- [ ] Índice completo: [Índice (TOC)](#índice-toc) en lectura lineal, hoja inferior con [etapas](#lectura-por-etapas) (`check-manual.mjs`).
- [ ] [Tables](#tables), [Callouts](#callouts), [Badges](#badges) y [Accordions](#accordion-bloques-colapsables) según su sección.
- [ ] Sin sombras ni redondeos fuera de [Elevation & Depth](#elevation--depth) y [Shapes](#shapes).
- [ ] Sin scroll horizontal de página a 360px; impresión según [Impresión](#impresión); movimiento según [Motion](#motion).
- [ ] Navegación: [índice](#índice-toc), [botón «Inicio»](#botón-inicio-volver-al-inicio), [mapa](#mapa-de-secciones), [píldora](#píldora-de-sección) y [copiar enlace](#copiar-enlace-a-una-sección) funcionan también en el visor final (`check-rendered.js`).
- [ ] [Sin marcas de novedad](#sin-marcas-de-novedad) (`check-manual.mjs`).
- [ ] [Glosario](#glosario): términos, definiciones y menciones (`check-manual.mjs`).
- [ ] [Puntos sobre capturas](#puntos-sobre-capturas): orden, numeración y anclaje (`check-manual.mjs`, `check-rendered.js`).
- [ ] [Comparación antes / después](#comparación-antes--después), [Menú de manuales](#menú-de-manuales) e [Ir al menú](#ir-al-menú) cuando se usan.
- [ ] [Referencias a secciones](#referencias-a-secciones) como links con su título (`check-manual.mjs`).

### Validación de la variante por etapas

`check-manual.mjs` valida el marcado de etapas y capítulos y los scripts incrustados;
`check-rendered.js` devuelve `stages` con lo que no cumple el contrato visible, y
`pnpm run test:user-manual` recorre en Chromium el comportamiento de [Lectura por etapas](#lectura-por-etapas)
(anchos, sidebar, teclado, impresión, enlaces) sobre el ejemplo y un visor local. Lo que queda manual:

- Recorrer el documento generado con contenido real: objetivo, estimación y recapitulación de cada
  etapa tienen sentido, y los simuladores siguen funcionando al cambiar de etapa.
- Comprobar carga directa, recarga, URL visible, copia y Atrás/Adelante **en el visor publicado**:
  localhost no prueba la sincronización ni las restricciones del host. Si no se puede acceder,
  informar exactamente qué quedó sin validar.

## Changelog

Cambios que alteran cómo se ve o se escribe un documento. Los documentos
viejos siguen funcionando: los nombres de clase no cambiaron.

### 2026-10-27

- **Boilerplate en archivos:** el CSS, el script de navegación y el esqueleto pasan a `assets/boilerplate/`;
  `scripts/build-manual.mjs --boilerplate` arma un documento nuevo y `build-manual.mjs <manual.html>` actualiza
  uno existente. `check-manual.mjs` compara el script de navegación con `navigation.js`.
- **Índice superior:** siempre en lectura lineal, también con pocas secciones (ya lo exigía `check-manual.mjs`).
- **Tokens de layout:** breakpoints `stage-menu` y `wide`, medidas con nombre en `layout` y
  `check-layout-tokens.mjs`; los paddings fuera de escala del selector de idioma, la barra de etapas y el
  índice de etapa pasan de 14px y 18px a 16px.
- **Etapas:** niveles de título para lectores de pantalla y textos de interfaz en el diccionario único.
- **Checklist:** cada ítem remite a la sección que define la regla, sin repetirla.

### 2026-10-26

- **Lectura por etapas:** variante para manuales largos con menú derecho, sidebar móvil,
  orientación y recapitulación, conservando el boilerplate lineal para documentos breves. CSS,
  script y plantilla en `assets/staged-reading/`, incrustados con `scripts/build-manual.mjs`.
  Capítulos opcionales dentro de cada etapa, contenido de la etapa activa en el menú, progreso de
  lectura, etapa anterior y siguiente en la recapitulación y grupos en la hoja del índice.
- **Navegación:** índice sin duplicación, título completo de sección actual, píldora anclada
  a la esquina y enlaces adaptados al contrato del visor, verificados en destino. El script de
  navegación suma puntos de extensión (`window.HeritageNavigation`, `window.HeritageViewer`,
  `heritage:visibility-change`, barras con `data-heritage-offset`), el adaptador de visor en
  `assets/viewer-adapters/`, el foco al destino al elegirlo en la hoja del índice y el destino de
  un salto como sección actual aunque no llegue a la línea activa.
- **Diagramas y alcance:** conservar representaciones legibles, evitar ampliación y librerías
  por defecto, y distinguir advertencias específicas de badges conceptuales repetitivos.

### 2026-10-02

- **Selector de idioma:** el cambio de idioma conserva la posición de lectura (el bloque que se veía arriba queda en el mismo lugar), en vez de volver al inicio de la sección.
- **Puntos sobre capturas:** la pista del pie dice «Hacé click en un número…» con mouse y «Tocá un número…» en pantallas táctiles (antes, siempre «Tocá»).
- **Accordions:** nunca hay dos abiertos en todo el documento (antes, uno por sección); también al abrirse por un salto del glosario.
- **Glosario:** cada término muestra superíndices con sus menciones en el documento; cada número lleva a la mención. Los saltos del glosario (término → definición, superíndice → mención) abren el accordion que contiene el destino y lo hacen latir 3 veces bajo el foco temporal, ajustado a su texto. Los destinos del final del documento (el glosario) también quedan centrados, y el foco no se corre cuando la palabra empieza a latir.
- **Puntos sobre capturas:** la lista de pasos va antes de la captura que la acompaña (antes iba después del `figcap`). Lo mismo para el texto con referencias en línea: va justo antes de la captura de sus puntos. Los puntos se numeran de arriba hacia abajo y de izquierda a derecha. Las referencias en el texto se mencionan en ese orden.
- **Referencias a secciones:** se escriben como link con el título de la sección; un link dentro de un paso o de una referencia ya no dispara el punto de la captura ni muestra "Ver en la captura".
- **Puntos sobre capturas:** una referencia dentro del texto de un paso lleva a su propio punto; antes el clic seguía hasta el paso y resaltaba también el punto de ese paso.

- **Componentes:** menú de manuales (`menu-stage` + `menu-link` sobre la captura real del menú de la app) y "Ir al menú" (`menu-back`, fijo arriba a la izquierda).
- **Navegación entre documentos:** script propio (`a[data-document-link]`) que abre en la página entera dentro de un visor embebido, lleva `?lang` y funde salida y llegada.
- **Idioma:** también se lee `?lang` de la URL del visor.
- **Saltos:** `landingOffset` deja la sección debajo de cualquier control fijo que tape la columna (selector o "Ir al menú").

### 2026-10-01

- **Componentes:** mapa de secciones (`section-rail`): marcas laterales fijas, una por sección, con vista previa al pasar el mouse o enfocar, efecto lupa sobre las marcas vecinas, sección actual resaltada y el mismo scroll que el índice. Lo arma el script de navegación.
- **Mapa de secciones:** progreso de lectura en la marca actual y atajos al pie de la vista previa (sin estado de lectura entre visitas).
- **Componentes:** píldora de sección con índice en hoja inferior (todos los anchos), copiar enlace a una sección, glosario con tarjeta (`a.term` + `dl.glossary`), puntos sobre capturas (`hotspot`) y comparación antes / después (`compare`).
- **Teclado:** `Alt`/`⌥` + `↑` `↓` cambia de sección, `Alt`/`⌥` + `I` va al índice, `Escape` cierra las vistas previas.
- **Tokens:** tipografía `rail-preview-title` y breakpoint `rail` (1024px).
- **Mockups:** modificador `.mockup--mobile` para capturas de celular y leyenda `.figcap`.
- **Puntos sobre capturas:** `data-target` (+ `data-target-text`) los ancla a un elemento de la captura; el runtime los ubica después de cada ajuste y no se corren con el ancho del lector.
- **Origen del código:** línea `Código: <rama> @ <commit>` en el pie del documento (`doc-footer`), con link al commit en GitHub, y metas `heritage:source-*` en documentos que describen código.
- **Quitado:** marcas de novedad (`data-change`, badges "Nuevo" / "Actualizado", "Novedades" en el `doc-meta`). Los documentos no marcan cambios.

### 2026-09-28

- **Motion:** nuevos tokens `motion` (`duration-fast`, `duration-base`, `easing-standard`) con sus variables `--motion-*`, verificadas por `check-design-tokens.sh`. Sección nueva con qué se anima y qué no.
- **Componentes:** botón "Inicio" (volver al inicio) y script de navegación: scroll suave del índice y del botón, alineación de la sección completa y corrección por contenido diferido (evento `heritage:before-scroll`).
- **Transiciones:** subrayado de links, apertura del accordion y aparición del botón "Inicio", todo bajo `prefers-reduced-motion: no-preference` y apagado en impresión.

### 2026-09-27

- **Contraste:** `label` pasa de `#888888` a `#6B6B6B` y `syntax-comment` de `#64748B` a `#7C8BA1` para cumplir WCAG AA. Nuevos tokens `link`, `focus-ring` y `border-neutral`.
- **Tipografía:** `table-header` y `badge` suben de 10px a 11px (nuevo piso). Nuevo token `accordion-title` (16/600): el `summary` deja de usar el tamaño de `section-title`. Stack de fallback de sistema para ambas familias.
- **Spacing:** la escala suma 10, 32 y 56px y se renombra en orden; los paddings fuera de escala se ajustan (callouts `12px 16px`, example box `16px 20px`, accordion `12px 16px`, code inline `1px 6px`, indentación de listas `24px`).
- **Componentes nuevos:** índice (TOC), estilos de link, `mockup-body` y `.table-wrap`.
- **Boilerplate:** HTML semántico (`<h1>`, `<h2>`, `<section>`, `<ol>`), variables CSS con el mismo nombre que los tokens, CSS de todos los componentes, foco visible, breakpoint mobile e impresión.
- **Tooling:** `scripts/check-design-tokens.sh` (en la skill user-manual) verifica que front matter y `:root` no se desalineen.

### 2026-06-26

- Componente accordion para documentos densos.

### 2026-05-25

- Versión inicial del sistema.

---

### Boilerplate HTML mínimo

El boilerplate no se copia de este documento: vive en `assets/boilerplate/` y lo arma
`scripts/build-manual.mjs`, así cada manual parte de los mismos archivos que validan los
scripts y las pruebas.

| Archivo | Qué tiene |
|---|---|
| `assets/boilerplate/skeleton.html` | Esqueleto del documento: `<head>` con fuentes, `doc-header`, una sección de ejemplo, `doc-footer`, botón «Inicio», mapa, píldora, hoja del índice y el script que abre los accordions al imprimir. |
| `assets/boilerplate/base.css` | CSS de **todos** los componentes, con los tokens como variables en `:root`; los que no se usen pueden quedarse. |
| `assets/boilerplate/navigation.js` | Script de navegación e interacciones (índice, mapa, píldora, «Inicio», atajos, copiar enlace, glosario, puntos sobre capturas, comparación antes/después). |

- `node scripts/build-manual.mjs --boilerplate <manual.html>` escribe el esqueleto con el CSS y el
  script incrustados: es el punto de partida de un documento nuevo.
- `node scripts/build-manual.mjs <manual.html>` actualiza un manual existente: reemplaza su script
  de navegación por el actual y, según corresponda, los assets de [lectura por etapas](#lectura-por-etapas)
  y del adaptador de visor. `check-manual.mjs` avisa cuando la copia de un manual quedó vieja.
- El `:root` de `base.css` declara la paleta y los tokens de motion del front matter
  (`check-design-tokens.sh`); sus breakpoints, espaciados y medidas de layout salen de los tokens
  `breakpoints`, `spacing` y `layout` (`node scripts/check-layout-tokens.mjs`).
- Sin JavaScript el documento se lee completo: solo faltan los atajos.

### Snippets de componentes

Markup de referencia para cada componente. Los nombres de clase son contrato:
otras skills (por ejemplo `user-manual`) dependen de ellos.

```html
<!-- Selector de idioma: primer hijo del <body> (solo en documentos con versión en portugués) -->
<div class="lang-switch" role="radiogroup" aria-label="Idioma">
  <button type="button" role="radio" data-lang="es" lang="es" aria-checked="true">Español</button>
  <button type="button" role="radio" data-lang="pt" lang="pt-BR" aria-checked="false">Português</button>
</div>
<!-- doc-header … secciones … doc-footer, una sola vez y en español -->
<!-- …botón Inicio, mapa, píldora y hoja del índice… -->
<script type="application/json" id="heritage-translations">
{"pt": {"htmlLang": "pt-BR", "title": "[Título en portugués]",
  "document": {"[Texto en español]": "[Texto em português]"},
  "captures": {"[Texto de la app en español]": "[Texto da app em pt-BR]"},
  "captureTemplates": {}}}
</script>
<script>
// Idioma: el documento se escribe en español y se traduce en la misma página con la tabla de
// heritage-translations (textos y atributos), sin duplicar el markup. Siempre abre en español;
// en portugués solo si la URL lo pide (?lang=pt, la propia o la del visor). No se guarda ninguna preferencia.
(function () {
  var source = document.getElementById('heritage-translations');
  var tables = source ? JSON.parse(source.textContent) : {};
  var ATTRIBUTES = ['aria-label', 'title', 'alt', 'placeholder', 'data-tooltip', 'data-target', 'data-target-text'];
  // Nunca se traducen: código, estilos, scripts y el selector (cada opción ya está en su idioma).
  var SKIPPED = 'script, style, code, template, .lang-switch';
  var spanishLang = document.documentElement.lang || 'es';
  var spanishTitle = document.title;
  // Español de cada texto o atributo traducido, para volver; lo que no está en la tabla no se toca.
  var spanishTexts = new WeakMap();
  var spanishAttributes = new WeakMap();
  var current = 'es';
  function lookup(dictionary, value) {
    var key = value.trim();
    if (!dictionary || !key || !Object.prototype.hasOwnProperty.call(dictionary, key)) return null;
    return value.replace(key, function () { return dictionary[key]; });
  }
  // Portugués → español, para lo que se copió ya traducido (la hoja del índice copia el índice al iniciar).
  var reverseTables = {};
  function reverseOf(kind) {
    if (!reverseTables[kind]) {
      reverseTables[kind] = {};
      Object.keys(tables).forEach(function (language) {
        var dictionary = tables[language][kind] || {};
        Object.keys(dictionary).forEach(function (spanish) {
          if (!Object.prototype.hasOwnProperty.call(reverseTables[kind], dictionary[spanish])) reverseTables[kind][dictionary[spanish]] = spanish;
        });
      });
    }
    return reverseTables[kind];
  }
  function translate(root, kind) {
    var dictionary = current === 'es' ? reverseOf(kind) : (tables[current] || {})[kind];
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (var node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.parentElement && node.parentElement.closest(SKIPPED)) continue;
      if (spanishTexts.has(node)) {
        // Ya traducido: vuelve a su español y, si el idioma nuevo no es español, se traduce de nuevo desde ahí.
        node.nodeValue = spanishTexts.get(node);
        spanishTexts.delete(node);
      }
      var translated = lookup(dictionary, node.nodeValue);
      if (translated === null) continue;
      if (current !== 'es') spanishTexts.set(node, node.nodeValue);
      node.nodeValue = translated;
    }
    root.querySelectorAll('[' + ATTRIBUTES.join('],[') + ']').forEach(function (element) {
      if (element.closest(SKIPPED)) return;
      var saved = spanishAttributes.get(element) || {};
      ATTRIBUTES.forEach(function (name) {
        if (!element.hasAttribute(name)) return;
        if (Object.prototype.hasOwnProperty.call(saved, name)) {
          element.setAttribute(name, saved[name]);
          delete saved[name];
        }
        var value = element.getAttribute(name);
        var translated = lookup(dictionary, value);
        if (translated === null) return;
        if (current !== 'es') saved[name] = value;
        element.setAttribute(name, translated);
      });
      spanishAttributes.set(element, saved);
    });
  }
  function set(language) {
    current = tables[language] ? language : 'es';
    translate(document.body, 'document');
    var table = tables[current];
    document.documentElement.lang = table ? table.htmlLang || current : spanishLang;
    document.title = table && table.title ? table.title : spanishTitle;
    document.documentElement.setAttribute('data-language', current);
    document.dispatchEvent(new CustomEvent('heritage:language-change', { detail: { language: current } }));
  }
  window.HeritageLanguage = {
    get current() { return current; },
    set: set,
    // Las capturas se traducen al renderizarse (embed-app-frames.mjs) con la parte "captures".
    translate: translate,
    captureTemplate: function (name) {
      var table = tables[current];
      return (table && table.captureTemplates && table.captureTemplates[name]) || null;
    }
  };
  // Dentro de un visor con iframe cuenta también la URL del visor: carga el iframe sin su ?lang.
  function requestedLanguage() {
    var own = new URLSearchParams(location.search).get('lang');
    if (own) return own;
    try { return window.parent !== window ? new URLSearchParams(window.parent.location.search).get('lang') : null; } catch (error) { return null; }
  }
  var requested = requestedLanguage();
  if (requested && tables[requested]) set(requested);
  else document.documentElement.setAttribute('data-language', 'es');
})();
</script>
<!-- …y después el script de navegación -->

<!-- Ir al menú: primer hijo del <body> (antes del selector de idioma), en documentos que se abren
     desde un menú de manuales. href = URL pública del menú (en un visor, su URL para compartir). -->
<a class="menu-back" href="[URL pública del menú]" target="_top" data-document-link><span aria-hidden="true">←</span> Ir al menú</a>

<!-- Menú de manuales: la captura real del menú de la app (app-frame) y un link por tarjeta, anclado con
     data-target + data-target-text. Tarjeta con manual: href a su URL pública (+ #slug para una sección).
     Sin manual: aria-disabled, sin href (el script pone su ícono en gris). Los links empiezan ocultos; el script los ubica. -->
<div class="mockup mockup--mobile">
  <div class="mockup-bar"><div class="mockup-dots" aria-hidden="true"><span></span><span></span><span></span></div><span class="mockup-url">/[ruta del menú]</span></div>
  <div class="menu-stage">
    <div class="app-frame" data-cap="[captura del menú]"></div>
    <a class="menu-link" href="[URL pública del manual]" target="_top" data-document-link data-target=".[tarjeta]" data-target-text="[Texto de la tarjeta]" aria-label="Abrir el manual de [Herramienta]" hidden></a>
    <a class="menu-link" role="link" aria-disabled="true" tabindex="0" data-document-link data-target=".[tarjeta]" data-target-text="[Texto de la tarjeta]" aria-label="[Herramienta]: manual en preparación" hidden></a>
  </div>
</div>
<div class="figcap">[Qué muestra la captura y quién ve cada tarjeta] (datos de ejemplo).</div>
<!-- Leyenda: qué hace una tarjeta normal y qué significa una con el ícono en gris (y adónde lleva cada excepción). -->

<!-- Script de navegación entre documentos: después del script de idioma (si lo hay), en el menú y en
     cada documento con "Ir al menú". Es independiente del script de navegación del documento. -->
<script>
// Navegación entre documentos Heritage: links a otros documentos publicados (menú de manuales ↔ manuales)
// que abren en la página entera también dentro de un visor con iframe, llevan el idioma que se lee,
// funden la salida y la llegada y, en un menú, ubican cada link sobre su tarjeta de la captura.
(function () {
  var root = document.documentElement;
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  // Lo que dura el desvanecimiento de salida del CSS (motion.duration-base).
  var LEAVE_MS = 200;
  function viewerDocument() {
    try { return window.parent !== window ? window.parent.document : null; } catch (error) { return null; }
  }
  // El idioma viaja en la URL de destino (?lang=pt); el español no lleva parámetro.
  function withLanguage(href) {
    var language = window.HeritageLanguage ? window.HeritageLanguage.current : 'es';
    var url = new URL(href, location.href);
    if (language !== 'es') url.searchParams.set('lang', language);
    else url.searchParams.delete('lang');
    return url.href;
  }
  // El sandbox de un visor puede no dejar que el iframe navegue la página de arriba (ni con target="_top"); un link
  // creado en el documento del visor, que es del mismo origen, sí la navega.
  function go(href) {
    var viewer = viewerDocument();
    if (!viewer) { location.href = href; return; }
    var link = viewer.createElement('a');
    link.href = href;
    link.hidden = true;
    viewer.body.appendChild(link);
    link.click();
    link.remove();
  }
  document.addEventListener('click', function (event) {
    var link = event.target.closest ? event.target.closest('a[data-document-link]') : null;
    if (!link) return;
    if (link.getAttribute('aria-disabled') === 'true') { event.preventDefault(); return; }
    var href = withLanguage(link.href);
    // Con modificadores (pestaña nueva) decide el navegador, con el idioma ya puesto en el link.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) { link.href = href; return; }
    event.preventDefault();
    if (reduceMotion.matches) { go(href); return; }
    root.classList.add('is-leaving');
    setTimeout(function () { go(href); }, LEAVE_MS);
  });
  // Al volver con "atrás" (bfcache) el documento no queda desvanecido.
  window.addEventListener('pageshow', function () { root.classList.remove('is-leaving'); });
  // Llegada desde otro documento del mismo visor: aparece con un fundido (una recarga no lo repite).
  try {
    var page = viewerDocument() || document;
    var from = page.referrer ? new URL(page.referrer) : null;
    if (from && from.origin === page.location.origin && from.pathname !== page.location.pathname && !reduceMotion.matches) {
      root.classList.add('is-arriving');
      document.body.addEventListener('animationend', function done(event) {
        if (event.target !== document.body) return;
        root.classList.remove('is-arriving');
        document.body.removeEventListener('animationend', done);
      });
    }
  } catch (error) { /* referrer ilegible: llega sin fundido */ }
  // Documento de una sola pantalla (menú de manuales), sin el script de navegación del documento: el
  // selector de idioma cambia en el lugar, con el mismo fundido; no hay sección a la que volver.
  var languageSwitch = document.querySelector('.lang-switch');
  if (languageSwitch && window.HeritageLanguage && !document.querySelector('.section-rail')) {
    var markChosen = function () {
      languageSwitch.querySelectorAll('[data-lang]').forEach(function (option) {
        option.setAttribute('aria-checked', String(option.getAttribute('data-lang') === window.HeritageLanguage.current));
      });
    };
    markChosen();
    languageSwitch.querySelectorAll('[data-lang]').forEach(function (option) {
      option.addEventListener('click', function () {
        var chosen = option.getAttribute('data-lang');
        if (chosen === window.HeritageLanguage.current) return;
        var change = function () {
          window.HeritageLanguage.set(chosen);
          markChosen();
          var query = new URLSearchParams(location.search);
          if (chosen === 'es') query.delete('lang');
          else query.set('lang', chosen);
          var search = query.toString() ? '?' + query.toString() : '';
          history.replaceState(history.state, '', location.pathname + search + location.hash);
        };
        if (document.startViewTransition && !reduceMotion.matches) document.startViewTransition(change);
        else change();
      });
    });
  }
  // Menú: la tarjeta de la captura crece al pasar el puntero o enfocar su link (1.05: entre tarjetas hay
  // pocos píxeles). La regla vive dentro de cada captura, porque la tarjeta está en su shadow root.
  // Tarjeta sin manual: su ícono (imagen o dibujo) en gris y al 45%, para que se lea como no disponible.
  var CARD_ACTIVE_RULES = '[data-menu-card]{transform-origin:center;}[data-menu-card][data-menu-active]{scale:1.05;}'
    + '[data-menu-card][data-menu-pending] :is(img,svg,picture,canvas){filter:grayscale(1);opacity:0.45;}'
    + '@media (prefers-reduced-motion:no-preference){[data-menu-card]{transition:scale var(--motion-duration-fast) var(--motion-easing-standard);}}';
  function setActive(link, active) {
    if (!link.__menuCard || link.getAttribute('aria-disabled') === 'true') return;
    link.classList.toggle('is-active', active);
    if (active) link.__menuCard.setAttribute('data-menu-active', '');
    else link.__menuCard.removeAttribute('data-menu-active');
  }
  document.querySelectorAll('.menu-link').forEach(function (link) {
    link.addEventListener('pointerenter', function () { setActive(link, true); });
    link.addEventListener('pointerleave', function () { if (document.activeElement !== link) setActive(link, false); });
    link.addEventListener('focus', function () { setActive(link, true); });
    link.addEventListener('blur', function () { setActive(link, false); });
  });
  // Cada .menu-link[data-target] cubre su tarjeta después de cada ajuste de la captura
  // (evento heritage:frame-fit del runtime de capturas), también al cambiar de idioma.
  document.addEventListener('heritage:frame-fit', function (event) {
    var host = event.target;
    var stage = host.closest && host.closest('.menu-stage');
    if (!stage || !host.shadowRoot) return;
    if (!host.shadowRoot.querySelector('style[data-menu-rules]')) {
      var rules = document.createElement('style');
      rules.setAttribute('data-menu-rules', '');
      rules.textContent = CARD_ACTIVE_RULES;
      host.shadowRoot.appendChild(rules);
    }
    var stageBox = stage.getBoundingClientRect();
    stage.querySelectorAll('.menu-link[data-target]').forEach(function (link) {
      var text = link.getAttribute('data-target-text');
      var target = Array.prototype.filter.call(host.shadowRoot.querySelectorAll(link.getAttribute('data-target')), function (element) {
        return !text || element.textContent.trim() === text;
      })[0];
      link.hidden = !target;
      if (!target) return;
      // Al cambiar de idioma la captura se vuelve a llenar: la tarjeta es otro nodo y hereda el estado.
      if (link.__menuCard && link.__menuCard !== target && link.__menuCard.hasAttribute('data-menu-active')) target.setAttribute('data-menu-active', '');
      link.__menuCard = target;
      target.setAttribute('data-menu-card', '');
      if (link.getAttribute('aria-disabled') === 'true') target.setAttribute('data-menu-pending', '');
      // Medida sin la escala del hover, para que el link cubra la tarjeta en reposo.
      var active = target.hasAttribute('data-menu-active');
      if (active) target.removeAttribute('data-menu-active');
      var box = target.getBoundingClientRect();
      if (active) target.setAttribute('data-menu-active', '');
      link.style.left = (box.left - stageBox.left) + 'px';
      link.style.top = (box.top - stageBox.top) + 'px';
      link.style.width = box.width + 'px';
      link.style.height = box.height + 'px';
    });
  });
})();
</script>

<!-- Índice (TOC): después del doc-header, solo con 5+ secciones -->
<nav class="toc" aria-labelledby="toc-label">
  <div class="toc-label" id="toc-label">Contenido</div>
  <ol>
    <li><a href="#[slug]"><span class="toc-num">01</span>[Título de la sección]</a></li>
    <li><a href="#[otro-slug]"><span class="toc-num">02</span>[Título de la sección]</a></li>
  </ol>
</nav>

<!-- Part header -->
<div class="part-header">
  <div class="part-header-label">Parte B</div>
  <h2 class="part-header-title">[Título de la parte]</h2>
</div>

<!-- Callout -->
<div class="callout c-warn"><strong>Ojo:</strong> …</div>

<!-- Tabla -->
<div class="table-wrap">
  <table>
    <thead><tr><th scope="col">Situación</th><th scope="col">Comportamiento</th><th scope="col">Estado</th></tr></thead>
    <tbody><tr><td>…</td><td>…</td><td><span class="badge b-green">✓ Sí</span></td></tr></tbody>
  </table>
</div>

<!-- Steps -->
<ol class="steps">
  <li class="step-item">
    <span class="step-circle" aria-hidden="true">1</span>
    <div class="step-body"><div class="step-label">[Acción]</div><div class="step-desc">[Detalle]</div></div>
  </li>
</ol>

<!-- Code block -->
<div class="code-block"><pre><span class="c-comment">// comentario</span>
<span class="c-key">const</span> total = <span class="c-fn">sum</span>(<span class="c-num">1</span>, <span class="c-num">2</span>);</pre></div>

<!-- Mockup -->
<div class="mockup">
  <div class="mockup-bar">
    <div class="mockup-dots" aria-hidden="true"><span></span><span></span><span></span></div>
    <span class="mockup-url">app.ejemplo.com/ruta</span>
  </div>
  <div class="mockup-body">…</div>
</div>

<!-- Example box -->
<div class="example-box">
  <div class="example-label">Ejemplo práctico</div>
  <p>…</p>
</div>

<!-- Flujo con pills -->
<div class="flow">
  <span class="pill pill-stale"><del>$15</del></span>
  <span class="flow-arrow" aria-hidden="true">→</span>
  <span class="pill pill-success">$20</span>
</div>

<!-- Accordion -->
<details class="acc">
  <summary><span class="acc-num">Reglas</span>[Título del bloque]</summary>
  <div class="acc-body"><p>…</p></div>
</details>

<!-- Divider -->
<hr class="divider">

<!-- Botón "Inicio": justo antes de </body>, junto con el script de navegación del boilerplate.
     El doc-header lleva id="top" y tabindex="-1". -->
<a class="back-to-top" href="#top" aria-label="Volver al inicio" hidden><span aria-hidden="true">↑</span> Inicio</a>

<!-- Mapa de secciones: vacío, junto al botón "Inicio". El script de navegación lo arma
     con una marca por cada section.section que tenga section-title con id. -->
<nav class="section-rail" aria-label="Mapa de secciones" hidden></nav>

<!-- Píldora de sección + hoja del índice: junto al mapa. El script completa ambas. -->
<button class="section-pill" type="button" aria-haspopup="dialog" aria-controls="toc-sheet" hidden><span class="section-pill-num"></span><span class="section-pill-title"></span></button>
<dialog class="toc-sheet" id="toc-sheet" aria-labelledby="toc-sheet-label">
  <div class="toc-sheet-body">
    <div class="toc-sheet-head"><div class="toc-label" id="toc-sheet-label">Contenido</div><button class="toc-sheet-close" type="button">Cerrar</button></div>
  </div>
</dialog>

<!-- URL pública para "Copiar enlace" cuando el documento se ve dentro de un iframe (en <head>) -->
<meta name="heritage:share-url" content="[URL del documento en el visor]">

<!-- Glosario: término en la prosa + definición única -->
<a class="term" href="#g-termino">término</a>
<dl class="glossary">
  <dt id="g-termino">Término</dt>
  <dd>[Definición en una o dos oraciones]</dd>
</dl>

<!-- Puntos sobre una captura + pasos y referencia vinculados: los pasos van ANTES de la captura -->
<ol class="steps">
  <li class="step-item" data-hotspot="1">…</li>
</ol>
<div class="mockup">
  <div class="mockup-bar">…</div>
  <div class="hotspot-stage">
    <div class="app-frame" data-cap="[captura]"></div>
    <span class="hotspot" data-hotspot="1" data-target="button" data-target-text="[Texto del botón]" style="--x:12%;--y:30%" aria-hidden="true">1</span>
  </div>
</div>
<div class="figcap">[Qué muestra la captura]</div>
<p>Tocá el botón <span class="hotspot-ref" data-hotspot="1"><span class="visually-hidden">punto </span>1</span>.</p>

<!-- Comparación antes / después -->
<div class="compare">
  <div class="compare-stage">
    <div class="compare-before"><div class="app-frame" data-cap="[antes]" aria-label="Captura de pantalla: antes, …"></div></div>
    <div class="compare-after"><div class="app-frame" data-cap="[después]" aria-label="Captura de pantalla: después, …"></div></div>
    <div class="compare-handle" aria-hidden="true"></div>
    <input class="compare-range" type="range" min="0" max="100" value="50" aria-label="Comparar antes y después">
  </div>
  <div class="compare-labels"><span>Antes</span><span>Después</span></div>
</div>
```

Componentes que se cargan de forma diferida (imágenes, capturas embebidas) y
cambian de alto al renderizarse escuchan `heritage:before-scroll`: el script de
navegación lo dispara con `event.detail.target` antes de medir el destino, para
que rendericen todo lo que está por encima.

```js
document.addEventListener('heritage:before-scroll', (event) => {
  // renderizar los elementos diferidos que están antes de event.detail.target
});
```
