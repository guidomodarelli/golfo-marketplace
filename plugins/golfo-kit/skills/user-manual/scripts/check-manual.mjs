#!/usr/bin/env node
/**
 * Static checks for a finished user manual, run before publishing. No dependencies.
 *
 * Usage:
 *   node check-manual.mjs <manual.html> [--translations <file> ...] [--forbidden <value,value,...>]
 *                         [--allow-host <host> ...]
 *
 *   --translations  .po or .json translation files of the documented app (reader's locale). Every
 *                   text quoted between «…» or “…” in the manual must exist in one of them.
 *   --translations-pt  the app's pt-BR files, for a manual with a Portuguese version (translation table
 *                   #heritage-translations), plus an optional JSON {"<es>": "<pt>"} of library texts
 *                   verified at their source. Each language is checked as its own document, and the
 *                   table's app texts must hold the catalogs' msgstr.
 *   --forbidden     real values seen while capturing (names, usernames, user ids). Zero hits allowed.
 *   --allow-host    extra hosts allowed in the file besides fonts, the app CDN and the share URL.
 *   --design        DESIGN.md to compare the language and document-link snippets with (default: the skill's
 *                   DESIGN.md). The navigation script is compared with assets/boilerplate/navigation.js.
 *
 * A menu of manuals (<meta name="heritage:kind" content="menu">, DESIGN.md "Menú de manuales") is one
 * screen: no TOC, section map, standard order or audience; it is checked for its capture and its links.
 *
 * A staged manual (<meta name="heritage:reading-mode" content="stages">, DESIGN.md "Lectura por etapas") has
 * no top TOC (the pill sheet is the complete index); its stages are checked instead: intro, contiguous
 * sections and recap with three key concepts, plus the embedded staged script (build-manual.mjs).
 *
 * Exit code: 0 when there are no errors (warnings do not fail), 1 with errors, 2 on bad usage.
 * The rendered checks (frame fit, pin distance) run in the browser with check-rendered.js.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const DEFAULT_ALLOWED_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com', 'www.w3.org'];
const SKILL_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_DESIGN_PATH = path.join(SKILL_DIR, 'DESIGN.md');
const STAGE_CONTRACT_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'stage-contract.js');
// Same rules as the staged script in the browser: one contract for activation and validation.
const stageContract = createRequire(import.meta.url)(STAGE_CONTRACT_PATH);
const STAGED_SCRIPT_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'staged-reading.js');
const DOCUMENT_VIEWER_ADAPTER_PATH = path.join(SKILL_DIR, 'assets', 'viewer-adapters', 'document-viewer-adapter.js');
const NAVIGATION_SCRIPT_MARKER = '// Navegación e interacciones Heritage';
const NAVIGATION_SCRIPT_PATH = path.join(SKILL_DIR, 'assets', 'boilerplate', 'navigation.js');
const STAGED_SCRIPT_MARKER = '// Lectura por etapas Heritage';
const STAGE_CONTRACT_MARKER = '// Contrato de etapas Heritage';
const DOCUMENT_VIEWER_ADAPTER_MARKER = '// Adaptador de visor de documentos Heritage';
const READING_MODES = ['linear', 'stages'];
const STAGED_MODE = 'stages';
const DOCUMENT_VIEW_PATH = /^\/d\/[^/]+\/view\/?$/;
const DOCUMENT_LINKS_SCRIPT_MARKER = '// Navegación entre documentos Heritage';
const LANGUAGE_SCRIPT_MARKER = '// Idioma: el documento se escribe en español';
const ENVIRONMENT_MARKERS = [':8443', 'localhost', '127.0.0.1'];
const SECRET_PATTERNS = [/type=\\?"hidden\\?"/i, /_csrf/i, /csrf-token/i, /session-id/i, /authorization:/i];
const CHANGE_MARKERS = [/data-change=/, /class="[^"]*change-badge/, /Novedades:/];
const HEADER_NOISE = [/<span>Estado:/, /Capturas: [0-9-]+ · App v/];
const SOURCE_META_NAMES = ['heritage:source-repo', 'heritage:source-ref', 'heritage:source-commit', 'heritage:source-files', 'heritage:source-commit-url'];

const parseArguments = (argv) => {
	const options = { manual: null, translations: [], translationsPt: [], forbidden: [], allowHosts: [], design: DEFAULT_DESIGN_PATH };
	for (let index = 0; index < argv.length; index += 1) {
		const argument = argv[index];
		if (argument === '--translations') options.translations.push(argv[(index += 1)]);
		else if (argument === '--translations-pt') options.translationsPt.push(argv[(index += 1)]);
		else if (argument === '--forbidden') options.forbidden.push(...argv[(index += 1)].split(',').map((value) => value.trim()).filter(Boolean));
		else if (argument === '--allow-host') options.allowHosts.push(argv[(index += 1)]);
		else if (argument === '--design') options.design = argv[(index += 1)];
		else if (!options.manual) options.manual = argument;
		else throw new Error(`check-manual: unexpected argument ${argument}`);
	}
	if (!options.manual) throw new Error('check-manual: missing <manual.html>');
	return options;
};

const decodeEntities = (text) =>
	text
		.replace(/&nbsp;/g, ' ')
		.replace(/&amp;/g, '&')
		.replace(/&lt;/g, '<')
		.replace(/&gt;/g, '>')
		.replace(/&quot;/g, '"')
		.replace(/&#39;/g, "'")
		.replace(/&#(\d+);/g, (match, code) => String.fromCharCode(Number(code)));
const stripTags = (html) => decodeEntities(html.replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').trim();
const metaContent = (html, name) => {
	const match = html.match(new RegExp(`<meta name="${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}" content="([^"]*)"`));
	return match ? decodeEntities(match[1]) : null;
};

/** Reads every msgid and msgstr / JSON key and value of the translation files (only msgids and keys with sourceOnly) into one normalized set. */
const loadTranslations = (files, sourceOnly = false) => {
	const texts = new Set();
	const normalize = (text) => text.replace(/\s+/g, ' ').trim();
	for (const file of files) {
		const content = fs.readFileSync(file, 'utf8');
		if (file.endsWith('.json')) {
			const walk = (node) => {
				if (typeof node === 'string') texts.add(normalize(node));
				else if (Array.isArray(node)) node.forEach(walk);
				else if (node && typeof node === 'object') Object.entries(node).forEach(([key, value]) => { texts.add(normalize(key)); if (!sourceOnly) walk(value); });
			};
			walk(JSON.parse(content));
		} else {
			for (const match of content.matchAll(/^(msgid|msgstr) "((?:[^"\\]|\\.)*)"((?:\n"(?:[^"\\]|\\.)*")*)/gm)) {
				if (sourceOnly && match[1] !== 'msgid') continue;
				const continuation = match[3].split('\n').filter(Boolean).map((line) => line.slice(1, -1)).join('');
				texts.add(normalize((match[2] + continuation).replace(/\\"/g, '"').replace(/\\n/g, ' ')));
			}
		}
	}
	return [...texts].filter(Boolean);
};

