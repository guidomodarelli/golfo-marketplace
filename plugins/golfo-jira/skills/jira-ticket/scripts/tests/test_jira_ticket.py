"""Tests de scripts/jira-ticket.py con una organización ficticia (ACME); sin datos reales."""

from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys

import pytest

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "jira-ticket.py"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

SITE_URL = "https://acme.atlassian.net"
BOARD_ID = 101
SPRINT_FIELD = "customfield_20001"
QUARTER_FIELD = "customfield_20002"
START_DATE_FIELD = "customfield_20003"
SPRINT_REGEX = r"^(?P<year>[0-9]{4})\.Q(?P<quarter>[1-4])\.R[0-9]+\.S[0-9]+$"
ACTIVE_SPRINT_ID = 501
TARGET_KEY = "ACME-42"
OTHER_KEY = "ACME-7"

BASE_ENV = {
    "JIRA_TICKET_ENV_FILE": "/nonexistent/jira-ticket.env",
    "JIRA_TICKET_SITE_URL": SITE_URL,
    "JIRA_TICKET_CLOUD_ID": "00000000-0000-0000-0000-000000000000",
    "JIRA_TICKET_PROJECT_KEY": "ACME",
    "JIRA_TICKET_BOARD_ID": str(BOARD_ID),
    "JIRA_TICKET_SPRINT_FIELD": SPRINT_FIELD,
    "JIRA_TICKET_SPRINT_NAME_REGEX": SPRINT_REGEX,
    "JIRA_TICKET_QUARTER_FIELD": QUARTER_FIELD,
    "JIRA_TICKET_START_DATE_FIELD": START_DATE_FIELD,
    "JIRA_TICKET_REPO_ID_SOURCES": ".app:application_name,package.json:name,basename",
    "JIRA_TICKET_REPO_PREFIXES": "acme_,acme-",
}


def load_module():
    spec = importlib.util.spec_from_file_location("jira_ticket", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


jira_ticket = load_module()


def config(**overrides):
    env = {**BASE_ENV, **overrides}
    return jira_ticket.load_config({key: value for key, value in env.items() if value is not None})


def run_cli(monkeypatch, capsys, argv, stdin_text="", env=None):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    exit_code = jira_ticket.main(argv, env if env is not None else BASE_ENV)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def sprint(sprint_id, name, state="active", board=BOARD_ID):
    return {"id": sprint_id, "name": name, "state": state, "boardId": board, "endDate": "2026-11-18T15:00:00.000Z"}


def jql_with(*sprints, field=SPRINT_FIELD):
    return {"issues": [{"key": f"ACME-{index}", "fields": {field: [item]}} for index, item in enumerate(sprints, start=1)], "isLast": True}


REALISTIC_JQL = jql_with(
    sprint(499, "2026.Q3.R3.S1", state="closed"),
    sprint(500, "2026.Q4.R1.S2", state="closed"),
    sprint(ACTIVE_SPRINT_ID, "2026.Q4.R2.S3"),
    sprint(900, "Sprint 7 otro equipo", board=202),
    sprint(ACTIVE_SPRINT_ID, "2026.Q4.R2.S3"),
)


def big_metadata(extra_fields=60, options_per_field=40):
    fields = [
        {"fieldId": "summary", "name": "Summary", "required": True, "hasDefaultValue": False, "schema": {"type": "string"}},
        {"fieldId": "issuetype", "name": "Issue Type", "required": True, "hasDefaultValue": False, "schema": {"type": "issuetype"}},
        {
            "fieldId": QUARTER_FIELD,
            "name": "Quarters",
            "required": False,
            "schema": {"type": "array"},
            "allowedValues": [{"self": "https://acme.example/opt", "id": str(9000 + i), "value": f"Q{q}/{y}"} for i, (y, q) in enumerate((y, q) for y in range(22, 28) for q in range(1, 5))],
        },
    ]
    for index in range(extra_fields):
        fields.append(
            {
                "fieldId": f"customfield_3{index:04d}",
                "name": f"Campo {index}",
                "required": False,
                "schema": {"type": "option", "custom": "com.example:select"},
                "allowedValues": [{"self": f"https://acme.example/opt/{index}/{n}", "id": str(n), "value": f"Opción larga de ejemplo número {n}"} for n in range(options_per_field)],
            }
        )
    return {"startAt": 0, "maxResults": 200, "total": len(fields), "fields": fields}


# --- config ------------------------------------------------------------------


def test_config_reports_missing_required_and_disabled_features(monkeypatch, capsys):
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["config"], env={"JIRA_TICKET_ENV_FILE": "/nonexistent"})
    data = json.loads(out)
    assert exit_code == jira_ticket.EXIT_CONFIG
    assert data["missing_required"] == ["JIRA_TICKET_SITE_URL", "JIRA_TICKET_CLOUD_ID", "JIRA_TICKET_PROJECT_KEY"]
    assert data["features"] == {"quarter": False, "start_date": False, "sprint": False, "default_assignee": False}


def test_config_reads_profile_file_and_env_wins(tmp_path):
    profile = tmp_path / "env"
    profile.write_text(
        "# perfil ACME\n"
        "export JIRA_TICKET_SITE_URL=https://file.atlassian.net\n"
        "JIRA_TICKET_PROJECT_KEY='ACME'\n"
        'export JIRA_TICKET_SPRINT_NAME_REGEX="^(?P<year>[0-9]{4})\\.Q(?P<quarter>[1-4])\\.R[0-9]+\\.S[0-9]+$"\n'
        "export JIRA_TICKET_CLOUD_ID=abc # comentario\n",
        encoding="utf-8",
    )
    loaded = jira_ticket.load_config({"JIRA_TICKET_ENV_FILE": str(profile), "JIRA_TICKET_SITE_URL": SITE_URL})
    assert loaded.get("SITE_URL") == SITE_URL and loaded.sources["SITE_URL"] == "env"
    assert loaded.get("PROJECT_KEY") == "ACME" and loaded.sources["PROJECT_KEY"] == "file"
    assert loaded.get("CLOUD_ID") == "abc"
    assert loaded.get("SPRINT_NAME_REGEX") == SPRINT_REGEX
    assert loaded.get("STORY_TYPE") == "Story" and loaded.sources["STORY_TYPE"] == "default"
    assert loaded.missing_required == []


