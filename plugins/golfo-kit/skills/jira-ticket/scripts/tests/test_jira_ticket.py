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
    sprint(900, "🟢 Billing_2026Q4R2SP1", board=202),
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