/** A quoted text matches when a translation contains it; «… » marks a truncated quote and [name] a value the app fills in. */
const quoteExists = (quote, translations) => {
	const fragments = quote.split(/…|\[[^\]]+\]/).map((fragment) => fragment.trim().replace(/[.:]$/, '')).filter((fragment) => fragment.length > 2);
	if (!fragments.length) return true;
	// Placeholders like {0} in translations stand for values the manual writes out (ARBA01, 50).
	const asPattern = (translation) => new RegExp(translation.split(/\{\d+\}/).map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('.+?'), 'i');
	return fragments.every((fragment) => translations.some((translation) => translation.includes(fragment) || (/\{\d+\}/.test(translation) && asPattern(translation).test(fragment))));
};

/** msgid → msgstr of .po / .json translation files (first plural form; empty when untranslated). */
const loadPairs = (files) => {
	const pairs = new Map();
	const unquote = (first, rest) => (first + rest.split('\n').filter(Boolean).map((line) => line.slice(1, -1)).join('')).replace(/\\"/g, '"').replace(/\\n/g, '\n');
	for (const file of files) {
		const content = fs.readFileSync(file, 'utf8');
		if (file.endsWith('.json')) {
			for (const [key, value] of Object.entries(JSON.parse(content))) {
				const text = Array.isArray(value) ? value[1] : value;
				if (typeof text === 'string' && !pairs.has(key)) pairs.set(key, text.trim());
			}
			continue;
		}
		for (const block of content.split(/\n\s*\n/)) {
			const msgid = block.match(/^msgid "((?:[^"\\]|\\.)*)"((?:\n"(?:[^"\\]|\\.)*")*)/m);
			const msgstr = block.match(/^msgstr(?:\[0\])? "((?:[^"\\]|\\.)*)"((?:\n"(?:[^"\\]|\\.)*")*)/m);
			if (!msgid || !msgstr) continue;
			const key = unquote(msgid[1], msgid[2]);
			if (key && !pairs.has(key)) pairs.set(key, unquote(msgstr[1], msgstr[2]).trim());
		}
	}
	return pairs;
};

/**
 * App texts are never translated by hand: every entry of the translation table whose Spanish text is an
 * app string must hold that string's msgstr in the app's pt-BR catalog. The Spanish the app shows is the
 * es-AR msgstr, or the msgid when es-AR lacks it. In "captures" every text is an app text, so values
 * ({0}), pieces split by markup ({1}…{2}) and "prefix: value" labels are checked too, and a text the
 * catalog does not have is reported (keep it in Spanish unless the app translates it).
 */