def test_config_file_is_never_executed(tmp_path):
    # Ruta POSIX: una barra invertida sin comillas se interpreta como escape, igual que en el shell.
    marker = (tmp_path / "pwned").as_posix()
    profile = tmp_path / "env"
    profile.write_text(f"export JIRA_TICKET_PROJECT_KEY=$(touch {marker})\n", encoding="utf-8")
    loaded = jira_ticket.load_config({"JIRA_TICKET_ENV_FILE": str(profile)})
    assert not pathlib.Path(marker).exists()
    assert loaded.get("PROJECT_KEY") == f"$(touch {marker})"


# --- quarter ---------------------------------------------------------------


@pytest.mark.parametrize(("date", "expected"), [("2026-01-01", "Q1/26"), ("2026-03-31", "Q1/26"), ("2026-04-01", "Q2/26"), ("2026-11-13", "Q4/26"), ("2026-12-31", "Q4/26")])
def test_quarter_boundaries(date, expected):
    assert jira_ticket.quarter_for(dt.date.fromisoformat(date))["quarters_value"] == expected


def test_quarter_custom_format():
    assert jira_ticket.quarter_for(dt.date(2026, 11, 13), "Q{quarter}-{yyyy}")["quarters_value"] == "Q4-2026"


def test_quarter_option_from_metadata(monkeypatch, capsys):
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["quarter", "--date", "2026-11-13", "--metadata"], json.dumps(big_metadata()))
    assert exit_code == 0
    assert json.loads(out)["option"]["value"] == "Q4/26"


def test_quarter_without_configured_field_fails_cleanly(monkeypatch, capsys):
    env = {k: v for k, v in BASE_ENV.items() if k != "JIRA_TICKET_QUARTER_FIELD"}
    exit_code, _, err = run_cli(monkeypatch, capsys, ["quarter", "--metadata"], json.dumps(big_metadata()), env=env)
    assert exit_code == jira_ticket.EXIT_CONFIG
    assert "JIRA_TICKET_QUARTER_FIELD" in err


def test_quarter_rejects_invalid_date(monkeypatch, capsys):
    exit_code, _, err = run_cli(monkeypatch, capsys, ["quarter", "--date", "13/11/2026"])
    assert exit_code == jira_ticket.EXIT_USAGE and "fecha inválida" in err


# --- sprint-pick -------------------------------------------------------------


def test_sprint_pick_returns_single_active_board_sprint():
    result = jira_ticket.pick_sprint(REALISTIC_JQL, dt.date(2026, 11, 13), config())
    assert result["status"] == "ok" and result["sprint"]["id"] == ACTIVE_SPRINT_ID and result["quarter_checked"] is True


def test_sprint_pick_other_quarter_is_none(monkeypatch, capsys):
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["sprint-pick", "--date", "2027-01-10"], json.dumps(REALISTIC_JQL))
    assert exit_code == jira_ticket.EXIT_UNRESOLVED
    assert json.loads(out)["status"] == "none"


def test_sprint_pick_two_candidates_is_ambiguous():
    result = jira_ticket.pick_sprint(jql_with(sprint(1, "2026.Q4.R2.S3"), sprint(2, "2026.Q4.R2.S4")), dt.date(2026, 11, 13), config())
    assert result["status"] == "ambiguous" and result["sprint"] is None


def test_sprint_pick_without_regex_only_filters_board_and_state():
    result = jira_ticket.pick_sprint(jql_with(sprint(7, "Sprint 34"), sprint(8, "Otro", board=999)), dt.date(2026, 11, 13), config(JIRA_TICKET_SPRINT_NAME_REGEX=None))
    assert result["status"] == "ok" and result["sprint"]["id"] == 7 and result["quarter_checked"] is False


def test_sprint_pick_requires_configuration(monkeypatch, capsys):
    env = {k: v for k, v in BASE_ENV.items() if k != "JIRA_TICKET_BOARD_ID"}
    exit_code, _, err = run_cli(monkeypatch, capsys, ["sprint-pick"], json.dumps(REALISTIC_JQL), env=env)
    assert exit_code == jira_ticket.EXIT_CONFIG and "JIRA_TICKET_BOARD_ID" in err


def test_sprint_pick_invalid_regex_is_config_error():
    with pytest.raises(jira_ticket.JiraTicketError) as error:
        jira_ticket.pick_sprint(REALISTIC_JQL, dt.date(2026, 11, 13), config(JIRA_TICKET_SPRINT_NAME_REGEX="(unclosed"))
    assert error.value.exit_code == jira_ticket.EXIT_CONFIG


# --- repo-id ---------------------------------------------------------------


def test_repo_id_follows_configured_sources(tmp_path):
    (tmp_path / ".app").write_text("application_name: billing-api\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name": "@acme/other"}', encoding="utf-8")
    assert jira_ticket.repository_id(tmp_path, config()) == {"repository_id": "billing-api", "source": ".app:application_name"}


def test_repo_id_package_json_without_scope(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "@acme/web-front"}', encoding="utf-8")
    assert jira_ticket.repository_id(tmp_path, config()) == {"repository_id": "web-front", "source": "package.json:name"}


def test_repo_id_basename_strips_configured_prefix(tmp_path):
    repo = tmp_path / "acme_payments-core"
    repo.mkdir()
    assert jira_ticket.repository_id(repo, config()) == {"repository_id": "payments-core", "source": "basename"}


def test_repo_id_defaults_without_configuration(tmp_path):
    repo = tmp_path / "acme_payments-core"
    repo.mkdir()
    default_config = config(JIRA_TICKET_REPO_ID_SOURCES=None, JIRA_TICKET_REPO_PREFIXES=None)
    assert jira_ticket.repository_id(repo, default_config)["repository_id"] == "acme_payments-core"


# --- pr-normalize -------------------------------------------------------------


def fake_viewer(responses):
    return lambda pr_input: responses[pr_input]


def test_pr_normalize_dedup_labels_and_open_state():
    url = "https://github.com/acme/acme_payments-core/pull/12"
    responses = {"12": {"number": 12, "url": url, "state": "OPEN"}, url: {"number": 12, "url": url, "state": "OPEN"}}
    result = jira_ticket.normalize_prs(["12", url], {"repository_id": "payments-core", "source": "basename"}, "acme/acme_payments-core", ["acme_"], fake_viewer(responses))
    assert len(result["pull_requests"]) == 1 and result["pr_labels"] == ["payments-core/PR-12"] and result["all_prs_merged"] is False


