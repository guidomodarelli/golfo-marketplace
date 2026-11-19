import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { afterEach, beforeEach, describe, test } from 'node:test';

const TOOL_DIRECTORY = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SKILL_NAME = 'flow-states';

/**
 * Copies the tool (without its tests) into `<pluginRoot>/tools/skill-coverage`, the way
 * `pnpm sync-shared-files` lays it out in every plugin that uses it.
 *
 * @param {string} pluginRoot
 */
function installToolCopy(pluginRoot) {
  fs.cpSync(TOOL_DIRECTORY, path.join(pluginRoot, 'tools', 'skill-coverage'), {
    recursive: true,
    filter: (source) => !source.split(path.sep).includes('tests'),
  });
}

/**
 * @param {string} skillsRoot
 * @param {string} body
 */
function writeSkill(skillsRoot, body) {
  fs.mkdirSync(path.join(skillsRoot, SKILL_NAME), { recursive: true });
  fs.writeFileSync(path.join(skillsRoot, SKILL_NAME, 'SKILL.md'), `---\nname: ${SKILL_NAME}\n---\n${body}\n`);
}

/**
 * Resolves the skill directory from a tool copy in a separate process, so the copy's own
 * `import.meta.url` decides which plugin it belongs to.
 *
 * @param {string} pluginRoot Plugin that carries the tool copy.
 * @param {Record<string, string>} [environment]
 * @returns {string}
 */
function resolveFromCopy(pluginRoot, environment = {}) {
  const moduleUrl = pathToFileURL(path.join(pluginRoot, 'tools', 'skill-coverage', 'lib', 'skill-definition.mjs')).href;
  const script = `import(${JSON.stringify(moduleUrl)}).then((module) => process.stdout.write(module.skillDirectory(${JSON.stringify(SKILL_NAME)})))`;
  const childEnvironment = { ...process.env, ...environment };
  if (!('GOLFO_COVERAGE_SKILLS_DIR' in environment)) delete childEnvironment.GOLFO_COVERAGE_SKILLS_DIR;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', script], { encoding: 'utf8', env: childEnvironment });
  assert.equal(result.status, 0, result.stderr);
  return path.resolve(result.stdout);
}

describe('skill definitions across sibling plugins', () => {
  let root;
  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'skill-coverage-siblings-'));
  });
  afterEach(() => fs.rmSync(root, { recursive: true, force: true }));

  test('a skill of another plugin is found next to the plugin that carries the tool (repository and Hermes layout)', () => {
    const webPlugin = path.join(root, 'plugins', 'golfo-web');
    installToolCopy(webPlugin);
    writeSkill(path.join(root, 'plugins', 'golfo-frontend', 'skills'), 'frontend copy');
    assert.equal(resolveFromCopy(webPlugin), path.join(root, 'plugins', 'golfo-frontend', 'skills', SKILL_NAME));
  });

  test('a skill of another plugin is found in the Claude Code cache layout (<marketplace>/<plugin>/<version>)', () => {
    const webPlugin = path.join(root, 'cache', 'golfo-marketplace', 'golfo-web', '0.129.0');
    installToolCopy(webPlugin);
    writeSkill(path.join(root, 'cache', 'golfo-marketplace', 'golfo-frontend', '0.129.0', 'skills'), 'cached frontend copy');
    assert.equal(resolveFromCopy(webPlugin), path.join(root, 'cache', 'golfo-marketplace', 'golfo-frontend', '0.129.0', 'skills', SKILL_NAME));
  });

  test('with several cached versions of a sibling, the one installed_plugins.json marks active wins', () => {
    const marketplace = path.join(root, 'plugins', 'cache', 'golfo-marketplace');
    const webPlugin = path.join(marketplace, 'golfo-web', '0.130.0');
    installToolCopy(webPlugin);
    const oldFrontend = path.join(marketplace, 'golfo-frontend', '0.129.0');
    const activeFrontend = path.join(marketplace, 'golfo-frontend', '0.130.0');
    writeSkill(path.join(oldFrontend, 'skills'), 'old rules');
    writeSkill(path.join(activeFrontend, 'skills'), 'active rules');
    fs.writeFileSync(path.join(root, 'plugins', 'installed_plugins.json'), JSON.stringify({
      version: 2,
      plugins: {
        'golfo-web@golfo-marketplace': [{ scope: 'user', installPath: webPlugin, version: '0.130.0' }],
        'golfo-frontend@golfo-marketplace': [{ scope: 'user', installPath: activeFrontend, version: '0.130.0' }],
      },
    }));
    assert.equal(resolveFromCopy(webPlugin), path.join(activeFrontend, 'skills', SKILL_NAME));
  });

  test('several cached versions of a sibling and no registry leave the skill unresolved instead of using an old copy', () => {
    const marketplace = path.join(root, 'plugins', 'cache', 'golfo-marketplace');
    const webPlugin = path.join(marketplace, 'golfo-web', '0.130.0');
    installToolCopy(webPlugin);
    writeSkill(path.join(marketplace, 'golfo-frontend', '0.129.0', 'skills'), 'old rules');
    writeSkill(path.join(marketplace, 'golfo-frontend', '0.130.0', 'skills'), 'new rules');
    assert.equal(resolveFromCopy(webPlugin), path.join(webPlugin, 'skills', SKILL_NAME));
  });

  test('the skill of the plugin that carries the tool wins over a sibling copy', () => {
    const webPlugin = path.join(root, 'plugins', 'golfo-web');
    installToolCopy(webPlugin);
    writeSkill(path.join(webPlugin, 'skills'), 'own copy');
    writeSkill(path.join(root, 'plugins', 'golfo-frontend', 'skills'), 'sibling copy');
    assert.equal(resolveFromCopy(webPlugin), path.join(webPlugin, 'skills', SKILL_NAME));
  });

  test('GOLFO_COVERAGE_SKILLS_DIR overrides the lookup', () => {
    const webPlugin = path.join(root, 'plugins', 'golfo-web');
    installToolCopy(webPlugin);
    writeSkill(path.join(root, 'plugins', 'golfo-frontend', 'skills'), 'sibling copy');
    const explicitDirectory = path.join(root, 'explicit-skills');
    assert.equal(resolveFromCopy(webPlugin, { GOLFO_COVERAGE_SKILLS_DIR: explicitDirectory }), path.join(explicitDirectory, SKILL_NAME));
  });

  test('a skill installed nowhere resolves to the own plugin path, which the CLI reports as not installed', () => {
    const webPlugin = path.join(root, 'plugins', 'golfo-web');
    installToolCopy(webPlugin);
    assert.equal(resolveFromCopy(webPlugin), path.join(webPlugin, 'skills', SKILL_NAME));
  });
});
