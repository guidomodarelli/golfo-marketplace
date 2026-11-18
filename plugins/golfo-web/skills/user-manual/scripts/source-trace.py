#!/usr/bin/env python3
"""Records which code a manual documents, and tells what changed in that code since then.

record — writes the source metas into the manual's <head> and the "Código:" line into its doc-footer:

    python3 source-trace.py record <manual.html> --repo <path-to-repo> --ref origin/develop \
        --files app/pages/flow app/components/Thing/index.tsx i18n/es-AR/messages.po

    <meta name="heritage:source-repo" content="example-org/example-app">
    <meta name="heritage:source-ref" content="origin/develop">
    <meta name="heritage:source-commit" content="7f4a77365a…">
    <meta name="heritage:source-files" content="app/pages/flow app/components/Thing/index.tsx …">
    <meta name="heritage:source-commit-url" content="https://github.com/example-org/example-app/commit/7f4a77365a…">

  and writes <footer class="doc-footer">Para el equipo técnico · Código: <ref> @ <commit></footer> at the
  end of the document, linked to that commit (new tab). Only maintainers need it, so it stays out of the
  doc-meta (an old "Código:" span there is removed). Inside an iframe viewer the link opens only
  when the viewer allows links to the repository's GitHub organization.

  --files takes the files and directories read to write the manual (pages, components, server hooks,
  API routes, validations, constants, translations). Directories cover files added to them later.

diff — on the next update, lists what changed in those paths since the recorded commit:

    python3 source-trace.py diff <manual.html> --repo <path-to-repo> [--ref origin/develop] [--patch]

  It fetches the ref, prints `git log` and `git diff --stat` for the recorded paths (and the full patch
  with --patch), so the update starts from the real changes instead of re-reading the whole flow.
  Older manuals without the metas but with a doc-footer commit link are compared from that commit over
  the whole repository; the ref defaults to origin/develop.
"""
import argparse
import html
import re
import subprocess
import sys
from pathlib import Path