def test_pr_normalize_cross_repo_and_all_merged():
    url_a = "https://github.com/acme/acme_billing-api/pull/3"
    url_b = "https://github.com/acme/acme_payments-core/pull/12"
    responses = {url_a: {"number": 3, "url": url_a, "state": "MERGED"}, "12": {"number": 12, "url": url_b, "state": "MERGED"}}
    result = jira_ticket.normalize_prs([url_a, "12"], {"repository_id": "payments-core", "source": "basename"}, "acme/acme_payments-core", ["acme_"], fake_viewer(responses))
    assert result["pr_labels"] == ["billing-api/PR-3", "payments-core/PR-12"] and result["all_prs_merged"] is True


def test_pr_normalize_empty_is_not_merged():
    assert jira_ticket.normalize_prs([], {"repository_id": "x", "source": "basename"}, None, [])["all_prs_merged"] is False


FAKE_GH_SOURCE = """import json, pathlib, sys
repo_name = pathlib.Path.cwd().name
if sys.argv[1:3] == ["repo", "view"]:
    print(f"acme/{repo_name}")
else:
    print(json.dumps({"number": int(sys.argv[3]), "url": f"https://github.com/acme/{repo_name}/pull/{sys.argv[3]}", "state": "OPEN"}))
"""


def install_fake_gh(bin_dir):
    """`gh` falso que responde según su directorio de trabajo: `.cmd` en Windows, shebang en POSIX."""
    bin_dir.mkdir()
    fake_script = bin_dir / "fake_gh.py"
    fake_script.write_text(FAKE_GH_SOURCE, encoding="utf-8")
    if os.name == "nt":
        (bin_dir / "gh.cmd").write_text(f'@"{sys.executable}" "{fake_script}" %*\r\n', encoding="utf-8")
    else:
        launcher = bin_dir / "gh"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake_script}" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)


def test_pr_normalize_script_runs_gh_lookups_in_root_repository(tmp_path):
    """Desde el repo A con --root B, `gh pr view` y `gh repo view` deben correr en B."""
    bin_dir = tmp_path / "bin"
    install_fake_gh(bin_dir)
    current_repo = tmp_path / "acme_alpha"
    root_repo = tmp_path / "acme_beta"
    current_repo.mkdir()
    root_repo.mkdir()
    (root_repo / "package.json").write_text(json.dumps({"name": "@acme/beta-service"}), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "pr-normalize", "--root", str(root_repo), "12"],
        cwd=current_repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, **BASE_ENV, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    pull_request = json.loads(completed.stdout)["pull_requests"][0]
    assert pull_request["repo"] == "acme/acme_beta"
    assert pull_request["repository_id"] == "beta-service"
    assert pull_request["repository_id_source"] == "package.json:name"


@pytest.mark.parametrize("bad_input", ["12; rm -rf /", "https://github.com/a/b/pull/1?x=1", "https://evil.example/a/b/pull/1", "PR-12", ""])
def test_pr_normalize_rejects_unvalidated_input(bad_input):
    with pytest.raises(jira_ticket.JiraTicketError):
        jira_ticket.validate_pr_input(bad_input)


# --- backlink --------------------------------------------------------------


def test_backlink_on_template_body_is_minimal_and_idempotent():
    body = (FIXTURES / "pr-body.md").read_text(encoding="utf-8")
    link = jira_ticket.backlink_line(TARGET_KEY, SITE_URL)
    once = jira_ticket.apply_backlink(body, TARGET_KEY, SITE_URL)
    assert jira_ticket.apply_backlink(once, TARGET_KEY, SITE_URL) == once
    assert once.splitlines().count(link) == 1
    assert once.replace("\n" + link + "\n", "", 1).rstrip() == body.rstrip()
    assert once.split("## 📝 Descripción\n", 1)[1].startswith("\n" + link + "\n\n### ❓")
    assert f"[{OTHER_KEY}]({SITE_URL}/browse/{OTHER_KEY})" in once
    assert link == f"🎫 Jira: [{TARGET_KEY}]({SITE_URL}/browse/{TARGET_KEY})"


def test_backlink_uses_configured_site_without_trailing_slash():
    assert jira_ticket.backlink_line(TARGET_KEY, SITE_URL + "/").endswith(f"({SITE_URL}/browse/{TARGET_KEY})")


def test_backlink_preserves_crlf_and_missing_final_newline():
    body = "## 📝 Descripción\r\n\r\n### ❓ ¿Qué problema resuelve?\r\nTexto"
    result = jira_ticket.apply_backlink(body, TARGET_KEY, SITE_URL)
    assert "\n" not in result.replace("\r\n", "") and not result.endswith("\n")
    assert jira_ticket.apply_backlink(result, TARGET_KEY, SITE_URL) == result


def test_backlink_replaces_same_key_variants_only():
    body = (
        "## 📝 Descripción\n"
        f"🎫 Jira: [{TARGET_KEY}]({SITE_URL}/browse/{TARGET_KEY})\n"
        f"> **Referencia:** {SITE_URL}/browse/{TARGET_KEY}\n"
        f"> **Referencia:** {SITE_URL}/browse/{TARGET_KEY}5\n"
        f"Texto que menciona {TARGET_KEY} en prosa.\n"
        f"🎫 Jira: [{TARGET_KEY}]({SITE_URL}/browse/{TARGET_KEY})\n"
    )
    result = jira_ticket.apply_backlink(body, TARGET_KEY, SITE_URL)
    assert result.splitlines().count(jira_ticket.backlink_line(TARGET_KEY, SITE_URL)) == 1
    assert f"{TARGET_KEY}5" in result and f"Texto que menciona {TARGET_KEY} en prosa." in result


def test_backlink_preserves_mixed_reference_line_with_other_ticket():
    mixed_reference = f"> **Referencia:** [{TARGET_KEY}]({SITE_URL}/browse/{TARGET_KEY}) y [{OTHER_KEY}]({SITE_URL}/browse/{OTHER_KEY})"
    body = f"## 📝 Descripción\n{mixed_reference}\nTexto\n"
    once = jira_ticket.apply_backlink(body, TARGET_KEY, SITE_URL)
    assert mixed_reference in once.splitlines()
    assert once.splitlines().count(jira_ticket.backlink_line(TARGET_KEY, SITE_URL)) == 1
    assert jira_ticket.apply_backlink(once, TARGET_KEY, SITE_URL) == once
    assert jira_ticket.verify_backlink(once, TARGET_KEY, SITE_URL)["canonical"] is True


