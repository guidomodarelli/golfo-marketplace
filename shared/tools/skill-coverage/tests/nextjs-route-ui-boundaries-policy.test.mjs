import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';

import { PERFORMANCE_SKILL, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const NEXTJS_SKILL = 'nextjs-route-ui-boundaries';
const PASSING_COMMAND = `"${process.execPath}" -e "process.exit(0)"`;

const MEMBERS_LIST = 'platform.members.list';
const MEMBERS_INVITE = 'platform.members.invite';
const PAYMENTS = 'platform.payments.view';
const SETTINGS = 'platform.settings.form';
const PRICING = 'public.pricing.view';
const PLATFORM_UNITS = [MEMBERS_LIST, MEMBERS_INVITE, PAYMENTS, SETTINGS];
const ALL_UNITS = [...PLATFORM_UNITS, PRICING];

const PLATFORM_LAYOUT = 'app/(platform)/layout.tsx';
const MEMBERS_PAGE = 'app/(platform)/members/page.tsx';
const MEMBERS_ERROR = 'app/(platform)/members/error.tsx';
const MEMBERS_PANEL = 'components/members/members-panel.tsx';
const PAYMENTS_PAGE = 'app/(platform)/payments/page.tsx';
const SETTINGS_FORM = 'components/settings/settings-form.tsx';
const DATA_TABLE = 'components/ui/data-table.tsx';

/**
 * A small App Router tree: a root layout, a `(platform)` route group with a
 * shared layout and sidebar over three routes (members with its own loading
 * and error boundaries, payments that awaits data, settings with a form),
 * and a `(public)` group without that layout. `DataTable` is shared by
 * members and payments.
 */
const APP_FILES = {
  'app/layout.tsx': 'export default function RootLayout({ children }) {\n  return <html lang="es"><body>{children}</body></html>;\n}\n',
  [PLATFORM_LAYOUT]: `import { Sidebar } from "@/components/platform/sidebar";

export default function PlatformLayout({ children }) {
  return (
    <div>
      <Sidebar />
      <main>{children}</main>
    </div>
  );
}
`,
  'components/platform/sidebar.tsx': 'import Link from "next/link";\n\nexport function Sidebar() {\n  return <nav><Link href="/members">Miembros</Link></nav>;\n}\n',
  [MEMBERS_PAGE]: 'import { MembersPanel } from "@/components/members/members-panel";\n\nexport default function MembersPage() {\n  return <MembersPanel />;\n}\n',
  'app/(platform)/members/loading.tsx': 'import { MembersSkeleton } from "@/components/members/members-skeleton";\n\nexport default function Loading() {\n  return <MembersSkeleton />;\n}\n',
  [MEMBERS_ERROR]: '"use client";\n\nexport default function MembersError({ reset }) {\n  return <button onClick={() => reset()}>Reintentar</button>;\n}\n',
  'components/members/members-skeleton.tsx': 'import styles from "./members-skeleton.module.scss";\n\nexport function MembersSkeleton() {\n  return <div className={styles.row} aria-hidden="true" />;\n}\n',
  'components/members/members-skeleton.module.scss': '.row { height: 48px; }\n',
  'components/members/members-panel.module.scss': '.panel { padding: 16px; }\n',
  [MEMBERS_PANEL]: `"use client";

import { useState } from "react";

import { DataTable } from "@/components/ui/data-table";
import { inviteMember } from "@/lib/members-client";
import styles from "./members-panel.module.scss";

export const MEMBERS_COPY = {
  inviteLabel: "Invitar",
  title: "Miembros",
} as const;

export function MembersPanel() {
  const [error, setError] = useState(null);
  const handleInvite = async () => {
    const result = await inviteMember("ana");
    if (!result.ok) setError(result.message);
  };
  return (
    <section className={styles.panel}>
      <h1>{MEMBERS_COPY.title}</h1>
      <button onClick={handleInvite}>{MEMBERS_COPY.inviteLabel}</button>
      <DataTable rows={[]} />
      {error}
    </section>
  );
}
`,
  [PAYMENTS_PAGE]: `import { DataTable } from "@/components/ui/data-table";
import { loadPayments } from "@/lib/payments";

export default async function PaymentsPage() {
  const payments = await loadPayments();
  return <DataTable rows={payments} />;
}
`,
  'app/(platform)/settings/page.tsx': 'import { SettingsForm } from "@/components/settings/settings-form";\n\nexport default function SettingsPage() {\n  return <SettingsForm />;\n}\n',
  [SETTINGS_FORM]: `"use client";

export function SettingsForm() {
  const handleSave = async () => {
    await fetch("/api/settings", { method: "POST" });
  };
  return <form onSubmit={handleSave}><button>Guardar</button></form>;
}
`,
  'app/(public)/pricing/page.tsx': 'export default function PricingPage() {\n  return <h1>Precios</h1>;\n}\n',
  [DATA_TABLE]: 'export function DataTable({ rows }) {\n  return <table><tbody>{rows.map((row) => <tr key={row.id} />)}</tbody></table>;\n}\n',
  'lib/members-client.ts': 'export async function inviteMember(name) {\n  const response = await fetch("/api/members", { body: JSON.stringify({ name }), method: "POST" });\n  return response.json();\n}\n',
  'lib/payments.ts': 'export async function loadPayments() {\n  return [];\n}\n',
  'next.config.ts': 'const nextConfig = {\n  reactStrictMode: true,\n};\n\nexport default nextConfig;\n',
};

const APP_UNITS = {
  [MEMBERS_INVITE]: {
    entries: [{ path: MEMBERS_PANEL, symbol: 'MembersPanel/handleInvite' }],
    hierarchy: { module: 'Platform', page: 'Members', section: 'Members panel', subflow: 'Invite member' },
    routes: ['/members'],
  },
  [MEMBERS_LIST]: {
    entries: [{ path: MEMBERS_PANEL, symbol: 'MembersPanel~shell' }],
    hierarchy: { module: 'Platform', page: 'Members', section: 'Members panel', subflow: 'List members' },
    routes: ['/members'],
  },
  [PAYMENTS]: {
    entries: [{ path: PAYMENTS_PAGE, symbol: 'default' }],
    hierarchy: { module: 'Platform', page: 'Payments', section: null, subflow: 'view' },
    routes: ['/payments'],
  },
  [PRICING]: {
    entries: [{ path: 'app/(public)/pricing/page.tsx', symbol: 'default' }],
    hierarchy: { module: 'Public', page: 'Pricing', section: null, subflow: 'view' },
    routes: ['/pricing'],
  },
  [SETTINGS]: {
    entries: [{ path: SETTINGS_FORM, symbol: 'SettingsForm' }],
    hierarchy: { module: 'Platform', page: 'Settings', section: null, subflow: 'Save settings' },
    routes: ['/settings'],
  },
};

/**
 * Accredited run of the Next.js policy: a boundary review, a witnessed
 * build command and a browser walk-through of the navigation states.
 *
 * @param {ReturnType<typeof createFixture>} fixture
 * @param {string} unitId
 * @param {{ mode?: string }} [options]
 */
function verifyNextjs(fixture, unitId, options = {}) {
  const begin = fixture.run(['begin', '--unit', unitId, '--skill', NEXTJS_SKILL, '--mode', options.mode ?? 'full']);
  if (begin.status !== 0) throw new Error(`begin failed: ${begin.stderr}`);
  const runId = begin.json.runId;
  fixture.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'segment map, server/client split and skeletons reviewed']);
  fixture.run(['evidence', '--run', runId, '--kind', 'command', '--exec', PASSING_COMMAND]);
  fixture.run(['evidence', '--run', runId, '--kind', 'browser', '--outcome', 'pass', '--summary', 'sibling navigation keeps the sidebar, skeleton in the destination segment, error contained with retry']);
  const record = fixture.run(['record', '--run', runId, '--result', 'verified']);
  if (record.status !== 0) throw new Error(`record failed: ${record.stderr}`);
  return record.json;
}

