/**
 * The coverage registry of one consumer repository (`.golfo/skill-coverage/`):
 * where each document lives and how it is loaded and saved. Units, records
 * and runs are small separate files so that two skills or two units never
 * rewrite the same file.
 */
import fs from 'node:fs';
import path from 'node:path';

import { COVERAGE_DIRECTORY, PENDING_RUN_MAX_AGE_MS, REGISTRY_PATHS, SCHEMA_VERSION } from '../constants.mjs';
import { CoverageError } from '../support.mjs';
import { listJsonFiles, readJsonFile, withFileLock, writeJsonFileAtomic } from './json-store.mjs';
import { UNIT_ID_PATTERN, validateConfig, validateRecord, validateUnit } from './schema.mjs';

/** Config used when a repository has no `config.json` yet. */
export const DEFAULT_CONFIG = {
  boundaries: [],
  ignore: ['**/*.test.*', '**/*.spec.*', 'tests/**', '**/__tests__/**', '**/*.stories.*'],
  schemaVersion: SCHEMA_VERSION,
  sharedInputs: [],
  skills: {},
  sourceRoots: ['app', 'src', 'components', 'lib', 'hooks'],
};

const GITIGNORE_CONTENT = '# Runs in progress: local to the machine that started them.\n.pending/\n*.lock/\n*.tmp\n';

/**
 * @param {string} skill
 */
function assertSkillName(skill) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(skill ?? '')) throw new CoverageError(`registry: invalid skill name ${JSON.stringify(skill)}`);
}

/**
 * @param {string} unitId
 */
function assertUnitId(unitId) {
  if (!UNIT_ID_PATTERN.test(unitId ?? '')) throw new CoverageError(`registry: invalid unit id ${JSON.stringify(unitId)}`);
}

/**
 * Opens the registry of a repository. Nothing is written until a save.
 *
 * @param {string} projectRoot Absolute repository root.
 */