const checkTranslationTable = (table, spanishFiles, portugueseFiles, manualTitles = new Set()) => {
	const problems = { errors: [], warnings: [] };
	const spanish = loadPairs(spanishFiles);
	const portuguese = loadPairs(portugueseFiles);
	const shown = new Map();
	for (const msgid of portuguese.keys()) {
		if (!shown.has(msgid)) shown.set(msgid, msgid);
		if (spanish.get(msgid)) shown.set(spanish.get(msgid), msgid);
	}
	const target = (msgid) => portuguese.get(msgid) || msgid;
	const placeholder = /\{\d+\}/g;
	const letters = (text) => (text.match(/\p{L}/gu) || []).length;
	const pieces = new Map();
	const patterns = [];
	for (const [text, msgid] of shown) {
		if (!placeholder.test(text)) continue;
		placeholder.lastIndex = 0;
		const sourcePieces = text.split(placeholder).map((piece) => piece.trim());
		const targetPieces = target(msgid).split(placeholder).map((piece) => piece.trim());
		if (sourcePieces.length === targetPieces.length) sourcePieces.forEach((piece, index) => { if (letters(piece) >= 3 && !pieces.has(piece)) pieces.set(piece, targetPieces[index]); });
		if (letters(text.replace(placeholder, '')) >= 3) patterns.push({ regex: new RegExp(`^${text.split(placeholder).map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('(.+?)')}$`, 's'), msgid });
	}
	const exact = (text) => {
		if (shown.has(text)) return target(shown.get(text));
		if (text.endsWith(':') && shown.has(text.slice(0, -1))) return `${target(shown.get(text.slice(0, -1)))}:`;
		return null;
	};
	const expected = (text) => {
		const direct = exact(text);
		if (direct !== null) return direct;
		if (pieces.has(text)) return pieces.get(text);
		// A text can fit several catalog strings ("¡Hola {0}!" and "¡Hola {0} {1}!"); when their translations
		// differ, only the source code tells which one the app uses.
		const candidates = new Map();
		for (const { regex, msgid } of patterns) {
			const match = text.match(regex);
			if (!match) continue;
			const values = match.slice(1);
			let index = 0;
			candidates.set(target(msgid).replace(placeholder, () => values[index++] ?? ''), msgid);
		}
		if (candidates.size > 1) return { ambiguous: [...candidates.entries()] };
		if (candidates.size === 1) return [...candidates.keys()][0];
		const [head, ...rest] = text.split(': ');
		if (rest.length && exact(head) !== null) {
			const value = rest.join(': ');
			const prefixOnly = `${exact(head)}: ${value}`;
			// The value can be a translated label too (a status built with gettext, "Estado: Habilitado" →
			// "Estado: Ativo"): then the app translates both parts, so either form is the app's text.
			const translatedValue = exact(value);
			return translatedValue !== null && translatedValue !== value ? { anyOf: [prefixOnly, `${exact(head)}: ${translatedValue}`] } : prefixOnly;
		}
		return null;
	};
	for (const [part, check] of [['document', exact], ['captures', expected]]) {
		for (const [text, translation] of Object.entries(table[part] || {})) {
			// Section and part titles are the manual's own words, even when an app string happens to match.
			if (part === 'document' && manualTitles.has(text)) continue;
			const wanted = check(text);
			if (wanted && wanted.ambiguous) {
				if (!wanted.ambiguous.some(([candidate]) => candidate.trim() === translation.trim())) problems.errors.push(`translations: «${text.slice(0, 60)}» is an app text: its pt-BR is one of ${wanted.ambiguous.map(([candidate]) => `«${candidate.slice(0, 40)}»`).join(', ')} (catalog), not «${translation.slice(0, 60)}»`);
				else problems.warnings.push(`translations: «${text.slice(0, 60)}» fits several catalog strings (${wanted.ambiguous.map(([, msgid]) => `"${msgid.slice(0, 40)}"`).join(', ')}); check in the source which one the app uses`);
				continue;
			}
			if (wanted && wanted.anyOf) {
				if (!wanted.anyOf.some((candidate) => candidate.trim() === translation.trim())) problems.errors.push(`translations: «${text.slice(0, 60)}» is an app text: its pt-BR is ${wanted.anyOf.map((candidate) => `«${candidate.slice(0, 40)}»`).join(' or ')} (catalog), not «${translation.slice(0, 60)}»`);
				continue;
			}
			if (wanted === null) {
				if (part === 'captures') problems.warnings.push(`translations: capture text «${text.slice(0, 60)}» is not in the app's catalog; keep it in Spanish unless the app translates it`);
				continue;
			}
			if (wanted.trim() !== translation.trim()) problems.errors.push(`translations: «${text.slice(0, 60)}» is an app text: its pt-BR is «${wanted.slice(0, 60)}» (catalog), not «${translation.slice(0, 60)}»`);
		}
	}
	return problems;
};

// A manual with a Portuguese version is written once, in Spanish, plus a translation table in
// <script type="application/json" id="heritage-translations"> (DESIGN.md, "Selector de idioma"). The
// Portuguese document for the checks is the Spanish one with the "document" table applied, as the
// language script does in the browser.
const TRANSLATIONS_SCRIPT = /<script type="application\/json" id="heritage-translations">([\s\S]*?)<\/script>/;
const TRANSLATED_ATTRIBUTES = ['aria-label', 'title', 'alt', 'placeholder', 'data-tooltip', 'data-target', 'data-target-text'];
const escapeText = (text) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const escapeAttribute = (text) => escapeText(text).replace(/"/g, '&quot;');
/** Applies a translation table the way the language script does: exact text without edge spaces. */
const applyTable = (html, table, used) => {
	const translate = (value) => {
		const key = value.trim();
		if (!key || !Object.prototype.hasOwnProperty.call(table, key)) return null;
		used.add(key);
		return value.replace(key, () => table[key]);
	};
	const attributes = new RegExp(`\\b(${TRANSLATED_ATTRIBUTES.join('|')})="([^"]*)"`, 'g');
	return html.replace(/<(script|style|code|template)\b[\s\S]*?<\/\1>|<div class="lang-switch"[\s\S]*?<\/div>|<[^>]+>|[^<]+/g, (token, skipped) => {
		if (skipped || token.startsWith('<div class="lang-switch"')) return token;
		if (token.startsWith('<')) return token.replace(attributes, (match, name, value) => {
			const translated = translate(decodeEntities(value));
			return translated === null ? match : `${name}="${escapeAttribute(translated)}"`;
		});
		const translated = translate(decodeEntities(token));
		return translated === null ? token : escapeText(translated);
	});
};
const splitLanguages = (html, options) => {
	const script = html.match(TRANSLATIONS_SCRIPT);
	if (!script) return { languages: [{ label: '', html, translations: options.translations }], unused: [], table: null };
	const table = JSON.parse(script[1]).pt || {};
	const used = new Set();
	let portuguese = applyTable(html, table.document || {}, used);
	if (table.title) portuguese = portuguese.replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeText(table.title)}</title>`);
	const unused = Object.keys(table.document || {}).filter((key) => !used.has(key));
	return {
		languages: [
			// The msgids of the pt-BR files are the app's Spanish source texts: they also count for Spanish, since
			// a string missing from the es-AR catalog is shown as its msgid.
			{ label: 'es', html, translations: options.translations, sourceTranslations: options.translationsPt },
			{ label: 'pt', html: portuguese, translations: options.translationsPt },
		],
		unused,
		table,
	};
};

/**
 * Stage structure (DESIGN.md, "Lectura por etapas"), with the same contract the staged script validates
 * before hiding anything (assets/staged-reading/stage-contract.js): the HTML blocks become descriptors and the
 * contract decides. Block classes are matched as tokens, like the browser selectors.
 */
const checkStages = (visible) => {
	const blocks = [...visible.matchAll(/<([a-z]+)\b[^>]*\bclass="([^"]*)"[^>]*>/g)]
		.map((match) => ({ match, kind: stageContract.kindOf(match[1], match[2]) }))
		.filter((block) => block.kind);
	const descriptors = blocks.map(({ match, kind }, index) => {
		const content = visible.slice(match.index, index + 1 < blocks.length ? blocks[index + 1].match.index : visible.length);
		const attribute = (name) => (match[0].match(new RegExp(`\\s${name}="([^"]*)"`)) || [])[1];
		const hasClass = (name) => new RegExp(`class="(?:[^"]*\\s)?${name}(?:\\s[^"]*)?"`).test(content);
		const concepts = (content.match(/<ul class="(?:[^"]*\s)?stage-concepts(?:\s[^"]*)?">([\s\S]*?)<\/ul>/) || [])[1] || '';
		return {
			kind,
			id: attribute('id'),
			stage: attribute('data-stage-intro') || attribute('data-stage') || attribute('data-stage-recap'),
			chapter: attribute('data-chapter'),
			sectionId: attribute('aria-labelledby'),
			parts: { title: hasClass('stage-title'), objective: hasClass('stage-objective'), reading: hasClass('stage-reading'), chapterTitle: hasClass('stage-chapter-title'), next: hasClass('stage-next') },
			concepts: (concepts.match(/<li\b/g) || []).length,
		};
	});
	return stageContract.validate(descriptors).problems.map((problem) => `stages: ${problem}`);
};