/**
 * @param {ReturnType<typeof createFixture>} fixture
 * @param {string[]} paths
 * @returns {string[]} Units whose Next.js closure includes the paths.
 */
function affectedUnits(fixture, paths) {
  const result = fixture.run(['affected', '--skill', NEXTJS_SKILL, '--paths', ...paths]);
  if (result.status !== 0) throw new Error(`affected failed: ${result.stderr}`);
  return result.json.affected.map((item) => item.unit).sort();
}

describe('nextjs-route-ui-boundaries policy', () => {
  let fixture;
  let verifiedHead;
  before(() => {
    fixture = createFixture({ withUnits: false });
    fixture.writeSkill(NEXTJS_SKILL, '1.2.0');
    for (const [filePath, content] of Object.entries(APP_FILES)) fixture.write(filePath, content);
    for (const [id, definition] of Object.entries(APP_UNITS)) fixture.writeUnit(id, definition);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'app router tree');
    for (const unitId of ALL_UNITS) verifyNextjs(fixture, unitId);
    fixture.verifyUiUx(MEMBERS_INVITE);
    fixture.verifyPerformance(MEMBERS_INVITE);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');
    verifiedHead = fixture.git('rev-parse', 'HEAD');
  });
  beforeEach(() => {
    fixture.git('reset', '--quiet', '--hard', verifiedHead);
    fixture.git('clean', '--quiet', '-fd');
  });
  after(() => fixture.cleanup());

  test('the closure includes the layouts, boundaries and configuration that wrap the route', () => {
    const inputs = fixture.run(['inputs', '--unit', MEMBERS_INVITE, '--skill', NEXTJS_SKILL]).json.inputs;
    const files = new Set(Object.keys(inputs).map((key) => key.split('#')[0]));
    for (const filePath of ['app/layout.tsx', PLATFORM_LAYOUT, 'components/platform/sidebar.tsx', MEMBERS_PAGE, 'app/(platform)/members/loading.tsx', MEMBERS_ERROR, 'components/members/members-skeleton.module.scss', 'next.config.ts']) {
      assert.ok(files.has(filePath), `${filePath} missing from the closure`);
    }
    assert.ok(!files.has(PAYMENTS_PAGE), 'a sibling route is not part of the unit');
    const uiInputs = fixture.run(['inputs', '--unit', MEMBERS_INVITE, '--skill', UI_SKILL]).json.inputs;
    assert.ok(!Object.keys(uiInputs).some((key) => key.startsWith(PLATFORM_LAYOUT)), 'other policies keep their own closure');
  });

  test('parallel route slots, their fallbacks and the middleware join the routes they wrap', () => {
    fixture.write('app/(platform)/members/@details/page.tsx', 'export default function MemberDetails() {\n  return <aside />;\n}\n');
    fixture.write('app/(platform)/members/@details/default.tsx', 'export default function NoDetails() {\n  return null;\n}\n');
    fixture.write('middleware.ts', 'export function middleware() {}\n\nexport const config = { matcher: ["/members/:path*"] };\n');
    assert.deepEqual(affectedUnits(fixture, ['app/(platform)/members/@details/page.tsx', 'app/(platform)/members/@details/default.tsx']), [MEMBERS_INVITE, MEMBERS_LIST]);
    assert.deepEqual(affectedUnits(fixture, ['middleware.ts']), [...ALL_UNITS].sort());
    const check = fixture.check(MEMBERS_LIST, NEXTJS_SKILL);
    assert.ok(check.relevantChanges.some((change) => change.key.startsWith('middleware.ts#') && change.reason.startsWith('project configuration')));
  });

  test('the layout wrapping a parallel slot fallback is part of the routes that render the slot', () => {
    fixture.write('app/@panel/default.tsx', 'export default function NoPanel() {\n  return null;\n}\n');
    fixture.write('app/@panel/layout.tsx', 'export default function PanelLayout({ children }) {\n  return <aside>{children}</aside>;\n}\n');
    verifyNextjs(fixture, PRICING, { mode: 'incremental' });
    fixture.replace('app/@panel/layout.tsx', 'export default function PanelLayout', '"use client";\n\nexport default function PanelLayout');
    const check = fixture.check(PRICING, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.ok(check.relevantChanges.some((change) => change.key === 'app/@panel/layout.tsx#<module>'));
  });

  test('verified coverage stays current and --force-full still forces a full audit', () => {
    for (const unitId of ALL_UNITS) {
      const check = fixture.check(unitId, NEXTJS_SKILL);
      assert.equal(check.state, 'verified', unitId);
      assert.equal(check.decision, 'skip', unitId);
    }
    const forced = fixture.check(PAYMENTS, NEXTJS_SKILL, ['--force-full']);
    assert.equal(forced.decision, 'full');
    assert.ok(forced.reasons.includes('full audit requested: previous coverage is not reused'));
    assert.match(forced.suggestedScope[0], /whole unit platform\.payments\.view \(\/payments\): map the segments/);
  });

  test('a client component handler change invalidates only its own subflow', () => {
    fixture.replace(MEMBERS_PANEL, 'const result = await inviteMember("ana");', 'const result = await inviteMember("ana", { role: "member" });');
    const invite = fixture.check(MEMBERS_INVITE, NEXTJS_SKILL);
    assert.equal(invite.freshness, 'stale');
    assert.equal(invite.decision, 'incremental');
    assert.ok(invite.relevantChanges.some((change) => change.key === `${MEMBERS_PANEL}#MembersPanel/handleInvite` && change.reason.startsWith('interactive handler changed')));
    assert.ok(invite.suggestedScope.some((scope) => scope.includes('handleInvite') && scope.includes('server action calls')));
    for (const unitId of [MEMBERS_LIST, PAYMENTS, SETTINGS, PRICING]) assert.equal(fixture.check(unitId, NEXTJS_SKILL).decision, 'skip', unitId);
  });

  test('a shared layout change identifies every route under it and no other', () => {
    assert.deepEqual(affectedUnits(fixture, [PLATFORM_LAYOUT]), [...PLATFORM_UNITS].sort());
    assert.deepEqual(affectedUnits(fixture, ['app/layout.tsx']), [...ALL_UNITS].sort());
    fixture.replace(PLATFORM_LAYOUT, 'export default function PlatformLayout({ children }) {', 'export default async function PlatformLayout({ children }) {\n  const tribe = await loadTribe();');
    fixture.replace(PLATFORM_LAYOUT, 'import { Sidebar }', 'import { loadTribe } from "@/lib/tribes";\nimport { Sidebar }');
    fixture.write('lib/tribes.ts', 'export async function loadTribe() {\n  return { name: "x" };\n}\n');
    for (const unitId of PLATFORM_UNITS) {
      const check = fixture.check(unitId, NEXTJS_SKILL);
      assert.equal(check.freshness, 'stale', unitId);
      assert.ok(check.relevantChanges.some((change) => change.key.startsWith(`${PLATFORM_LAYOUT}#`) && /adds awaited work to the render path \(.*\+1 awaited steps/.test(change.reason)), unitId);
    }
    assert.equal(fixture.check(PRICING, NEXTJS_SKILL).decision, 'skip');
  });

  test('a shared chrome component reached through the layout is part of every route under it', () => {
    fixture.replace('components/platform/sidebar.tsx', 'import Link from "next/link";', '"use client";\n\nimport Link from "next/link";');
    for (const unitId of PLATFORM_UNITS) {
      const check = fixture.check(unitId, NEXTJS_SKILL);
      assert.ok(check.relevantChanges.some((change) => change.key === 'components/platform/sidebar.tsx#<module>'), unitId);
    }
    assert.equal(fixture.check(PRICING, NEXTJS_SKILL).decision, 'skip');
  });

  test('adding "use client" to a server container is relevant to the route', () => {
    fixture.replace(PAYMENTS_PAGE, 'import { DataTable }', '"use client";\n\nimport { DataTable }');
    const check = fixture.check(PAYMENTS, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    const change = check.relevantChanges.find((item) => item.key === `${PAYMENTS_PAGE}#<module>`);
    assert.equal(change?.reason, 'module directives ("use client", "use server") or side-effect imports changed');
    assert.ok(check.suggestedScope.some((scope) => scope.includes('where the server/client boundary falls')));
  });

  test('a new await in a page is reported as work that can block navigation', () => {
    fixture.replace(PAYMENTS_PAGE, 'const payments = await loadPayments();', 'const payments = await loadPayments();\n  const totals = await loadPayments();');
    const check = fixture.check(PAYMENTS, NEXTJS_SKILL);
    assert.equal(check.decision, 'incremental');
    assert.ok(check.relevantChanges.some((change) => /^adds awaited work to the render path \(\+1 awaited steps, \+1 calls to I\/O helpers\)/.test(change.reason)));
  });

  test('a new loading.tsx is relevant to its segment only', () => {
    fixture.write('app/(platform)/payments/loading.tsx', 'export default function Loading() {\n  return <div aria-busy="true" />;\n}\n');
    const payments = fixture.check(PAYMENTS, NEXTJS_SKILL);
    assert.equal(payments.freshness, 'stale');
    assert.ok(payments.relevantChanges.some((change) => change.change === 'added' && change.key.startsWith('app/(platform)/payments/loading.tsx#') && change.reason === 'new route file: segment, layout or boundary added'));
    assert.deepEqual(affectedUnits(fixture, ['app/(platform)/payments/loading.tsx']), [PAYMENTS]);
    assert.equal(fixture.check(MEMBERS_LIST, NEXTJS_SKILL).decision, 'skip');
  });

  test('an error.tsx change reaches the routes of its segment and a group error.tsx reaches the whole group', () => {
    fixture.replace(MEMBERS_ERROR, '<button onClick={() => reset()}>Reintentar</button>', '<button onClick={() => reset()}>Volver a intentar</button>');
    assert.deepEqual(affectedUnits(fixture, [MEMBERS_ERROR]), [MEMBERS_INVITE, MEMBERS_LIST]);
    assert.equal(fixture.check(MEMBERS_LIST, NEXTJS_SKILL).freshness, 'stale');
    assert.equal(fixture.check(PAYMENTS, NEXTJS_SKILL).decision, 'skip');
    fixture.write('app/(platform)/error.tsx', '"use client";\n\nexport default function PlatformError({ reset }) {\n  return <button onClick={() => reset()}>Reintentar</button>;\n}\n');
    assert.deepEqual(affectedUnits(fixture, ['app/(platform)/error.tsx']), [...PLATFORM_UNITS].sort());
    assert.equal(fixture.check(PRICING, NEXTJS_SKILL).decision, 'skip');
  });

  test('a page moved to another route group is relevant even with identical content', () => {
    fixture.write('app/(admin)/layout.tsx', 'export default function AdminLayout({ children }) {\n  return <section>{children}</section>;\n}\n');
    fixture.write('app/(admin)/settings/page.tsx', fixture.read('app/(platform)/settings/page.tsx'));
    fixture.git('rm', '--quiet', 'app/(platform)/settings/page.tsx');
    const check = fixture.check(SETTINGS, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.notEqual(check.decision, 'skip');
    assert.ok(check.relevantChanges.some((change) => change.change === 'relocated' && change.key.startsWith('app/(admin)/settings/page.tsx#') && change.reason.startsWith('route file moved to another segment')));
    assert.ok(check.relevantChanges.some((change) => change.change === 'removed' && change.key.startsWith(`${PLATFORM_LAYOUT}#`)));
    assert.ok(check.relevantChanges.some((change) => change.change === 'added' && change.key.startsWith('app/(admin)/layout.tsx#')));
  });

  test('a shared component moved to another file without changes stays current', () => {
    fixture.write('components/ui/table/data-table.tsx', fixture.read(DATA_TABLE));
    fixture.git('rm', '--quiet', DATA_TABLE);
    fixture.replace(MEMBERS_PANEL, '"@/components/ui/data-table"', '"@/components/ui/table/data-table"');
    fixture.replace(PAYMENTS_PAGE, '"@/components/ui/data-table"', '"@/components/ui/table/data-table"');
    for (const unitId of [MEMBERS_LIST, PAYMENTS]) {
      const check = fixture.check(unitId, NEXTJS_SKILL);
      assert.equal(check.decision, 'skip', unitId);
      assert.ok(check.ignoredChanges.some((change) => change.change === 'relocated' && change.reason === 'moved without changes outside the route tree'), unitId);
    }
  });

  test('a shared component change invalidates every route that renders it', () => {
    fixture.replace(DATA_TABLE, '<table>', '<table className="striped">');
    assert.deepEqual(affectedUnits(fixture, [DATA_TABLE]), [MEMBERS_INVITE, MEMBERS_LIST, PAYMENTS]);
    for (const unitId of [MEMBERS_LIST, PAYMENTS]) assert.equal(fixture.check(unitId, NEXTJS_SKILL).freshness, 'stale', unitId);
    assert.equal(fixture.check(SETTINGS, NEXTJS_SKILL).decision, 'skip');
  });

  test('a next.config change invalidates every route', () => {
    fixture.replace('next.config.ts', 'reactStrictMode: true,', 'reactStrictMode: true,\n  cacheComponents: true,');
    for (const unitId of ALL_UNITS) {
      const check = fixture.check(unitId, NEXTJS_SKILL);
      assert.equal(check.freshness, 'stale', unitId);
      assert.ok(check.relevantChanges.some((change) => change.key.startsWith('next.config.ts#') && change.reason === 'project configuration of rendering, caching or navigation changed: applies to every route'), unitId);
      assert.ok(check.suggestedScope.some((scope) => scope.includes('cacheComponents')), unitId);
    }
  });

  test('formatting, comments, copy and styles outside skeletons keep the coverage current', () => {
    fixture.replace(PAYMENTS_PAGE, 'return <DataTable rows={payments} />;', '// Payments of the tribe, newest first.\n  return <DataTable\n    rows={payments}\n  />;');
    fixture.replace(MEMBERS_PANEL, 'title: "Miembros",', 'title: "Miembros de la tribu",');
    fixture.replace('components/members/members-panel.module.scss', 'padding: 16px;', 'padding: 24px;');
    assert.equal(fixture.check(PAYMENTS, NEXTJS_SKILL).decision, 'skip');
    const members = fixture.check(MEMBERS_LIST, NEXTJS_SKILL);
    assert.equal(members.decision, 'skip');
    const reasons = members.ignoredChanges.map((change) => change.reason);
    assert.ok(reasons.includes('copy or display member: no route boundary depends on it'));
    assert.ok(reasons.includes('styles outside skeletons and loading boundaries: no route boundary or server/client decision depends on them'));
    assert.equal(fixture.check(MEMBERS_LIST, UI_SKILL).decision, 'full', 'UI/UX never ran on this unit');
  });

  test('styles of a skeleton reached from loading.tsx are relevant', () => {
    fixture.replace('components/members/members-skeleton.module.scss', 'height: 48px;', 'height: 56px;');
    const check = fixture.check(MEMBERS_LIST, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.ok(check.relevantChanges.some((change) => change.reason === 'styles of a skeleton or loading boundary changed'));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('final shape, reserved heights and reduced motion')));
  });

  test('a stylesheet shared by a component and a loading boundary is relevant whichever reaches it first', () => {
    // The panel entry reaches the stylesheet before the loading boundary of
    // the route context does, so its first dependency path is not loading UI.
    fixture.write('app/(platform)/members/loading.tsx', 'import styles from "@/components/members/members-panel.module.scss";\n\nexport default function Loading() {\n  return <div className={styles.panel} aria-busy="true" />;\n}\n');
    verifyNextjs(fixture, MEMBERS_LIST, { mode: 'incremental' });
    fixture.replace('components/members/members-panel.module.scss', 'padding: 16px;', 'padding: 24px;');
    const check = fixture.check(MEMBERS_LIST, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.ok(check.relevantChanges.some((change) => change.key === 'components/members/members-panel.module.scss#*' && change.reason === 'styles of a skeleton or loading boundary changed'));
  });

  test('a convention file renamed inside its segment is relevant even with identical content', () => {
    const loadingPath = 'app/(platform)/members/loading.tsx';
    fixture.write('app/(platform)/members/template.tsx', fixture.read(loadingPath));
    fixture.git('rm', '--quiet', loadingPath);
    const check = fixture.check(MEMBERS_LIST, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.notEqual(check.decision, 'skip');
    assert.ok(check.relevantChanges.some((change) => change.change === 'relocated' && change.key.startsWith('app/(platform)/members/template.tsx#') && change.reason === 'route convention changed (loading → template): the boundary the segment defines changed'));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('loading, error or template boundary')));
  });

  test('data a page awaits before rendering the unit is part of a unit that enters through a component', () => {
    fixture.write('lib/members.ts', 'export async function loadMembers() {\n  return [];\n}\n');
    fixture.write(MEMBERS_PAGE, 'import { MembersPanel } from "@/components/members/members-panel";\nimport { loadMembers } from "@/lib/members";\n\nexport default async function MembersPage() {\n  await loadMembers();\n  return <MembersPanel />;\n}\n');
    verifyNextjs(fixture, MEMBERS_LIST, { mode: 'incremental' });
    fixture.replace('lib/members.ts', 'export async function loadMembers() {\n  return [];', 'import { cookies } from "next/headers";\n\nexport async function loadMembers() {\n  const store = await cookies();\n  return store.get("tribe") ? [] : [];');
    const check = fixture.check(MEMBERS_LIST, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.ok(check.relevantChanges.some((change) => change.key === 'lib/members.ts#loadMembers'));
    // The section components the page renders are not followed from the page context.
    const inputs = fixture.run(['inputs', '--unit', PAYMENTS, '--skill', NEXTJS_SKILL]).json.inputs;
    assert.ok(Object.keys(inputs).some((key) => key.startsWith('lib/payments.ts#')), 'the payments loader is tracked');
  });

  test('a framework upgrade invalidates routes whose files never import it', () => {
    fixture.replace('package.json', '"react": "19.0.0"', '"next": "15.5.0", "react": "19.0.0"');
    verifyNextjs(fixture, PRICING, { mode: 'incremental' });
    fixture.replace('package.json', '"next": "15.5.0"', '"next": "16.0.0"');
    assert.ok(affectedUnits(fixture, ['package.json']).includes(PRICING));
    const check = fixture.check(PRICING, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.ok(check.relevantChanges.some((change) => change.key === 'pkg:next' && change.reason === 'framework package version changed (next): App Router APIs may differ'));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('against the installed version')));
  });

  test('a declared test run never accredits a lightweight run', () => {
    fixture.replace('app/(public)/pricing/page.tsx', '<h1>Precios</h1>', '<h1>Planes y precios</h1>');
    const begin = fixture.run(['begin', '--unit', PRICING, '--skill', NEXTJS_SKILL, '--mode', 'lightweight']);
    const runId = begin.json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'heading copy reviewed']);
    fixture.run(['evidence', '--run', runId, '--kind', 'test', '--outcome', 'pass', '--summary', 'pricing tests passed']);
    const record = fixture.run(['record', '--run', runId, '--result', 'verified']);
    assert.equal(record.status, 0, record.stderr);
    assert.equal(record.json.result, 'partial');
    assert.ok(record.json.downgradeReasons.includes('test evidence (build, lint, typecheck or tests) must be run with evidence --exec, not declared'));
  });

  test('a loading UI member of a copy dictionary stays relevant while its copy members do not', () => {
    fixture.write('components/members/members-content.tsx', 'export const content = {\n  fallback: <div aria-busy="true" />,\n  title: "Miembros",\n};\n');
    fixture.replace(MEMBERS_PANEL, 'import styles from "./members-panel.module.scss";', 'import styles from "./members-panel.module.scss";\nimport { Suspense } from "react";\nimport { content } from "./members-content";');
    fixture.replace(MEMBERS_PANEL, '<DataTable rows={[]} />', '<Suspense fallback={content.fallback}><DataTable rows={[]} /></Suspense>\n      <p>{content.title}</p>');
    verifyNextjs(fixture, MEMBERS_LIST, { mode: 'incremental' });
    fixture.replace('components/members/members-content.tsx', 'title: "Miembros",', 'title: "Miembros de la tribu",');
    assert.equal(fixture.check(MEMBERS_LIST, NEXTJS_SKILL).decision, 'skip');
    fixture.replace('components/members/members-content.tsx', 'fallback: <div aria-busy="true" />,', 'fallback: null,');
    const check = fixture.check(MEMBERS_LIST, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.ok(check.relevantChanges.some((change) => change.key === 'components/members/members-content.tsx#content.fallback'));
  });

  test('a dependency that cannot be resolved statically gets a conservative review', () => {
    fixture.replace(MEMBERS_PANEL, 'import { inviteMember } from "@/lib/members-client";', 'import { inviteMember } from "@/lib/members-client";\nimport { trackInvite } from "@/lib/generated/analytics";');
    fixture.replace(MEMBERS_PANEL, 'if (!result.ok) setError(result.message);', 'trackInvite();\n    if (!result.ok) setError(result.message);');
    const check = fixture.check(MEMBERS_INVITE, NEXTJS_SKILL);
    assert.notEqual(check.decision, 'skip');
    assert.ok(check.relevantChanges.some((change) => change.key === 'unresolved:@/lib/generated/analytics' && change.reason === 'import that cannot be resolved: boundary impact unknown, reviewed conservatively'));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('import that cannot be resolved')));
  });

  test('insufficient evidence records partial, never verified', () => {
    fixture.replace(PAYMENTS_PAGE, 'return <DataTable rows={payments} />;', 'return <section><DataTable rows={payments} /></section>;');
    const begin = fixture.run(['begin', '--unit', PAYMENTS, '--skill', NEXTJS_SKILL, '--mode', 'incremental']);
    const runId = begin.json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'page wrapper reviewed']);
    fixture.run(['evidence', '--run', runId, '--kind', 'command', '--outcome', 'pass', '--summary', 'next build passed']);
    const record = fixture.run(['record', '--run', runId, '--result', 'verified']);
    assert.equal(record.status, 0, record.stderr);
    assert.equal(record.json.result, 'partial');
    assert.ok(record.json.downgradeReasons.includes('command evidence (build, lint, typecheck or tests) must be run with evidence --exec, not declared'));
    assert.ok(record.json.downgradeReasons.includes('missing passing evidence of kind command'));
    assert.ok(record.json.downgradeReasons.includes('missing passing evidence of kind browser or test'));
    const check = fixture.check(PAYMENTS, NEXTJS_SKILL);
    assert.equal(check.state, 'partial');
    assert.equal(check.decision, 'incremental');
    assert.ok(check.suggestedScope.some((scope) => scope.startsWith('pending from the previous run: missing passing evidence of kind command')));
  });

  test('coverage recorded over uncommitted code stays current after commit and rebase', () => {
    fixture.replace(PAYMENTS_PAGE, 'return <DataTable rows={payments} />;', 'return <section><DataTable rows={payments} /></section>;');
    verifyNextjs(fixture, PAYMENTS, { mode: 'incremental' });
    assert.ok(fixture.readRecord(NEXTJS_SKILL, PAYMENTS).verified.baseline.uncommittedFiles.includes(PAYMENTS_PAGE));
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'wrap payments');
    assert.equal(fixture.check(PAYMENTS, NEXTJS_SKILL).decision, 'skip');
    fixture.git('commit', '--quiet', '--amend', '-m', 'wrap payments (reworded)');
    const rebased = fixture.check(PAYMENTS, NEXTJS_SKILL);
    assert.equal(rebased.decision, 'skip');
    assert.equal(rebased.freshness, 'current');
  });

  test('a Next.js run never touches the UI/UX or performance records of the same unit', () => {
    const uiBefore = fixture.readRecord(UI_SKILL, MEMBERS_INVITE);
    const performanceBefore = fixture.readRecord(PERFORMANCE_SKILL, MEMBERS_INVITE);
    fixture.replace(MEMBERS_PANEL, 'const result = await inviteMember("ana");', 'const result = await inviteMember("ana", { role: "member" });');
    verifyNextjs(fixture, MEMBERS_INVITE, { mode: 'incremental' });
    assert.deepEqual(fixture.readRecord(UI_SKILL, MEMBERS_INVITE), uiBefore);
    assert.deepEqual(fixture.readRecord(PERFORMANCE_SKILL, MEMBERS_INVITE), performanceBefore);
    assert.equal(fixture.check(MEMBERS_INVITE, NEXTJS_SKILL).decision, 'skip');
    assert.equal(fixture.check(MEMBERS_INVITE, UI_SKILL).freshness, 'stale', 'UI/UX coverage is not refreshed by a Next.js run');
  });

  test('UI/UX coverage alone never accredits Next.js coverage', () => {
    fixture.writeUnit('platform.settings.extra', { entries: [{ path: SETTINGS_FORM, symbol: 'SettingsForm/handleSave' }], hierarchy: { module: 'Platform', page: 'Settings', section: null, subflow: 'Extra' }, routes: ['/settings'] });
    fixture.verifyUiUx('platform.settings.extra');
    const check = fixture.check('platform.settings.extra', NEXTJS_SKILL);
    assert.equal(check.state, 'unreviewed');
    assert.equal(check.decision, 'full');
  });

  test('a rules change of the skill re-checks verified units against the changed rules', () => {
    fixture.writeSkill(NEXTJS_SKILL, '1.3.0', 'New rule: forbidden.tsx for permission errors.');
    const check = fixture.check(PRICING, NEXTJS_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.equal(check.decision, 'incremental');
    assert.ok(check.suggestedScope.includes('re-check the unit against the rules changed in nextjs-route-ui-boundaries/SKILL.md'));
    fixture.writeSkill(NEXTJS_SKILL, '2.0.0', 'Major rewrite.');
    assert.equal(fixture.check(PRICING, NEXTJS_SKILL).decision, 'full');
  });
});