@pytest.mark.parametrize("body", ["", "# Título", "## 📝 Descripción", "# Título\n"])
def test_backlink_is_idempotent_for_empty_or_heading_only_bodies(body):
    once = jira_ticket.apply_backlink(body, TARGET_KEY, SITE_URL)
    assert jira_ticket.apply_backlink(once, TARGET_KEY, SITE_URL) == once
    assert once.endswith("\n") == body.endswith("\n")
    assert jira_ticket.verify_backlink(once, TARGET_KEY, SITE_URL)["canonical"] is True


def test_backlink_fallbacks_first_heading_then_prepend():
    link = jira_ticket.backlink_line(TARGET_KEY, SITE_URL)
    assert jira_ticket.apply_backlink("# Título\nCuerpo\n", TARGET_KEY, SITE_URL).splitlines()[:3] == ["# Título", "", link]
    assert jira_ticket.apply_backlink("Cuerpo sin títulos\n", TARGET_KEY, SITE_URL).splitlines()[0] == link


def test_backlink_ignores_headings_and_backlinks_inside_code_fences():
    link = jira_ticket.backlink_line(TARGET_KEY, SITE_URL)
    fenced_example = ["```markdown", "## Ejemplo", link, "```"]
    body = "\n".join(["Intro", *fenced_example, "", "## Real", "Cuerpo"]) + "\n"
    once = jira_ticket.apply_backlink(body, TARGET_KEY, SITE_URL)
    lines = once.splitlines()
    assert lines[1:5] == fenced_example
    assert lines[lines.index("## Real") + 1 : lines.index("## Real") + 3] == ["", link]
    assert jira_ticket.apply_backlink(once, TARGET_KEY, SITE_URL) == once
    assert jira_ticket.verify_backlink(once, TARGET_KEY, SITE_URL) == {"key": TARGET_KEY, "occurrences": 1, "canonical": True}
    assert jira_ticket.verify_backlink(body, TARGET_KEY, SITE_URL)["occurrences"] == 0


def test_backlink_prepends_when_every_heading_is_fenced():
    link = jira_ticket.backlink_line(TARGET_KEY, SITE_URL)
    body = "Intro\n~~~~\n## Ejemplo\n~~~\n~~~~\n"
    once = jira_ticket.apply_backlink(body, TARGET_KEY, SITE_URL)
    assert once == f"{link}\n\n{body}"
    assert jira_ticket.apply_backlink(once, TARGET_KEY, SITE_URL) == once
    assert jira_ticket.verify_backlink(once, TARGET_KEY, SITE_URL)["canonical"] is True


def test_backlink_rejects_invalid_key():
    with pytest.raises(jira_ticket.JiraTicketError):
        jira_ticket.backlink_line("acme-1; echo", SITE_URL)


def test_backlink_script_process_writes_utf8_and_keeps_crlf():
    """El script real, con tuberías del sistema: en Windows la code page local no admite el emoji."""
    body = "## 📝 Descripción\r\n\r\n### ❓ ¿Qué problema resuelve?\r\nTexto\r\n"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "backlink", "apply", "--key", TARGET_KEY],
        input=body.encode("utf-8"),
        capture_output=True,
        env={**os.environ, **BASE_ENV, "PYTHONIOENCODING": "", "PYTHONUTF8": "0"},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    output = completed.stdout.decode("utf-8")
    assert output == jira_ticket.apply_backlink(body, TARGET_KEY, SITE_URL)
    assert "\n" not in output.replace("\r\n", "")


def test_backlink_cli_verify_apply_verify(monkeypatch, capsys):
    body = (FIXTURES / "pr-body.md").read_text(encoding="utf-8")
    assert run_cli(monkeypatch, capsys, ["backlink", "verify", "--key", TARGET_KEY], body)[0] == jira_ticket.EXIT_UNRESOLVED
    exit_code, applied, _ = run_cli(monkeypatch, capsys, ["backlink", "apply", "--key", TARGET_KEY], body)
    assert exit_code == 0
    assert run_cli(monkeypatch, capsys, ["backlink", "verify", "--key", TARGET_KEY], applied)[0] == 0


# --- slim ------------------------------------------------------------------


def test_slim_metadata_reduces_large_payload(monkeypatch, capsys):
    raw = json.dumps(big_metadata())
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["slim", "--fields", f"{QUARTER_FIELD},{START_DATE_FIELD}"], raw)
    assert exit_code == 0 and len(out) * 10 < len(raw)
    assert {item["fieldId"] for item in json.loads(out)["fields"]} == {QUARTER_FIELD}


def test_slim_metadata_without_fields_keeps_required_only():
    reduced = jira_ticket.slim(big_metadata(), [])
    assert [item["fieldId"] for item in reduced["fields"]] == ["summary", "issuetype"]


def test_slim_jql_keeps_key_and_requested_fields():
    reduced = jira_ticket.slim(REALISTIC_JQL, [SPRINT_FIELD])
    assert len(reduced["issues"]) == 5 and set(reduced["issues"][0]) == {"key", "fields"}


def test_slim_rejects_unknown_payload():
    with pytest.raises(jira_ticket.JiraTicketError):
        jira_ticket.slim(["not", "jira"], [])


# --- tracking: tabla de pasos de una subtarea ----------------------------------

STORY_DESCRIPTION = """## Problema
Los emails de bienvenida salen sin logo.

## Solución
Migrar los templates al nuevo servicio de emails.

## Pull requests
- [acme/payments-api#88](https://github.com/acme/payments-api/pull/88)
"""

SUBTASK_DESCRIPTION = """## Qué hacer
- Migrar los templates de bienvenida.

```markdown
## Pasos
| Paso | Estado | Nota |
```

## Cómo se valida
- El email de bienvenida llega con logo.

## Pasos
**Progreso:** 1/3 · ✅ 1 hecho · 🔄 1 en curso · ⬜ 1 pendiente

| Paso | Estado | Nota |
|---|---|---|
| Copiar templates | ✅ Hecho | — |
| Probar envío \\| staging | 🔄 En curso | — |
| Revisar copy | ⬜ Pendiente | — |
"""


def step(title, state="todo", **extra):
    return {"title": title, "state": state, **extra}


CURRENT_STEPS = [
    step("Copiar templates", "done"),
    step("Probar envío | staging", "done"),
    step("Revisar copy"),
]


def changed_lines(before, after):
    old_lines, new_lines = before.splitlines(), after.splitlines()
    assert len(old_lines) == len(new_lines)
    return [(old, new) for old, new in zip(old_lines, new_lines) if old != new]