const main = () => {
	const options = parseArguments(process.argv.slice(2));
	const source = fs.readFileSync(options.manual, 'utf8');
	const { languages, unused, table } = splitLanguages(source, options);
	let failed = 0;
	// Keys that no longer match any text are stale translations: the Spanish text changed and the
	// Portuguese one did not follow.
	for (const key of unused) console.log(`  WARN  languages: translation never used (stale?): «${key.slice(0, 80)}»`);
	if (table && options.translations.length && options.translationsPt.length) {
		const manualTitles = new Set([...source.matchAll(/<h2 class="(?:section-title|part-header-title)"[^>]*>([\s\S]*?)<\/h2>/g)].map((match) => stripTags(match[1])));
		const problems = checkTranslationTable(table, options.translations, options.translationsPt, manualTitles);
		for (const message of problems.errors) console.log(`  ERROR ${message}`);
		for (const message of problems.warnings) console.log(`  WARN  ${message}`);
		failed += problems.errors.length;
	} else if (table) {
		console.log('  WARN  translations: no --translations / --translations-pt given; the table was not checked against the app catalogs');
	}
	// The language switch exists only with a Portuguese version, and a Portuguese version needs the switch.
	const hasSwitch = /<div class="lang-switch"/.test(source);
	if (hasSwitch !== (languages.length > 1)) {
		console.log(hasSwitch ? '  ERROR languages: language switch without a Portuguese version (a Spanish-only manual has no switch)' : '  ERROR languages: Portuguese version without the language switch');
		failed += 1;
	}
	for (const language of languages) failed += checkDocument(language.html, { ...options, translations: language.translations, sourceTranslations: language.sourceTranslations }, language.label, source);

	process.exitCode = failed ? 1 : 0;
};

