/**
 * Structural validation of the registry documents (config, units, records).
 * Validators return a list of messages instead of throwing, so `validate`
 * can report every problem at once.
 */
import {
  ENTRY_ROLES,
  EVIDENCE_KINDS,
  EVIDENCE_OUTCOMES,
  EXECUTION_MODES,
  EXECUTION_RESULTS,
  SCHEMA_VERSION,
  UNIT_KINDS,
} from '../constants.mjs';

/** Stable unit identifiers: lowercase dotted segments with kebab-case words. */
export const UNIT_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)*$/;

/** Entry symbol grammar: `*`, `Name`, `Name/inner`, `Name.member` or `Name~shell`. */
export const ENTRY_SYMBOL_PATTERN = /^(?:\*|[A-Za-z_$][\w$]*(?:\/[A-Za-z_$][\w$]*|\.[A-Za-z_$][\w$-]*|~shell)?)$/;

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const isNonEmptyString = (value) => typeof value === 'string' && value.trim().length > 0;

/**
 * @param {unknown} document
 * @param {string} label File label used in the messages.
 * @returns {string[]}
 */
function checkSchemaVersion(document, label) {
  if (!isObject(document)) return [`${label}: must be a JSON object`];
  if (document.schemaVersion !== SCHEMA_VERSION) {
    return [`${label}: schemaVersion ${JSON.stringify(document.schemaVersion)} is not supported (expected ${SCHEMA_VERSION})`];
  }
  return [];
}

/**
 * @param {unknown} entry
 * @param {string} label
 * @returns {string[]}
 */
function checkEntry(entry, label) {
  if (!isObject(entry)) return [`${label}: must be an object with path and symbol`];
  const errors = [];
  if (!isNonEmptyString(entry.path) || entry.path.startsWith('/') || entry.path.includes('\\') || entry.path.split('/').includes('..')) {
    errors.push(`${label}.path: must be a repository-relative POSIX path`);
  }
  if (entry.symbol !== undefined && !ENTRY_SYMBOL_PATTERN.test(entry.symbol)) {
    errors.push(`${label}.symbol: ${JSON.stringify(entry.symbol)} must be *, Name, Name/inner, Name.member or Name~shell`);
  }
  if (entry.role !== undefined && !ENTRY_ROLES.includes(entry.role)) errors.push(`${label}.role: must be one of ${ENTRY_ROLES.join(', ')}`);
  if (entry.follow !== undefined && typeof entry.follow !== 'boolean') errors.push(`${label}.follow: must be a boolean`);
  return errors;
}

/**
 * Validates `.golfo/skill-coverage/config.json`.
 *
 * @param {unknown} config
 * @returns {string[]}
 */
export function validateConfig(config) {
  const errors = checkSchemaVersion(config, 'config.json');
  if (errors.length) return errors;
  for (const field of ['ignore', 'sourceRoots']) {
    if (config[field] !== undefined && (!Array.isArray(config[field]) || !config[field].every(isNonEmptyString))) {
      errors.push(`config.json.${field}: must be a list of strings`);
    }
  }
  if (config.pathAliases !== undefined && !isObject(config.pathAliases)) errors.push('config.json.pathAliases: must map alias patterns to target lists');
  (config.sharedInputs ?? []).forEach((input, index) => {
    errors.push(...checkEntry(input, `config.json.sharedInputs[${index}]`));
    if (input?.skills !== undefined && (!Array.isArray(input.skills) || !input.skills.every(isNonEmptyString))) {
      errors.push(`config.json.sharedInputs[${index}].skills: must be a list of skill names`);
    }
  });
  (config.boundaries ?? []).forEach((boundary, index) => {
    errors.push(...checkEntry(boundary, `config.json.boundaries[${index}]`));
    if (!isNonEmptyString(boundary?.reason)) errors.push(`config.json.boundaries[${index}].reason: explain why the dependencies of this code are not followed`);
  });
  if (config.skills !== undefined && !isObject(config.skills)) errors.push('config.json.skills: must map skill names to policy options');
  return errors;
}

/**
 * Validates one unit definition (`units/<id>.json`).
 *
 * @param {unknown} unit
 * @param {string} label
 * @returns {string[]}
 */