def test_tracking_status_change_touches_only_its_cell_and_progress():
    result = jira_ticket.update_tracking(SUBTASK_DESCRIPTION, CURRENT_STEPS)
    assert result["updated"] == ["Probar envío | staging"] and result["added"] == [] and result["changed"] is True
    assert result["progress"] == "**Progreso:** 2/3 · ✅ 2 hechos · 🔄 0 en curso · ⬜ 1 pendiente"
    assert changed_lines(SUBTASK_DESCRIPTION, result["description"]) == [
        ("**Progreso:** 1/3 · ✅ 1 hecho · 🔄 1 en curso · ⬜ 1 pendiente", "**Progreso:** 2/3 · ✅ 2 hechos · 🔄 0 en curso · ⬜ 1 pendiente"),
        ("| Probar envío \\| staging | 🔄 En curso | — |", "| Probar envío \\| staging | ✅ Hecho | — |"),
    ]


def test_tracking_is_idempotent():
    first = jira_ticket.update_tracking(SUBTASK_DESCRIPTION, CURRENT_STEPS)
    second = jira_ticket.update_tracking(first["description"], CURRENT_STEPS)
    assert second["changed"] is False and second["updated"] == [] and second["description"] == first["description"]


@pytest.mark.parametrize(
    "states, expected",
    [
        ([], "**Progreso:** 0/0 · ✅ 0 hechos · 🔄 0 en curso · ⬜ 0 pendientes"),
        (["done", "todo"], "**Progreso:** 1/2 · ✅ 1 hecho · 🔄 0 en curso · ⬜ 1 pendiente"),
        (["done", "done", "in_progress", "blocked"], "**Progreso:** 2/4 · ✅ 2 hechos · 🔄 1 en curso · ⬜ 0 pendientes · 🚫 1 bloqueado"),
        (["blocked", "blocked"], "**Progreso:** 0/2 · ✅ 0 hechos · 🔄 0 en curso · ⬜ 0 pendientes · 🚫 2 bloqueados"),
    ],
)
def test_progress_legend_names_every_count_with_its_emoji(states, expected):
    assert jira_ticket.progress_line(states) == expected


def test_tracking_matches_titles_ignoring_case_and_spaces_and_appends_new_steps():
    steps = [step("copiar   TEMPLATES", "done"), step("Revisar copy", "in_progress"), step("Avisar a soporte")]
    result = jira_ticket.update_tracking(SUBTASK_DESCRIPTION, steps)
    assert result["updated"] == ["Revisar copy"] and result["added"] == ["Avisar a soporte"]
    assert result["rows_without_step"] == ["Probar envío | staging"]
    assert "| Probar envío \\| staging | 🔄 En curso | — |" in result["description"]
    assert result["description"].endswith("| Revisar copy | 🔄 En curso | — |\n| Avisar a soporte | ⬜ Pendiente | — |\n")
    assert result["progress"] == "**Progreso:** 1/4 · ✅ 1 hecho · 🔄 2 en curso · ⬜ 1 pendiente"


def test_tracking_blocked_step_sets_note_and_unblocking_clears_it():
    blocked = jira_ticket.update_tracking(SUBTASK_DESCRIPTION, [step("Revisar copy", "blocked", note="espera a producto | UX")])
    assert "| Revisar copy | 🚫 Bloqueado | espera a producto \\| UX |" in blocked["description"]
    assert blocked["progress"].endswith("⬜ 0 pendientes · 🚫 1 bloqueado")
    kept = jira_ticket.update_tracking(blocked["description"], [step("Revisar copy", "blocked")])
    assert kept["changed"] is False
    unblocked = jira_ticket.update_tracking(blocked["description"], [step("Revisar copy", "in_progress")])
    assert "| Revisar copy | 🔄 En curso | — |" in unblocked["description"]


def test_tracking_missing_section_is_left_alone_without_create_and_appended_with_it():
    description = "## Qué hacer\r\n- Migrar templates.\r\n\r\n## Cómo se valida\r\n- Llega con logo."
    missing = jira_ticket.update_tracking(description, CURRENT_STEPS)
    assert missing["section"] == "missing" and missing["changed"] is False and missing["description"] == description
    created = jira_ticket.update_tracking(description, CURRENT_STEPS, create=True)
    assert created["section"] == "created" and created["added"] == [item["title"] for item in CURRENT_STEPS]
    assert created["description"] == description + (
        "\r\n\r\n## Pasos\r\n**Progreso:** 2/3 · ✅ 2 hechos · 🔄 0 en curso · ⬜ 1 pendiente\r\n\r\n"
        "| Paso | Estado | Nota |\r\n|---|---|---|\r\n"
        "| Copiar templates | ✅ Hecho | — |\r\n| Probar envío \\| staging | ✅ Hecho | — |\r\n| Revisar copy | ⬜ Pendiente | — |"
    )


def test_tracking_fills_empty_section_and_rejects_unrecognizable_one():
    filled = jira_ticket.update_tracking("## Pasos\n\n## Cómo se valida\n- ok\n", [step("Copiar templates")])
    assert filled["description"] == (
        "## Pasos\n**Progreso:** 0/1 · ✅ 0 hechos · 🔄 0 en curso · ⬜ 1 pendiente\n\n"
        "| Paso | Estado | Nota |\n|---|---|---|\n| Copiar templates | ⬜ Pendiente | — |\n\n## Cómo se valida\n- ok\n"
    )
    with pytest.raises(jira_ticket.JiraTicketError) as error:
        jira_ticket.update_tracking("## Pasos\nTexto libre sin tabla.\n", [step("Copiar templates")])
    assert error.value.exit_code == jira_ticket.EXIT_UNRESOLVED


@pytest.mark.parametrize(
    "steps",
    [
        "no-es-lista",
        [step("")],
        [step("Copiar", "hecho")],
        [step("Copiar"), step("  copiar ")],
        ["texto"],
    ],
)
def test_tracking_rejects_invalid_steps(steps):
    with pytest.raises(jira_ticket.JiraTicketError):
        jira_ticket.update_tracking(SUBTASK_DESCRIPTION, steps)


NESTED_LIST_DESCRIPTION = (
    "## Qué hacer\n- Migrar templates.\n\n"
    "## Pasos\n**Progreso:** 1/2 · ✅ 1 hecho · 🔄 0 en curso · ⬜ 1 pendiente\n\n"
    "- ✅ Copiar templates\n  - Estado: Hecho\n"
    "- ⬜ Revisar copy\n  - Estado: Pendiente\n"
)


