/**
 * Wires the layers for one command over one consumer repository: registry,
 * config, Git, source index, policies and skill definitions, plus the
 * evaluation of a unit for a skill that most commands share.
 */
import fs from 'node:fs';
import path from 'node:path';

import { findRepositoryRoot, openGitRepository } from '../git/git-repository.mjs';
import { computeUnitInputs } from '../impact/unit-inputs.mjs';
import { openRegistry } from '../persistence/registry.mjs';
import { resolvePolicy } from '../policies/index.mjs';
import { readSkillDefinition } from '../skill-definition.mjs';
import { createProjectIndex } from '../source/project-index.mjs';
import { CoverageError } from '../support.mjs';
import { deriveCoverage } from './coverage-evaluation.mjs';
import { decideExecution } from './execution-decision.mjs';

/**
 * @param {{ root?: string, cwd?: string, skillsDirectory?: string }} options
 */
export function openProjectContext(options = {}) {
  const startDirectory = path.resolve(options.root ?? options.cwd ?? process.cwd());
  if (!fs.existsSync(startDirectory)) throw new CoverageError(`project: ${startDirectory} does not exist`);
  const projectRoot = options.root ? startDirectory : findRepositoryRoot(startDirectory) ?? startDirectory;
  const registry = openRegistry(projectRoot);
  const config = registry.loadConfig();
  const git = openGitRepository(projectRoot);
  let index = createProjectIndex({ config, git, projectRoot });
  const policies = new Map();
  const definitions = new Map();

  const context = {
    config,
    git,
    get index() {
      return index;
    },
    projectRoot,
    registry,

    /** @param {string} skill */
    policy(skill) {
      if (!policies.has(skill)) policies.set(skill, resolvePolicy(skill, config));
      return policies.get(skill);
    },

    /** @param {string} skill */
    definition(skill) {
      if (!definitions.has(skill)) definitions.set(skill, readSkillDefinition(this.policy(skill), { skillsDirectory: options.skillsDirectory }));
      return definitions.get(skill);
    },

    /** Rebuilds the source index so later reads see files edited meanwhile. */
    refresh() {
      index = createProjectIndex({ config, git, projectRoot });
      git.dirtyPaths({ refresh: true });
      definitions.clear();
    },

    /**
     * Current inputs of a unit for a skill.
     *
     * @param {any} unit
     * @param {string} skill
     */
    inputs(unit, skill) {
      return computeUnitInputs({ config, index, policy: this.policy(skill), unit });
    },

    /**
     * Coverage state, freshness and decision of a unit for a skill.
     *
     * @param {any} unit
     * @param {string} skill
     * @param {{ forceFull?: boolean, record?: any }} [evaluationOptions]
     */
    evaluate(unit, skill, evaluationOptions = {}) {
      const policy = this.policy(skill);
      const definition = this.definition(skill);
      const current = this.inputs(unit, skill);
      const record = evaluationOptions.record !== undefined ? evaluationOptions.record : registry.loadRecord(skill, unit.id);
      const coverage = deriveCoverage({ current, definition, git, policy, record, unit });
      const decision = decideExecution({ coverage, current, forceFull: evaluationOptions.forceFull, policy, unit });
      return { coverage, current, decision, definition, policy, record };
    },
  };
  return context;
}