export function openRegistry(projectRoot) {
  const root = path.join(projectRoot, COVERAGE_DIRECTORY);
  const at = (...segments) => path.join(root, ...segments);

  return {
    root,
    exists: () => fs.existsSync(root),

    /** Creates the directory layout and default config; keeps existing files. */
    initialize() {
      for (const directory of [REGISTRY_PATHS.units, REGISTRY_PATHS.records, REGISTRY_PATHS.runs]) fs.mkdirSync(at(directory), { recursive: true });
      if (!fs.existsSync(at(REGISTRY_PATHS.config))) writeJsonFileAtomic(at(REGISTRY_PATHS.config), DEFAULT_CONFIG);
      if (!fs.existsSync(at(REGISTRY_PATHS.gitignore))) fs.writeFileSync(at(REGISTRY_PATHS.gitignore), GITIGNORE_CONTENT, 'utf8');
    },

    /** @returns {typeof DEFAULT_CONFIG} Config merged over the defaults. */
    loadConfig() {
      const config = readJsonFile(at(REGISTRY_PATHS.config));
      if (config === undefined) return structuredClone(DEFAULT_CONFIG);
      const errors = validateConfig(config);
      if (errors.length) throw new CoverageError(`registry:config is invalid: ${errors.join('; ')}`, { details: errors });
      return { ...structuredClone(DEFAULT_CONFIG), ...config };
    },

    unitPath: (unitId) => at(REGISTRY_PATHS.units, `${unitId}.json`),

    /**
     * Loads every unit definition, validating each one.
     *
     * @returns {{ units: any[], errors: string[] }}
     */
    loadUnits() {
      const units = [];
      const errors = [];
      const seen = new Map();
      for (const filePath of listJsonFiles(at(REGISTRY_PATHS.units))) {
        const label = path.relative(root, filePath).split(path.sep).join('/');
        let unit;
        try {
          unit = readJsonFile(filePath);
        } catch (error) {
          errors.push(error.message);
          continue;
        }
        const unitErrors = validateUnit(unit, label);
        if (!unitErrors.length && path.basename(filePath, '.json') !== unit.id) unitErrors.push(`${label}: file name must be ${unit.id}.json`);
        if (!unitErrors.length && seen.has(unit.id)) unitErrors.push(`${label}: duplicates unit id ${unit.id} from ${seen.get(unit.id)}`);
        if (unitErrors.length) {
          errors.push(...unitErrors);
          continue;
        }
        seen.set(unit.id, label);
        units.push(unit);
      }
      return { errors, units };
    },

    /**
     * @param {string} unitId
     * @returns {any} The unit definition.
     */
    loadUnit(unitId) {
      assertUnitId(unitId);
      const unit = readJsonFile(at(REGISTRY_PATHS.units, `${unitId}.json`));
      if (unit === undefined) throw new CoverageError(`registry: unit ${unitId} does not exist; list units with \`status\` or create one with \`add-unit\` or \`discover --write\``);
      const errors = validateUnit(unit, `units/${unitId}.json`);
      if (errors.length) throw new CoverageError(`registry: unit ${unitId} is invalid: ${errors.join('; ')}`, { details: errors });
      return unit;
    },

    /**
     * Saves a unit definition without replacing an existing different unit.
     *
     * @param {any} unit
     * @param {{ overwrite?: boolean }} [options]
     * @returns {boolean} Whether the file was written.
     */
    saveUnit(unit, options = {}) {
      const errors = validateUnit(unit, `units/${unit.id}.json`);
      if (errors.length) throw new CoverageError(`registry: refusing to save invalid unit: ${errors.join('; ')}`, { details: errors });
      const filePath = at(REGISTRY_PATHS.units, `${unit.id}.json`);
      return withFileLock(filePath, () => {
        if (!options.overwrite && fs.existsSync(filePath)) return false;
        writeJsonFileAtomic(filePath, unit);
        return true;
      });
    },

    recordPath: (skill, unitId) => at(REGISTRY_PATHS.records, skill, `${unitId}.json`),

    /**
     * @param {string} skill
     * @param {string} unitId
     * @returns {any | undefined} The record, or undefined when the skill never ran on the unit.
     */
    loadRecord(skill, unitId) {
      assertSkillName(skill);
      assertUnitId(unitId);
      const label = `records/${skill}/${unitId}.json`;
      const record = readJsonFile(at(REGISTRY_PATHS.records, skill, `${unitId}.json`));
      if (record === undefined) return undefined;
      const errors = validateRecord(record, label);
      if (errors.length) throw new CoverageError(`registry: ${label} is invalid: ${errors.join('; ')}`, { details: errors });
      return record;
    },

    /**
     * Applies `update` to the record under a lock and writes it atomically.
     *
     * @param {string} skill
     * @param {string} unitId
     * @param {(current: any | undefined) => any} update Returns the new record.
     * @returns {any} The saved record.
     */
    updateRecord(skill, unitId, update) {
      assertSkillName(skill);
      assertUnitId(unitId);
      const filePath = at(REGISTRY_PATHS.records, skill, `${unitId}.json`);
      return withFileLock(filePath, () => {
        const next = update(readJsonFile(filePath));
        const errors = validateRecord(next, `records/${skill}/${unitId}.json`);
        if (errors.length) throw new CoverageError(`registry: refusing to save invalid record: ${errors.join('; ')}`, { details: errors });
        writeJsonFileAtomic(filePath, next);
        return next;
      });
    },

    /** @returns {{ skill: string, unitId: string, filePath: string }[]} */
    listRecordFiles() {
      return listJsonFiles(at(REGISTRY_PATHS.records)).map((filePath) => ({
        filePath,
        skill: path.basename(path.dirname(filePath)),
        unitId: path.basename(filePath, '.json'),
      }));
    },

    /**
     * @param {string} runId
     * @param {any} report
     * @returns {string} Registry-relative path of the report.
     */
    saveRunReport(runId, report) {
      writeJsonFileAtomic(at(REGISTRY_PATHS.runs, `${runId}.json`), report);
      return `${REGISTRY_PATHS.runs}/${runId}.json`;
    },

    runReportExists: (relativePath) => fs.existsSync(at(relativePath)),

    pendingPath: (runId) => at(REGISTRY_PATHS.pending, `${runId}.json`),

    /** @param {any} run */
    savePendingRun(run) {
      this.initialize();
      writeJsonFileAtomic(at(REGISTRY_PATHS.pending, `${run.runId}.json`), run);
    },

    /**
     * @param {string} runId
     * @returns {any}
     */
    loadPendingRun(runId) {
      if (!/^[\w.-]+$/.test(runId ?? '')) throw new CoverageError(`registry: invalid run id ${JSON.stringify(runId)}`);
      const run = readJsonFile(at(REGISTRY_PATHS.pending, `${runId}.json`));
      if (run === undefined) throw new CoverageError(`registry: run ${runId} is not pending (already recorded, aborted or started on another machine); start a new one with \`begin\``);
      return run;
    },

    /**
     * @param {string} runId
     * @param {(run: any) => any} update
     * @returns {any}
     */
    updatePendingRun(runId, update) {
      const filePath = at(REGISTRY_PATHS.pending, `${runId}.json`);
      return withFileLock(filePath, () => {
        const next = update(this.loadPendingRun(runId));
        writeJsonFileAtomic(filePath, next);
        return next;
      });
    },

    /** @param {string} runId */
    deletePendingRun(runId) {
      fs.rmSync(at(REGISTRY_PATHS.pending, `${runId}.json`), { force: true });
    },

    /**
     * Lists pending runs, flagging the ones past the maximum age.
     *
     * @returns {{ run: any, expired: boolean }[]}
     */
    listPendingRuns() {
      return listJsonFiles(at(REGISTRY_PATHS.pending)).flatMap((filePath) => {
        try {
          const run = readJsonFile(filePath);
          return [{ expired: Date.now() - Date.parse(run.startedAt) > PENDING_RUN_MAX_AGE_MS, run }];
        } catch {
          return [];
        }
      });
    },
  };
}