def test_tracking_list_updates_emoji_status_and_note_and_appends_nested_step():
    blocked = jira_ticket.update_tracking(NESTED_LIST_DESCRIPTION, [step("Revisar copy", "blocked", note="espera a UX"), step("Avisar a soporte")])
    assert blocked["format"] == "list" and blocked["updated"] == ["Revisar copy"] and blocked["added"] == ["Avisar a soporte"]
    assert blocked["rows_without_step"] == ["Copiar templates"]
    assert blocked["description"].endswith(
        "- ✅ Copiar templates\n  - Estado: Hecho\n"
        "- 🚫 Revisar copy\n  - Estado: Bloqueado\n  - Nota: espera a UX\n"
        "- ⬜ Avisar a soporte\n  - Estado: Pendiente\n"
    )
    assert blocked["progress"] == "**Progreso:** 1/3 · ✅ 1 hecho · 🔄 0 en curso · ⬜ 1 pendiente · 🚫 1 bloqueado"
    done = jira_ticket.update_tracking(blocked["description"], [step("Revisar copy", "done")])
    assert "- ✅ Revisar copy\n  - Estado: Hecho\n- ⬜ Avisar" in done["description"]


def test_tracking_list_flag_creates_nested_list_and_converts_existing_table():
    created = jira_ticket.update_tracking("## Qué hacer\n- x\n", [step("Copiar templates", "blocked", note="falta acceso")], create=True, as_list=True)
    assert created["format"] == "list" and created["description"].endswith(
        "## Pasos\n**Progreso:** 0/1 · ✅ 0 hechos · 🔄 0 en curso · ⬜ 0 pendientes · 🚫 1 bloqueado\n\n"
        "- 🚫 Copiar templates\n  - Estado: Bloqueado\n  - Nota: falta acceso\n"
    )
    converted = jira_ticket.update_tracking(SUBTASK_DESCRIPTION, CURRENT_STEPS, as_list=True)
    assert converted["converted_from"] == "table" and converted["format"] == "list"
    assert converted["description"].endswith(
        "- ✅ Copiar templates\n  - Estado: Hecho\n"
        "- ✅ Probar envío | staging\n  - Estado: Hecho\n"
        "- ⬜ Revisar copy\n  - Estado: Pendiente\n"
    )
    assert "```markdown\n## Pasos\n| Paso | Estado | Nota |\n```" in converted["description"]


def test_tracking_cli_round_trip_and_unknown_state(monkeypatch, capsys):
    payload = json.dumps({"description": SUBTASK_DESCRIPTION, "steps": CURRENT_STEPS})
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["tracking"], payload)
    assert exit_code == 0 and json.loads(out)["updated"] == ["Probar envío | staging"]
    bad = json.dumps({"description": SUBTASK_DESCRIPTION, "steps": [step("Copiar templates", "listo")]})
    exit_code, _, err = run_cli(monkeypatch, capsys, ["tracking"], bad)
    assert exit_code == jira_ticket.EXIT_UNRESOLVED and "listo" in err


# --- tracking sobre ADF --------------------------------------------------------


def subtask_adf():
    return jira_ticket.adf.markdown_to_document(SUBTASK_DESCRIPTION)


def story_adf():
    return jira_ticket.adf.markdown_to_document(STORY_DESCRIPTION)


def adf_table_texts(doc):
    table = find_nodes(doc, "table")[-1]
    return [[jira_ticket.adf.node_text(cell) for cell in row["content"]] for row in table["content"]]


def test_tracking_adf_status_change_touches_only_its_cell_and_progress():
    before = subtask_adf()
    result = jira_ticket.update_tracking_adf(before, CURRENT_STEPS)
    after = result["description"]
    assert result["format"] == "adf-table" and result["updated"] == ["Probar envío | staging"] and result["changed"] is True
    assert adf_table_texts(after) == [
        ["Paso", "Estado", "Nota"],
        ["Copiar templates", "✅ Hecho", "—"],
        ["Probar envío | staging", "✅ Hecho", "—"],
        ["Revisar copy", "⬜ Pendiente", "—"],
    ]
    lozenge = find_nodes(after["content"][-1]["content"][2], "status")[0]
    assert lozenge["attrs"] == {"text": "Hecho", "color": "green"}
    progress = after["content"][-2]
    assert jira_ticket.adf.node_text(progress) == "Progreso: 2/3 · ✅ 2 hechos · 🔄 0 en curso · ⬜ 1 pendiente"
    assert after["content"][:-2] == before["content"][:-2]


def test_tracking_adf_is_idempotent_and_does_not_mutate_input():
    before = subtask_adf()
    snapshot = json.loads(json.dumps(before))
    first = jira_ticket.update_tracking_adf(before, CURRENT_STEPS)
    assert before == snapshot
    second = jira_ticket.update_tracking_adf(first["description"], CURRENT_STEPS)
    assert second["changed"] is False and second["description"] == first["description"]


def test_tracking_adf_blocks_with_red_lozenge_and_appends_new_step():
    result = jira_ticket.update_tracking_adf(subtask_adf(), [step("Revisar copy", "blocked", note="espera a UX"), step("Avisar a soporte")])
    assert result["added"] == ["Avisar a soporte"] and result["rows_without_step"] == ["Copiar templates", "Probar envío | staging"]
    rows = adf_table_texts(result["description"])
    assert rows[3] == ["Revisar copy", "🚫 Bloqueado", "espera a UX"] and rows[4] == ["Avisar a soporte", "⬜ Pendiente", "—"]
    blocked_row = result["description"]["content"][-1]["content"][3]
    assert find_nodes(blocked_row, "status")[0]["attrs"] == {"text": "Bloqueado", "color": "red"}


def test_tracking_adf_creates_section_after_a_divider_at_the_end():
    before = jira_ticket.adf.markdown_to_document("## Qué hacer\n- Migrar templates.\n\n## Cómo se valida\n- Llega con logo.\n")
    assert jira_ticket.update_tracking_adf(before, CURRENT_STEPS)["section"] == "missing"
    created = jira_ticket.update_tracking_adf(before, CURRENT_STEPS, create=True)
    content = created["description"]["content"]
    assert created["section"] == "created" and content[: len(before["content"])] == before["content"]
    assert adf_types(content[len(before["content"]):]) == ["rule", "heading", "paragraph", "table"]


def test_tracking_adf_rejects_section_with_unrecognizable_content():
    doc = jira_ticket.adf.markdown_to_document("## Pasos\nTexto libre.\n")
    with pytest.raises(jira_ticket.JiraTicketError) as error:
        jira_ticket.update_tracking_adf(doc, CURRENT_STEPS)
    assert error.value.exit_code == jira_ticket.EXIT_UNRESOLVED


