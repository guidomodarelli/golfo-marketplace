#!/usr/bin/env node
/**
 * Checks the layout tokens of DESIGN.md against the CSS and scripts of the skill assets. No dependencies.
 *
 *   - padding, margin and gap only use the `spacing` scale, the named `layout` measures, 0 or up to 2px
 *     (inline chips);
 *   - every width media query (CSS and matchMedia in scripts) uses a `breakpoints` token: min-width: <token>
 *     or max-width: <token> - 1px.
 *
 * Usage:
 *   node check-layout-tokens.mjs [--design <DESIGN.md>] [file ...]
 *
 * Without files it checks assets/boilerplate/base.css, assets/boilerplate/navigation.js and the CSS and
 * scripts of assets/staged-reading/. Exit code: 0 when everything uses the tokens, 1 with problems, 2 on
 * bad usage or a missing token block.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_DESIGN_PATH = path.join(SKILL_DIR, 'DESIGN.md');
const DEFAULT_FILES = [
	path.join(SKILL_DIR, 'assets', 'boilerplate', 'base.css'),
	path.join(SKILL_DIR, 'assets', 'boilerplate', 'navigation.js'),
	path.join(SKILL_DIR, 'assets', 'staged-reading', 'staged-reading.css'),
	path.join(SKILL_DIR, 'assets', 'staged-reading', 'staged-reading.js'),
];
const TOKEN_BLOCKS = ['spacing', 'layout', 'breakpoints'];
// Inline chips (badges, code inline) use 1–2px: below this, a value is not spacing (DESIGN.md, spacing).
const HAIRLINE_MAX_PX = 2;
const SPACING_PROPERTY = /(?:^|[;{\s])((?:padding|margin)(?:-(?:top|right|bottom|left|inline|block)(?:-(?:start|end))?)?|gap|row-gap|column-gap)\s*:\s*([^;}]+)/g;
const WIDTH_QUERY = /\((min|max)-width\s*:\s*(\d+(?:\.\d+)?)px\)/g;

/** Reads the px values of the front matter blocks spacing, layout and breakpoints. */
export const readLayoutTokens = (designSource) => {
	const frontMatter = (designSource.replace(/\r\n/g, '\n').match(/^---\n([\s\S]*?)\n---/) || [])[1];
	if (!frontMatter) throw new Error('check-layout-tokens: DESIGN.md has no front matter');
	const tokens = {};
	let current = null;
	for (const line of frontMatter.split('\n')) {
		const blockMatch = line.match(/^([a-z][a-z0-9-]*):\s*$/);
		if (blockMatch) { current = TOKEN_BLOCKS.includes(blockMatch[1]) ? blockMatch[1] : null; if (current) tokens[current] = new Map(); continue; }
		if (/^\S/.test(line)) { current = null; continue; }
		const tokenMatch = current && line.match(/^\s+([a-z0-9-]+):\s*(\d+(?:\.\d+)?)px\b/);
		if (tokenMatch) tokens[current].set(tokenMatch[1], Number(tokenMatch[2]));
	}
	const missing = TOKEN_BLOCKS.filter((block) => !tokens[block] || !tokens[block].size);
	if (missing.length) throw new Error(`check-layout-tokens: DESIGN.md front matter has no ${missing.join(', ')} block`);
	return tokens;
};

/** Problems of one CSS or script source against the tokens, with 1-based line numbers. */
export const checkSource = (source, tokens, fileName) => {
	const problems = [];
	const allowed = new Set([...tokens.spacing.values(), ...tokens.layout.values()]);
	const breakpoints = new Set(tokens.breakpoints.values());
	const lineOf = (index) => source.slice(0, index).split('\n').length;
	if (fileName.endsWith('.css')) {
		for (const match of source.matchAll(SPACING_PROPERTY)) {
			for (const value of match[2].matchAll(/(-?\d+(?:\.\d+)?)px/g)) {
				const size = Math.abs(Number(value[1]));
				if (size > HAIRLINE_MAX_PX && !allowed.has(size)) problems.push(`${fileName}:${lineOf(match.index)}: ${match[1]} uses ${value[1]}px, outside the spacing scale and the layout tokens`);
			}
		}
	}
	for (const match of source.matchAll(WIDTH_QUERY)) {
		const width = Number(match[2]);
		const expected = match[1] === 'min' ? width : width + 1;
		if (!breakpoints.has(expected)) problems.push(`${fileName}:${lineOf(match.index)}: (${match[1]}-width:${match[2]}px) does not match a breakpoint token (${[...tokens.breakpoints].map(([name, value]) => `${name} ${value}px`).join(', ')})`);
	}
	return problems;
};

const parseArguments = (argv) => {
	const options = { design: DEFAULT_DESIGN_PATH, files: [] };
	for (let index = 0; index < argv.length; index += 1) {
		if (argv[index] === '--design') options.design = argv[(index += 1)];
		else options.files.push(argv[index]);
	}
	if (!options.files.length) options.files = DEFAULT_FILES;
	return options;
};

const main = () => {
	let tokens;
	let options;
	try {
		options = parseArguments(process.argv.slice(2));
		tokens = readLayoutTokens(fs.readFileSync(options.design, 'utf8'));
	} catch (setupError) {
		console.error(setupError.message);
		process.exitCode = 2;
		return;
	}
	const problems = options.files.flatMap((file) => checkSource(fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n'), tokens, path.relative(process.cwd(), file) || file));
	problems.forEach((problem) => console.log(`  ERROR ${problem}`));
	console.log(`check-layout-tokens: ${options.files.length} file(s), ${tokens.spacing.size} spacing, ${tokens.layout.size} layout and ${tokens.breakpoints.size} breakpoint tokens, ${problems.length} problem(s)`);
	process.exitCode = problems.length ? 1 : 0;
};

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
