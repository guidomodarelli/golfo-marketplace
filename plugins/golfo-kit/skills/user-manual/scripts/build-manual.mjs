#!/usr/bin/env node
/**
 * Builds and refreshes user manuals from the skill assets (DESIGN.md, "Boilerplate HTML mínimo" and
 * "Lectura por etapas"). No dependencies.
 *
 * Usage:
 *   node build-manual.mjs --boilerplate <out.html>
 *   node build-manual.mjs <manual.html> [--viewer document] [--out <file>]
 *   node build-manual.mjs --example <out.html> [--linear] [--viewer document]
 *
 *   --boilerplate  writes assets/boilerplate/skeleton.html with base.css and navigation.js embedded: the
 *                  starting point of a new document.
 *   <manual.html>  refreshes an existing manual: replaces its navigation, language and document-link scripts
 *                  (the ones it has; a script holding just its marker line gets filled) with the current
 *                  assets and,
 *                  with <meta name="heritage:reading-mode" content="stages">, embeds the staged CSS, contract
 *                  and script. The blocks are replaced on every run. Written in place unless --out is given.
 *   --viewer document  also embeds the document viewer adapter (public URL /d/<doc_id>/view?href=<id>,
 *                  manual in an iframe /d/<doc_id>/raw). A refresh without --viewer keeps the adapter
 *                  already embedded.
 *   --example      builds assets/staged-reading/template.html on the boilerplate; --linear builds the same
 *                  content as a linear manual (top TOC, no stages).
 *
 * Exit code: 0 on success, 1 when the manual cannot take the assets, 2 on bad usage.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const BOILERPLATE_DIR = path.join(SKILL_DIR, 'assets', 'boilerplate');
export const SKELETON_PATH = path.join(BOILERPLATE_DIR, 'skeleton.html');
export const BASE_STYLE_PATH = path.join(BOILERPLATE_DIR, 'base.css');
export const NAVIGATION_SCRIPT_PATH = path.join(BOILERPLATE_DIR, 'navigation.js');
export const STAGED_STYLE_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'staged-reading.css');
export const STAGED_SCRIPT_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'staged-reading.js');
export const STAGE_CONTRACT_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'stage-contract.js');
export const STAGED_TEMPLATE_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'template.html');
export const VIEWER_ADAPTER_PATHS = { document: path.join(SKILL_DIR, 'assets', 'viewer-adapters', 'document-viewer-adapter.js') };
const NAVIGATION_SCRIPT_MARKER = '// Navegación e interacciones Heritage';
const BASE_STYLE_PLACEHOLDER = '/* heritage:base-style */';
const NAVIGATION_SCRIPT_PLACEHOLDER = '// heritage:navigation-script';
const STAGED_MODE_META = /<meta name="heritage:reading-mode" content="stages">/;
const BLOCK_START = (name) => `<!-- heritage:${name}:start -->`;
const BLOCK_END = (name) => `<!-- heritage:${name}:end -->`;
const STAGED_STYLE_BLOCK = 'staged-reading-style';
const STAGED_SCRIPT_BLOCK = 'staged-reading-script';
const VIEWER_BLOCK = 'viewer-adapter';

const readText = (file) => fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const removeBlock = (html, name) => html.replace(new RegExp(`\\n?${escapeRegExp(BLOCK_START(name))}[\\s\\S]*?${escapeRegExp(BLOCK_END(name))}`, 'g'), '');
const block = (name, content) => `\n${BLOCK_START(name)}\n${content.trim()}\n${BLOCK_END(name)}`;
// Function replacements: the assets contain "$" sequences that String.replace would otherwise expand.
const replaceLiteral = (text, search, replacement) => text.replace(search, () => replacement);

/** The skeleton with the base styles and the navigation script embedded. */
export const readBoilerplate = () => {
	const skeleton = readText(SKELETON_PATH);
	if (!skeleton.includes(BASE_STYLE_PLACEHOLDER) || !skeleton.includes(NAVIGATION_SCRIPT_PLACEHOLDER)) throw new Error('build-manual: assets/boilerplate/skeleton.html lost its base-style or navigation-script placeholder');
	return replaceLiteral(replaceLiteral(skeleton, BASE_STYLE_PLACEHOLDER, readText(BASE_STYLE_PATH).trim()), NAVIGATION_SCRIPT_PLACEHOLDER, readText(NAVIGATION_SCRIPT_PATH).trim());
};