def test_tracking_cli_accepts_adf_description_and_rejects_list_flag(monkeypatch, capsys):
    payload = json.dumps({"description": subtask_adf(), "steps": CURRENT_STEPS})
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["tracking"], payload)
    assert exit_code == 0 and json.loads(out)["format"] == "adf-table"
    exit_code, _, err = run_cli(monkeypatch, capsys, ["tracking", "--list"], payload)
    assert exit_code == jira_ticket.EXIT_USAGE and "--list" in err
    exit_code, _, err = run_cli(monkeypatch, capsys, ["tracking"], json.dumps({"description": {"type": "paragraph"}, "steps": []}))
    assert exit_code == jira_ticket.EXIT_USAGE and "doc" in err


# --- expand sin links ------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "- PR: [acme/api#88](https://github.com/acme/api/pull/88)",
        "- Ver https://acme.atlassian.net/browse/ACME-30",
    ],
)
def test_adf_rejects_links_inside_expand_because_jira_does_not_make_them_clickable(monkeypatch, capsys, body):
    markdown = f"## Solución\nTexto.\n\n<details><summary>Detalle técnico</summary>\n\n{body}\n\n</details>\n"
    exit_code, out, err = run_cli(monkeypatch, capsys, ["adf"], markdown)
    assert exit_code == jira_ticket.EXIT_USAGE and out == "" and "Detalle técnico" in err and "fuera del bloque" in err
    moved = "## Solución\nTexto con [acme/api#88](https://github.com/acme/api/pull/88).\n\n<details><summary>Detalle técnico</summary>\n\n- Áreas: `templates/`\n\n</details>\n"
    doc = jira_ticket.adf.markdown_to_document(moved)
    assert adf_types(doc["content"]) == ["heading", "paragraph", "expand"]
    assert jira_ticket.adf.markdown_to_plain(markdown).count("https://") == 1


@pytest.mark.parametrize(
    "body",
    [
        "```bash\ncurl https://api.example.com/health\n```",
        "- Endpoint: `https://api.example.com/health`",
    ],
)
def test_adf_keeps_urls_written_as_code_inside_expand(body):
    markdown = f"## Solución\nTexto.\n\n<details><summary>Detalle técnico</summary>\n\n{body}\n\n</details>\n"
    doc = jira_ticket.adf.markdown_to_document(markdown)
    expand = doc["content"][-1]
    assert expand["type"] == "expand" and "https://api.example.com/health" in jira_ticket.adf.node_text(expand)
    with pytest.raises(jira_ticket.adf.AdfError):
        jira_ticket.adf.markdown_to_document(markdown.replace(body, body + "\n\n- Ver [doc](https://acme.atlassian.net/wiki/x)"))


# --- adf: Markdown enriquecido → ADF ------------------------------------------


def adf_types(nodes):
    return [node["type"] for node in nodes]


def find_nodes(node, node_type):
    found = [node] if node.get("type") == node_type else []
    for inner in node.get("content") or []:
        found.extend(find_nodes(inner, node_type))
    return found


RICH_MARKDOWN = """## Problema
Los emails salen **sin logo** desde {date:2026-07-21}.

> [!WARNING] Bloqueo
> Depende de [ACME-30](https://acme.atlassian.net/browse/ACME-30).

> [!DECISION]
> - Se migra con el servicio nuevo, no con un parche

> «Necesitamos el logo antes del lanzamiento»

<details><summary>Detalle técnico</summary>

- Áreas
  - `templates/`
  - `mailer`
1. Paso uno

</details>

---

| Key | Estado |
|---|---|
| ACME-1 | ✅ {status:green:Done} |
"""


def test_adf_compiles_every_rich_block_to_its_jira_node():
    doc = jira_ticket.adf.markdown_to_document(RICH_MARKDOWN)
    assert doc["version"] == 1 and doc["type"] == "doc"
    assert adf_types(doc["content"]) == ["heading", "paragraph", "panel", "decisionList", "blockquote", "expand", "rule", "table"]
    panel = doc["content"][2]
    assert panel["attrs"] == {"panelType": "warning"}
    assert jira_ticket.adf.node_text(panel) == "BloqueoDepende de ACME-30."
    assert find_nodes(panel, "text")[0]["marks"] == [{"type": "strong"}]
    links = [mark for node in find_nodes(panel, "text") for mark in node.get("marks", []) if mark["type"] == "link"]
    assert links == [{"type": "link", "attrs": {"href": "https://acme.atlassian.net/browse/ACME-30"}}]
    decision = doc["content"][3]["content"][0]
    assert decision["attrs"]["state"] == "DECIDED" and jira_ticket.adf.node_text(decision) == "Se migra con el servicio nuevo, no con un parche"
    expand = doc["content"][5]
    assert expand["attrs"] == {"title": "Detalle técnico"}
    assert adf_types(expand["content"]) == ["bulletList", "orderedList"]
    nested = expand["content"][0]["content"][0]["content"]
    assert adf_types(nested) == ["paragraph", "bulletList"] and len(nested[1]["content"]) == 2
    assert find_nodes(doc, "date")[0]["attrs"] == {"timestamp": "1784592000000"}
    assert find_nodes(doc, "status")[0]["attrs"] == {"text": "Done", "color": "green"}
    table = doc["content"][7]
    assert adf_types(table["content"][0]["content"]) == ["tableHeader", "tableHeader"]
    assert jira_ticket.adf.node_text(table["content"][1]["content"][1]) == "✅ Done"


def test_adf_compilation_is_deterministic():
    assert jira_ticket.adf.markdown_to_document(RICH_MARKDOWN) == jira_ticket.adf.markdown_to_document(RICH_MARKDOWN)


@pytest.mark.parametrize(
    "markdown, expected",
    [
        ("{status:rosa:Done}", "color de status"),
        ("{date:2026-02-30}", "fecha"),
        ("> [!DANGER]\n> texto", "desconocido"),
        ("<details><summary>Título</summary>\n\ntexto", "</details>"),
        ("> [!INFO]", "no tiene contenido"),
    ],
)
def test_adf_cli_rejects_invalid_rich_markdown(monkeypatch, capsys, markdown, expected):
    exit_code, out, err = run_cli(monkeypatch, capsys, ["adf"], markdown)
    assert exit_code == jira_ticket.EXIT_USAGE and out == "" and expected in err


