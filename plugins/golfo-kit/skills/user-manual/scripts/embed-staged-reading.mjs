#!/usr/bin/env node
/**
 * Embeds the staged reading assets (DESIGN.md, "Lectura por etapas") and, optionally, a viewer adapter into
 * a manual, or builds the example manual from the real boilerplate of DESIGN.md. No dependencies.
 *
 * Usage:
 *   node embed-staged-reading.mjs <manual.html> [--viewer document] [--out <file>]
 *   node embed-staged-reading.mjs --example <out.html> [--linear] [--viewer document] [--design <DESIGN.md>]
 *
 *   <manual.html>  a manual written with the boilerplate. With <meta name="heritage:reading-mode"
 *                  content="stages"> it gets the staged CSS and script; the blocks are replaced on every
 *                  run, so running it again after updating the assets refreshes them. Written in place
 *                  unless --out is given.
 *   --viewer document  also embeds the document viewer adapter (public URL /d/<doc_id>/view?href=<id>,
 *                  manual in an iframe /d/<doc_id>/raw).
 *   --example      builds assets/staged-reading/template.html on top of the DESIGN.md boilerplate;
 *                  --linear builds the same content as a linear manual (top TOC, no stages).
 *
 * Exit code: 0 on success, 1 when the manual cannot take the assets, 2 on bad usage.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
export const DEFAULT_DESIGN_PATH = path.join(SKILL_DIR, 'DESIGN.md');
export const STAGED_STYLE_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'staged-reading.css');
export const STAGED_SCRIPT_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'staged-reading.js');
export const STAGED_TEMPLATE_PATH = path.join(SKILL_DIR, 'assets', 'staged-reading', 'template.html');
export const VIEWER_ADAPTER_PATHS = { document: path.join(SKILL_DIR, 'assets', 'viewer-adapters', 'document-viewer-adapter.js') };
const NAVIGATION_SCRIPT_MARKER = '// Navegación e interacciones Heritage';
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

/** The minimal boilerplate of DESIGN.md ("Boilerplate HTML mínimo"), the single source of the navigation. */
export const readBoilerplate = (designSource) => {
	const match = designSource.replace(/\r\n/g, '\n').match(/### Boilerplate HTML mínimo[\s\S]*?```html\n([\s\S]*?)\n```/);
	if (!match) throw new Error('embed-staged-reading: DESIGN.md has no "Boilerplate HTML mínimo" html block');
	return match[1];
};

/** Inserts (or refreshes) the staged reading assets and the viewer adapter into a manual's HTML. */
export const embedStagedReading = (html, { viewer = null } = {}) => {
	const staged = STAGED_MODE_META.test(html);
	if (!staged && !viewer) throw new Error('embed-staged-reading: nothing to embed (no <meta name="heritage:reading-mode" content="stages"> and no --viewer)');
	if (viewer && !VIEWER_ADAPTER_PATHS[viewer]) throw new Error(`embed-staged-reading: unknown viewer "${viewer}" (known: ${Object.keys(VIEWER_ADAPTER_PATHS).join(', ')})`);
	let output = [STAGED_STYLE_BLOCK, STAGED_SCRIPT_BLOCK, VIEWER_BLOCK].reduce(removeBlock, html);
	const markerIndex = output.indexOf(NAVIGATION_SCRIPT_MARKER);
	if (markerIndex === -1) throw new Error('embed-staged-reading: the manual has no Heritage navigation script; start from the DESIGN.md boilerplate');
	const navigationEnd = output.indexOf('</script>', markerIndex) + '</script>'.length;
	// After the navigation script: the adapter first, so the staged script reads the viewer's initial target.
	const scripts = [
		viewer ? block(VIEWER_BLOCK, `<script>\n${readText(VIEWER_ADAPTER_PATHS[viewer]).trim()}\n</script>`) : '',
		staged ? block(STAGED_SCRIPT_BLOCK, `<script>\n${readText(STAGED_SCRIPT_PATH).trim()}\n</script>`) : '',
	].join('');
	output = output.slice(0, navigationEnd) + scripts + output.slice(navigationEnd);
	if (staged) {
		const headEnd = output.indexOf('</head>');
		if (headEnd === -1) throw new Error('embed-staged-reading: the manual has no </head>');
		output = `${output.slice(0, headEnd).replace(/\n$/, '')}${block(STAGED_STYLE_BLOCK, `<style>\n${readText(STAGED_STYLE_PATH).trim()}\n</style>`)}\n${output.slice(headEnd)}`;
	}
	return output;
};

const between = (text, name) => {
	const match = text.match(new RegExp(`<!-- heritage:${name} -->\\n([\\s\\S]*?)<!-- /heritage:${name} -->`));
	if (!match) throw new Error(`embed-staged-reading: the template has no heritage:${name} block`);
	return match[1];
};

/** Linear version of the same content: no stage blocks or attributes, and the top TOC the linear mode needs. */
const toLinear = (head, body) => {
	const linearBody = body.replace(/<!-- heritage:stage-only -->[\s\S]*?<!-- \/heritage:stage-only -->\n*/g, '').replace(/ data-stage="[^"]*"/g, '');
	const entries = [...linearBody.matchAll(/<div class="section-num">(\d+)<\/div>\s*<h2 class="section-title" id="([^"]+)">([\s\S]*?)<\/h2>/g)];
	const toc = `<nav class="toc" aria-labelledby="toc-label">\n  <div class="toc-label" id="toc-label">Contenido</div>\n  <ol>\n${entries.map(([, number, id, title]) => `    <li><a href="#${id}"><span class="toc-num">${number}</span>${title}</a></li>`).join('\n')}\n  </ol>\n</nav>\n`;
	return { head: head.replace(/<meta name="heritage:reading-mode"[^>]*>\n/, ''), body: linearBody.replace(/(<\/header>\n)/, `$1\n${toc}`) };
};

/** Builds the example manual: the template's content on the real DESIGN.md boilerplate, assets embedded. */
export const buildExample = ({ designPath = DEFAULT_DESIGN_PATH, templatePath = STAGED_TEMPLATE_PATH, linear = false, viewer = null } = {}) => {
	const boilerplate = readBoilerplate(readText(designPath));
	const template = readText(templatePath);
	let head = between(template, 'head');
	let body = between(template, 'body');
	if (linear) ({ head, body } = toLinear(head, body));
	const title = (body.match(/<h1 class="doc-title">([^<]+)<\/h1>/) || [])[1] || 'Manual';
	const bodyStart = boilerplate.indexOf('<header class="doc-header"');
	const footerEnd = boilerplate.indexOf('</footer>', bodyStart) + '</footer>'.length;
	if (bodyStart === -1 || footerEnd < bodyStart) throw new Error('embed-staged-reading: the boilerplate has no doc-header … doc-footer range to replace');
	const html = (boilerplate.slice(0, bodyStart) + body.trim() + boilerplate.slice(footerEnd))
		.replace(/<title>[^<]*<\/title>/, `<title>${title}</title>\n${head.trim()}`);
	return linear && !viewer ? html : embedStagedReading(html, { viewer });
};

const parseArguments = (argv) => {
	const options = { manual: null, example: null, out: null, viewer: null, linear: false, design: DEFAULT_DESIGN_PATH };
	for (let index = 0; index < argv.length; index += 1) {
		const argument = argv[index];
		if (argument === '--example') options.example = argv[(index += 1)];
		else if (argument === '--out') options.out = argv[(index += 1)];
		else if (argument === '--viewer') options.viewer = argv[(index += 1)];
		else if (argument === '--design') options.design = argv[(index += 1)];
		else if (argument === '--linear') options.linear = true;
		else if (!options.manual && !argument.startsWith('--')) options.manual = argument;
		else throw new Error(`embed-staged-reading: unexpected argument ${argument}`);
	}
	if (!options.manual === !options.example) throw new Error('embed-staged-reading: pass either <manual.html> or --example <out.html>');
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
		if (options.example) {
			fs.writeFileSync(options.example, buildExample({ designPath: options.design, linear: options.linear, viewer: options.viewer }));
			console.log(`embed-staged-reading: example ${options.linear ? 'linear' : 'staged'} manual written to ${options.example}`);
			return;
		}
		const output = options.out || options.manual;
		fs.writeFileSync(output, embedStagedReading(readText(options.manual), { viewer: options.viewer }));
		console.log(`embed-staged-reading: assets embedded into ${output}`);
	} catch (embedError) {
		console.error(embedError.message);
		process.exitCode = 1;
	}
};

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