// Scripts a manual carries inline, found by the marker on their first line. Navigation is required; the
// language and document-link scripts only when the manual uses them. A script holding just its marker line
// (as in the DESIGN.md snippets) gets filled with the asset.
export const MANUAL_SCRIPTS = [
	{ name: 'navigation', marker: NAVIGATION_SCRIPT_MARKER, path: NAVIGATION_SCRIPT_PATH, required: true },
	{ name: 'language', marker: '// Idioma: el documento se escribe en español', path: path.join(BOILERPLATE_DIR, 'language.js'), required: false },
	{ name: 'document links', marker: '// Navegación entre documentos Heritage', path: path.join(BOILERPLATE_DIR, 'document-links.js'), required: false },
];

/** Replaces each script the manual carries (from its marker to </script>) with the current asset. */
const refreshScripts = (html) => MANUAL_SCRIPTS.reduce((output, script) => {
	const start = output.indexOf(script.marker);
	if (start === -1) {
		if (script.required) throw new Error(`build-manual: the manual has no Heritage ${script.name} script; start from node build-manual.mjs --boilerplate`);
		return output;
	}
	const end = output.indexOf('</script>', start);
	return `${output.slice(0, start)}${readText(script.path).trim()}\n${output.slice(end)}`;
}, html);

/** The viewer whose adapter is already embedded, so a refresh without --viewer keeps it. */
const embeddedViewer = (html) => {
	const start = html.indexOf(BLOCK_START(VIEWER_BLOCK));
	if (start === -1) return null;
	const embedded = html.slice(start, html.indexOf(BLOCK_END(VIEWER_BLOCK), start));
	return Object.keys(VIEWER_ADAPTER_PATHS).find((name) => embedded.includes(readText(VIEWER_ADAPTER_PATHS[name]).split('\n')[0])) || null;
};

/** Refreshes a manual: current navigation script, plus the staged reading assets and the viewer adapter that apply. */
export const refreshManual = (html, { viewer: requestedViewer = null } = {}) => {
	const viewer = requestedViewer || embeddedViewer(html);
	const staged = STAGED_MODE_META.test(html);
	if (viewer && !VIEWER_ADAPTER_PATHS[viewer]) throw new Error(`build-manual: unknown viewer "${viewer}" (known: ${Object.keys(VIEWER_ADAPTER_PATHS).join(', ')})`);
	let output = refreshScripts([STAGED_STYLE_BLOCK, STAGED_SCRIPT_BLOCK, VIEWER_BLOCK].reduce(removeBlock, html));
	const navigationEnd = output.indexOf('</script>', output.indexOf(NAVIGATION_SCRIPT_MARKER)) + '</script>'.length;
	// After the navigation script: the adapter first, so the staged script reads the viewer's initial target.
	const scripts = [
		viewer ? block(VIEWER_BLOCK, `<script>\n${readText(VIEWER_ADAPTER_PATHS[viewer]).trim()}\n</script>`) : '',
		// The contract goes in its own <script>, before the staged script that reads it.
		staged ? block(STAGED_SCRIPT_BLOCK, `<script>\n${readText(STAGE_CONTRACT_PATH).trim()}\n</script>\n<script>\n${readText(STAGED_SCRIPT_PATH).trim()}\n</script>`) : '',
	].join('');
	output = output.slice(0, navigationEnd) + scripts + output.slice(navigationEnd);
	if (staged) {
		const headEnd = output.indexOf('</head>');
		if (headEnd === -1) throw new Error('build-manual: the manual has no </head>');
		output = `${output.slice(0, headEnd).replace(/\n$/, '')}${block(STAGED_STYLE_BLOCK, `<style>\n${readText(STAGED_STYLE_PATH).trim()}\n</style>`)}\n${output.slice(headEnd)}`;
	}
	return output;
};

const between = (text, name) => {
	const match = text.match(new RegExp(`<!-- heritage:${name} -->\\n([\\s\\S]*?)<!-- /heritage:${name} -->`));
	if (!match) throw new Error(`build-manual: the template has no heritage:${name} block`);
	return match[1];
};

