---
name: mobile-first-responsive-layout
description: "Guia para aplicar unidades y patrones mobile-first en CSS/SCSS: usa unidades fluidas (%, rem, vw), evita valores fijos, y ajusta breakpoints y escalas responsivas al crear o modificar layouts, grids o componentes."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "css, scss, responsive, mobile-first, layout"
  command: "/mobile-first-responsive-layout"
---

# Mobile First Responsive Units

## Overview

Esta skill define criterios claros para usar unidades responsivas y mobile-first en CSS/SCSS. Ayuda a mantener layouts fluidos, escalas tipograficas consistentes y breakpoints bien justificados.

## Cuando usar esta skill

- Al crear o modificar estilos en `.scss` o `.module.scss`.
- Al tocar layouts, grids, espaciados o tipografia en componentes.
- Al definir o ajustar breakpoints y reglas responsivas.

## Guidelines

### Unidades y escalas
- Tipografia: usar `rem` (base del documento) y evitar `px` fijos.
- Espaciados: preferir `rem` o tokens de spacing; evitar valores rigidos.
- Anchos: usar `%`, `max-width`, `min()`, `max()` o `clamp()` para fluidos.
- Alturas: evitar alturas fijas; usar `min-height` cuando sea necesario.
- Imagenes/medios: usar `width: 100%` con `height: auto` o `aspect-ratio`.

### Mobile-first
- Definir estilos base para mobile primero.
- Agregar breakpoints solo cuando un cambio sea necesario.
- Mantener la especificidad baja y evitar overrides en cascada.

### Breakpoints y contenedores
- Usar tokens o constantes de breakpoints del proyecto.
- Preferir `max-width` en contenedores y padding responsivo.
- Evitar media queries duplicadas y hardcodeadas.

## Workflow recomendado

1) Detecta el layout principal y su escala (tipografia, espacios, ancho).
2) Define el estilo base para mobile con unidades fluidas.
3) Agrega breakpoints solo si el contenido lo requiere.
4) Valida en viewport chico, mediano y grande.

## Ejemplos

### Espaciado y tipografia mobile-first
```scss
.card {
  padding: 1rem;
  font-size: 1rem;
  max-width: 100%;
}

@media (min-width: $bp-medium) {
  .card {
    padding: 1.5rem;
    font-size: 1.125rem;
    max-width: 36rem;
  }
}
```

### Ancho fluido con clamp
```scss
.title {
  font-size: clamp(1.25rem, 2vw + 1rem, 2rem);
}
```

## No hacer

- No usar `px` fijos en tipografia o spacing sin justificar.
- No definir breakpoints por dispositivo; usar necesidad de contenido.
- No usar alturas fijas en contenedores que deban crecer.
