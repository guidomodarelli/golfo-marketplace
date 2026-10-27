// Navegación e interacciones Heritage: índice, mapa de secciones, píldora de sección, botón "Inicio",
// atajos, copiar enlace, glosario, puntos sobre capturas y comparación antes/después.
// Respeta "reducir movimiento". Sin JavaScript el documento se lee completo: solo faltan los atajos.
(function () {
  var button = document.querySelector('.back-to-top');
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  // Mouse o trackpad: los textos de la interfaz dicen "Hacé click en" en vez de "Tocá".
  var finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  // Idioma del documento (lo fija el script de idioma antes de este) y textos de la interfaz por idioma.
  var language = document.documentElement.getAttribute('data-language') || 'es';
  var UI_TEXT = {
    es: {
      copyLink: 'Copiar enlace', copyLinkTo: 'Copiar enlace a la sección ', linkCopied: 'Enlace copiado', copyFailed: 'No se pudo copiar',
      shortcutSections: ' ↑ ↓ secciones', shortcutIndex: ' I índice', start: 'Inicio: ', currentSection: 'Sección actual: ', openIndex: '. Abrir índice',
      startHeading: 'Inicio', currentSectionHeading: 'Sección actual',
      hintSteps: 'Tocá un número para ir a su paso.', hintMentions: 'Tocá un número para ir a su mención en el texto.',
      hintStepsPointer: 'Hacé click en un número para ir a su paso.', hintMentionsPointer: 'Hacé click en un número para ir a su mención en el texto.',
      goToStep: 'Ir al paso ', goToMention: 'Ir a su mención en el texto', seeInCapture: 'Ver en la captura', mentionIn: 'Mención en ',
      before: 'Antes ', after: '%, después ', backToTop: 'Volver al inicio', backToTopText: 'Inicio', sectionMap: 'Mapa de secciones',
      contents: 'Contenido', close: 'Cerrar', languageLabel: 'Idioma',
      // Lectura por etapas ({nombre} se reemplaza con text(clave, valores)).
      stages: 'Etapas', stageViewAll: 'Ver todo', stage: 'Etapa ', stageWholeManual: 'Todo el manual', stageOpenSelector: 'Abrir el selector de etapas. ',
      stageMinutes: ' min', stageRead: 'leída', stagePrevious: 'Etapa anterior: ', stageNext: 'Etapa siguiente: ', stageOutline: 'Contenido de la etapa ',
      stagePosition: 'Etapa {number} de {total} · {minutes} min',
      stageReading: 'Lectura estimada: {minutes} min (referencia de {rate} palabras por minuto; no incluye ejercicios ni simuladores).',
      chapterReading: 'Lectura estimada del capítulo: {minutes} min.'
    },
    pt: {
      copyLink: 'Copiar link', copyLinkTo: 'Copiar link da seção ', linkCopied: 'Link copiado', copyFailed: 'Não foi possível copiar',
      shortcutSections: ' ↑ ↓ seções', shortcutIndex: ' I índice', start: 'Início: ', currentSection: 'Seção atual: ', openIndex: '. Abrir índice',
      startHeading: 'Início', currentSectionHeading: 'Seção atual',
      hintSteps: 'Toque em um número para ir ao passo.', hintMentions: 'Toque em um número para ir à menção no texto.',
      hintStepsPointer: 'Clique em um número para ir ao passo.', hintMentionsPointer: 'Clique em um número para ir à menção no texto.',
      goToStep: 'Ir ao passo ', goToMention: 'Ir à menção no texto', seeInCapture: 'Ver na captura', mentionIn: 'Menção em ',
      before: 'Antes ', after: '%, depois ', backToTop: 'Voltar ao início', backToTopText: 'Início', sectionMap: 'Mapa de seções',
      contents: 'Conteúdo', close: 'Fechar', languageLabel: 'Idioma',
      stages: 'Etapas', stageViewAll: 'Ver tudo', stage: 'Etapa ', stageWholeManual: 'Manual completo', stageOpenSelector: 'Abrir o seletor de etapas. ',
      stageMinutes: ' min', stageRead: 'lida', stagePrevious: 'Etapa anterior: ', stageNext: 'Próxima etapa: ', stageOutline: 'Conteúdo da etapa ',
      stagePosition: 'Etapa {number} de {total} · {minutes} min',
      stageReading: 'Leitura estimada: {minutes} min (referência de {rate} palavras por minuto; não inclui exercícios nem simuladores).',
      chapterReading: 'Leitura estimada do capítulo: {minutes} min.'
    }
  };
  var ui = UI_TEXT[language] || UI_TEXT.es;
  // Textos que arma este script: se escriben al iniciar y otra vez cuando el idioma cambia en la misma página.
  var relabels = [];
  function whenLanguage(apply) { relabels.push(apply); apply(); }
  // Textos fijos fuera del contenido (botón Inicio, mapa, hoja del índice) en el idioma del documento.
  var railLabelled = document.querySelector('.section-rail');
  var sheetLabel = document.getElementById('toc-sheet-label');
  var sheetClose = document.querySelector('.toc-sheet-close');
  whenLanguage(function () {
    if (button) {
      button.setAttribute('aria-label', ui.backToTop);
      if (button.lastChild && button.lastChild.nodeType === 3) button.lastChild.textContent = ' ' + ui.backToTopText;
    }
    if (railLabelled) railLabelled.setAttribute('aria-label', ui.sectionMap);
    if (sheetLabel) sheetLabel.textContent = ui.contents;
    if (sheetClose) sheetClose.textContent = ui.close;
  });

  // —— Selector de idioma: cambia en la misma página, sin red ni recarga. La tabla de traducciones
  // (script de idioma) reemplaza textos y capturas; este script reescribe lo suyo y deja en el mismo lugar
  // de la pantalla lo que se estaba leyendo (el texto traducido tiene otro largo, así que no basta el scroll).
  var languageSwitch = document.querySelector('.lang-switch');
  if (languageSwitch) {
    whenLanguage(function () {
      languageSwitch.setAttribute('aria-label', ui.languageLabel);
      languageSwitch.querySelectorAll('[data-lang]').forEach(function (option) {
        option.setAttribute('aria-checked', String(option.getAttribute('data-lang') === language));
      });
    });
    languageSwitch.querySelectorAll('[data-lang]').forEach(function (option) {
      option.addEventListener('click', function () {
        var chosen = option.getAttribute('data-lang');
        if (chosen === language || !window.HeritageLanguage) return;
        var anchor = window.scrollY > 0 ? readingAnchor() : null;
        var change = function () {
          window.HeritageLanguage.set(chosen);
          // La URL dice el idioma (?lang=pt), así un enlace compartido abre igual; no se guarda ninguna preferencia.
          var query = new URLSearchParams(location.search);
          if (chosen === 'es') query.delete('lang'); else query.set('lang', chosen);
          var search = query.toString() ? '?' + query.toString() : '';
          history.replaceState(history.state, '', location.pathname + search + location.hash);
          if (anchor) {
            document.dispatchEvent(new CustomEvent('heritage:before-scroll', { detail: { target: anchor.element } }));
            holdPosition(function () {
              window.scrollTo({ top: anchor.element.getBoundingClientRect().top + window.scrollY - anchor.offset, behavior: 'instant' });
            });
          }
        };
        // Mismo documento: el navegador funde el antes y el después (view transition); sin soporte o con
        // "reducir movimiento", cambia al instante.
        if (document.startViewTransition && !reduceMotion.matches) document.startViewTransition(change);
        else change();
      });
    });
  }
  var SHOW_AFTER_PX = 480;
  var TARGET_OFFSET_PX = 16;
  var SETTLE_MS = 1500;
  var FALLBACK_MS = 900;
  var ACTIVE_LINE_RATIO = 0.3;
  var VIEWPORT_MARGIN_PX = 16;
  var POPOVER_GAP_PX = 8;
  var MIN_RAIL_SECTIONS = 2;
  var CURRENT_TICK_WIDTH_PX = 24;
  var REST_TICK_WIDTH_PX = 12;
  var MAGNIFIED_TICK_WIDTH_PX = 40;
  var MAGNIFIER_RADIUS_PX = 48;
  var TERM_HIDE_DELAY_MS = 150;
  var COPY_FEEDBACK_MS = 1600;
  var HOTSPOT_REVEAL_MS = 2600;
  var SPOTLIGHT_MARGIN_PX = 44;
  // Vida total del foco temporal: 500ms de apertura + 500ms de cierre.
  var SPOTLIGHT_LIFETIME_MS = 1000;
  var spotlightTimer = null;
  // Apertura y cierre de accordions: 1,5 × motion.duration-base (300ms).
  var ACCORDION_FACTOR = 1.5;
  // Manito de los pasos (trazo al estilo de Lucide "pointer", ISC): halo claro, relleno, destello y línea.
  var TAP_HAND_PATHS = '<path d="M22 14a8 8 0 0 1-8 8"/><path d="M18 11v-1a2 2 0 0 0-2-2a2 2 0 0 0-2 2"/><path d="M14 10V9a2 2 0 0 0-2-2a2 2 0 0 0-2 2v1"/><path d="M10 9.5V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v10"/><path d="M18 11a2 2 0 1 1 4 0v3a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>';
  // Vuelta al paso (trazo al estilo de Lucide "undo-2", ISC).
  var RETURN_SVG = '<span class="hotspot-return" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/></svg></span>';
  var TAP_HAND_SVG = '<svg class="tap-hand" viewBox="-2 -4 28 30" aria-hidden="true" focusable="false">' +
    '<g class="tap-hand-halo">' + TAP_HAND_PATHS + '</g>' +
    '<g class="tap-hand-fill"><path d="M8 2.6a1.5 1.5 0 0 1 1.5 1.5V9.6l.6-.3a1.6 1.6 0 0 1 3.4.4l.4-.2a1.6 1.6 0 0 1 3.6 1l.6-.1a1.5 1.5 0 0 1 3.4.9v2.8a7.5 7.5 0 0 1-7.5 7.4h-2c-2.6 0-4.2-.8-5.6-2.2L3.2 16a1.5 1.5 0 0 1 2.2-2.1L6.5 15V4.1A1.5 1.5 0 0 1 8 2.6z"/></g>' +
    '<g class="tap-hand-rays"><path d="M4.6 0.4 3.2-1"/><path d="M8 -0.6V-2.6"/><path d="M11.4 0.4 12.8-1"/></g>' +
    '<g class="tap-hand-line">' + TAP_HAND_PATHS + '</g></svg>';
  var stopSettling = null;
  var frameRequested = false;
  var currentEntry = null;
  // Sección a la que llevó el último salto; se olvida cuando el lector scrollea por su cuenta.
  var landedEntry = null;
  ['wheel', 'touchstart', 'keydown'].forEach(function (type) {
    window.addEventListener(type, function () { landedEntry = null; }, { capture: true, passive: true });
  });

  // —— Scroll a un destino
  // Inicio: arriba de todo (0). Título de sección: la sección completa, número incluido, con aire.
  function targetTop(target) {
    if (target.id === 'top') return 0;
    var anchor = (target.matches('.section-title') && target.closest('section')) || target;
    return Math.max(0, anchor.getBoundingClientRect().top + window.scrollY - landingOffset(anchor));
  }
  // El selector de idioma, "Ir al menú" y las barras marcadas con data-heritage-offset (la barra de
  // etapas) quedan sobre el contenido: si alguno cae sobre la columna del destino, el destino queda debajo
  // de él (si no, taparía el número de la sección y su "Copiar enlace"). Una barra sticky se mide por
  // donde queda pegada, no por donde está antes del salto.
  function landingOffset(anchor) {
    var anchorBox = anchor.getBoundingClientRect();
    var offset = TARGET_OFFSET_PX;
    document.querySelectorAll('.lang-switch, .menu-back, [data-heritage-offset]').forEach(function (control) {
      var style = getComputedStyle(control);
      if (style.position !== 'fixed' && style.position !== 'sticky') return;
      var box = control.getBoundingClientRect();
      if (!box.height || box.left >= anchorBox.right || box.right <= anchorBox.left) return;
      var bottom = style.position === 'sticky' ? (parseFloat(style.top) || 0) + box.height : box.bottom;
      offset = Math.max(offset, bottom + TARGET_OFFSET_PX);
    });
    return offset;
  }
  // 'instant' explícito: con html{scroll-behavior:smooth}, un scrollTo común también sería suave.
  function jump(target) { window.scrollTo({ top: targetTop(target), behavior: 'instant' }); }

  // El contenido de arriba puede cambiar de alto mientras se scrollea (imágenes o capturas diferidas):
  // mantiene el destino alineado hasta que el layout se asienta, salvo que el lector scrollee por su cuenta.
  function settleOn(target) { holdPosition(function () { jump(target); }); }
  // Repite place() cada vez que la página cambia de alto, durante SETTLE_MS o hasta que el lector scrollee.
  function holdPosition(place) {
    if (stopSettling) stopSettling();
    var observer = new ResizeObserver(place);
    var stop = function () {
      observer.disconnect();
      ['wheel', 'touchstart', 'keydown'].forEach(function (type) { window.removeEventListener(type, stop); });
      stopSettling = null;
    };
    ['wheel', 'touchstart', 'keydown'].forEach(function (type) { window.addEventListener(type, stop, { passive: true }); });
    observer.observe(document.body);
    place();
    setTimeout(stop, SETTLE_MS);
    stopSettling = stop;
  }

  // Lo que el lector tiene arriba de la pantalla: el primer bloque del contenido que todavía se ve y su
  // distancia al borde. Los nodos no cambian al traducir, así que sirve de ancla aunque el texto cambie de largo.
  var READING_BLOCKS = ':is(.doc-header, nav.toc, section.section) :is(h1, h2, p, li, dt, dd, tr, summary, .section-num, .mockup, .figcap, .callout, .example-box)';
  function readingAnchor() {
    var blocks = document.querySelectorAll(READING_BLOCKS);
    for (var index = 0; index < blocks.length; index++) {
      var box = blocks[index].getBoundingClientRect();
      if (box.height && box.bottom > 0) return { element: blocks[index], offset: box.top };
    }
    return null;
  }

  // Adaptador de visor opcional (window.HeritageViewer, por ejemplo el de un visor de documentos): traduce entre la sección y
  // la URL pública del visor. Se busca al usarlo, así puede cargarse después de este script.
  function viewerAdapter() { return window.HeritageViewer || null; }

  // La URL sigue a la sección: el inicio la deja sin hash. Con adaptador, él decide si puede actualizar la
  // URL pública (mismo origen y mismo documento) y si no, solo cambia la propia. Sin adaptador, en un visor
  // del mismo origen también se actualiza su barra, porque un script de sincronización puede recibir el
  // hash sin escribirlo.
  function setHash(id) {
    var hash = id === 'top' ? '' : '#' + id;
    history.replaceState(null, '', location.pathname + location.search + hash);
    var adapter = viewerAdapter();
    if (adapter) { adapter.syncLocation(id); return; }
    try {
      var viewer = window.parent !== window ? window.parent : null;
      if (viewer && viewer.location.hash !== hash) viewer.history.replaceState(viewer.history.state, '', viewer.location.pathname + viewer.location.search + hash);
    } catch (crossOriginError) { /* fallback deliberado: visor de otro origen, solo la URL propia */ }
  }

  function scrollToTarget(target, updateHash) {
    // Avisa a los componentes diferidos que se rendericen antes de medir el destino.
    document.dispatchEvent(new CustomEvent('heritage:before-scroll', { detail: { target: target } }));
    setTimeout(function () {
      var settled = false;
      var finish = function () {
        if (settled) return;
        settled = true;
        settleOn(target);
      };
      window.scrollTo({ top: targetTop(target), behavior: reduceMotion.matches ? 'auto' : 'smooth' });
      // El navegador puede saltear o frenar el scroll suave (pestaña en segundo plano, visor embebido).
      if ('onscrollend' in window) window.addEventListener('scrollend', finish, { once: true });
      setTimeout(finish, FALLBACK_MS);
    }, 50);
    if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
    if (updateHash && target.id) setHash(target.id);
    landedEntry = entries.filter(function (entry) { return entry.heading === target; })[0] || null;
  }
  // Punto de extensión para variantes como la lectura por etapas: reusan este scroll y esta URL en vez
  // de reimplementarlos.
  // Texto de interfaz en el idioma actual: un único diccionario para este script y sus variantes.
  function uiText(key, values) {
    var template = ui[key] !== undefined ? ui[key] : UI_TEXT.es[key];
    return values ? String(template).replace(/\{(\w+)\}/g, function (match, name) { return values[name] !== undefined ? values[name] : match; }) : template;
  }
  window.HeritageNavigation = { scrollTo: scrollToTarget, setLocation: setHash, text: uiText };

  // —— Utilidades
  function createElement(tagName, className, text) {
    var element = document.createElement(tagName);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }
  // Ubica una tarjeta debajo del ancla (o arriba si no entra) sin salirse de la ventana.
  function placeNear(card, anchorRect) {
    var top = anchorRect.bottom + POPOVER_GAP_PX;
    if (top + card.offsetHeight > window.innerHeight - VIEWPORT_MARGIN_PX) top = anchorRect.top - POPOVER_GAP_PX - card.offsetHeight;
    var left = Math.min(anchorRect.left, window.innerWidth - card.offsetWidth - VIEWPORT_MARGIN_PX);
    card.style.top = Math.max(VIEWPORT_MARGIN_PX, top) + 'px';
    card.style.left = Math.max(VIEWPORT_MARGIN_PX, left) + 'px';
  }
  var liveRegion = createElement('div', 'visually-hidden');
  liveRegion.setAttribute('role', 'status');
  document.body.appendChild(liveRegion);
  function announce(message) { liveRegion.textContent = message; }

  // —— Secciones: fuente única para índice, mapa, píldora y atajos
  var entries = [];
  document.querySelectorAll('section.section').forEach(function (section) {
    var heading = section.querySelector('.section-title');
    if (!heading || !heading.id) return;
    var numberElement = section.querySelector('.section-num');
    var firstParagraph = section.querySelector('p');
    entries.push({
      section: section,
      heading: heading,
      numberElement: numberElement,
      number: numberElement ? numberElement.textContent.trim() : '',
      title: heading.textContent.trim(),
      summary: firstParagraph ? firstParagraph.textContent.replace(/\s+/g, ' ').trim() : '',
      link: null
    });
  });
  // El inicio del documento es la primera entrada del mapa, de la hoja y de la píldora (sin número).
  var docHeader = document.getElementById('top');
  var docTitle = docHeader && docHeader.querySelector('.doc-title');
  if (docTitle) {
    var docSub = docHeader.querySelector('.doc-sub');
    entries.unshift({
      section: docHeader,
      heading: docHeader,
      numberElement: null,
      number: '',
      title: docTitle.textContent.replace(/\s+/g, ' ').trim(),
      summary: docSub ? docSub.textContent.replace(/\s+/g, ' ').trim() : '',
      isStart: true,
      link: null
    });
  }
  var toc = document.querySelector('.toc');
  // Título y resumen salen del contenido: se vuelven a leer cuando cambia el idioma.
  function readEntryText(entry) {
    var title = entry.isStart ? docTitle : entry.heading;
    var summary = entry.isStart ? docHeader.querySelector('.doc-sub') : entry.section.querySelector('p');
    entry.title = title.textContent.replace(/\s+/g, ' ').trim();
    entry.summary = summary ? summary.textContent.replace(/\s+/g, ' ').trim() : '';
  }

  // —— Copiar enlace a una sección. En visores embebidos, <meta name="heritage:share-url"> da la URL pública
  // y el adaptador del visor, si lo hay, su formato (por ejemplo …/view?href=<id>).
  var shareMeta = document.querySelector('meta[name="heritage:share-url"]');
  var shareBase = (shareMeta && shareMeta.content) || location.href.split('#')[0];
  function shareUrlFor(id) {
    var adapter = viewerAdapter();
    return (adapter && adapter.shareUrl(id)) || shareBase + '#' + id;
  }
  function copyWithSelection(text) {
    return new Promise(function (resolve, reject) {
      var field = createElement('textarea', 'visually-hidden');
      field.value = text;
      field.setAttribute('readonly', '');
      document.body.appendChild(field);
      field.select();
      var copied = false;
      try { copied = document.execCommand('copy'); } catch (copyError) { copied = false; }
      field.remove();
      if (copied) resolve();
      else reject(new Error('Heritage:copyText failed: clipboard unavailable in this viewer'));
    });
  }
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () { return copyWithSelection(text); });
    }
    return copyWithSelection(text);
  }
  entries.forEach(function (entry) {
    if (!entry.numberElement) return;
    var copyButton = createElement('button', 'section-link');
    copyButton.type = 'button';
    whenLanguage(function () {
      if (!copyButton.classList.contains('is-copied')) copyButton.textContent = ui.copyLink;
      copyButton.setAttribute('aria-label', ui.copyLinkTo + (entry.number || entry.title));
    });
    copyButton.addEventListener('click', function () {
      var url = shareUrlFor(entry.heading.id);
      // La barra de direcciones también pasa a la sección, también la del visor.
      setHash(entry.heading.id);
      var showFeedback = function (message) {
        copyButton.textContent = message;
        copyButton.classList.add('is-copied');
        copyButton.focus({ preventScroll: true });
        announce(message);
        setTimeout(function () {
          copyButton.textContent = ui.copyLink;
          copyButton.classList.remove('is-copied');
        }, COPY_FEEDBACK_MS);
      };
      copyText(url).then(function () { showFeedback(ui.linkCopied); }, function (copyError) {
        console.warn('Heritage:copySectionLink failed', { sectionId: entry.heading.id, error: copyError });
        showFeedback(ui.copyFailed);
      });
    });
    entry.numberElement.appendChild(copyButton);
  });

  // Una sección oculta (por ejemplo, de otra etapa) no cuenta para el mapa, la sección actual ni los atajos;
  // la hoja del índice sigue listándolas todas. Quien oculta o muestra secciones avisa con
  // heritage:visibility-change.
  function isRendered(entry) { return entry.section.getClientRects().length > 0; }
  function renderedEntries() { return entries.filter(isRendered); }

  // —— Mapa de secciones: una marca por sección, lupa, vista previa y progreso.
  var rail = document.querySelector('.section-rail');
  var preview = null;
  var hidePreview = function () { if (preview) preview.hidden = true; };
  var isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  var modifierLabel = isMac ? '⌥' : 'Alt';
  if (rail && entries.length >= MIN_RAIL_SECTIONS) {
    var railList = createElement('ol');
    preview = createElement('div', 'section-rail-preview');
    var previewMeta = createElement('div', 'section-rail-preview-meta');
    var previewNumber = createElement('span', 'section-rail-preview-num');
    var previewTitle = createElement('div', 'section-rail-preview-title');
    var previewSummary = createElement('div', 'section-rail-preview-summary');
    var previewHint = createElement('div', 'section-rail-preview-hint');
    whenLanguage(function () { previewHint.textContent = modifierLabel + ui.shortcutSections + (toc || document.querySelector('.toc-sheet') ? ' · ' + modifierLabel + ui.shortcutIndex : ''); });
    previewMeta.append(previewNumber);
    preview.append(previewMeta, previewTitle, previewSummary, previewHint);
    preview.setAttribute('aria-hidden', 'true');
    preview.hidden = true;

    entries.forEach(function (entry) {
      var item = createElement('li');
      entry.link = createElement('a', entry.isStart ? 'section-rail-tick is-start' : 'section-rail-tick');
      entry.link.href = '#' + entry.heading.id;
      whenLanguage(function () { entry.link.setAttribute('aria-label', (entry.isStart ? ui.start : entry.number ? entry.number + ' ' : '') + entry.title); });
      item.appendChild(entry.link);
      railList.appendChild(item);
    });
    rail.appendChild(railList);
    document.body.appendChild(preview);
    rail.hidden = false;

    var showPreview = function (entry) {
      previewNumber.textContent = entry.number;
      previewTitle.textContent = entry.title;
      previewSummary.textContent = entry.summary;
      previewNumber.hidden = !entry.number;
      previewSummary.hidden = !entry.summary;
      preview.hidden = false;
      var tick = entry.link.getBoundingClientRect();
      var centeredTop = tick.top + tick.height / 2 - preview.offsetHeight / 2;
      var maxTop = window.innerHeight - preview.offsetHeight - VIEWPORT_MARGIN_PX;
      preview.style.top = Math.max(VIEWPORT_MARGIN_PX, Math.min(centeredTop, maxTop)) + 'px';
    };

    // Lupa: cada marca crece según su distancia vertical al puntero (o a la marca enfocada).
    var magnify = function (pointerY) {
      entries.forEach(function (entry) {
        var tick = entry.link.getBoundingClientRect();
        var distance = Math.min(Math.abs(tick.top + tick.height / 2 - pointerY) / MAGNIFIER_RADIUS_PX, 1);
        var influence = (1 + Math.cos(Math.PI * distance)) / 2;
        var width = REST_TICK_WIDTH_PX + (MAGNIFIED_TICK_WIDTH_PX - REST_TICK_WIDTH_PX) * influence;
        if (entry.link.hasAttribute('aria-current')) width = Math.max(width, CURRENT_TICK_WIDTH_PX);
        entry.link.style.setProperty('--tick-width', width.toFixed(1) + 'px');
      });
    };
    var resetMagnifier = function () {
      entries.forEach(function (entry) { entry.link.style.removeProperty('--tick-width'); });
    };
    rail.addEventListener('pointermove', function (event) { magnify(event.clientY); });
    rail.addEventListener('pointerleave', resetMagnifier);

    entries.forEach(function (entry) {
      entry.link.addEventListener('mouseenter', function () { showPreview(entry); });
      entry.link.addEventListener('focus', function () {
        showPreview(entry);
        var tick = entry.link.getBoundingClientRect();
        magnify(tick.top + tick.height / 2);
      });
      entry.link.addEventListener('mouseleave', hidePreview);
      entry.link.addEventListener('blur', function () {
        hidePreview();
        if (!rail.matches(':hover')) resetMagnifier();
      });
    });
  }

  // —— Píldora de sección + índice en hoja inferior (pantallas angostas, donde el mapa no entra)
  var pill = document.querySelector('.section-pill');
  var sheet = document.querySelector('.toc-sheet');
  var sheetReady = Boolean(pill && sheet && sheet.showModal && entries.length >= MIN_RAIL_SECTIONS);
  var focusAfterSheet = null;
  // Cierra la hoja bajándola; sin animación (o con "reducir movimiento") cierra al instante.
  function closeSheet() {
    if (!sheet || !sheet.open || sheet.classList.contains('is-closing')) return;
    if (reduceMotion.matches) { sheet.close(); return; }
    var finished = false;
    var finish = function () {
      if (finished) return;
      finished = true;
      sheet.classList.remove('is-closing');
      sheet.close();
    };
    sheet.classList.add('is-closing');
    sheet.addEventListener('animationend', function (event) { if (event.target === sheet) finish(); }, { once: true });
    setTimeout(finish, (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--motion-duration-base')) || 200) * 1.5 + 100);
  }
  if (sheetReady) {
    var sheetBody = sheet.querySelector('.toc-sheet-body');
    var sheetHead = sheet.querySelector('.toc-sheet-head');
    // Sección actual con su título completo (la píldora puede truncarlo).
    var sheetCurrent = createElement('div', 'toc-sheet-current');
    var sheetCurrentLabel = createElement('span', 'toc-sheet-current-label');
    var sheetCurrentTitle = createElement('span');
    sheetCurrent.append(sheetCurrentLabel, sheetCurrentTitle);
    if (sheetHead) sheetHead.appendChild(sheetCurrent);
    var sheetList = toc ? toc.querySelector('ol').cloneNode(true) : createElement('ol');
    if (!toc) {
      entries.forEach(function (entry) {
        var item = createElement('li');
        var link = createElement('a', '', entry.title);
        link.href = '#' + entry.heading.id;
        link.prepend(createElement('span', 'toc-num', entry.number));
        item.appendChild(link);
        sheetList.appendChild(item);
      });
    }
    var startEntry = entries[0] && entries[0].isStart ? entries[0] : null;
    if (startEntry && toc) {
      var startItem = createElement('li');
      var startLink = createElement('a', 'toc-sheet-start');
      whenLanguage(function () { startLink.textContent = startEntry.title; });
      startLink.href = '#top';
      startItem.appendChild(startLink);
      sheetList.prepend(startItem);
    }
    sheetBody.appendChild(sheetList);
    pill.addEventListener('click', function () {
      // Exactamente una entrada actual, aunque el índice repita un destino.
      var currentLink = null;
      sheetList.querySelectorAll('a').forEach(function (link) {
        if (!currentLink && currentEntry && link.getAttribute('href') === '#' + currentEntry.heading.id) {
          link.setAttribute('aria-current', 'location');
          currentLink = link;
        } else link.removeAttribute('aria-current');
      });
      if (currentEntry) {
        sheetCurrentLabel.textContent = (currentEntry.isStart ? ui.startHeading : ui.currentSectionHeading) + ' · ' + (currentEntry.number ? currentEntry.number + ' · ' : '');
        sheetCurrentTitle.textContent = currentEntry.title;
      }
      sheetCurrent.hidden = !currentEntry;
      sheet.showModal();
      // La entrada actual queda a la vista, debajo del encabezado fijo de la hoja.
      if (currentLink) {
        var linkTop = currentLink.getBoundingClientRect().top - sheetBody.getBoundingClientRect().top + sheetBody.scrollTop;
        var headHeight = sheetHead ? sheetHead.offsetHeight : 0;
        if (linkTop < sheetBody.scrollTop + headHeight || linkTop + currentLink.offsetHeight > sheetBody.scrollTop + sheetBody.clientHeight) sheetBody.scrollTop = Math.max(0, linkTop - headHeight);
      }
    });
    sheet.querySelector('.toc-sheet-close').addEventListener('click', closeSheet);
    // Al cerrarse, el <dialog> devuelve el foco a la píldora: si se eligió un destino, el foco va a él.
    sheet.addEventListener('close', function () {
      if (!focusAfterSheet) return;
      focusAfterSheet.focus({ preventScroll: true });
      focusAfterSheet = null;
    });
    // Click en el fondo (fuera de .toc-sheet-body) cierra la hoja; Escape también, con la misma animación.
    sheet.addEventListener('click', function (event) { if (event.target === sheet) closeSheet(); });
    sheet.addEventListener('cancel', function (event) { event.preventDefault(); closeSheet(); });
  }

  // —— Sección actual: progreso de lectura, píldora y mapa
  function renderCurrent(current, progress) {
    entries.forEach(function (entry) {
      if (!entry.link) return;
      if (entry === current) {
        entry.link.setAttribute('aria-current', 'location');
        entry.link.style.setProperty('--tick-progress', Math.round(progress * 100) + '%');
      } else {
        entry.link.removeAttribute('aria-current');
        entry.link.style.removeProperty('--tick-progress');
      }
    });
    if (sheetReady) {
      var pillNumber = pill.querySelector('.section-pill-num');
      pillNumber.textContent = current.number;
      pillNumber.hidden = !current.number;
      pill.querySelector('.section-pill-title').textContent = current.title;
      pill.title = current.title;
      pill.setAttribute('aria-label', (current.isStart ? ui.start : ui.currentSection + (current.number ? current.number + ' ' : '')) + current.title + ui.openIndex);
    }
  }
  function updateCurrent() {
    frameRequested = false;
    var visibleEntries = renderedEntries();
    if (!visibleEntries.length) return;
    var activeLine = window.innerHeight * ACTIVE_LINE_RATIO;
    var atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 1;
    var current = visibleEntries[0];
    visibleEntries.forEach(function (entry) {
      if (entry.section.getBoundingClientRect().top <= activeLine) current = entry;
    });
    if (atBottom) current = visibleEntries[visibleEntries.length - 1];
    // Tras un salto, el destino es la sección actual mientras se vea, aunque no llegue a la línea activa
    // (las últimas secciones no pueden subir tanto); el lector scrolleando vuelve a la regla general.
    if (landedEntry && isRendered(landedEntry)) {
      var landedBox = landedEntry.section.getBoundingClientRect();
      if (landedBox.top < window.innerHeight && landedBox.bottom > 0) current = landedEntry;
    }
    var rect = current.section.getBoundingClientRect();
    var progress = atBottom ? 1 : Math.min(Math.max((activeLine - rect.top) / rect.height, 0), 1);
    currentEntry = current;
    renderCurrent(current, progress);
  }
  // setTimeout y no requestAnimationFrame: rAF no corre en pestañas en segundo plano ni en algunos visores.
  function requestUpdate() {
    if (frameRequested) return;
    frameRequested = true;
    setTimeout(updateCurrent, 16);
  }
  function toggleFloating() {
    var scrolled = window.scrollY >= SHOW_AFTER_PX;
    if (button) button.hidden = !scrolled;
    // La píldora se ve siempre: arriba de todo muestra el título del documento.
    if (sheetReady) pill.hidden = false;
  }
  window.addEventListener('scroll', requestUpdate, { passive: true });
  window.addEventListener('scroll', toggleFloating, { passive: true });
  window.addEventListener('scroll', hidePreview, { passive: true });
  window.addEventListener('resize', requestUpdate);
  document.addEventListener('heritage:visibility-change', function () {
    entries.forEach(function (entry) { if (entry.link) entry.link.parentElement.hidden = !isRendered(entry); });
    hidePreview();
    updateCurrent();
  });
  toggleFloating();
  updateCurrent();

  // —— Glosario: el término enlaza a su <dt>; la definición se lee con aria-describedby y se ve al pasar o enfocar.
  var termCard = createElement('div', 'term-card');
  var termCardTitle = createElement('div', 'term-card-title');
  var termCardText = createElement('div', 'term-card-text');
  var termHideTimer = null;
  termCard.append(termCardTitle, termCardText);
  termCard.setAttribute('aria-hidden', 'true');
  termCard.hidden = true;
  var hideTermCard = function () { clearTimeout(termHideTimer); termCard.hidden = true; };
  var scheduleHideTermCard = function () {
    clearTimeout(termHideTimer);
    termHideTimer = setTimeout(hideTermCard, TERM_HIDE_DELAY_MS);
  };
  // El título del término sin sus superíndices de menciones.
  var termLabel = function (definitionTerm) {
    var copy = definitionTerm.cloneNode(true);
    copy.querySelectorAll('.glossary-mentions').forEach(function (node) { node.remove(); });
    return copy.textContent.trim();
  };
  var terms = document.querySelectorAll('a.term[href^="#"]');
  if (terms.length) document.body.appendChild(termCard);
  terms.forEach(function (term) {
    var definitionTerm = document.getElementById(term.getAttribute('href').slice(1));
    var definition = definitionTerm && definitionTerm.nextElementSibling;
    if (!definition || definition.tagName !== 'DD') return;
    if (!definition.id) definition.id = definitionTerm.id + '-definition';
    term.setAttribute('aria-describedby', definition.id);
    var showTermCard = function () {
      clearTimeout(termHideTimer);
      termCardTitle.textContent = termLabel(definitionTerm);
      termCardText.textContent = definition.textContent.replace(/\s+/g, ' ').trim();
      termCard.hidden = false;
      placeNear(termCard, term.getBoundingClientRect());
    };
    term.addEventListener('mouseenter', showTermCard);
    term.addEventListener('focus', showTermCard);
    term.addEventListener('mouseleave', scheduleHideTermCard);
    term.addEventListener('blur', hideTermCard);
  });
  // La tarjeta se puede recorrer con el puntero sin que desaparezca (WCAG 1.4.13).
  termCard.addEventListener('mouseenter', function () { clearTimeout(termHideTimer); });
  termCard.addEventListener('mouseleave', scheduleHideTermCard);
  window.addEventListener('scroll', hideTermCard, { passive: true });

  // —— Glosario: cada <dt> suma un superíndice por mención del término en el documento (1, 2, 3…), en orden
  // de aparición; lleva a esa mención y su tooltip dice en qué sección está.
  document.querySelectorAll('.glossary dt[id]').forEach(function (definitionTerm) {
    var mentions = document.querySelectorAll('a.term[href="#' + definitionTerm.id + '"]');
    if (!mentions.length) return;
    var references = createElement('sup', 'glossary-mentions');
    mentions.forEach(function (mention, index) {
      if (!mention.id) mention.id = definitionTerm.id + '-mention-' + (index + 1);
      var section = mention.closest('section');
      var sectionTitle = section && section.querySelector('.section-title');
      var link = createElement('a', null, String(index + 1));
      link.href = '#' + mention.id;
      whenLanguage(function () {
        var label = ui.mentionIn + (sectionTitle ? sectionTitle.textContent.trim() : '');
        link.title = label;
        link.setAttribute('aria-label', label);
      });
      link.addEventListener('click', function (event) {
        event.preventDefault();
        revealText(mention);
      });
      if (index) references.append(' ');
      references.append(link);
    });
    definitionTerm.append(' ', references);
  });

  // —— Links internos: índice, mapa, hoja inferior y términos del glosario usan el mismo scroll.
  document.querySelectorAll('.toc a[href^="#"], .section-rail a[href^="#"], .toc-sheet a[href^="#"], a.term[href^="#"]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      var target = document.getElementById(link.getAttribute('href').slice(1));
      if (!target) return;
      event.preventDefault();
      if (sheet && sheet.open) { focusAfterSheet = target; closeSheet(); }
      hideTermCard();
      if (link.matches('a.term')) { revealText(target); return; }
      scrollToTarget(target, true);
    });
  });

  if (button) {
    button.addEventListener('click', function (event) {
      event.preventDefault();
      // true: volver al inicio también limpia el hash de la URL.
      scrollToTarget(document.getElementById('top'), true);
    });
  }

  // —— Atajos: Alt+↓ / Alt+↑ cambian de sección, Alt+I va al índice, Escape cierra las vistas previas.
  // Con modificador para no chocar con lectores de pantalla ni con la escritura (WCAG 2.1.4).
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') { hidePreview(); hideTermCard(); return; }
    if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.target.closest && event.target.closest('input, textarea, select, [contenteditable]')) return;
    if (sheet && sheet.open) return;
    var navigable = renderedEntries();
    var currentIndex = navigable.indexOf(currentEntry);
    var destination = null;
    if (event.key === 'ArrowDown' && navigable[currentIndex + 1]) destination = navigable[currentIndex + 1].heading;
    else if (event.key === 'ArrowUp' && navigable[currentIndex - 1]) destination = navigable[currentIndex - 1].heading;
    else if (event.code === 'KeyI' && toc) destination = toc;
    // Sin índice superior (lectura por etapas), Alt+I abre la hoja, que es el índice completo.
    else if (event.code === 'KeyI' && sheetReady) { event.preventDefault(); pill.click(); return; }
    if (!destination) return;
    event.preventDefault();
    scrollToTarget(destination, destination !== toc);
  });

  // —— Foco temporal sobre el destino de un salto: se abre al llegar y se va enseguida (vida total
  // SPOTLIGHT_LIFETIME_MS), o si el lector scrollea. Lo usan los puntos y el glosario.
  function spotlightOn(destination) {
    if (reduceMotion.matches) return;
    var spot = document.querySelector('.hotspot-spotlight');
    if (!spot) {
      spot = createElement('div', 'hotspot-spotlight');
      spot.setAttribute('aria-hidden', 'true');
      document.body.appendChild(spot);
    }
    var rect = destination.getBoundingClientRect();
    spot.style.setProperty('--spot-x', (rect.left + rect.width / 2) + 'px');
    spot.style.setProperty('--spot-y', (rect.top + rect.height / 2) + 'px');
    spot.style.setProperty('--spot-target', (Math.max(rect.width, rect.height) / 2 + SPOTLIGHT_MARGIN_PX) + 'px');
    spot.classList.remove('is-on', 'is-leaving');
    void spot.offsetWidth;
    spot.classList.add('is-on');
    clearTimeout(spotlightTimer);
    spotlightTimer = setTimeout(spotlightOff, SPOTLIGHT_LIFETIME_MS / 2);
  }
  // Mueve el foco temporal con su destino, sin reiniciarlo.
  function spotlightFollow(destination) {
    var spot = document.querySelector('.hotspot-spotlight');
    if (!spot || !spot.classList.contains('is-on')) return;
    var rect = destination.getBoundingClientRect();
    spot.style.setProperty('--spot-x', (rect.left + rect.width / 2) + 'px');
    spot.style.setProperty('--spot-y', (rect.top + rect.height / 2) + 'px');
  }
  function spotlightOff() {
    var spot = document.querySelector('.hotspot-spotlight');
    if (!spot || !spot.classList.contains('is-on')) return;
    spot.classList.remove('is-on');
    spot.classList.add('is-leaving');
  }
  window.addEventListener('wheel', spotlightOff, { passive: true });
  window.addEventListener('touchstart', spotlightOff, { passive: true });

  // Al final del documento (el glosario) no hay lugar para centrar: un espaciador al pie lo da durante
  // el salto, y se achica solo mientras el lector vuelve a subir, por debajo de lo que se ve.
  var scrollSpacer = null;
  var centering = false;
  function spacerHeight() { return scrollSpacer ? scrollSpacer.offsetHeight : 0; }
  function contentBottom() { return document.documentElement.scrollHeight - spacerHeight(); }
  function makeRoomFor(top) {
    var contentMaxScroll = contentBottom() - window.innerHeight;
    var needed = Math.max(0, Math.ceil(top - contentMaxScroll), Math.ceil(window.scrollY - contentMaxScroll));
    if (!scrollSpacer) {
      if (!needed) return;
      scrollSpacer = createElement('div', 'scroll-spacer');
      scrollSpacer.setAttribute('aria-hidden', 'true');
      document.body.appendChild(scrollSpacer);
    }
    if (needed !== spacerHeight()) scrollSpacer.style.height = needed + 'px';
  }
  window.addEventListener('scroll', function () {
    if (centering || !spacerHeight()) return;
    var visible = Math.max(0, Math.ceil(window.scrollY + window.innerHeight - contentBottom()));
    if (visible < spacerHeight()) scrollSpacer.style.height = visible + 'px';
  }, { passive: true });

  // Centra un destino en la pantalla (aunque ya se vea) y avisa al llegar. Después lo mantiene centrado
  // mientras la página se acomoda (capturas o accordions que cambian de alto) y avisa cada corrección,
  // salvo que el lector scrollee por su cuenta.
  function centerOnTarget(destination, onArrive, onMove) {
    var destinationTop = function () {
      var top = destination.getBoundingClientRect().top + window.scrollY - (window.innerHeight - destination.offsetHeight) / 2;
      makeRoomFor(top);
      return Math.max(0, top);
    };
    centering = true;
    // Las capturas diferidas de arriba se renderizan antes de medir, para que el destino no se corra.
    document.dispatchEvent(new CustomEvent('heritage:before-scroll', { detail: { target: destination } }));
    setTimeout(function () {
      var arrived = false;
      // Al terminar el scroll (o si el navegador lo salteó: pestaña en segundo plano, visor embebido).
      var arrive = function () {
        if (arrived) return;
        arrived = true;
        if (Math.abs(window.scrollY - destinationTop()) > 1) window.scrollTo({ top: destinationTop(), behavior: 'instant' });
        onArrive();
        if (!onMove) { centering = false; return; }
        var observer = new ResizeObserver(function () {
          if (Math.abs(window.scrollY - destinationTop()) <= 1) return;
          window.scrollTo({ top: destinationTop(), behavior: 'instant' });
          onMove();
        });
        var stop = function () {
          observer.disconnect();
          centering = false;
          ['wheel', 'touchstart', 'keydown'].forEach(function (type) { window.removeEventListener(type, stop); });
        };
        ['wheel', 'touchstart', 'keydown'].forEach(function (type) { window.addEventListener(type, stop, { passive: true }); });
        observer.observe(document.body);
        setTimeout(stop, SETTLE_MS);
      };
      if (Math.abs(window.scrollY - destinationTop()) <= 1) { arrive(); return; }
      window.scrollTo({ top: destinationTop(), behavior: reduceMotion.matches ? 'auto' : 'smooth' });
      if ('onscrollend' in window) window.addEventListener('scrollend', arrive, { once: true });
      setTimeout(arrive, FALLBACK_MS);
    }, 50);
  }

  // —— Saltos a un texto (de un término a su definición y de la definición a cada mención): abre los
  // accordions que lo contienen, lo centra, lo resalta y lo hace latir 3 veces bajo el foco temporal.
  function revealText(target) {
    // Antes de abrir accordions y enfocar: un destino oculto (otra etapa) se muestra primero.
    document.dispatchEvent(new CustomEvent('heritage:before-scroll', { detail: { target: target } }));
    var closed = [];
    for (var node = target.parentElement; node; node = node.parentElement) {
      if (node.matches('details.acc') && (!node.open || node.classList.contains('is-closing'))) closed.unshift(node);
    }
    closed.forEach(function (accordion) { setAccordion(accordion, true); });
    if (!target.hasAttribute('tabindex') && !target.matches('a[href]')) target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
    if (target.id) setHash(target.id);
    // Se centra cuando terminan de abrirse y cerrarse los accordions: antes, el destino todavía se mueve.
    var animations = [];
    document.querySelectorAll('details.acc').forEach(function (accordion) {
      if (accordion.__accordionAnimation) animations.push(accordion.__accordionAnimation.finished.catch(function () {}));
    });
    var spotTarget = target;
    // El resaltado (que hace del término un inline-block para poder latir) va antes de medir y centrar.
    target.classList.remove('is-text-pulsing', 'is-text-revealed');
    void target.offsetWidth;
    target.classList.add('is-text-revealed');
    // Si el navegador pausa las animaciones (pestaña en segundo plano), centra igual al rato.
    var animationsDone = new Promise(function (resolve) { setTimeout(resolve, FALLBACK_MS); });
    Promise.race([Promise.all(animations), animationsDone]).then(function () {
      centerOnTarget(target, function () {
        // En un bloque (el término en el glosario) el foco se centra en la palabra: no en todo el ancho ni
        // en los superíndices de menciones que la siguen.
        if (getComputedStyle(target).display === 'block') {
          var range = document.createRange();
          var mentions = target.querySelector('.glossary-mentions');
          range.setStart(target, 0);
          if (mentions) range.setEndBefore(mentions); else range.setEnd(target, target.childNodes.length);
          spotTarget = { getBoundingClientRect: function () { return range.getBoundingClientRect(); } };
        }
        spotlightOn(spotTarget);
        // Con "reducir movimiento" no late: el resaltado dura lo mismo que los latidos.
        if (reduceMotion.matches) {
          setTimeout(function () { target.classList.remove('is-text-revealed'); }, HOTSPOT_REVEAL_MS);
          return;
        }
        target.classList.add('is-text-pulsing');
        target.addEventListener('animationend', function () {
          target.classList.remove('is-text-pulsing', 'is-text-revealed');
          spotlightOff();
        }, { once: true });
      }, function () { spotlightFollow(spotTarget); });
    });
  }

  // —— Puntos sobre capturas: pasar por un paso o una referencia resalta su punto, y viceversa.
  // Tocar un paso o una referencia lleva a su punto; tocar el punto lleva a su paso. Ambos quedan resaltados un momento.
  document.querySelectorAll('section.section').forEach(function (section) {
    if (!section.querySelector('.hotspot[data-hotspot]')) return;
    var linked = section.querySelectorAll('[data-hotspot]');
    var revealTimer = null;
    var highlight = function (number) {
      linked.forEach(function (element) { element.classList.toggle('is-highlighted', element.dataset.hotspot === number); });
      section.classList.toggle('has-hotspot-highlight', Boolean(number));
    };
    // Latido de destino: reinicia la animación si ya estaba latiendo; con "reducir movimiento" no late.
    var pulse = function (destination) {
      if (reduceMotion.matches) return;
      destination.classList.remove('is-pulsing');
      void destination.offsetWidth;
      destination.classList.add('is-pulsing');
      // El resaltado y la burbuja de vuelta terminan justo con el último latido (sin animación, a los HOTSPOT_REVEAL_MS).
      destination.addEventListener('animationend', function () {
        destination.classList.remove('is-pulsing');
        destination.classList.remove('is-revealed');
        clearTimeout(revealTimer);
        revealTimer = null;
        highlight('');
        spotlightOff();
      }, { once: true });
    };
    // Centra el destino en la pantalla, aunque ya se vea, y lo hace latir al llegar.
    var centerOn = function (destination) {
      centerOnTarget(destination, function () {
        spotlightOn(destination);
        pulse(destination);
      });
    };
    var reveal = function (number, selector) {
      var destination = section.querySelector(selector + '[data-hotspot="' + number + '"]');
      if (!destination) return;
      highlight(number);
      // Al llegar a un punto desde un paso, el punto muestra cómo volver mientras dura el resaltado.
      section.querySelectorAll('.hotspot.is-revealed').forEach(function (pin) { pin.classList.remove('is-revealed'); });
      if (destination.classList.contains('hotspot')) destination.classList.add('is-revealed');
      clearTimeout(revealTimer);
      revealTimer = setTimeout(function () {
        revealTimer = null;
        highlight('');
        destination.classList.remove('is-revealed');
      }, HOTSPOT_REVEAL_MS);
      centerOn(destination.querySelector('.step-circle') || destination);
    };
    // Pista en el pie de la primera captura con puntos: "Tocá" en pantallas táctiles y "Hacé click en" con mouse.
    var firstStage = section.querySelector('.hotspot-stage');
    var caption = firstStage && firstStage.closest('.mockup, .compare');
    caption = caption && caption.nextElementSibling;
    // Va después del pie, no adentro: el pie es la descripción accesible de la captura.
    if (caption && caption.classList.contains('figcap') && !(caption.nextElementSibling && caption.nextElementSibling.classList.contains('figcap-hint'))) {
      var hasSteps = Boolean(section.querySelector('.step-item[data-hotspot]'));
      var hint = createElement('div', 'figcap figcap-hint');
      var writeHint = function () {
        var pointer = finePointer.matches;
        hint.textContent = hasSteps ? (pointer ? ui.hintStepsPointer : ui.hintSteps) : (pointer ? ui.hintMentionsPointer : ui.hintMentions);
      };
      whenLanguage(writeHint);
      finePointer.addEventListener('change', writeHint);
      hint.setAttribute('aria-hidden', 'true');
      caption.after(hint);
    }
    section.querySelectorAll('.hotspot[data-hotspot]').forEach(function (pin) {
      if (!pin.querySelector('.hotspot-return')) pin.insertAdjacentHTML('beforeend', RETURN_SVG);
    });
    section.querySelectorAll('.step-item[data-hotspot]').forEach(function (step) {
      var circle = step.querySelector('.step-circle');
      if (!circle || circle.querySelector('.tap-hand')) return;
      circle.insertAdjacentHTML('beforeend', TAP_HAND_SVG);
    });
    linked.forEach(function (element) {
      var isPin = element.classList.contains('hotspot');
      var hasStep = Boolean(section.querySelector('.step-item[data-hotspot="' + element.dataset.hotspot + '"]'));
      // Del punto se va al paso (o, sin pasos, a la primera referencia); del paso o la referencia, al punto.
      var destinationSelector = isPin ? (hasStep ? '.step-item' : '.hotspot-ref') : '.hotspot';
      // El tooltip dice qué pasa al tocar.
      whenLanguage(function () { element.title = isPin ? (hasStep ? ui.goToStep + element.dataset.hotspot : ui.goToMention) : ui.seeInCapture; });
      // Mientras dura un salto, el resaltado es del destino: lo que pasa por debajo del puntero al
      // scrollear (otro punto, otro paso) no lo cambia.
      element.addEventListener('mouseenter', function () { if (!revealTimer) highlight(element.dataset.hotspot); });
      element.addEventListener('mouseleave', function () { if (!revealTimer) highlight(''); });
      // Un link dentro del paso (una sección, un término del glosario) va a su destino y no muestra el
      // tooltip del paso: el title vacío lo tapa.
      element.querySelectorAll('a[href]').forEach(function (link) { if (!link.hasAttribute('title')) link.setAttribute('title', ''); });
      element.addEventListener('click', function (event) {
        if (event.target.closest && event.target.closest('a[href]') && element.contains(event.target.closest('a[href]'))) return;
        // Una referencia dentro del texto de un paso ("«Cancelar» (3)" en el paso 2) lleva a su punto, no
        // al del paso que la contiene: el clic no sigue hasta el paso.
        if (element.classList.contains('hotspot-ref')) event.stopPropagation();
        reveal(element.dataset.hotspot, destinationSelector);
      });
      if (!element.classList.contains('hotspot-ref')) return;
      element.setAttribute('role', 'button');
      element.setAttribute('tabindex', '0');
      element.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        reveal(element.dataset.hotspot, destinationSelector);
      });
    });
  });

  // —— Accordions: la apertura y el cierre deslizan el cuerpo (alto, padding y opacidad) en vez de saltar.
  // Con "reducir movimiento" o sin Web Animations, el <details> nativo abre y cierra al instante.
  var motionDurationMs = function (factor) {
    var base = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--motion-duration-base')) || 200;
    return base * factor;
  };
  var motionEasing = getComputedStyle(document.documentElement).getPropertyValue('--motion-easing-standard').trim() || 'ease';
  // Nunca hay dos accordions abiertos: abrir uno (con un clic o con un salto) cierra, con la misma
  // animación, todos los demás abiertos del documento, salvo los que lo contienen.
  var setAccordion = function (accordion, opening) {
    var body = accordion.querySelector('.acc-body');
    if (!body) return;
    if (opening) {
      document.querySelectorAll('details.acc[open]').forEach(function (other) {
        if (other === accordion || other.contains(accordion) || accordion.contains(other) || other.classList.contains('is-closing')) return;
        setAccordion(other, false);
      });
    }
    if (reduceMotion.matches || !body.animate) { accordion.open = opening; return; }
    if (accordion.__accordionAnimation) accordion.__accordionAnimation.cancel();
    if (opening) accordion.open = true;
    accordion.classList.toggle('is-closing', !opening);
    var style = getComputedStyle(body);
    var expanded = { height: body.scrollHeight + 'px', paddingTop: style.paddingTop, paddingBottom: style.paddingBottom, opacity: 1 };
    var collapsed = { height: '0px', paddingTop: '0px', paddingBottom: '0px', opacity: 0 };
    body.classList.add('is-animating');
    var running = body.animate(opening ? [collapsed, expanded] : [expanded, collapsed], { duration: motionDurationMs(ACCORDION_FACTOR), easing: motionEasing });
    accordion.__accordionAnimation = running;
    running.onfinish = function () {
      accordion.__accordionAnimation = null;
      body.classList.remove('is-animating');
      accordion.classList.remove('is-closing');
      if (!opening) accordion.open = false;
    };
    running.oncancel = function () { body.classList.remove('is-animating'); };
  };
  document.querySelectorAll('details.acc').forEach(function (accordion) {
    var summary = accordion.querySelector('summary');
    if (!summary || !accordion.querySelector('.acc-body')) return;
    summary.addEventListener('click', function (event) {
      event.preventDefault();
      var opening = !accordion.open || accordion.classList.contains('is-closing');
      setAccordion(accordion, opening);
    });
  });

  // —— Comparación antes/después: un <input type="range"> nativo mueve el divisor (mouse, táctil y teclado).
  document.querySelectorAll('.compare').forEach(function (compare) {
    var range = compare.querySelector('.compare-range');
    if (!range) return;
    var update = function () {
      var value = Number(range.value);
      compare.style.setProperty('--compare-position', value + '%');
      range.setAttribute('aria-valuetext', ui.before + value + ui.after + (100 - value) + '%');
    };
    range.addEventListener('input', update);
    whenLanguage(update);
  });

  // —— Enlace directo al cargar: "Copiar enlace" da …#permissions, pero al abrirlo o recargarlo el salto nativo
  // ocurre antes de que se rendericen las capturas de arriba, y en visores embebidos el hash queda
  // en la página que envuelve al iframe. Se lee de los dos lados y se salta como desde el índice.
  function parentHash() {
    try { return window.parent !== window ? window.parent.location.hash : ''; } catch (crossOriginError) { return ''; }
  }
  function openDeepLink(hash) {
    var target = hash && hash.length > 1 && document.getElementById(decodeURIComponent(hash.slice(1)));
    if (target) scrollToTarget(target, false);
  }
  function openDeepLinkId(id) { if (id) openDeepLink('#' + encodeURIComponent(id)); }
  // Con adaptador de visor, el destino también sale de la URL pública (al cargar y con Atrás/Adelante del
  // visor). El hash del visor sigue valiendo como respaldo: los enlaces copiados antes del adaptador
  // (…/view#faq) no dejan de llegar a su sección.
  var openInitialLink = function () {
    var adapter = viewerAdapter();
    var adapterTarget = adapter && adapter.initialTargetId();
    if (location.hash.length > 1) openDeepLink(location.hash);
    else if (adapterTarget) openDeepLinkId(adapterTarget);
    else openDeepLink(parentHash());
    if (adapter) adapter.onNavigate(openDeepLinkId);
    // El visor copia a su barra el hash que deja el índice; solo un hash distinto (pegado por el lector) mueve el documento.
    try {
      if (window.parent !== window) window.parent.addEventListener('hashchange', function () { if (parentHash() !== location.hash) openDeepLink(parentHash()); });
    } catch (crossOriginError) { /* fallback deliberado: visor de otro origen, solo el hash propio */ }
  };
  // DOMContentLoaded: después de todos los scripts, así las capturas diferidas y el adaptador del visor ya están.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', openInitialLink, { once: true });
  else setTimeout(openInitialLink, 0);
  window.addEventListener('hashchange', function () { openDeepLink(location.hash); });

  // —— Cambio de idioma en la misma página: el script de idioma ya tradujo el contenido.
  document.addEventListener('heritage:language-change', function (event) {
    language = event.detail.language;
    ui = UI_TEXT[language] || UI_TEXT.es;
    entries.forEach(readEntryText);
    relabels.forEach(function (apply) { apply(); });
    hidePreview();
    hideTermCard();
    updateCurrent();
  });
})();
