// Contrato de etapas Heritage: única definición de las reglas de etapas y capítulos. La usan el script de
// etapas en el navegador (antes de ocultar nada) y check-manual.mjs (sobre el HTML), así la activación y la
// validación no pueden divergir. Cada uno traduce sus bloques a descriptores y llama a validate().
(function (root) {
  var STAGE_ID_PATTERN = /^[a-z][a-z0-9-]*$/;
  var KEY_CONCEPTS_PER_STAGE = 3;
  var MIN_STAGES = 2;
  var MIN_SECTIONS_PER_CHAPTER = 2;
  // Clases que marcan cada bloque (como token: el bloque puede tener más clases).
  var BLOCK_KINDS = { 'stage-intro': 'intro', 'stage-chapter': 'chapter', section: 'section', 'stage-recap': 'recap' };

  /**
   * Tipo de bloque según sus clases y su etiqueta (una sección es siempre un <section class="section">).
   * @param {string} tagName etiqueta en minúsculas.
   * @param {string} className valor del atributo class.
   * @returns {string|null} intro, chapter, section, recap o null.
   */
  function kindOf(tagName, className) {
    var tokens = (className || '').split(/\s+/);
    for (var index = 0; index < tokens.length; index++) {
      var kind = BLOCK_KINDS[tokens[index]];
      if (kind && (kind !== 'section' || tagName === 'section')) return kind;
    }
    return null;
  }

  /**
   * Valida los bloques en orden de documento y arma el modelo de etapas.
   * Cada descriptor: { kind, id, stage, chapter, sectionId, parts: { title, objective, reading, chapterTitle, next }, concepts }.
   * @returns {{ stages: Array, problems: string[] }} stages con índices de bloque (intro, chapters, sections, recap).
   */
  function validate(blocks) {
    var stages = [];
    var chapterIds = [];
    var problems = [];
    var open = null;
    var closeChapter = function () {
      var chapter = open && open.chapters[open.chapters.length - 1];
      if (chapter && chapter.sections.length < MIN_SECTIONS_PER_CHAPTER) problems.push('chapter "' + chapter.id + '" has ' + chapter.sections.length + ' section(s); it needs at least ' + MIN_SECTIONS_PER_CHAPTER);
    };
    blocks.forEach(function (block, index) {
      var parts = block.parts || {};
      if (block.kind === 'intro') {
        var id = block.stage || '';
        if (open) problems.push('stage "' + open.id + '" has no .stage-recap before stage "' + id + '"');
        if (!STAGE_ID_PATTERN.test(id)) problems.push('stage id "' + id + '" is not a kebab-case slug');
        if (stages.some(function (stage) { return stage.id === id; })) problems.push('stage "' + id + '" is repeated');
        if (block.id !== 'stage-' + id) problems.push('stage "' + id + '" intro needs id="stage-' + id + '"');
        ['title', 'objective', 'reading'].forEach(function (part) { if (!parts[part]) problems.push('stage "' + id + '" intro has no .stage-' + part); });
        open = { id: id, intro: index, chapters: [], sections: [], recap: null };
        stages.push(open);
      } else if (block.kind === 'chapter') {
        var chapterId = block.chapter || '';
        if (!open) { problems.push('chapter "' + chapterId + '" is outside a stage'); return; }
        if (block.stage !== open.id) problems.push('chapter "' + chapterId + '" has data-stage="' + (block.stage || '') + '" inside stage "' + open.id + '"');
        if (!STAGE_ID_PATTERN.test(chapterId)) problems.push('chapter id "' + chapterId + '" is not a kebab-case slug');
        if (chapterIds.indexOf(chapterId) !== -1) problems.push('chapter "' + chapterId + '" is repeated');
        if (block.id !== 'chapter-' + chapterId) problems.push('chapter "' + chapterId + '" needs id="chapter-' + chapterId + '"');
        if (!parts.chapterTitle) problems.push('chapter "' + chapterId + '" has no .stage-chapter-title');
        if (!open.chapters.length && open.sections.length) problems.push('stage "' + open.id + '" has sections before its first chapter');
        closeChapter();
        chapterIds.push(chapterId);
        open.chapters.push({ id: chapterId, element: index, sections: [] });
      } else if (block.kind === 'recap') {
        if (!open || block.stage !== open.id) { problems.push('recap "' + block.stage + '" does not close the open stage'); return; }
        if (!open.sections.length) problems.push('stage "' + open.id + '" has no sections');
        if (block.concepts !== KEY_CONCEPTS_PER_STAGE) problems.push('stage "' + open.id + '" recap has ' + block.concepts + ' key concepts; it needs exactly ' + KEY_CONCEPTS_PER_STAGE + ' in ul.stage-concepts');
        if (!parts.next) problems.push('stage "' + open.id + '" recap has no .stage-next ("Qué sigue")');
        closeChapter();
        open.recap = index;
        open = null;
      } else if (block.kind === 'section') {
        if (!open) problems.push('section "' + block.sectionId + '" is outside a stage (between a .stage-intro and its .stage-recap)');
        else if (block.stage !== open.id) problems.push('section "' + block.sectionId + '" has data-stage="' + (block.stage || '') + '" inside stage "' + open.id + '"');
        else {
          open.sections.push(index);
          if (open.chapters.length) open.chapters[open.chapters.length - 1].sections.push(index);
        }
      }
    });
    if (open) problems.push('stage "' + open.id + '" has no .stage-recap');
    if (stages.length < MIN_STAGES) problems.push('a staged manual needs at least ' + MIN_STAGES + ' stages (found ' + stages.length + ')');
    return { stages: stages, problems: problems };
  }

  var contract = { kindOf: kindOf, validate: validate, STAGE_ID_PATTERN: STAGE_ID_PATTERN, KEY_CONCEPTS_PER_STAGE: KEY_CONCEPTS_PER_STAGE, MIN_STAGES: MIN_STAGES, MIN_SECTIONS_PER_CHAPTER: MIN_SECTIONS_PER_CHAPTER };
  if (typeof module !== 'undefined' && module.exports) module.exports = contract;
  else root.HeritageStageContract = contract;
})(typeof window !== 'undefined' ? window : globalThis);