const checkDocument = (html, options, label, source) => {
	const errors = [];
	const warnings = [];
	const payloadStart = html.indexOf('<!-- app-frames:start -->');
	const document = payloadStart === -1 ? html : html.slice(0, payloadStart);
	const body = document.slice(document.indexOf('<body>'));
	// Markup only: scripts and styles may mention class names or old features in comments.
	const visible = body.replace(/<script\b[\s\S]*?<\/script>/g, '').replace(/<style\b[\s\S]*?<\/style>/g, '');

	// Structure: TOC entries ↔ section titles.
	const titles = new Map([...visible.matchAll(/<h2 class="section-title" id="([^"]+)">([\s\S]*?)<\/h2>/g)].map((match) => [match[1], stripTags(match[2])]));
	const tocEntries = [...visible.matchAll(/<nav class="toc"[\s\S]*?<\/nav>/g)].flatMap((toc) => [...toc[0].matchAll(/<a href="#([^"]+)"><span class="toc-num">\d+<\/span>([\s\S]*?)<\/a>/g)]);

	// Section ids are fixed slugs (DESIGN.md, "Copiar enlace a una sección"): not the number, so inserting a
	// section does not move links, and not the title, so retitling does not either.
	const slugOf = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
	const sectionIds = [...visible.matchAll(/<section class="section" aria-labelledby="([^"]+)"/g)].map((match) => match[1]);
	for (const id of sectionIds) {
		if (/^s\d+$/.test(id)) errors.push(`ids: section id "${id}" is its number; use a fixed slug`);
		else if (!/^[a-z][a-z0-9-]*$/.test(id)) errors.push(`ids: section id "${id}" is not a kebab-case slug`);
		if (!label || label === 'es') { if (titles.has(id) && slugOf(titles.get(id)) === id) errors.push(`ids: section id "${id}" is its title; use a slug that does not change when the title does`); }
		if (sectionIds.filter((other) => other === id).length > 1) errors.push(`ids: section id "${id}" is repeated`);
	}

	// Section references are links named after the section (DESIGN.md, "Referencias a secciones"): a bare
	// number ("sección 03") says nothing and cannot be followed.
	const plainReferences = stripTags(visible.replace(/<nav class="toc"[\s\S]*?<\/nav>/g, '')).match(/(?<![\p{L}])(?:secci(?:ón|ones)|se(?:ção|ções)) \d{2}(?!\d)/giu) || [];
	for (const reference of new Set(plainReferences)) errors.push(`section references: «${reference}» names a section by its number; link it with its title (<a href="#slug">sección Título</a>)`);

	// Steps linked to a capture go before it (DESIGN.md, "Puntos sobre capturas"): what to do first, then where.
	const stepsAfterCapture = (visible.match(/<div class="figcap">[\s\S]*?<\/div>\s*<ol class="steps">\s*<li class="step-item" data-hotspot=/g) || []).length;
	if (stepsAfterCapture) errors.push(`order: ${stepsAfterCapture} steps list(s) linked to pins come after their capture; put each ol.steps before its .mockup`);

	// Inline references (span.hotspot-ref) also go before the capture they point to, as close to it as the text
	// allows: read the reference, then find its pin (DESIGN.md, "Puntos sobre capturas").
	for (const section of visible.matchAll(/<section class="section"[^>]*aria-labelledby="([^"]+)"[\s\S]*?<\/section>/g)) {
		const text = section[0];
		const pinEnds = new Map();
		for (const mockup of text.matchAll(/<div class="mockup[ "][\s\S]*?<div class="figcap">/g)) {
			for (const pin of mockup[0].matchAll(/class="hotspot" data-hotspot="(\d+)"/g)) if (!pinEnds.has(pin[1])) pinEnds.set(pin[1], mockup.index + mockup[0].length);
		}
		const late = new Set();
		for (const reference of text.matchAll(/class="hotspot-ref" data-hotspot="(\d+)"/g)) {
			const insideStep = text.lastIndexOf('<li class="step-item', reference.index) > text.lastIndexOf('</li>', reference.index);
			if (!insideStep && pinEnds.has(reference[1]) && reference.index > pinEnds.get(reference[1])) late.add(reference[1]);
		}
		if (late.size) errors.push(`order: in #${section[1]}, the inline reference(s) ${[...late].join(', ')} come after the capture with their pin; move that text before the capture`);
	}

	// Inside one paragraph, list or table the inline references read in ascending order, like the pins
	// (DESIGN.md, "Puntos sobre capturas"): "(5) … (6) … (7)", never "(6) … (5)".
	for (const block of visible.matchAll(/<(p|ul|ol|table|dl)\b[^>]*>[\s\S]*?<\/\1>/g)) {
		const numbers = [...block[0].matchAll(/class="hotspot-ref" data-hotspot="(\d+)"/g)].map((match) => Number(match[1]));
		if (numbers.some((number, index) => index && number < numbers[index - 1])) errors.push(`order: inline references ${numbers.join(', ')} are not ascending in «${stripTags(block[0]).replace(/\s+/g, ' ').trim().slice(0, 60)}…»; mention the pins in order`);
	}

	const isMenu = metaContent(html, 'heritage:kind') === 'menu';
	// The scripts travel inside each document: compare them with the current boilerplate or asset.
	const extractScript = (text, marker) => {
		const start = text.indexOf(marker);
		return start === -1 ? null : text.slice(start, text.indexOf('</script>', start) === -1 ? text.length : text.indexOf('</script>', start)).replace(/\r\n/g, '\n').trim();
	};
	const readSource = (file) => (fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null);
	const designSource = readSource(options.design);
	const compareScript = (marker, name, referenceSource = designSource, referenceName = 'its DESIGN.md snippet') => {
		const embedded = extractScript(body, marker);
		const current = referenceSource && extractScript(referenceSource, marker);
		if (embedded && current && embedded !== current) warnings.push(`${name}: the script differs from ${referenceName} (outdated); copy the current one`);
		return embedded;
	};

	// Reading mode: linear (default) or by stages (DESIGN.md, "Lectura por etapas").
	const readingMode = metaContent(html, 'heritage:reading-mode');
	if (readingMode !== null && !READING_MODES.includes(readingMode)) errors.push(`stages: unknown heritage:reading-mode "${readingMode}" (use "${STAGED_MODE}", or omit it for a linear manual)`);
	const isStaged = readingMode === STAGED_MODE;
	if (isStaged) {
		errors.push(...checkStages(visible));
		if (!compareScript(STAGED_SCRIPT_MARKER, 'stages', readSource(STAGED_SCRIPT_PATH), 'assets/staged-reading/staged-reading.js')) errors.push('stages: the staged reading script is missing (run scripts/build-manual.mjs on the manual)');
		if (!compareScript(STAGE_CONTRACT_MARKER, 'stage contract', readSource(STAGE_CONTRACT_PATH), 'assets/staged-reading/stage-contract.js')) errors.push('stages: the stage contract script is missing (run scripts/build-manual.mjs on the manual)');
		if (!/\.stage-drawer\{/.test(document)) errors.push('stages: the staged reading styles are missing (run scripts/build-manual.mjs on the manual)');
	} else if (/\sdata-stage(?:-intro|-recap)?="/.test(visible)) {
		errors.push(`stages: stage markup without <meta name="heritage:reading-mode" content="${STAGED_MODE}"> (the stages would never show)`);
	}
	// A document viewer that shows /d/<doc_id>/view?href=<id> needs its adapter: without it, copied links use
	// the generic #<id>.
	const shareUrl = (() => { try { return new URL(metaContent(html, 'heritage:share-url')); } catch (invalidUrlError) { return null; } })();
	const hasViewerAdapter = compareScript(DOCUMENT_VIEWER_ADAPTER_MARKER, 'viewer adapter', readSource(DOCUMENT_VIEWER_ADAPTER_PATH), 'assets/viewer-adapters/document-viewer-adapter.js');
	if (shareUrl && DOCUMENT_VIEW_PATH.test(shareUrl.pathname) && !hasViewerAdapter) warnings.push('share-url: it is a document viewer URL (/d/<doc_id>/view) but the document viewer adapter is missing; copied links and the viewer URL keep the generic #<id> format (build-manual.mjs --viewer document)');
	if (/id="heritage-translations"/.test(html) && !compareScript(LANGUAGE_SCRIPT_MARKER, 'language')) errors.push('language: the language script (HeritageLanguage) is missing');

	// Links to other published documents (menu ↔ manuals, DESIGN.md "Navegación entre documentos").
	const documentLinks = [...visible.matchAll(/<a\b[^>]*data-document-link[^>]*>/g)].map((match) => match[0]);
	if (documentLinks.length && !compareScript(DOCUMENT_LINKS_SCRIPT_MARKER, 'document links')) errors.push('document links: data-document-link without the "Navegación entre documentos" script (links would not leave the viewer iframe)');
	for (const link of [...visible.matchAll(/<a class="menu-back"[^>]*>/g)].map((match) => match[0])) {
		if (!/href="https:\/\/[^"]+"/.test(link)) errors.push('menu-back: "Ir al menú" needs the public URL of the menu');
		if (!link.includes('data-document-link')) errors.push('menu-back: "Ir al menú" needs data-document-link');
	}
	if (/<a class="menu-back"/.test(visible) && !/<body>\s*<a class="menu-back"/.test(visible)) errors.push('menu-back: "Ir al menú" must be the first child of <body>');

	if (isMenu) {
		const menuLinks = [...visible.matchAll(/<a class="menu-link"[^>]*>/g)].map((match) => match[0]);
		if (!/<div class="menu-stage">\s*<div class="app-frame" data-cap="[^"]+"><\/div>/.test(visible)) errors.push('menu: the menu is a capture of the app menu (div.menu-stage > div.app-frame), never drawn by hand');
		if (!menuLinks.length) errors.push('menu: no a.menu-link over the cards');
		for (const link of menuLinks) {
			const card = (link.match(/data-target-text="([^"]*)"/) || [])[1] || '?';
			if (!/data-target="[^"]+"/.test(link)) errors.push(`menu: link «${card}» has no data-target`);
			if (!link.includes('data-document-link')) errors.push(`menu: link «${card}» needs data-document-link`);
			if (!/aria-label="[^"]+"/.test(link)) errors.push(`menu: link «${card}» has no aria-label`);
			const disabled = link.includes('aria-disabled="true"');
			const hasHref = /\shref="/.test(link);
			if (disabled === hasHref) errors.push(`menu: link «${card}» must have either an href (with manual) or aria-disabled="true" (without), not both or none`);
		}
		const cardTexts = menuLinks.map((link) => (link.match(/data-target-text="([^"]*)"/) || [])[1]).filter(Boolean);
		for (const text of new Set(cardTexts)) if (cardTexts.filter((other) => other === text).length > 1) errors.push(`menu: two links over the card «${text}»`);
	}

	if (isMenu) { /* one screen: no TOC */ } else if (isStaged) {
		// With stages the pill sheet is the complete index, built from every section by the navigation script.
		if (/<nav class="toc"/.test(visible)) errors.push('toc: a staged manual has no top nav.toc; the pill sheet is the complete index');
	} else if (!tocEntries.length) errors.push('toc: no nav.toc entries found');
	for (const [, id, label] of tocEntries) {
		if (!titles.has(id)) errors.push(`toc: link #${id} has no section`);
		else if (stripTags(label) !== titles.get(id)) errors.push(`toc: "${stripTags(label)}" differs from the title of #${id} ("${titles.get(id)}")`);
	}
	if (!isStaged) for (const id of titles.keys()) if (!tocEntries.some((entry) => entry[1] === id)) errors.push(`toc: section #${id} is missing from the TOC`);
	if (!isMenu) {
		for (const required of ['class="section-rail"', 'class="section-pill"', 'class="toc-sheet"', 'class="back-to-top"']) {
			if (!visible.includes(required)) errors.push(`navigation: ${required} missing`);
		}
		if (!compareScript(NAVIGATION_SCRIPT_MARKER, 'navigation', readSource(NAVIGATION_SCRIPT_PATH), 'assets/boilerplate/navigation.js (refresh it with scripts/build-manual.mjs)')) errors.push('navigation: the Heritage navigation script is missing');
	}

	// Glossary terms resolve.
	const definitions = new Set([...visible.matchAll(/<dt id="([^"]+)"/g)].map((match) => match[1]));
	for (const [, target] of visible.matchAll(/class="term" href="#([^"]+)"/g)) if (!definitions.has(target)) errors.push(`glossary: term link #${target} has no <dt>`);

	// Standard order (user-manual skill, Step 3): the same sections in the same order in every manual,
	// marked with data-section (and the same slug as id), so the check works in any language.
	const STANDARD_HEAD = ['purpose', 'audience', 'permissions', 'access', 'happy-path'];
	const STANDARD_TAIL = ['limits', 'messages', 'good-practices', 'faq', 'escalation', 'glossary'];
	const sectionTags = [...visible.matchAll(/<section class="section"[^>]*>/g)].map((match) => match[0]);
	const roleOf = (tag) => (tag.match(/data-section="([^"]+)"/) || [])[1] || '';
	const roles = sectionTags.map(roleOf);
	const glossaryIndex = roles.indexOf('glossary');
	for (const role of new Set(roles.filter(Boolean))) {
		if (roles.filter((other) => other === role).length > 1) errors.push(`order: more than one data-section="${role}"`);
		if (![...STANDARD_HEAD, 'unhappy-paths', ...STANDARD_TAIL].includes(role)) errors.push(`order: unknown data-section="${role}"`);
	}
	sectionTags.forEach((tag, index) => {
		const role = roles[index];
		const id = (tag.match(/aria-labelledby="([^"]+)"/) || [])[1];
		if (role && id !== role) errors.push(`order: the "${role}" section must use "${role}" as its id (found "${id}")`);
	});
	if (!isMenu) STANDARD_HEAD.forEach((role, index) => {
		if (roles[index] !== role) errors.push(`order: section ${String(index + 1).padStart(2, '0')} must be data-section="${role}" (found "${roles[index] || 'none'}")`);
	});
	const unhappyIndex = roles.indexOf('unhappy-paths');
	// The unhappy paths come after the happy path and every particularity of the flow (its initial
	// configuration and steps), right before the closing sections: how it works first, then how it fails.
	if (unhappyIndex !== -1 && roles.slice(unhappyIndex + 1).some((role) => !STANDARD_TAIL.includes(role))) errors.push('order: "Flujos no felices" (unhappy-paths) goes after the happy path and every particularity (configuration, steps), right before the closing sections');
	// Tail sections close the manual, after the flow's particularities, in their fixed relative order.
	const tailPositions = STANDARD_TAIL.map((role) => roles.indexOf(role)).filter((position) => position !== -1);
	if (tailPositions.some((position, index) => index && position < tailPositions[index - 1])) errors.push(`order: closing sections out of order; expected ${STANDARD_TAIL.join(' → ')}`);
	if (tailPositions.length) {
		const firstTail = tailPositions[0];
		if (roles.slice(firstTail).some((role) => !STANDARD_TAIL.includes(role))) errors.push('order: particularities go before the closing sections (limits, messages, good practices, FAQ, escalation, glossary)');
	}
	if (glossaryIndex !== -1 && glossaryIndex !== roles.length - 1) errors.push('glossary: the Glosario section must be the last one');
	// Audience: the only place that describes the roles, with every role of the doc-meta
	// ("Audiencia:" / "Público:") named in it.
	if (roles.includes('audience')) {
		const audienceSection = [...visible.matchAll(/<section class="section"[^>]*data-section="audience"[^>]*>([\s\S]*?)<\/section>/g)][0];
		const metaRoles = ((visible.match(/<span>(?:Audiencia|Público): ([^<]+)<\/span>/) || [])[1] || '').split('/').map((role) => decodeEntities(role).trim()).filter(Boolean);
		const audienceText = audienceSection ? stripTags(audienceSection[1]).toLowerCase() : '';
		for (const role of metaRoles) if (!audienceText.includes(role.toLowerCase())) errors.push(`audience: role "${role}" of the doc-meta is not described in the Audiencia section`);
	}
	const glossaryLists = [...visible.matchAll(/<dl class="glossary">([\s\S]*?)<\/dl>/g)];
	if (glossaryLists.some((list) => !/<dt\b/.test(list[1]))) errors.push('glossary: empty glossary; without confirmed terms the section is not shown');
	if (glossaryLists.length && glossaryIndex === -1) errors.push('glossary: the <dl class="glossary"> must live in the Glosario section (data-section="glossary")');
	if (definitions.size && !/class="term" href="#/.test(visible)) warnings.push('glossary: no a.term links to the glossary in the text');

	// Mockups: caption after each one, url bar without host, pins anchored on captures.
	// The url bar is a <span> in the current snippets and a <div> in older manuals.
	const mockups = [...visible.matchAll(/<div class="mockup(?: [^"]*)?">[\s\S]*?<(?:span|div) class="mockup-url">([^<]*)<\/(?:span|div)>/g)];
	for (const [, url] of mockups) if (/https?:\/\/|[a-z0-9-]+\.(com|io|net|ar|br)\b|:\d{2,5}/i.test(url)) errors.push(`mockup-url: "${url}" shows a host`);
	const figcapCount = (visible.match(/class="figcap"/g) || []).length;
	if (figcapCount < mockups.length) warnings.push(`figcap: ${mockups.length} mockups but ${figcapCount} captions`);
	for (const stage of visible.matchAll(/<div class="hotspot-stage">([\s\S]*?)<\/div>\s*<\/div>/g)) {
		if (!stage[1].includes('class="app-frame"')) continue;
		const capture = (stage[1].match(/data-cap="([^"]+)"/) || [])[1];
		for (const pin of stage[1].matchAll(/<span class="hotspot"[^>]*>/g)) if (!pin[0].includes('data-target=')) errors.push(`pins: a pin on capture "${capture}" has no data-target`);
	}

	// Pins: each section owns its pins; one pin per number, and every step or reference has its pin.
	for (const [, sectionId, sectionBody] of visible.matchAll(/<section class="section" aria-labelledby="([^"]+)"[^>]*>([\s\S]*?)<\/section>/g)) {
		const pinNumbers = [...sectionBody.matchAll(/<span class="hotspot"[^>]*data-hotspot="([^"]+)"/g)].map((match) => match[1]);
		const linkedNumbers = new Set([...sectionBody.matchAll(/class="(?:step-item|hotspot-ref)"[^>]*data-hotspot="([^"]+)"/g)].map((match) => match[1]));
		const repeated = [...new Set(pinNumbers.filter((number, index) => pinNumbers.indexOf(number) !== index))];
		if (repeated.length) errors.push(`pins: section ${sectionId} has more than one pin numbered ${repeated.join(', ')} (one pin per number per section)`);
		for (const number of linkedNumbers) if (!pinNumbers.includes(number)) errors.push(`pins: section ${sectionId} refers to pin ${number} but has no pin with that number (repeat the capture in this section)`);
		for (const number of new Set(pinNumbers)) if (!linkedNumbers.has(number)) errors.push(`pins: section ${sectionId} has pin ${number} with no step or reference in the same section`);
	}

	// Root-relative images inside captures resolve against the manual's host and show empty.
	const relativeImages = new Set([...html.matchAll(/<img[^>]*?\bsrc=\\?"(\/(?!\/)[^"\\]*)/g)].map((match) => match[1]));
	for (const source of relativeImages) errors.push(`images: capture image ${source} has a root-relative path (inline it as a data URI; recapture with the current capture-snippet.js)`);

	// No change markers.
	for (const marker of CHANGE_MARKERS) if (marker.test(visible)) errors.push(`change markers: found ${marker} (manuals never mark new or updated sections)`);
	// The doc-meta carries only what tells the reader something.
	if (!isMenu && !/<div class="doc-meta">[\s\S]*?<span>(?:Audiencia|Público): [^<]+<\/span>[\s\S]*?<\/div>/.test(visible)) errors.push('doc-meta: missing "Audiencia: <rol> / <rol>" ("Público:" in Portuguese)');
	for (const noise of HEADER_NOISE) if (noise.test(visible)) errors.push(`doc-meta: found ${noise} (no "Estado" and no app version in a manual header)`);

	// Source trace (where the content comes from).
	const missingSource = SOURCE_META_NAMES.filter((name) => metaContent(html, name) === null);
	if (missingSource.length) errors.push(`source: missing ${missingSource.join(', ')} (scripts/source-trace.py record)`);
	const commitUrl = metaContent(html, 'heritage:source-commit-url');
	const commit = metaContent(html, 'heritage:source-commit');
	const codeLink = visible.match(/<footer class="doc-footer">[^<]*Código: <a href="([^"]+)"[^>]*>([^<]+)<\/a><\/footer>/);
	if (!codeLink) errors.push('source: no doc-footer with the "Código: <ref> @ <commit>" line linked to the commit (run source-trace.py record)');
	if (/<div class="doc-meta">[\s\S]*?Código:[\s\S]*?<\/div>/.test(visible.slice(0, visible.indexOf('</header>')))) errors.push('source: "Código:" belongs in the doc-footer, not in the doc-meta');
	else if (commitUrl && decodeEntities(codeLink[1]) !== commitUrl) errors.push('source: the "Código" link does not point to heritage:source-commit-url');
	if (commitUrl && commit && !commitUrl.endsWith(`/commit/${commit}`)) errors.push('source: heritage:source-commit-url does not match heritage:source-commit');
	if (!isMenu && !metaContent(html, 'heritage:share-url')) warnings.push('share-url: no heritage:share-url meta (needed when the manual is shown inside an iframe)');

	// Environment data and secrets anywhere in the file, captures payload included.
	const shareHost = (() => { try { return new URL(metaContent(html, 'heritage:share-url')).host; } catch (error) { return null; } })();
	const commitHost = (() => { try { return new URL(commitUrl).host; } catch (error) { return null; } })();
	// Documents linked from this one (menu ↔ manuals) live in the same viewer.
	const linkedHosts = documentLinks.map((link) => { try { return new URL(decodeEntities((link.match(/\shref="([^"]+)"/) || [])[1] || '')).host; } catch (error) { return null; } }).filter(Boolean);
	const allowedHosts = new Set([...DEFAULT_ALLOWED_HOSTS, ...options.allowHosts, ...(shareHost ? [shareHost] : []), ...(commitHost ? [commitHost] : []), ...linkedHosts]);
	const unexpectedHosts = new Set([...html.matchAll(/https?:\\?\/\\?\/([a-z0-9.-]+)/gi)].map((match) => match[1].toLowerCase()).filter((host) => !allowedHosts.has(host)));
	for (const host of unexpectedHosts) errors.push(`hosts: unexpected host ${host}`);
	for (const marker of ENVIRONMENT_MARKERS) if (html.includes(marker)) errors.push(`hosts: environment marker "${marker}" found`);
	for (const pattern of SECRET_PATTERNS) if (pattern.test(html)) errors.push(`secrets: ${pattern} found`);
	for (const value of options.forbidden) if (html.includes(value)) errors.push(`forbidden: real value "${value.slice(0, 3)}…" found`);

	// Quoted texts must exist in the app's translations (catches obsolete strings).
	if (options.translations.length) {
		const translations = [...loadTranslations(options.translations), ...loadTranslations(options.sourceTranslations || [], true)];
		const quotes = [...new Set([...visible.matchAll(/«([^»]+)»|“([^”]+)”/g)].map((match) => stripTags(match[1] || match[2])))];
		const missing = quotes.filter((quote) => !quoteExists(quote, translations));
		for (const quote of missing) errors.push(`texts: «${quote}» is not in the translations (obsolete or misquoted)`);
		console.log(`texts: ${quotes.length - missing.length}/${quotes.length} quoted texts found in ${options.translations.length} translation file(s)`);
	} else {
		warnings.push('texts: no --translations given; quoted texts were not checked against the app');
	}

	console.log(`check-manual: ${path.basename(options.manual)}${label ? ` [${label}]` : ''} — ${titles.size} sections, ${mockups.length} mockups, ${errors.length} errors, ${warnings.length} warnings`);
	warnings.forEach((warning) => console.log(`  warn  ${warning}`));
	errors.forEach((error) => console.log(`  ERROR ${error}`));
	return errors.length;
};

try {
	main();
} catch (error) {
	console.error(error.message);
	process.exitCode = 2;
}
