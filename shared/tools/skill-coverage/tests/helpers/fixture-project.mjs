/**
 * Temporary Git repositories shaped like a small Next.js App Router app, plus
 * a temporary skills directory, for exercising the real CLI end to end.
 *
 * The fixture page has two sections in the same file (`ProvidersSection` and
 * `ReviewQueueSection`, whose `approve` and `reject` handlers are separate
 * units), a copy dictionary shared by both, and a shared HTTP helper.
 */
import { execFileSync, spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const CLI_PATH = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../skill-coverage.mjs');
export const UI_SKILL = 'ui-ux-flow-patterns';
export const PERFORMANCE_SKILL = 'measured-performance-optimization';

export const MANAGEMENT_FILE = 'components/academy-management/index.tsx';

const FILES = {
  'app/(platform)/academy/manage/loading.tsx': 'export default function Loading() { return <p>Cargando…</p>; }\n',
  'app/(platform)/academy/manage/page.tsx': `import { AcademyManagement } from "@/components/academy-management";
import { loadManagement } from "@/lib/academy-server";

export default async function ManagePage() {
  const data = await loadManagement();
  return <AcademyManagement data={data} />;
}
`,
  [MANAGEMENT_FILE]: `"use client";

import { useState } from "react";

import { decideRequest, saveProvider } from "@/lib/api-client";

export const COPY = {
  approved: "Aprobada",
  providerSaved: "Proveedor guardado.",
  providersTitle: "Proveedores",
  queueTitle: "Solicitudes",
} as const;

export function AcademyManagement({ data }) {
  return (
    <main>
      <ProvidersSection />
      <ReviewQueueSection />
    </main>
  );
}

function ProvidersSection() {
  const [error, setError] = useState(null);
  const handleSubmit = async () => {
    const result = await saveProvider({ name: "x" });
    if (!result.ok) setError(result.message);
  };
  return (
    <section>
      <h2>{COPY.providersTitle}</h2>
      <button onClick={handleSubmit}>Guardar</button>
      {error}
    </section>
  );
}

function ReviewQueueSection() {
  const approve = async (id) => {
    await decideRequest(id, "approved");
  };
  const reject = async (id) => {
    await decideRequest(id, "rejected");
  };
  return (
    <section>
      <h2>{COPY.queueTitle}</h2>
      <button onClick={() => approve(1)}>Aprobar</button>
      <button onClick={() => reject(1)}>Rechazar</button>
    </section>
  );
}
`,
  'lib/academy-server.ts': 'export async function loadManagement() {\n  return { ok: true };\n}\n',
  'lib/api-client.ts': `import { request } from "./http";

export function saveProvider(input) {
  return request("/api/providers", input);
}

export function decideRequest(id, decision) {
  return request(\`/api/requests/\${id}\`, { decision });
}
`,
  'lib/http.ts': `export async function request(path, body) {
  const response = await fetch(path, { body: JSON.stringify(body), method: "POST" });
  return response.json();
}
`,
  'package.json': '{\n  "name": "fixture-app",\n  "private": true,\n  "dependencies": { "react": "19.0.0" }\n}\n',
  'tsconfig.json': '{\n  // Aliases like a Next.js app\n  "compilerOptions": { "paths": { "@/*": ["./*"] } },\n}\n',
};

const UNITS = {
  'academy.manage.providers.save': {
    entries: [{ path: MANAGEMENT_FILE, symbol: 'ProvidersSection' }],
    hierarchy: { module: 'Academy', page: 'Management', section: 'Verification Providers', subflow: 'Save' },
  },
  'academy.manage.requests.approve': {
    entries: [{ path: MANAGEMENT_FILE, symbol: 'ReviewQueueSection/approve' }],
    hierarchy: { module: 'Academy', page: 'Management', section: 'Verification Requests', subflow: 'Approve' },
  },
  'academy.manage.requests.reject': {
    entries: [{ path: MANAGEMENT_FILE, symbol: 'ReviewQueueSection/reject' }],
    hierarchy: { module: 'Academy', page: 'Management', section: 'Verification Requests', subflow: 'Reject' },
  },
};

/**
 * @param {string} version
 * @param {string} rules
 * @returns {string}
 */
export function skillDocument(name, version, rules = 'Rules of the skill.') {
  return `---\nname: ${name}\ndescription: test skill\nmetadata:\n  version: "${version}"\n---\n\n# ${name}\n\n${rules}\n`;
}

/**
 * Creates a fixture repository with one commit and the three units.
 *
 * @param {{ withUnits?: boolean }} [options]
 */
export function createFixture(options = {}) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'skill-coverage-'));
  const root = path.join(base, 'app');
  const skillsDirectory = path.join(base, 'skills');
  fs.mkdirSync(root, { recursive: true });

  const write = (relativePath, content) => {
    const target = path.join(root, relativePath);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content, 'utf8');
  };
  const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');
  const replace = (relativePath, search, replacement) => {
    const content = read(relativePath);
    if (!content.includes(search)) throw new Error(`fixture: ${search} not found in ${relativePath}`);
    write(relativePath, content.replace(search, replacement));
  };
  const git = (...args) => execFileSync('git', ['-C', root, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  const writeSkill = (name, version, rules) => {
    fs.mkdirSync(path.join(skillsDirectory, name, 'references'), { recursive: true });
    fs.writeFileSync(path.join(skillsDirectory, name, 'SKILL.md'), skillDocument(name, version, rules), 'utf8');
    fs.writeFileSync(path.join(skillsDirectory, name, 'references', 'rules.md'), `# ${name} rules\n`, 'utf8');
  };

  for (const [relativePath, content] of Object.entries(FILES)) write(relativePath, content);
  writeSkill(UI_SKILL, '1.0.0');
  writeSkill(PERFORMANCE_SKILL, '1.0.0');
  git('init', '--quiet', '--initial-branch=main');
  git('config', 'user.email', 'fixture@example.invalid');
  git('config', 'user.name', 'Fixture');
  git('config', 'core.autocrlf', 'false');

  const fixture = {
    base,
    git,
    read,
    replace,
    root,
    skillsDirectory,
    write,
    writeSkill,

    /**
     * Runs the CLI synchronously with `--json`.
     *
     * @param {string[]} args
     * @param {{ env?: Record<string, string>, json?: boolean }} [runOptions]
     * @returns {{ status: number, stdout: string, stderr: string, json: any }}
     */
    run(args, runOptions = {}) {
      const finalArgs = [CLI_PATH, ...args, '--root', root, '--skills-dir', skillsDirectory, ...(runOptions.json === false ? [] : ['--json'])];
      const result = spawnSync(process.execPath, finalArgs, { encoding: 'utf8', env: { ...process.env, ...runOptions.env } });
      let json;
      try {
        json = runOptions.json === false ? undefined : JSON.parse(result.stdout);
      } catch {
        json = undefined;
      }
      return { json, status: result.status, stderr: result.stderr, stdout: result.stdout };
    },

    /**
     * Runs the CLI asynchronously (for concurrency tests).
     *
     * @param {string[]} args
     * @returns {Promise<{ status: number, stdout: string, stderr: string }>}
     */
    runAsync(args) {
      return new Promise((resolve) => {
        const child = spawn(process.execPath, [CLI_PATH, ...args, '--root', root, '--skills-dir', skillsDirectory, '--json']);
        let stdout = '';
        let stderr = '';
        child.stdout.on('data', (chunk) => { stdout += chunk; });
        child.stderr.on('data', (chunk) => { stderr += chunk; });
        child.on('close', (status) => resolve({ status, stderr, stdout }));
      });
    },

    /** Writes a unit definition directly. */
    writeUnit(id, definition) {
      write(`.golfo/skill-coverage/units/${id}.json`, `${JSON.stringify({ id, kind: 'ui-flow', schemaVersion: 1, ...definition }, null, 2)}\n`);
    },

    recordPath: (skill, unitId) => path.join(root, '.golfo/skill-coverage/records', skill, `${unitId}.json`),

    readRecord(skill, unitId) {
      const filePath = this.recordPath(skill, unitId);
      return fs.existsSync(filePath) ? JSON.parse(fs.readFileSync(filePath, 'utf8')) : undefined;
    },

    /**
     * Full accredited UI/UX run: review, a witnessed test command and a
     * browser walk-through.
     *
     * @param {string} unitId
     * @param {{ mode?: string, skill?: string }} [runOptions]
     */
    verifyUiUx(unitId, runOptions = {}) {
      const begin = this.run(['begin', '--unit', unitId, '--skill', runOptions.skill ?? UI_SKILL, '--mode', runOptions.mode ?? 'full']);
      if (begin.status !== 0) throw new Error(`begin failed: ${begin.stderr}`);
      const runId = begin.json.runId;
      this.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'state matrix and feedback channels reviewed']);
      this.run(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "process.exit(0)"`]);
      this.run(['evidence', '--run', runId, '--kind', 'browser', '--outcome', 'pass', '--summary', 'walked loading, error and data states with Playwright']);
      const record = this.run(['record', '--run', runId, '--result', 'verified']);
      if (record.status !== 0) throw new Error(`record failed: ${record.stderr}`);
      return record.json;
    },

    /** Accredited performance run with a before/after measurement. */
    verifyPerformance(unitId) {
      const begin = this.run(['begin', '--unit', unitId, '--skill', PERFORMANCE_SKILL, '--mode', 'full']);
      if (begin.status !== 0) throw new Error(`begin failed: ${begin.stderr}`);
      const runId = begin.json.runId;
      this.run(['evidence', '--run', runId, '--kind', 'measurement', '--outcome', 'measured', '--summary', 'requests per save', '--metric', 'requests per save', '--before', '1', '--after', '1', '--tool', 'playwright', '--conditions', 'production build, cold cache']);
      this.run(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "process.exit(0)"`]);
      const record = this.run(['record', '--run', runId, '--result', 'verified']);
      if (record.status !== 0) throw new Error(`record failed: ${record.stderr}`);
      return record.json;
    },

    check(unitId, skill = UI_SKILL, extra = []) {
      const result = this.run(['check', '--unit', unitId, '--skill', skill, ...extra]);
      if (result.status !== 0) throw new Error(`check failed: ${result.stderr}`);
      return result.json;
    },

    cleanup() {
      fs.rmSync(base, { force: true, recursive: true });
    },
  };

  if (options.withUnits !== false) {
    for (const [id, definition] of Object.entries(UNITS)) fixture.writeUnit(id, definition);
  }
  git('add', '-A');
  git('commit', '--quiet', '-m', 'initial');
  return fixture;
}
