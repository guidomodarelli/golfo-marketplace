# Pantallas y páginas

Cómo lograr una UI linda y con vida sin atarla a una estética. Si el proyecto tiene design system, sus tokens y componentes mandan y esta referencia solo agrega lo que falte.

Qué mostrar en cada estado es de `ui-ux-flow-patterns`; elementos nativos, teclado y foco, de `semantic-html-a11y`; unidades y breakpoints, de `mobile-first-responsive-layout`. Cargarlas cuando el cambio lo pida.

## Índice

1. [Carácter y tokens](#1-carácter-y-tokens)
2. [Jerarquía y tipografía](#2-jerarquía-y-tipografía)
3. [Tablas y listas](#3-tablas-y-listas)
4. [Movimiento](#4-movimiento)
5. [Tema y contraste](#5-tema-y-contraste)
6. [Mobile](#6-mobile)
7. [Antes y después](#7-antes-y-después)
8. [Verificar](#8-verificar)

## 1. Carácter y tokens

- Definir tokens por rol, no por valor: `--surface`, `--text`, `--text-muted`, `--border`, `--accent` y uno por estado (`--done`, `--warning`, `--error`). Espaciado, radios y tiempos también son tokens.
- Elegir la paleta desde el proyecto. Un producto contable, un juego y un panel de infraestructura no deberían compartir el mismo violeta. Gradientes, texturas e ilustraciones están permitidos, siempre que el contraste se siga midiendo.
- Los componentes solo usan tokens. Cambiar el carácter no toca los componentes.

## 2. Jerarquía y tipografía

- Una sola cosa domina cada pantalla. El ojo tiene que saber a dónde ir primero sin leer.
- Escala corta con saltos visibles y tamaños fluidos con `clamp()`. Textos largos con `max-width` cerca de `65ch`.
- Cifras con `font-variant-numeric: tabular-nums`, para que las columnas no bailen.
- Respetar la tipografía del proyecto. Si no hay, la pila del sistema es mejor que una web font que demora el primer render.

## 3. Tablas y listas

- Títulos claros, filas con aire y separadores suaves en vez de una grilla completa. Números a la derecha.
- Cada estado lleva ícono y palabra, nunca solo un punto de color.
- En angosto, la tabla pasa a tarjetas que conservan cada dato con su título. Si cambia el `display` de una tabla, reponer los roles (`role="table"`, `row`, `cell`), porque algunos navegadores los pierden.
- Listas con jerarquía por sangría y tamaño, no solo por color.

## 4. Movimiento

Cada animación explica qué pasó: de dónde viene algo, qué cambió, a dónde fue. Si no explica nada, sobra.

- Acompaña una espera real, nunca la crea. Sin retrasos para mostrar datos que ya están. Los bucles solo mientras hay trabajo, y se detienen al terminar.
- Cambios de estado entre 120 y 240 ms, salidas más cortas que entradas. Animar `transform` y `opacity`, no propiedades que recalculan el layout.
- Escribir el movimiento dentro de `@media (prefers-reduced-motion: no-preference)`. Sin esa preferencia, el estado final aparece igual: se quita el desplazamiento, no la información.
- Con movimiento reducido, reemplazar un spinner por un texto como «Cargando…».

## 5. Tema y contraste

- Declarar `color-scheme: light dark` y redefinir los tokens en `prefers-color-scheme: dark`. Si el proyecto cambia de tema con un atributo como `data-theme`, seguir ese mecanismo. El tema oscuro no es el claro invertido: bajar saturación y separar capas con superficies.
- Contraste AA en los dos temas: texto 4.5:1, texto grande 3:1, y bordes de controles e íconos con significado 3:1.
- El color nunca es el único portador de información.
- Medir, no estimar. Los analizadores no pueden evaluar texto sobre un gradiente o una imagen, así que esos casos se miden a mano.

## 6. Mobile

- Sin scroll horizontal de página a 320 CSS px. Una tabla ancha no se fuerza: se reacomoda.
- Controles táctiles de al menos 24 px, y mejor 44 px, sin depender de `:hover` para mostrar información.
- Probar el contenido más largo real, no el del mockup.

## 7. Antes y después

Antes: se ve bien en un solo monitor y en un solo tema.

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Estado del release</title>
<style>
  body { font-family: Arial, sans-serif; background: #fff; margin: 40px; }
  .wrap { width: 900px; }
  h1 { font-size: 18px; color: #bbb; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 8px; border: 1px solid #ddd; color: #aaa; text-align: left; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; animation: pulse 1s infinite; }
  .ok { background: #7ed387; } .warn { background: #f0c460; } .err { background: #f47676; }
  @keyframes pulse { 50% { opacity: .2; transform: scale(1.6); } }
</style>
</head>
<body>
<div class="wrap">
  <h1>Estado del release</h1>
  <table>
    <tr><th>Servicio</th><th>Versión</th><th></th><th>Duración</th></tr>
    <tr><td>api-gateway</td><td>3.14.2</td><td><span class="dot ok"></span></td><td>12s</td></tr>
    <tr><td>search-indexer</td><td>5.0.0-rc.1</td><td><span class="dot warn"></span></td><td>1m 03s</td></tr>
    <tr><td>legacy-importer</td><td>0.4.1</td><td><span class="dot err"></span></td><td>7s</td></tr>
  </table>
</div>
</body>
</html>
```

Qué falla: ancho fijo que rompe en mobile, contraste insuficiente, un tema solo, un estado que solo se distingue por color y un bucle infinito que ignora el movimiento reducido.

Después: tokens por rol, los dos temas, tabla que pasa a tarjetas y un cambio de estado que se explica solo. Tomar la mecánica, no el aspecto: la paleta y la composición de este ejemplo no se copian, porque cada proyecto define las suyas.

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Estado del release</title>
<style>
  /* El carácter del proyecto vive acá. Reemplazar estos valores: solo muestran la forma. */
  :root {
    color-scheme: light dark;
    --surface: #f6f3ec;
    --surface-raised: #fffdf8;
    --text: #1d2a2e;
    --text-muted: #4f5e64;
    --border: #d8d2c4;
    --accent: #0a6c6c;
    --on-accent: #ffffff;
    --done: #1b6637;
    --done-surface: #e2f2e6;
    --changed: #1b56a2;
    --changed-surface: #e2ecfa;
    --skipped: #4f5e64;
    --skipped-surface: #eae8e1;
    --warning: #734d00;
    --warning-surface: #fbefcf;
    --error: #a12727;
    --error-surface: #fbe5e2;
    --space-1: 0.25rem;
    --space-2: 0.5rem;
    --space-3: 1rem;
    --space-4: 1.5rem;
    --space-5: clamp(1.5rem, 5vw, 3rem);
    --radius: 0.75rem;
    --state-duration: 220ms;
    --state-easing: cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --surface: #11181b;
      --surface-raised: #1a2327;
      --text: #e9eef0;
      --text-muted: #a9b6bc;
      --border: #303d43;
      --accent: #63cdbe;
      --on-accent: #06211d;
      --done: #8fe0a8;
      --done-surface: #15301f;
      --changed: #a2c6ff;
      --changed-surface: #16294a;
      --skipped: #b3bfc4;
      --skipped-surface: #252f33;
      --warning: #f2cb74;
      --warning-surface: #36290c;
      --error: #ffaaa3;
      --error-surface: #431a18;
    }
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    background: var(--surface);
    color: var(--text);
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.5;
  }

  main {
    max-width: 60rem;
    margin-inline: auto;
    padding: var(--space-5) var(--space-3);
  }

  header::after {
    content: '';
    display: block;
    height: 0.25rem;
    margin-block: var(--space-3) var(--space-4);
    border-radius: var(--radius);
    background: linear-gradient(90deg, var(--accent), var(--changed), var(--warning));
  }

  h1 {
    margin: 0;
    font-size: clamp(1.75rem, 1.2rem + 2.5vw, 2.75rem);
    line-height: 1.1;
    letter-spacing: -0.02em;
  }

  .lead { margin: var(--space-2) 0 0; color: var(--text-muted); max-width: 65ch; }

  .summary {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: 0 0 var(--space-4);
    padding: 0;
    list-style: none;
  }

  .summary li {
    flex: 1 1 7.5rem;
    padding: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-raised);
  }

  .summary strong { display: block; font-size: 1.75rem; line-height: 1.1; font-variant-numeric: tabular-nums; }

  .card { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-raised); overflow: hidden; }

  table { width: 100%; border-collapse: collapse; }

  th, td { padding: var(--space-3); text-align: left; vertical-align: middle; }

  th { color: var(--text-muted); font-size: 0.875rem; font-weight: 600; }

  tbody tr { border-top: 1px solid var(--border); }

  .number { text-align: right; font-variant-numeric: tabular-nums; }

  .service { font-weight: 600; overflow-wrap: anywhere; }

  .status {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-1) var(--space-2);
    border-radius: 999px;
    font-size: 0.875rem;
    font-weight: 600;
    white-space: nowrap;
  }

  .status[data-status='done'] { color: var(--done); background: var(--done-surface); }
  .status[data-status='changed'] { color: var(--changed); background: var(--changed-surface); }
  .status[data-status='skipped'] { color: var(--skipped); background: var(--skipped-surface); }
  .status[data-status='warning'] { color: var(--warning); background: var(--warning-surface); }
  .status[data-status='error'] { color: var(--error); background: var(--error-surface); }

  button {
    min-height: 2.75rem;
    padding: var(--space-2) var(--space-3);
    border: 0;
    border-radius: var(--radius);
    background: var(--accent);
    color: var(--on-accent);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }

  button:focus-visible { outline: 3px solid var(--text); outline-offset: 2px; }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  @media (prefers-reduced-motion: no-preference) {
    button { transition: transform var(--state-duration) var(--state-easing); }
    button:active { transform: scale(0.97); }
    .row-settled { animation: settle 700ms var(--state-easing); }
    .row-settled .status { animation: arrive var(--state-duration) var(--state-easing); }
    @keyframes settle { from { background: var(--done-surface); } }
    @keyframes arrive { from { opacity: 0; transform: translateY(0.25rem); } }
  }

  @media (max-width: 40rem) {
    thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
    table, tbody, tr, td { display: block; }
    td { display: flex; justify-content: space-between; gap: var(--space-3); padding-block: var(--space-2); }
    td::before { content: attr(data-label); color: var(--text-muted); font-size: 0.875rem; }
    td.service { font-size: 1.0625rem; padding-top: var(--space-3); }
    td.service::before { content: none; }
    .number { text-align: left; }
    td.action { padding-bottom: var(--space-3); }
    td.action::before { content: none; }
    td.action button { width: 100%; }
  }
</style>
</head>
<body>
<main>
  <header>
    <h1>Estado del release</h1>
    <p class="lead">Cinco servicios revisados. Uno necesita un reintento antes de publicar las notas.</p>
  </header>

  <ul class="summary" aria-label="Resumen">
    <li><strong id="done-count">1</strong> hecho</li>
    <li><strong>1</strong> cambiado</li>
    <li><strong>1</strong> saltado</li>
    <li><strong>1</strong> con aviso</li>
    <li><strong id="error-count">1</strong> con error</li>
  </ul>

  <div class="card">
    <table role="table" aria-label="Servicios del release">
      <thead role="rowgroup">
        <tr role="row">
          <th role="columnheader" scope="col">Servicio</th>
          <th role="columnheader" scope="col">Versión</th>
          <th role="columnheader" scope="col">Estado</th>
          <th role="columnheader" scope="col" class="number">Duración</th>
          <th role="columnheader" scope="col"><span class="visually-hidden">Acción</span></th>
        </tr>
      </thead>
      <tbody role="rowgroup">
        <tr role="row">
          <td role="cell" class="service" data-label="Servicio">api-gateway</td>
          <td role="cell" data-label="Versión">3.14.2</td>
          <td role="cell" data-label="Estado"><span class="status" data-status="done"><span aria-hidden="true">✓</span> Hecho</span></td>
          <td role="cell" class="number" data-label="Duración">12s</td>
          <td role="cell" class="action"></td>
        </tr>
        <tr role="row">
          <td role="cell" class="service" data-label="Servicio">billing-worker-eu-central</td>
          <td role="cell" data-label="Versión">2.8.0</td>
          <td role="cell" data-label="Estado"><span class="status" data-status="changed"><span aria-hidden="true">~</span> Cambiado</span></td>
          <td role="cell" class="number" data-label="Duración">48s</td>
          <td role="cell" class="action"></td>
        </tr>
        <tr role="row">
          <td role="cell" class="service" data-label="Servicio">notifications</td>
          <td role="cell" data-label="Versión">1.9.7</td>
          <td role="cell" data-label="Estado"><span class="status" data-status="skipped"><span aria-hidden="true">↷</span> Saltado</span></td>
          <td role="cell" class="number" data-label="Duración">—</td>
          <td role="cell" class="action"></td>
        </tr>
        <tr role="row">
          <td role="cell" class="service" data-label="Servicio">search-indexer</td>
          <td role="cell" data-label="Versión">5.0.0-rc.1</td>
          <td role="cell" data-label="Estado"><span class="status" data-status="warning"><span aria-hidden="true">!</span> Aviso</span></td>
          <td role="cell" class="number" data-label="Duración">1m 03s</td>
          <td role="cell" class="action"></td>
        </tr>
        <tr role="row">
          <td role="cell" class="service" data-label="Servicio">legacy-importer</td>
          <td role="cell" data-label="Versión">0.4.1</td>
          <td role="cell" data-label="Estado"><span class="status" data-status="error"><span aria-hidden="true">✗</span> Error</span></td>
          <td role="cell" class="number" data-label="Duración">7s</td>
          <td role="cell" class="action"><button type="button" id="retry">Reintentar legacy-importer</button></td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="visually-hidden" role="status" id="announcement"></p>
</main>
<script>
  // Reemplazar por la llamada real. El resaltado acompaña el resultado: no agrega espera.
  const retryService = () => Promise.resolve();

  document.getElementById('retry').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const row = button.closest('tr');
    button.disabled = true;
    await retryService();
    const status = row.querySelector('.status');
    status.dataset.status = 'done';
    status.innerHTML = '<span aria-hidden="true">✓</span> Hecho';
    row.classList.add('row-settled');
    document.getElementById('done-count').textContent = '2';
    document.getElementById('error-count').textContent = '0';
    document.getElementById('announcement').textContent = 'legacy-importer quedó en estado hecho.';
    button.remove();
  });
</script>
</body>
</html>
```

## 8. Verificar

Usar el navegador real que tenga el proyecto, por ejemplo Playwright con `page.emulateMedia({ colorScheme, reducedMotion })` y `axe-core`.

Sacar capturas de la matriz completa y mirarlas: 1280 y 375 px, claro y oscuro, movimiento normal y reducido. Sumar una en escala de grises con `filter: grayscale(1)`.

Chequeos medibles:

- `axe` sin violaciones de `color-contrast` en ningún tema. Los resultados `incomplete` se revisan a mano.
- `document.documentElement.scrollWidth <= clientWidth` en todos los anchos.
- Con movimiento reducido, `document.getAnimations()` no devuelve animaciones infinitas, tampoco después de usar los controles.
- En la captura en grises, los estados se siguen distinguiendo.

Algunas vistas embebidas renderizan siempre en tema claro los documentos locales. Si el tema oscuro no cambia, emular el tema con el navegador o servir la página por `localhost`.

Si algo de esto no se puede correr, decirlo en el reporte.