export function validateUnit(unit, label) {
  const errors = checkSchemaVersion(unit, label);
  if (errors.length) return errors;
  if (!UNIT_ID_PATTERN.test(unit.id ?? '')) errors.push(`${label}.id: ${JSON.stringify(unit.id)} must be lowercase dotted kebab-case`);
  if (!UNIT_KINDS.includes(unit.kind)) errors.push(`${label}.kind: must be one of ${UNIT_KINDS.join(', ')}`);
  if (!isObject(unit.hierarchy) || !isNonEmptyString(unit.hierarchy.module) || !isNonEmptyString(unit.hierarchy.subflow)) {
    errors.push(`${label}.hierarchy: needs at least module and subflow labels`);
  } else {
    for (const level of ['page', 'section']) {
      if (unit.hierarchy[level] !== undefined && unit.hierarchy[level] !== null && !isNonEmptyString(unit.hierarchy[level])) {
        errors.push(`${label}.hierarchy.${level}: must be a label or null`);
      }
    }
  }
  if (!Array.isArray(unit.entries) || unit.entries.length === 0) errors.push(`${label}.entries: needs at least one entry`);
  else unit.entries.forEach((entry, index) => errors.push(...checkEntry(entry, `${label}.entries[${index}]`)));
  (unit.dependsOn ?? []).forEach((entry, index) => {
    errors.push(...checkEntry(entry, `${label}.dependsOn[${index}]`));
    if (!isNonEmptyString(entry?.reason)) errors.push(`${label}.dependsOn[${index}].reason: explain why the dependency is not found statically`);
  });
  if (unit.routes !== undefined && (!Array.isArray(unit.routes) || !unit.routes.every(isNonEmptyString))) errors.push(`${label}.routes: must be a list of strings`);
  if (unit.skills !== undefined) {
    if (!isObject(unit.skills)) errors.push(`${label}.skills: must map skill names to applicability`);
    else for (const [skill, setting] of Object.entries(unit.skills)) {
      if (!isObject(setting) || typeof setting.applicable !== 'boolean' || !isNonEmptyString(setting.reason)) {
        errors.push(`${label}.skills.${skill}: needs applicable (boolean) and reason`);
      }
    }
  }
  return errors;
}

/**
 * @param {unknown} evidence
 * @param {string} label
 * @returns {string[]}
 */
function checkEvidence(evidence, label) {
  if (!isObject(evidence)) return [`${label}: must be an object`];
  const errors = [];
  if (!EVIDENCE_KINDS.includes(evidence.kind)) errors.push(`${label}.kind: must be one of ${EVIDENCE_KINDS.join(', ')}`);
  if (!EVIDENCE_OUTCOMES.includes(evidence.outcome)) errors.push(`${label}.outcome: must be one of ${EVIDENCE_OUTCOMES.join(', ')}`);
  if (!['witnessed', 'attested'].includes(evidence.source)) errors.push(`${label}.source: must be witnessed or attested`);
  return errors;
}

/**
 * @param {unknown} attempt
 * @param {string} label
 * @returns {string[]}
 */
function checkAttempt(attempt, label) {
  if (!isObject(attempt)) return [`${label}: must be an object`];
  const errors = [];
  if (!EXECUTION_RESULTS.includes(attempt.result)) errors.push(`${label}.result: must be one of ${EXECUTION_RESULTS.join(', ')}`);
  if (!EXECUTION_MODES.includes(attempt.mode)) errors.push(`${label}.mode: must be one of ${EXECUTION_MODES.join(', ')}`);
  if (!isNonEmptyString(attempt.recordedAt) || Number.isNaN(Date.parse(attempt.recordedAt))) errors.push(`${label}.recordedAt: must be an ISO date`);
  if (!isObject(attempt.skill) || !isNonEmptyString(attempt.skill.definitionHash)) errors.push(`${label}.skill.definitionHash: missing`);
  const baseline = attempt.baseline;
  if (!isObject(baseline) || !isNonEmptyString(baseline.fingerprint) || !isObject(baseline.inputs) || !isObject(baseline.files)) {
    errors.push(`${label}.baseline: needs fingerprint, inputs and files`);
  }
  if (!Array.isArray(attempt.evidence)) errors.push(`${label}.evidence: must be a list`);
  else attempt.evidence.forEach((evidence, index) => errors.push(...checkEvidence(evidence, `${label}.evidence[${index}]`)));
  if (attempt.result === 'verified' && attempt.evidence?.some((evidence) => evidence.outcome === 'fail')) {
    errors.push(`${label}: a verified attempt cannot contain failing evidence`);
  }
  return errors;
}

/**
 * Validates one coverage record (`records/<skill>/<unit>.json`).
 *
 * @param {unknown} record
 * @param {string} label
 * @returns {string[]}
 */
export function validateRecord(record, label) {
  const errors = checkSchemaVersion(record, label);
  if (errors.length) return errors;
  if (!UNIT_ID_PATTERN.test(record.unitId ?? '')) errors.push(`${label}.unitId: invalid`);
  if (!isNonEmptyString(record.skill)) errors.push(`${label}.skill: missing`);
  if (record.verified === null && record.latest === null) errors.push(`${label}: holds no attempt`);
  if (record.verified !== null && record.verified !== undefined) {
    errors.push(...checkAttempt(record.verified, `${label}.verified`));
    if (record.verified.result !== 'verified') errors.push(`${label}.verified.result: must be verified`);
  }
  if (record.latest !== null && record.latest !== undefined) {
    errors.push(...checkAttempt(record.latest, `${label}.latest`));
    if (record.latest.result === 'verified') errors.push(`${label}.latest: a verified attempt belongs in verified`);
  }
  return errors;
}
