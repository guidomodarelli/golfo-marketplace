/**
 * Lee los templates de respuesta del plugin y saca de cada uno la firma que tiene que aparecer
 * en el body publicado. Los templates siguen siendo la única fuente del formato: este módulo no
 * copia ningún encabezado, los deriva de los archivos de las skills.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

/** Raíz del plugin golfo-github, dos niveles arriba de `hooks/lib/`. */
export const PLUGIN_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

/**
 * Dónde viven los templates de respuesta.
 * - `directory`: un archivo `.md` por variante (codex-comment-closeout).
 * - `markdown-blocks`: varias variantes, cada una en un bloque ```markdown (inline-thread-autofix).
 */
export const TEMPLATE_SOURCES = [
  { format: 'directory', path: 'skills/codex-comment-closeout/templates' },
  { format: 'markdown-blocks', path: 'skills/inline-thread-autofix/references/closeout-template.md' },
];

/** Comienzo del pie que llevan los templates: `<sub>🤖 …</sub>`. */
export const FOOTER_MARK = '<sub>🤖';

const MARKDOWN_BLOCK_PATTERN = /```markdown\r?\n([\s\S]*?)\r?\n```/g;
const VARIATION_SELECTOR_PATTERN = /️/g;
const HORIZONTAL_RULE = '---';
const QUOTE_PREFIX = '>';
const BOLD_DELIMITER = '**';
const PLACEHOLDER_OPENERS = ['[', '{{'];
const FIRST_NON_ASCII_CODE_POINT = 128;

/**
 * Normaliza un texto para comparar firmas: NFC y sin el selector de variación U+FE0F, que algunos
 * editores agregan o quitan de emojis como «ℹ️» o «⚠️».
 *
 * @param {string} text Texto a normalizar.
 * @returns {string} Texto comparable.
 */
export function normalizeForComparison(text) {
  return text.normalize('NFC').replace(VARIATION_SELECTOR_PATTERN, '');
}

/**
 * Posición del primer marcador de placeholder o link (`[` o `{{`) de una línea.
 *
 * @param {string} line Línea del template.
 * @returns {number} Índice, o el largo de la línea si no hay ninguno.
 */
function firstPlaceholderIndex(line) {
  const positions = PLACEHOLDER_OPENERS.map((opener) => line.indexOf(opener)).filter((index) => index >= 0);
  return positions.length > 0 ? Math.min(...positions) : line.length;
}

/**
 * Saca la firma de un template: el encabezado de su primera línea con contenido, hasta el cierre
 * del primer texto en negrita o, si no tiene, hasta el primer link o placeholder.
 * Se saltean las líneas vacías, las divisorias (`---`) y las citas (`> …`), y se descartan los
 * encabezados que no empiezan con un emoji, porque un texto común no distingue un template.
 *
 * @param {string} templateText Contenido del template.
 * @returns {string | null} La firma, o `null` si el template no tiene un encabezado reconocible.
 */
export function extractSignature(templateText) {
  const headerLine = templateText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line !== '' && line !== HORIZONTAL_RULE && !line.startsWith(QUOTE_PREFIX));
  if (!headerLine || headerLine.codePointAt(0) < FIRST_NON_ASCII_CODE_POINT) {
    return null;
  }
  const placeholderIndex = firstPlaceholderIndex(headerLine);
  const boldStart = headerLine.indexOf(BOLD_DELIMITER);
  const boldEnd = boldStart >= 0 ? headerLine.indexOf(BOLD_DELIMITER, boldStart + BOLD_DELIMITER.length) : -1;
  const cutIndex = boldStart >= 0 && boldStart < placeholderIndex && boldEnd > 0
    ? boldEnd + BOLD_DELIMITER.length
    : placeholderIndex;
  const signature = headerLine.slice(0, cutIndex).trim();
  return signature === '' ? null : signature;
}

/**
 * Lee las variantes de una fuente de templates.
 *
 * @param {{ format: string, path: string }} source Fuente declarada en {@link TEMPLATE_SOURCES}.
 * @param {string} pluginRoot Raíz del plugin.
 * @returns {{ text: string, origin: string }[]} Una entrada por variante.
 */
function readTemplateVariants(source, pluginRoot) {
  const sourcePath = join(pluginRoot, source.path);
  if (source.format === 'directory') {
    return readdirSync(sourcePath)
      .filter((fileName) => fileName.endsWith('.md'))
      .sort()
      .map((fileName) => ({
        text: readFileSync(join(sourcePath, fileName), 'utf8'),
        origin: relative(pluginRoot, join(sourcePath, fileName)).replaceAll('\\', '/'),
      }));
  }
  const document = readFileSync(sourcePath, 'utf8');
  return [...document.matchAll(MARKDOWN_BLOCK_PATTERN)].map((match) => ({ text: match[1], origin: source.path }));
}

/**
 * Carga las firmas de todos los templates de respuesta del plugin.
 * Dos variantes con la misma firma se juntan, y el pie solo es obligatorio si todas lo llevan.
 *
 * @param {string} [pluginRoot] Raíz del plugin; por defecto, la de este archivo.
 * @returns {{ templates: { signature: string, requiresFooter: boolean, origins: string[] }[], errors: string[] }}
 *   Las firmas encontradas y un error legible por cada fuente que no se pudo leer.
 */
export function loadReplyTemplates(pluginRoot = PLUGIN_ROOT) {
  const templatesBySignature = new Map();
  const errors = [];
  for (const source of TEMPLATE_SOURCES) {
    let variants;
    try {
      variants = readTemplateVariants(source, pluginRoot);
    } catch (readError) {
      errors.push(`${source.path}: ${readError.code ?? readError.message}`);
      continue;
    }
    for (const variant of variants) {
      const signature = extractSignature(variant.text);
      if (signature === null) {
        continue;
      }
      const requiresFooter = variant.text.includes(FOOTER_MARK);
      const existing = templatesBySignature.get(signature);
      if (existing) {
        existing.requiresFooter &&= requiresFooter;
        if (!existing.origins.includes(variant.origin)) {
          existing.origins.push(variant.origin);
        }
      } else {
        templatesBySignature.set(signature, { signature, requiresFooter, origins: [variant.origin] });
      }
    }
  }
  return { templates: [...templatesBySignature.values()], errors };
}
