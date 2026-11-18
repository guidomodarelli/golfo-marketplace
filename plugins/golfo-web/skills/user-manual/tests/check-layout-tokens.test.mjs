/**
 * Public contract of check-layout-tokens.mjs through its CLI: the skill assets use the spacing, layout and
 * breakpoint tokens of DESIGN.md, and values outside them are reported with their file and line.
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';

const CHECK_LAYOUT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'scripts', 'check-layout-tokens.mjs');
const DESIGN_FIXTURE = `---
name: Fixture
spacing:
  md:   8px
  2xl:  16px
layout:
  menu-reserve: 280px  # reserva del menú
breakpoints:
  mobile: 720px
motion:
  duration-fast: 120ms
---

# Fixture
`;

let workspace;
const write = (name, content) => {
	const file = path.join(workspace, name);
	fs.writeFileSync(file, content);
	return file;
};
const run = (...args) => {
	const result = spawnSync(process.execPath, [CHECK_LAYOUT, ...args], { encoding: 'utf8' });
	return { status: result.status, output: `${result.stdout}${result.stderr}` };
};

before(() => { workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'user-manual-layout-')); });
after(() => fs.rmSync(workspace, { recursive: true, force: true }));

describe('check-layout-tokens CLI', () => {
	test('the skill assets use only the layout tokens of DESIGN.md', () => {
		const result = run();
		assert.equal(result.status, 0, result.output);
		assert.match(result.output, /0 problem\(s\)/);
	});

	test('accepts spacing, layout tokens, zero and hairlines', () => {
		const design = write('DESIGN.md', DESIGN_FIXTURE);
		const css = write('ok.css', '.a{padding:8px 16px;margin:0 -16px;gap:2px;}\n.b{padding-right:280px;}\n@media (max-width:719px){.c{margin-top:1px;}}\n');
		const result = run('--design', design, css);
		assert.equal(result.status, 0, result.output);
	});

	test('reports spacing outside the scale with its line', () => {
		const design = write('DESIGN.md', DESIGN_FIXTURE);
		const css = write('spacing.css', '.a{padding:8px;}\n.b{padding:6px 14px;}\n');
		const result = run('--design', design, css);
		assert.equal(result.status, 1);
		assert.match(result.output, /spacing\.css:2: padding uses 6px, outside the spacing scale and the layout tokens/);
		assert.match(result.output, /spacing\.css:2: padding uses 14px/);
	});

	test('reports width media queries that are not breakpoint tokens, also in scripts', () => {
		const design = write('DESIGN.md', DESIGN_FIXTURE);
		const css = write('media.css', '@media (max-width:720px){.a{padding:8px;}}\n@media (min-width:720px){.b{padding:8px;}}\n');
		const script = write('media.js', "var wide = window.matchMedia('(min-width: 900px)');\n");
		const result = run('--design', design, css, script);
		assert.equal(result.status, 1);
		assert.match(result.output, /media\.css:1: \(max-width:720px\) does not match a breakpoint token/);
		assert.doesNotMatch(result.output, /media\.css:2/);
		assert.match(result.output, /media\.js:1: \(min-width:900px\) does not match a breakpoint token/);
	});

	test('fails clearly without the token blocks', () => {
		const design = write('DESIGN.md', '---\nname: Fixture\nspacing:\n  md: 8px\n---\n');
		const result = run('--design', design, write('any.css', '.a{padding:8px;}\n'));
		assert.equal(result.status, 2);
		assert.match(result.output, /has no layout, breakpoints block/);
	});
});
