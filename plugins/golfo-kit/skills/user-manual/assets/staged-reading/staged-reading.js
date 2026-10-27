// Lectura por etapas Heritage: muestra una etapa por vez (o todas con «Ver todo»), con menú a la derecha
// desde 820px y barra compacta con sidebar modal debajo. Una etapa puede agruparse en capítulos. Solo decide
// qué se ve, el selector, el contenido de la etapa activa y la orientación de etapas y capítulos; el scroll,
// los enlaces, el mapa, la píldora, las capturas y el foco siguen en el script de navegación del boilerplate
// (window.HeritageNavigation y heritage:before-scroll).
// Sin JavaScript, o si el marcado de etapas no es válido, el documento se lee completo y lineal.
(function () {
  var STAGED_MODE = 'stages';
  var WORDS_PER_MINUTE = 200;
  var KEY_CONCEPTS_PER_STAGE = 3;
  var MIN_STAGES = 2;
  var MIN_SECTIONS_PER_CHAPTER = 2;
  var DESKTOP_QUERY = '(min-width: 820px)';
  var STAGE_ID_PATTERN = /^[a-z][a-z0-9-]*$/;
  // Una etapa cuenta como leída cuando se ve la mitad de su recapitulación.
  var RECAP_READ_RATIO = 0.5;
  // Texto que no se lee como contenido: controles que agrega el script y piezas decorativas.
  var NOT_READ = 'script, style, button, [aria-hidden="true"], .visually-hidden';
  var BLOCKS = '.stage-intro, .stage-chapter, section.section, .stage-recap';
  var UI_TEXT = {
    es: {
      stages: 'Etapas', viewAll: 'Ver todo', close: 'Cerrar', stage: 'Etapa ', wholeManual: 'Todo el manual',
      openStages: 'Abrir el selector de etapas. ', minutes: ' min', read: 'leída', previous: 'Etapa anterior: ', next: 'Etapa siguiente: ',
      outline: 'Contenido de la etapa ',
      position: function (number, total, minutes) { return 'Etapa ' + number + ' de ' + total + ' · ' + minutes + ' min'; },
      reading: function (minutes) { return 'Lectura estimada: ' + minutes + ' min (referencia de ' + WORDS_PER_MINUTE + ' palabras por minuto; no incluye ejercicios ni simuladores).'; },
      chapterReading: function (minutes) { return 'Lectura estimada del capítulo: ' + minutes + ' min.'; }
    },
    pt: {
      stages: 'Etapas', viewAll: 'Ver tudo', close: 'Fechar', stage: 'Etapa ', wholeManual: 'Manual completo',
      openStages: 'Abrir o seletor de etapas. ', minutes: ' min', read: 'lida', previous: 'Etapa anterior: ', next: 'Próxima etapa: ',
      outline: 'Conteúdo da etapa ',
      position: function (number, total, minutes) { return 'Etapa ' + number + ' de ' + total + ' · ' + minutes + ' min'; },
      reading: function (minutes) { return 'Leitura estimada: ' + minutes + ' min (referência de ' + WORDS_PER_MINUTE + ' palavras por minuto; não inclui exercícios nem simuladores).'; },
      chapterReading: function (minutes) { return 'Leitura estimada do capítulo: ' + minutes + ' min.'; }
    }
  };

  var modeMeta = document.querySelector('meta[name="heritage:reading-mode"]');
  if (!modeMeta || modeMeta.content !== STAGED_MODE) return;
  var root = document.documentElement;
  var language = root.getAttribute('data-language') || 'es';
  var ui = UI_TEXT[language] || UI_TEXT.es;
  var navigation = window.HeritageNavigation;

  // —— Modelo único: por etapa, intro, capítulos opcionales con sus secciones contiguas y recapitulación,
  // en el orden del documento. Menú, hoja del índice, mapa y enlaces salen de acá.
  function readStages() {
    var stages = [];
    var chapterIds = [];
    var problems = [];
    var open = null;
    var closeChapter = function () {
      var chapter = open && open.chapters[open.chapters.length - 1];
      if (chapter && chapter.sections.length < MIN_SECTIONS_PER_CHAPTER) problems.push('chapter "' + chapter.id + '" needs at least ' + MIN_SECTIONS_PER_CHAPTER + ' sections');
    };
    document.querySelectorAll(BLOCKS).forEach(function (block) {
      if (block.matches('.stage-intro')) {
        var id = block.getAttribute('data-stage-intro') || '';
        if (open) problems.push('stage "' + open.id + '" has no .stage-recap before stage "' + id + '"');
        if (!STAGE_ID_PATTERN.test(id)) problems.push('stage id "' + id + '" is not a kebab-case slug');
        if (stages.some(function (stage) { return stage.id === id; })) problems.push('stage "' + id + '" is repeated');
        if (block.id !== 'stage-' + id) problems.push('stage "' + id + '" intro needs id="stage-' + id + '"');
        if (!block.querySelector('.stage-title') || !block.querySelector('.stage-objective') || !block.querySelector('.stage-reading')) problems.push('stage "' + id + '" intro needs .stage-title, .stage-objective and .stage-reading');
        open = { id: id, intro: block, chapters: [], sections: [], recap: null };
        stages.push(open);
        return;
      }
      if (block.matches('.stage-chapter')) {
        var chapterId = block.getAttribute('data-chapter') || '';
        if (!open) { problems.push('chapter "' + chapterId + '" is outside a stage'); return; }
        if (block.getAttribute('data-stage') !== open.id) problems.push('chapter "' + chapterId + '" has data-stage="' + block.getAttribute('data-stage') + '" inside stage "' + open.id + '"');
        if (!STAGE_ID_PATTERN.test(chapterId)) problems.push('chapter id "' + chapterId + '" is not a kebab-case slug');
        if (chapterIds.indexOf(chapterId) !== -1) problems.push('chapter "' + chapterId + '" is repeated');
        if (block.id !== 'chapter-' + chapterId) problems.push('chapter "' + chapterId + '" needs id="chapter-' + chapterId + '"');
        if (!block.querySelector('.stage-chapter-title')) problems.push('chapter "' + chapterId + '" needs .stage-chapter-title');
        if (!open.chapters.length && open.sections.length) problems.push('stage "' + open.id + '" has sections before its first chapter');
        closeChapter();
        chapterIds.push(chapterId);
        open.chapters.push({ id: chapterId, element: block, stage: open, sections: [] });
        return;
      }
      if (block.matches('.stage-recap')) {
        var recapId = block.getAttribute('data-stage-recap');
        if (!open || recapId !== open.id) { problems.push('recap "' + recapId + '" does not close the open stage'); return; }
        if (!open.sections.length) problems.push('stage "' + open.id + '" has no sections');
        if (block.querySelectorAll('.stage-concepts > li').length !== KEY_CONCEPTS_PER_STAGE) problems.push('stage "' + open.id + '" recap needs exactly ' + KEY_CONCEPTS_PER_STAGE + ' key concepts');
        if (!block.querySelector('.stage-next')) problems.push('stage "' + open.id + '" recap needs .stage-next');
        closeChapter();
        open.recap = block;
        open = null;
        return;
      }
      var sectionId = block.getAttribute('aria-labelledby');
      var sectionStage = block.getAttribute('data-stage');
      if (!open) problems.push('section "' + sectionId + '" is outside a stage');
      else if (sectionStage !== open.id) problems.push('section "' + sectionId + '" has data-stage="' + sectionStage + '" inside stage "' + open.id + '"');
      else {
        open.sections.push(block);
        if (open.chapters.length) open.chapters[open.chapters.length - 1].sections.push(block);
      }
    });
    if (open) problems.push('stage "' + open.id + '" has no .stage-recap');
    if (stages.length < MIN_STAGES) problems.push('a staged manual needs at least ' + MIN_STAGES + ' stages');
    if (!navigation) problems.push('window.HeritageNavigation is missing (copy the current boilerplate navigation script)');
    return { stages: stages, problems: problems };
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
    });
    if (!stage.intro.hasAttribute('tabindex')) stage.intro.setAttribute('tabindex', '-1');
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
    groupStart(sectionId(stage.sections[0]), 'stage-sheet-stage', function () { return ui.stage + stage.number + ' · ' + stageTitle(stage); }, stageIndex > 0);
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
    barStatus.textContent = state.mode === 'all' ? ui.wholeManual : ui.stage + state.stage.number + '/' + stages.length + ' · ' + stageTitle(state.stage);
    barStatus.title = barStatus.textContent;
    barToggle.setAttribute('aria-label', ui.openStages + barStatus.textContent);
  }
  function writeProgress(stage) {
    stage.optionStatus.hidden = !stage.read;
    stage.optionStatus.textContent = ui.read;
    stage.option.toggleAttribute('data-read', stage.read);
  }
  function writeTexts() {
    menuLabel.textContent = ui.stages;
    drawerLabel.textContent = ui.stages;
    drawerClose.textContent = ui.close;
    barToggle.textContent = ui.stages;
    allOption.textContent = ui.viewAll;
    stages.forEach(function (stage, index) {
      stage.optionTitle.textContent = stageTitle(stage);
      stage.optionMeta.textContent = stage.minutes + ui.minutes;
      stage.outline.setAttribute('aria-label', ui.outline + stageTitle(stage));
      stage.intro.querySelector('.stage-reading').textContent = ui.reading(stage.minutes);
      stage.position.textContent = ui.position(stage.number, stages.length, stage.minutes);
      if (stage.previousButton) stage.previousButton.textContent = ui.previous + stageTitle(stages[index - 1]);
      if (stage.nextButton) stage.nextButton.textContent = ui.next + stageTitle(stages[index + 1]);
      stage.chapters.forEach(function (chapter) {
        var reading = chapter.element.querySelector('.stage-chapter-reading');
        if (reading) reading.textContent = ui.chapterReading(chapter.minutes);
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
        if (!entry.isIntersecting) return;
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

  document.addEventListener('heritage:language-change', function (event) {
    language = event.detail.language;
    ui = UI_TEXT[language] || UI_TEXT.es;
    writeTexts();
  });

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
