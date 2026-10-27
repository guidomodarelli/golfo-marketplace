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
