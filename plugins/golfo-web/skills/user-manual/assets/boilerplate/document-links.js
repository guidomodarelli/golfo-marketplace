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