/** Linear version of the same content: no stage blocks or attributes, and the top TOC the linear mode needs. */
const toLinear = (head, body) => {
	const linearBody = body.replace(/<!-- heritage:stage-only -->[\s\S]*?<!-- \/heritage:stage-only -->\n*/g, '').replace(/ data-stage="[^"]*"/g, '');
	const entries = [...linearBody.matchAll(/<div class="section-num">(\d+)<\/div>\s*<h2 class="section-title" id="([^"]+)">([\s\S]*?)<\/h2>/g)];
	const toc = `<nav class="toc" aria-labelledby="toc-label">\n  <div class="toc-label" id="toc-label">Contenido</div>\n  <ol>\n${entries.map(([, number, id, title]) => `    <li><a href="#${id}"><span class="toc-num">${number}</span>${title}</a></li>`).join('\n')}\n  </ol>\n</nav>\n`;
	return { head: head.replace(/<meta name="heritage:reading-mode"[^>]*>\n/, ''), body: linearBody.replace(/(<\/header>\n)/, `$1\n${toc}`) };
};

/** Builds the example manual: the template's content on the boilerplate, assets embedded. */
export const buildExample = ({ templatePath = STAGED_TEMPLATE_PATH, linear = false, viewer = null } = {}) => {
	const boilerplate = readBoilerplate();
	const template = readText(templatePath);
	let head = between(template, 'head');
	let body = between(template, 'body');
	if (linear) ({ head, body } = toLinear(head, body));
	const title = (body.match(/<h1 class="doc-title">([^<]+)<\/h1>/) || [])[1] || 'Manual';
	const bodyStart = boilerplate.indexOf('<header class="doc-header"');
	const footerEnd = boilerplate.indexOf('</footer>', bodyStart) + '</footer>'.length;
	if (bodyStart === -1 || footerEnd < bodyStart) throw new Error('build-manual: the boilerplate has no doc-header … doc-footer range to replace');
	const html = replaceLiteral(boilerplate.slice(0, bodyStart) + body.trim() + boilerplate.slice(footerEnd), /<title>[^<]*<\/title>/, `<title>${title}</title>\n${head.trim()}`);
	return refreshManual(html, { viewer });
};

const parseArguments = (argv) => {
	const options = { manual: null, example: null, boilerplate: null, out: null, viewer: null, linear: false };
	for (let index = 0; index < argv.length; index += 1) {
		const argument = argv[index];
		if (argument === '--example') options.example = argv[(index += 1)];
		else if (argument === '--boilerplate') options.boilerplate = argv[(index += 1)];
		else if (argument === '--out') options.out = argv[(index += 1)];
		else if (argument === '--viewer') options.viewer = argv[(index += 1)];
		else if (argument === '--linear') options.linear = true;
		else if (!options.manual && !argument.startsWith('--')) options.manual = argument;
		else throw new Error(`build-manual: unexpected argument ${argument}`);
	}
	if ([options.manual, options.example, options.boilerplate].filter(Boolean).length !== 1) throw new Error('build-manual: pass exactly one of <manual.html>, --example <out.html> or --boilerplate <out.html>');
	return options;
};

const main = () => {
	let options;
	try {
		options = parseArguments(process.argv.slice(2));
	} catch (usageError) {
		console.error(usageError.message);
		process.exitCode = 2;
		return;
	}
	try {
		if (options.boilerplate) {
			fs.writeFileSync(options.boilerplate, readBoilerplate());
			console.log(`build-manual: boilerplate written to ${options.boilerplate}`);
			return;
		}
		if (options.example) {
			fs.writeFileSync(options.example, buildExample({ linear: options.linear, viewer: options.viewer }));
			console.log(`build-manual: example ${options.linear ? 'linear' : 'staged'} manual written to ${options.example}`);
			return;
		}
		const output = options.out || options.manual;
		fs.writeFileSync(output, refreshManual(readText(options.manual), { viewer: options.viewer }));
		console.log(`build-manual: manual refreshed in ${output}`);
	} catch (buildError) {
		console.error(buildError.message);
		process.exitCode = 1;
	}
};

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