META_PATTERN = '<meta name="heritage:source-{name}" content="([^"]*)">'
VIEWPORT_META = '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
FOOTER_CSS = '.doc-footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);font-family:var(--mono);font-size:11px;color:var(--label);}'
FOOTER_ANCHOR = '<a class="back-to-top"'


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(['git', '-C', str(repo), *arguments], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'source-trace: git {" ".join(arguments)} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def repository_name(repo: Path) -> str:
    remote = git(repo, 'remote', 'get-url', 'origin')
    match = re.search(r'[:/]([^/:]+/[^/]+?)(?:\.git)?$', remote)
    return match.group(1) if match else remote


def repository_web_url(repo: Path) -> str:
    """Turns the origin remote (ssh or https) into its web URL, for commit links."""
    remote = git(repo, 'remote', 'get-url', 'origin')
    match = re.match(r'^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?/?$', remote) or re.match(r'^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$', remote)
    if not match:
        raise SystemExit(f'source-trace: cannot build a web URL from the origin remote {remote!r}')
    return f'https://{match.group(1)}/{match.group(2)}'


def read_meta(manual: str, name: str) -> str | None:
    match = re.search(META_PATTERN.format(name=name), manual)
    return html.unescape(match.group(1)) if match else None


def record(arguments) -> None:
    repo = Path(arguments.repo).expanduser()
    manual_path = Path(arguments.manual)
    manual = manual_path.read_text()
    git(repo, 'fetch', '--quiet', 'origin')
    commit = git(repo, 'rev-parse', arguments.ref)
    missing = [path for path in arguments.files if git(repo, 'ls-tree', '--name-only', commit, '--', path) == '']
    if missing:
        raise SystemExit(f'source-trace: paths not found at {arguments.ref}: {" ".join(missing)}')
    values = {
        'repo': repository_name(repo),
        'ref': arguments.ref,
        'commit': commit,
        'files': ' '.join(arguments.files),
        'commit-url': f'{repository_web_url(repo)}/commit/{commit}',
    }
    manual = re.sub(r'\s*<meta name="heritage:source-[a-z-]+" content="[^"]*">', '', manual)
    metas = ''.join(f'\n<meta name="heritage:source-{name}" content="{html.escape(value, quote=True)}">' for name, value in values.items())
    if VIEWPORT_META not in manual:
        raise SystemExit('source-trace: viewport meta not found; is this a Heritage manual?')
    manual = manual.replace(VIEWPORT_META, VIEWPORT_META + metas, 1)
    short_ref = arguments.ref.split('/', 1)[-1]
    commit_link = f'<a href="{html.escape(values["commit-url"], quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(short_ref)} @ {commit[:7]}</a>'
    footer = f'<footer class="doc-footer">Para el equipo técnico · Código: {commit_link}</footer>'
    manual = re.sub(r'\s*<span>Código: (?:<a [^>]*>[^<]*</a>|[^<]*)</span>', '', manual, count=1)
    manual, replaced = re.subn(r'<footer class="doc-footer">[\s\S]*?</footer>', lambda match: footer, manual, count=1)
    if not replaced:
        # A menu of manuals (one screen, no "Inicio" button) ends its content with </main>.
        if FOOTER_ANCHOR in manual:
            manual = manual.replace(FOOTER_ANCHOR, footer + '\n\n' + FOOTER_ANCHOR, 1)
        elif '</main>' in manual:
            manual = manual.replace('</main>', '</main>\n\n' + footer, 1)
        else:
            raise SystemExit('source-trace: neither the back-to-top button nor </main> found; is this a Heritage document?')
    if '.doc-footer{' not in manual:
        manual = manual.replace('</style>', FOOTER_CSS + '\n</style>', 1)
    manual_path.write_text(manual)
    print(f'source-trace: {values["repo"]} {arguments.ref} @ {commit[:7]} ({len(arguments.files)} paths) -> {manual_path}')


def diff(arguments) -> None:
    repo = Path(arguments.repo).expanduser()
    manual = Path(arguments.manual).read_text()
    commit = read_meta(manual, 'commit')
    files = (read_meta(manual, 'files') or '').split()
    ref = arguments.ref or read_meta(manual, 'ref') or 'origin/develop'
    if not commit:
        # Older manuals only link the commit in their doc-footer ("Código: develop @ <commit>"): compare
        # from it over the whole repository, since the documented paths were not recorded.
        footer = re.search(r'class="doc-footer"[^>]*>.*?/commit/([0-9a-f]{7,40})', manual, re.S)
        if not footer:
            raise SystemExit('source-trace: the manual records no commit (no heritage:source-* metas nor doc-footer link); read the whole flow and record it')
        commit = footer.group(1)
        files = []
        print('source-trace: no recorded paths; comparing the whole repository from the doc-footer commit')
    git(repo, 'fetch', '--quiet', 'origin')
    commit = git(repo, 'rev-parse', commit)
    head = git(repo, 'rev-parse', ref)
    print(f'source-trace: {read_meta(manual, "repo") or repository_name(repo)} {commit[:7]} -> {ref} @ {head[:7]}')
    if head == commit:
        print('No changes: the documented code is still current.')
        return
    print(git(repo, 'log', '--oneline', f'{commit}..{head}', '--', *files) or 'No commits touch the documented paths.')
    print(git(repo, 'diff', '--stat', commit, head, '--', *files) or 'No changes in the documented paths.')
    if arguments.patch:
        print(git(repo, 'diff', commit, head, '--', *files))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    record_parser = commands.add_parser('record')
    record_parser.add_argument('manual')
    record_parser.add_argument('--repo', required=True)
    record_parser.add_argument('--ref', default='origin/develop')
    record_parser.add_argument('--files', nargs='+', required=True)
    diff_parser = commands.add_parser('diff')
    diff_parser.add_argument('manual')
    diff_parser.add_argument('--repo', required=True)
    diff_parser.add_argument('--ref')
    diff_parser.add_argument('--patch', action='store_true')
    arguments = parser.parse_args()
    record(arguments) if arguments.command == 'record' else diff(arguments)


if __name__ == '__main__':
    sys.exit(main())