def test_adf_cli_emits_document(monkeypatch, capsys):
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["adf"], "## Qué hacer\n- Migrar templates\n")
    assert exit_code == 0 and adf_types(json.loads(out)["content"]) == ["heading", "bulletList"]


# --- section -------------------------------------------------------------------

PROBLEM_PANEL = "> [!NOTE]\n> Los emails salen sin logo.\n"
PR_SECTION_BODY = "- [acme/payments-api#88](https://github.com/acme/payments-api/pull/88)\n"


def test_section_replaces_only_its_adf_nodes_and_is_idempotent():
    before = story_adf()
    result = jira_ticket.update_section(before, "Problema", PROBLEM_PANEL)
    after = result["description"]["content"]
    assert result["action"] == "replaced" and adf_types(after[:2]) == ["heading", "panel"]
    assert after[2:] == before["content"][2:]
    assert jira_ticket.update_section(result["description"], "Problema", PROBLEM_PANEL)["action"] == "unchanged"


def test_section_creates_adf_section_before_anchor_or_at_end():
    before = story_adf()
    created = jira_ticket.update_section(before, "Criterios de aceptación", "- El email llega con logo\n", before="Pull requests")
    headings = [jira_ticket.adf.node_text(node) for node in created["description"]["content"] if node["type"] == "heading"]
    assert created["action"] == "created" and headings == ["Problema", "Solución", "Criterios de aceptación", "Pull requests"]
    appended = jira_ticket.update_section(before, "Notas", "- uno\n")
    assert appended["description"]["content"][:-2] == before["content"]


def test_section_on_markdown_description_keeps_the_rest_byte_for_byte():
    second_pr = "- [acme/payments-api#90](https://github.com/acme/payments-api/pull/90)\n"
    result = jira_ticket.update_section(STORY_DESCRIPTION, "Pull requests", PR_SECTION_BODY + second_pr)
    assert result["action"] == "replaced" and result["description"] == STORY_DESCRIPTION + second_pr
    assert jira_ticket.update_section(STORY_DESCRIPTION, "Pull requests", PR_SECTION_BODY)["action"] == "unchanged"
    created = jira_ticket.update_section("## Problema\r\nAlgo falla.", "Pull requests", "- [acme/api#1](https://github.com/acme/api/pull/1)")
    assert created["description"] == "## Problema\r\nAlgo falla.\r\n\r\n## Pull requests\r\n- [acme/api#1](https://github.com/acme/api/pull/1)"


def test_section_cli_round_trip(monkeypatch, capsys):
    payload = json.dumps({"description": story_adf(), "markdown": PR_SECTION_BODY})
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["section", "--heading", "Pull requests"], payload)
    assert exit_code == 0 and json.loads(out)["action"] == "unchanged"
    exit_code, _, err = run_cli(monkeypatch, capsys, ["section", "--heading", "Pull requests"], json.dumps({"description": "x"}))
    assert exit_code == jira_ticket.EXIT_USAGE and "markdown" in err


def test_section_with_empty_markdown_removes_only_that_section():
    blocked = jira_ticket.update_section(story_adf(), "Bloqueo", "> [!ERROR] Bloqueado\n> Espera ACME-30.\n", before="Problema")
    assert blocked["action"] == "created" and adf_types(blocked["description"]["content"][:2]) == ["heading", "panel"]
    removed = jira_ticket.update_section(blocked["description"], "Bloqueo", "")
    assert removed["action"] == "removed" and removed["description"] == story_adf()
    assert jira_ticket.update_section(story_adf(), "Bloqueo", "")["action"] == "unchanged"
    markdown = "## Bloqueo\n> 🚫 **Bloqueado**\n> Espera ACME-30.\n\n" + STORY_DESCRIPTION
    assert jira_ticket.update_section(markdown, "Bloqueo", "")["description"] == STORY_DESCRIPTION
    assert jira_ticket.update_section(STORY_DESCRIPTION, "Pull requests", "\n")["description"] == STORY_DESCRIPTION.split("\n## Pull requests")[0]


# --- plain ---------------------------------------------------------------------


def test_plain_drops_adf_only_elements_and_keeps_content_and_code():
    plain = jira_ticket.adf.markdown_to_plain(RICH_MARKDOWN + "\n```markdown\n> [!INFO]\n{date:2026-01-01}\n```\n")
    assert "Los emails salen **sin logo** desde 2026-07-21." in plain
    assert "> ⚠️ **Bloqueo**\n> Depende de [ACME-30]" in plain
    assert "> 🧭 **Decisiones**\n> - Se migra con el servicio nuevo" in plain
    assert "**Detalle técnico**\n\n- Áreas\n  - `templates/`" in plain
    assert "| ACME-1 | ✅ Done |" in plain
    assert "<details>" not in plain and "</details>" not in plain and "{status" not in plain
    assert plain.endswith("```markdown\n> [!INFO]\n{date:2026-01-01}\n```\n")


def test_plain_cli_writes_markdown_and_rejects_unknown_callout(monkeypatch, capsys):
    exit_code, out, _ = run_cli(monkeypatch, capsys, ["plain"], "> [!ERROR] Bloqueado\n> Espera ACME-30 hasta {date:2026-07-21}.\n")
    assert exit_code == 0 and out == "> 🚫 **Bloqueado**\n> Espera ACME-30 hasta 2026-07-21.\n"
    exit_code, _, err = run_cli(monkeypatch, capsys, ["plain"], "> [!DANGER]\n> x\n")
    assert exit_code == jira_ticket.EXIT_USAGE and "desconocido" in err


# --- regresiones de review ------------------------------------------------------


def test_adf_keeps_every_list_item_after_blank_separated_nested_list():
    doc = jira_ticket.adf.markdown_to_document("- Áreas\n\n  - templates/\n- Cobertura automática: tests\n- Criterio: email con logo\n\nTexto final.\n")
    assert adf_types(doc["content"]) == ["bulletList", "paragraph"]
    items = doc["content"][0]["content"]
    assert [jira_ticket.adf.node_text(item["content"][0]) for item in items] == ["Áreas", "Cobertura automática: tests", "Criterio: email con logo"]
    assert adf_types(items[0]["content"]) == ["paragraph", "bulletList"]
    deeper_first = jira_ticket.adf.markdown_to_document("  - hijo\n- padre\n")
    assert [jira_ticket.adf.node_text(item) for node in deeper_first["content"] for item in node["content"]] == ["hijo", "padre"]
