// Lectura por etapas Heritage: muestra una etapa por vez (o todas con «Ver todo»), con menú a la derecha
// desde 820px y barra compacta con sidebar modal debajo. Una etapa puede agruparse en capítulos. Solo decide
// qué se ve, el selector, el contenido de la etapa activa y la orientación de etapas y capítulos; el scroll,
// los enlaces, el mapa, la píldora, las capturas y el foco siguen en el script de navegación del boilerplate
// (window.HeritageNavigation y heritage:before-scroll).
// Sin JavaScript, o si el marcado de etapas no es válido, el documento se lee completo y lineal.
(function () {
  var STAGED_MODE = 'stages';
  var WORDS_PER_MINUTE = 200;
  var DESKTOP_QUERY = '(min-width: 820px)';
  // Nivel anunciado de un capítulo: debajo de la etapa (h2).
  var CHAPTER_HEADING_LEVEL = 3;
  // Una etapa cuenta como leída cuando se ve la mitad de su recapitulación.
  var RECAP_READ_RATIO = 0.5;
  // Texto que no se lee como contenido: controles que agrega el script y piezas decorativas.
  var NOT_READ = 'script, style, button, [aria-hidden="true"], .visually-hidden';
  var BLOCKS = '.stage-intro, .stage-chapter, section.section, .stage-recap';
  var modeMeta = document.querySelector('meta[name="heritage:reading-mode"]');
  if (!modeMeta || modeMeta.content !== STAGED_MODE) return;
  var root = document.documentElement;
  var navigation = window.HeritageNavigation;
  // Textos de interfaz: el diccionario único del script de navegación (UI_TEXT), en el idioma actual.
  function text(key, values) { return navigation.text(key, values); }

  // —— Modelo único: las reglas viven en el contrato de etapas (window.HeritageStageContract), el mismo que
  // usa check-manual.mjs. Acá solo se describen los bloques del DOM y se arma el modelo con sus índices.
  function readStages() {
    var contract = window.HeritageStageContract;
    if (!contract) return { stages: [], problems: ['window.HeritageStageContract is missing (embed assets/staged-reading/stage-contract.js)'] };
    var elements = [].slice.call(document.querySelectorAll(BLOCKS));
    var descriptors = elements.map(function (element) {
      return {
        kind: contract.kindOf(element.tagName.toLowerCase(), element.className),
        id: element.id,
        stage: element.getAttribute('data-stage-intro') || element.getAttribute('data-stage') || element.getAttribute('data-stage-recap'),
        chapter: element.getAttribute('data-chapter'),
        sectionId: element.getAttribute('aria-labelledby'),
        parts: {
          title: Boolean(element.querySelector('.stage-title')),
          objective: Boolean(element.querySelector('.stage-objective')),
          reading: Boolean(element.querySelector('.stage-reading')),
          chapterTitle: Boolean(element.querySelector('.stage-chapter-title')),
          next: Boolean(element.querySelector('.stage-next'))
        },
        concepts: element.querySelectorAll('.stage-concepts > li').length
      };
    });
    var result = contract.validate(descriptors);
    if (!navigation || !navigation.text) result.problems.push('window.HeritageNavigation is missing or outdated (refresh the manual with scripts/build-manual.mjs)');
    var stages = result.stages.map(function (stage) {
      var model = { id: stage.id, intro: elements[stage.intro], recap: elements[stage.recap], sections: stage.sections.map(function (index) { return elements[index]; }), chapters: [] };
      model.chapters = stage.chapters.map(function (chapter) {
        return { id: chapter.id, element: elements[chapter.element], stage: model, sections: chapter.sections.map(function (index) { return elements[index]; }) };
      });
      return model;
    });
    return { stages: stages, problems: result.problems };
  }
  var model = readStages();
  if (model.problems.length) {
    root.setAttribute('data-reading-mode', 'linear-fallback');
    console.warn('Heritage:stagedReading disabled: invalid stage markup, the manual stays linear', { problems: model.problems });
    return;
  }
  var stages = model.stages;

  function createElement(tagName, className, text) {
    var element = document.createElement(tagName);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }
  function textOf(element) { return element ? element.textContent.replace(/\s+/g, ' ').trim() : ''; }
  function stageBlocks(stage) {
    return [stage.intro].concat(stage.chapters.map(function (chapter) { return chapter.element; }), stage.sections, [stage.recap]);
  }
  function stageOf(element) {
    var block = element && element.closest && element.closest(BLOCKS);
    if (!block) return null;
    var id = block.getAttribute('data-stage-intro') || block.getAttribute('data-stage') || block.getAttribute('data-stage-recap');
    return stages.filter(function (stage) { return stage.id === id; })[0] || null;
  }
  function sectionHeading(section) { return section.querySelector('.section-title'); }
  function sectionId(section) {
    var heading = sectionHeading(section);
    return heading ? heading.id : section.getAttribute('aria-labelledby');
  }
  function stageTitle(stage) { return textOf(stage.intro.querySelector('.stage-title')); }
  function chapterTitle(chapter) { return textOf(chapter.element.querySelector('.stage-chapter-title')); }

  // —— Lectura estimada: palabras de las secciones a una tasa de referencia, nunca menos de 1 min.
  function countWords(sections) {
    var words = 0;
    sections.forEach(function (section) {
      var walker = document.createTreeWalker(section, NodeFilter.SHOW_TEXT, {
        acceptNode: function (node) { return node.parentElement.closest(NOT_READ) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; }
      });
      for (var node = walker.nextNode(); node; node = walker.nextNode()) words += (node.textContent.match(/\S+/g) || []).length;
    });
    return words;
  }
  function minutesFor(sections) { return Math.max(1, Math.ceil(countWords(sections) / WORDS_PER_MINUTE)); }
  stages.forEach(function (stage, index) {
    stage.number = index + 1;
    stage.minutes = minutesFor(stage.sections);
    stage.read = false;
    stage.chapters.forEach(function (chapter) {
      chapter.minutes = minutesFor(chapter.sections);
      if (!chapter.element.hasAttribute('tabindex')) chapter.element.setAttribute('tabindex', '-1');
      chapter.element.querySelector('.stage-chapter-title').setAttribute('aria-level', String(CHAPTER_HEADING_LEVEL));
    });
    if (!stage.intro.hasAttribute('tabindex')) stage.intro.setAttribute('tabindex', '-1');
    // Jerarquía para lectores de pantalla: etapa (h2) > capítulo > sección. Los títulos de sección siguen
    // siendo h2 (contrato de clases y del índice); solo cambia el nivel que se anuncia.
    var sectionLevel = stage.chapters.length ? CHAPTER_HEADING_LEVEL + 1 : CHAPTER_HEADING_LEVEL;
    stage.sections.forEach(function (section) {
      var heading = sectionHeading(section);
      if (heading) heading.setAttribute('aria-level', String(sectionLevel));
    });
  });

  // —— Controles: los mismos nodos van al menú (escritorio) o al sidebar modal (pantallas angostas).
  var controls = createElement('div', 'stage-controls');
  var list = createElement('ol', 'stage-list');

  // Contenido de la etapa activa en el menú: capítulos y secciones, para ir directo sin abrir el índice.
  function outlineLink(target, label, number) {
    var link = createElement('a', 'stage-outline-link');
    link.href = '#' + target.id;
    if (number) link.appendChild(createElement('span', 'stage-outline-num', number));
    link.appendChild(createElement('span', 'stage-outline-title', label));
    link.addEventListener('click', function (event) {
      event.preventDefault();
      closeDrawer(false);
      navigation.scrollTo(target, true);
    });
    return link;
  }
  // El número es el primer texto de .section-num: el boilerplate le suma después el botón «Copiar enlace».
  function sectionNumber(section) {
    var numberElement = section.querySelector('.section-num');
    return numberElement && numberElement.firstChild ? numberElement.firstChild.textContent.trim() : '';
  }
  function sectionItems(sections, className) {
    var items = createElement('ol', className);
    sections.forEach(function (section) {
      var item = createElement('li');
      item.appendChild(outlineLink(sectionHeading(section), textOf(sectionHeading(section)), sectionNumber(section)));
      items.appendChild(item);
    });
    return items;
  }
  function buildOutline(stage) {
    var outline = stage.chapters.length ? createElement('ol', 'stage-outline') : sectionItems(stage.sections, 'stage-outline');
    outline.id = 'stage-outline-' + stage.id;
    stage.chapters.forEach(function (chapter) {
      var item = createElement('li', 'stage-outline-chapter');
      chapter.outlineLink = outlineLink(chapter.element, chapterTitle(chapter));
      item.append(chapter.outlineLink, sectionItems(chapter.sections, 'stage-outline-sections'));
      outline.appendChild(item);
    });
    return outline;
  }

  stages.forEach(function (stage) {
    var item = createElement('li');
    stage.option = createElement('button', 'stage-option');
    stage.option.type = 'button';
    stage.optionTitle = createElement('span', 'stage-option-title');
    stage.optionMeta = createElement('span', 'stage-option-meta');
    stage.optionStatus = createElement('span', 'stage-option-status');
    stage.optionStatus.hidden = true;
    stage.option.append(createElement('span', 'stage-option-num', String(stage.number).padStart(2, '0')), stage.optionTitle, stage.optionStatus, stage.optionMeta);
    stage.option.addEventListener('click', function () { chooseStage(stage); });
    stage.outline = buildOutline(stage);
    stage.option.setAttribute('aria-controls', stage.outline.id);
    item.append(stage.option, stage.outline);
    list.appendChild(item);
  });
  var allOption = createElement('button', 'stage-option stage-option-all');
  allOption.type = 'button';
  allOption.addEventListener('click', chooseAll);
  controls.append(list, allOption);

  var menu = createElement('nav', 'stage-menu');
  var menuLabel = createElement('div', 'stage-menu-label');
  menuLabel.id = 'stage-menu-label';
  menu.setAttribute('aria-labelledby', menuLabel.id);
  menu.appendChild(menuLabel);

  // Barra compacta: dice en qué etapa se está y abre el sidebar. El scroll de los saltos la tiene en cuenta.
  var bar = createElement('div', 'stage-bar');
  bar.setAttribute('data-heritage-offset', '');
  var barStatus = createElement('span', 'stage-bar-status');
  var barToggle = createElement('button', 'stage-bar-toggle');
  barToggle.type = 'button';
  barToggle.setAttribute('aria-haspopup', 'dialog');
  barToggle.setAttribute('aria-controls', 'stage-drawer');
  barToggle.setAttribute('aria-expanded', 'false');
  bar.append(barStatus, barToggle);

  var drawer = createElement('dialog', 'stage-drawer');
  drawer.id = 'stage-drawer';
  var drawerBody = createElement('div', 'stage-drawer-body');
  var drawerHead = createElement('div', 'stage-drawer-head');
  var drawerLabel = createElement('div', 'stage-menu-label');
  drawerLabel.id = 'stage-drawer-label';
  drawer.setAttribute('aria-labelledby', drawerLabel.id);
  var drawerClose = createElement('button', 'stage-drawer-close');
  drawerClose.type = 'button';
  drawerHead.append(drawerLabel, drawerClose);
  drawerBody.appendChild(drawerHead);
  drawer.appendChild(drawerBody);

  var header = document.getElementById('top');
  if (header) header.after(bar); else document.body.prepend(bar);
  document.body.append(menu, drawer);

  // —— Orientación dentro del documento: posición en la recapitulación, paso a la etapa vecina y lectura
  // estimada de cada capítulo.
  stages.forEach(function (stage, index) {
    stage.position = createElement('p', 'stage-recap-meta');
    var label = stage.recap.querySelector('.stage-recap-label');
    if (label) label.after(stage.position); else stage.recap.prepend(stage.position);
    var pager = createElement('div', 'stage-pager');
    stage.previousButton = index ? createElement('button', 'stage-pager-previous') : null;
    stage.nextButton = index < stages.length - 1 ? createElement('button', 'stage-pager-next') : null;
    [[stage.previousButton, stages[index - 1]], [stage.nextButton, stages[index + 1]]].forEach(function (pair) {
      if (!pair[0]) return;
      pair[0].type = 'button';
      pair[0].addEventListener('click', function () { chooseStage(pair[1]); });
      pager.appendChild(pair[0]);
    });
    if (pager.children.length) stage.recap.appendChild(pager);
  });

  // —— Hoja del índice (la arma el boilerplate con todas las secciones): etiquetas de etapa y capítulo
  // antes de su primera sección. Mapa: un respiro entre grupos.
  var sheetGroupLabels = [];
  // separated: la marca del mapa deja un respiro arriba (no la primera sección, que ya sigue al inicio).
  function groupStart(id, className, text, separated) {
    var railLink = document.querySelector('.section-rail a[href="#' + id + '"]');
    if (railLink && separated) railLink.parentElement.classList.add('stage-rail-group-start');
    var sheetLink = document.querySelector('.toc-sheet a[href="#' + id + '"]');
    if (!sheetLink) return;
    var item = createElement('li', 'stage-sheet-group');
    var label = createElement('div', 'toc-label ' + className);
    item.appendChild(label);
    sheetLink.closest('li').before(item);
    sheetGroupLabels.push({ element: label, text: text });
  }
  stages.forEach(function (stage, stageIndex) {
    groupStart(sectionId(stage.sections[0]), 'stage-sheet-stage', function () { return text('stage') + stage.number + ' · ' + stageTitle(stage); }, stageIndex > 0);
    stage.chapters.forEach(function (chapter, chapterIndex) {
      groupStart(sectionId(chapter.sections[0]), 'stage-sheet-chapter', function () { return chapterTitle(chapter); }, chapterIndex > 0);
    });
  });

  var desktop = window.matchMedia(DESKTOP_QUERY);
  function placeControls() {
    var container = desktop.matches ? menu : drawerBody;
    if (controls.parentNode !== container) container.appendChild(controls);
  }

  // —— Estado: una etapa visible o todo el manual.
  var state = { mode: 'stage', stage: stages[0] };
  function render() {
    stages.forEach(function (stage) {
      var visible = state.mode === 'all' || stage === state.stage;
      var active = state.mode === 'stage' && stage === state.stage;
      stageBlocks(stage).forEach(function (block) {
        block.hidden = !visible;
        block.toggleAttribute('data-stage-hidden', !visible);
      });
      stage.option.setAttribute('aria-pressed', String(active));
      stage.option.setAttribute('aria-expanded', String(active));
      stage.outline.hidden = !active;
    });
    allOption.setAttribute('aria-pressed', String(state.mode === 'all'));
    writeStatus();
    document.dispatchEvent(new CustomEvent('heritage:visibility-change', { detail: { mode: state.mode, stage: state.stage.id } }));
  }
  function setState(mode, stage) {
    state = { mode: mode, stage: stage || state.stage };
    render();
  }
  function writeStatus() {
    barStatus.textContent = state.mode === 'all' ? text('stageWholeManual') : text('stage') + state.stage.number + '/' + stages.length + ' · ' + stageTitle(state.stage);
    barStatus.title = barStatus.textContent;
    barToggle.setAttribute('aria-label', text('stageOpenSelector') + barStatus.textContent);
  }
  function writeProgress(stage) {
    stage.optionStatus.hidden = !stage.read;
    stage.optionStatus.textContent = text('stageRead');
    stage.option.toggleAttribute('data-read', stage.read);
  }
  function writeTexts() {
    menuLabel.textContent = text('stages');
    drawerLabel.textContent = text('stages');
    drawerClose.textContent = text('close');
    barToggle.textContent = text('stages');
    allOption.textContent = text('stageViewAll');
    stages.forEach(function (stage, index) {
      stage.optionTitle.textContent = stageTitle(stage);
      stage.optionMeta.textContent = stage.minutes + text('stageMinutes');
      stage.outline.setAttribute('aria-label', text('stageOutline') + stageTitle(stage));
      stage.intro.querySelector('.stage-reading').textContent = text('stageReading', { minutes: stage.minutes, rate: WORDS_PER_MINUTE });
      stage.position.textContent = text('stagePosition', { number: stage.number, total: stages.length, minutes: stage.minutes });
      if (stage.previousButton) stage.previousButton.textContent = text('stagePrevious') + stageTitle(stages[index - 1]);
      if (stage.nextButton) stage.nextButton.textContent = text('stageNext') + stageTitle(stages[index + 1]);
      stage.chapters.forEach(function (chapter) {
        var reading = chapter.element.querySelector('.stage-chapter-reading');
        if (reading) reading.textContent = text('chapterReading', { minutes: chapter.minutes });
        if (chapter.outlineLink) chapter.outlineLink.querySelector('.stage-outline-title').textContent = chapterTitle(chapter);
      });
      writeProgress(stage);
    });
    sheetGroupLabels.forEach(function (group) { group.element.textContent = group.text(); });
    writeStatus();
  }

  // —— Progreso: una etapa queda leída al llegar a su recapitulación (solo en esta visita, sin guardar nada).
  if (window.IntersectionObserver) {
    var recapObserver = new IntersectionObserver(function (observed) {
      observed.forEach(function (entry) {
        // El observer también avisa cuando el recap apenas entra (cambio de isIntersecting): exigir la proporción.
        if (!entry.isIntersecting || entry.intersectionRatio < RECAP_READ_RATIO) return;
        var stage = stageOf(entry.target);
        if (!stage || stage.read) return;
        stage.read = true;
        writeProgress(stage);
        recapObserver.unobserve(entry.target);
      });
    }, { threshold: RECAP_READ_RATIO });
    stages.forEach(function (stage) { recapObserver.observe(stage.recap); });
  }

  // —— Sidebar modal: foco confinado por showModal, Escape y toque fuera lo cierran y devuelven el foco.
  function openDrawer() {
    placeControls();
    drawer.showModal();
    root.classList.add('has-open-stage-drawer');
    barToggle.setAttribute('aria-expanded', 'true');
    var pressed = controls.querySelector('[aria-pressed="true"]');
    if (pressed) pressed.focus();
  }
  function closeDrawer(restoreFocus) {
    if (drawer.open) drawer.close();
    if (restoreFocus) barToggle.focus();
  }
  drawer.addEventListener('close', function () {
    root.classList.remove('has-open-stage-drawer');
    barToggle.setAttribute('aria-expanded', 'false');
  });
  drawer.addEventListener('cancel', function (event) { event.preventDefault(); closeDrawer(true); });
  // showModal deja el fondo inerte, pero Tab puede salir a la interfaz del navegador: el foco da la vuelta.
  drawer.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab') return;
    var focusable = [].filter.call(drawer.querySelectorAll('button, a[href]'), function (control) { return !control.disabled && control.getClientRects().length; });
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  drawer.addEventListener('click', function (event) { if (event.target === drawer) closeDrawer(true); });
  drawerClose.addEventListener('click', function () { closeDrawer(true); });
  barToggle.addEventListener('click', openDrawer);
  // Al cruzar el breakpoint el sidebar se cierra (libera el scroll) y los controles vuelven al menú.
  desktop.addEventListener('change', function () {
    var focusWasInDrawer = drawer.contains(document.activeElement);
    closeDrawer(false);
    placeControls();
    if (focusWasInDrawer) (desktop.matches ? controls.querySelector('[aria-pressed="true"]') : barToggle).focus();
  });

  // —— Elegir: una etapa muestra su orientación y deja el enlace en su primera sección; «Ver todo» mantiene
  // en pantalla lo que se estaba leyendo.
  function chooseStage(stage) {
    closeDrawer(false);
    setState('stage', stage);
    navigation.scrollTo(stage.intro, false);
    navigation.setLocation(sectionId(stage.sections[0]));
  }
  function chooseAll() {
    var anchor = null;
    stageBlocks(state.stage).some(function (block) {
      var box = block.getBoundingClientRect();
      if (box.height && box.bottom > 0) anchor = { element: block, offset: box.top };
      return Boolean(anchor);
    });
    var fromDrawer = drawer.open;
    closeDrawer(fromDrawer);
    setState('all');
    if (anchor && window.scrollY > 0) window.scrollTo({ top: anchor.element.getBoundingClientRect().top + window.scrollY - anchor.offset, behavior: 'instant' });
  }

  // —— Cualquier salto (índice, mapa, glosario, enlace directo, historial, visor) avisa antes de medir:
  // si el destino está en otra etapa, esa etapa se muestra primero.
  document.addEventListener('heritage:before-scroll', function (event) {
    var stage = stageOf(event.detail && event.detail.target);
    if (stage && state.mode === 'stage' && stage !== state.stage) setState('stage', stage);
  });

  // —— Impresión: todas las etapas; al terminar, vuelve el estado anterior.
  var beforePrint = null;
  window.addEventListener('beforeprint', function () {
    if (beforePrint) return;
    beforePrint = state;
    setState('all');
  });
  window.addEventListener('afterprint', function () {
    if (!beforePrint) return;
    var previous = beforePrint;
    beforePrint = null;
    setState(previous.mode, previous.stage);
  });

  // El script de navegación ya cambió su diccionario: solo hay que reescribir los textos.
  document.addEventListener('heritage:language-change', writeTexts);

  // Estado inicial: la etapa del destino del enlace (propio o del visor), o la primera.
  var adapter = window.HeritageViewer;
  var initialId = location.hash.length > 1 ? decodeURIComponent(location.hash.slice(1)) : adapter && adapter.initialTargetId ? adapter.initialTargetId() : null;
  var initialStage = (initialId && stageOf(document.getElementById(initialId))) || stages[0];
  placeControls();
  writeTexts();
  root.classList.add('has-stages');
  root.setAttribute('data-reading-mode', STAGED_MODE);
  setState('stage', initialStage);

  window.HeritageStages = {
    state: function () { return { mode: state.mode, stage: state.stage.id, stages: stages.map(function (stage) { return stage.id; }) }; },
    sectionsOf: function (id) {
      var stage = stages.filter(function (candidate) { return candidate.id === id; })[0];
      return stage ? stage.sections.map(function (section) { return section.getAttribute('aria-labelledby'); }) : [];
    },
    chaptersOf: function (id) {
      var stage = stages.filter(function (candidate) { return candidate.id === id; })[0];
      return stage ? stage.chapters.map(function (chapter) { return { id: chapter.id, sections: chapter.sections.map(function (section) { return section.getAttribute('aria-labelledby'); }) }; }) : [];
    },
    progress: function () { return stages.filter(function (stage) { return stage.read; }).map(function (stage) { return stage.id; }); }
  };
})();
