"""agent-ready ci setup|detect: choose the CI provider whose files agent-ready-setup manages, and apply.

The choice is ci.provider in the project layer (.agents/agent-ready.json, versioned); the files are
the assets of the CI profile it picks (ci-<provider>), so an apply creates them, keeps their
ownership and retires those of the previous provider like any other asset. This module only
writes the key, runs the apply and says what the repository still has to do in its CI.

The question (ask_ci_provider) offers the provider whose files the repository already has first, and
only runs with a terminal: ci setup without --provider and the full wizard of init ask it, and every
other run (SessionStart, background updates, review mode, CI) never does.
"""

import os
import sys

from agent_ready_cli_common import (
    CLI_NAME,
    EXIT_OK,
    SUPPORTED_PROVIDERS,
    UsageError,
    apply_selection,
    engine,
    resolve_provider,
    write_layer,
)
from agent_ready_common import serialize_json
from agent_ready_config import LAYER_PROJECT, load_schema
from agent_ready_options import CI_PROVIDER_KEY, CI_PROVIDER_NONE, PROFILES_KEY, UPDATES_FROM_LOCK_KEY
from agent_ready_prompts import ask_text, can_prompt, equivalent_command

CI_SCRIPT_PATH = ".agents/ci/agent-ready-check.sh"
JENKINS_STAGE_PATH = ".agents/ci/jenkins-stage.groovy"
# Files that reveal the CI of a repository, checked in this order: (provider, path, kind).
CI_SIGNALS = (
    ("github", ".github/workflows", "workflows"),
    ("gitlab", ".gitlab-ci.yml", "file"),
    ("jenkins", "Jenkinsfile", "file"),
    ("generic", "azure-pipelines.yml", "file"),
    ("generic", "bitbucket-pipelines.yml", "file"),
)
# The workflow agent-ready-setup itself writes is not a sign that the repository uses GitHub Actions.
MANAGED_WORKFLOW_NAME = "agent-ready.yml"
WORKFLOW_SUFFIXES = (".yml", ".yaml")
PROVIDER_CHOICES_HELP = ("github (workflow), gitlab (job and include), jenkins (stage to copy), "
                         "generic (script only) or none (no file)")
SECRET_HINT = ("Private packs: give the CI the secret AGENT_READY_GIT_TOKEN (a read token) and "
               "AGENT_READY_GIT_URL (the URL prefix of the packs); no generated file holds a token.")
NEXT_STEPS = {
    "github": "Commit .github/workflows/agent-ready.yml and .agents/ci/: the workflow runs on every pull request.",
    "gitlab": "Commit .gitlab-ci.yml and .agents/ci/: .gitlab-ci.yml includes the job from a managed block.",
    "jenkins": f"Copy the stage of {JENKINS_STAGE_PATH} into your Jenkinsfile; agent-ready-setup never edits it.",
    "generic": f"Call `sh {CI_SCRIPT_PATH}` from your pipeline; its exit statuses are those of {CLI_NAME} check.",
}


def ci_providers():
    """The values of ci.provider, from its schema."""
    return load_schema().leaves[CI_PROVIDER_KEY]["enum"]


def detect_ci_provider(project_root):
    """(provider, evidence) of the first CI whose files the repository has, or (None, None)."""
    for provider, relative_path, kind in CI_SIGNALS:
        path = os.path.join(project_root, relative_path)
        if kind == "workflows":
            if not os.path.isdir(path):
                continue
            workflows = sorted(name for name in os.listdir(path)
                               if name.endswith(WORKFLOW_SUFFIXES) and name != MANAGED_WORKFLOW_NAME)
            if workflows:
                return provider, f"{relative_path}/{workflows[0]}"
        elif os.path.isfile(path):
            return provider, relative_path
    return None, None


def ask_ci_provider(project_root):
    """One question with the detected provider first and as the default; none when nothing is detected."""
    providers = ci_providers()
    detected, evidence = detect_ci_provider(project_root)
    ordered = ([detected] if detected else []) + [provider for provider in providers if provider != detected]
    if detected:
        sys.stderr.write(f"Detected CI: {detected} ({evidence})\n")
    sys.stderr.write(f"CI check files: {PROVIDER_CHOICES_HELP}; ci.mode stays fail.\n")
    return ask_text(f"CI provider ({'|'.join(ordered)})", detected or CI_PROVIDER_NONE,
                    lambda answer: None if answer in providers else f"answer one of {', '.join(ordered)}")


def write_ci_provider(arguments, ci_provider):
    """Write ci.provider into the project layer and say whether it changed."""
    arguments.layer = LAYER_PROJECT

    def change(schema, document):
        section = document.setdefault("ci", {})
        previous = section.get("provider")
        section["provider"] = ci_provider
        return previous != ci_provider

    path, changed = write_layer(arguments, change)
    sys.stderr.write(f"{CI_PROVIDER_KEY}={ci_provider} {'set' if changed else 'already set'} in {path}.\n")


def report_ci_next_steps(project_root, ci_provider):
    """What the repository still has to do in its CI after an apply with this provider."""
    if ci_provider == CI_PROVIDER_NONE:
        sys.stderr.write("No CI file is managed now; those of a previous provider were retired.\n")
        return
    sys.stderr.write(NEXT_STEPS[ci_provider] + "\n" + SECRET_HINT + "\n")
    if ci_provider == "jenkins":
        with open(os.path.join(project_root, JENKINS_STAGE_PATH), encoding="utf-8") as stage:
            sys.stdout.write(stage.read())


def apply_arguments(project_root):
    """Selection flags of the apply: explicit when updates.fromLock reproduces the lock."""
    state = engine()
    configuration = state.configuration_of(project_root)
    selection = configuration.value(PROFILES_KEY)
    if selection is not None and configuration.value(UPDATES_FROM_LOCK_KEY) and os.path.isfile(
            os.path.join(project_root, state.LOCK_RELATIVE_PATH)):
        # The lock holds the CI profile of the previous provider: an apply from it could not change it.
        # An empty selection (the core only) goes as "none", the value --profiles has for it.
        return ["--profiles", ",".join(selection) or state.EMPTY_SELECTION_TOKEN]
    return []


def command_ci_setup(arguments):
    """Write ci.provider into the project layer, then apply so the files of that provider exist.

    Without --provider it asks, only with a terminal; without one it fails naming the flag.
    """
    asked = arguments.ci_provider is None
    if asked:
        if not can_prompt(arguments.no_input):
            raise UsageError(f"choose the CI provider with --provider {'|'.join(ci_providers())}; "
                             "there is no terminal to ask")
        arguments.ci_provider = ask_ci_provider(arguments.project_root)
    write_ci_provider(arguments, arguments.ci_provider)
    if asked:
        command = [CLI_NAME, "ci", "setup", "--provider", arguments.ci_provider]
        command += (["--project", arguments.project] if arguments.project != "." else [])
        command += ["--no-apply"] if arguments.no_apply else []
        sys.stderr.write(f"Equivalent command: {equivalent_command(command)}\n")
    if arguments.no_apply:
        sys.stderr.write(f"Not applied: run {CLI_NAME} apply to create the files of the provider.\n")
        return EXIT_OK
    status = apply_selection(arguments, resolve_provider(arguments.agent), apply_arguments(arguments.project_root))
    if status != EXIT_OK:
        return status
    report_ci_next_steps(arguments.project_root, arguments.ci_provider)
    return EXIT_OK


def command_ci_detect(arguments):
    """Print the CI provider whose files the repository has and the file that shows it, or none."""
    provider, evidence = detect_ci_provider(arguments.project_root)
    if arguments.json:
        sys.stdout.write(serialize_json({"provider": provider, "evidence": evidence}))
    else:
        sys.stdout.write(f"{provider}\t{evidence}\n" if provider else "none\n")
    return EXIT_OK


def register(subparsers, new_subparser):
    """Add ci setup to the CLI parser."""
    ci = new_subparser(subparsers, "ci", "Set up the CI check of this repository.",
                       "  agent-ready ci detect\n  agent-ready ci setup --provider github", None, with_project=False)
    actions = ci.add_subparsers(dest="ci_action", metavar="<action>", required=True)
    setup = new_subparser(actions, "setup", "Choose the CI provider (ci.provider) and create its files with an apply.",
                          "  agent-ready ci setup\n  agent-ready ci setup --provider github\n"
                          "  agent-ready ci setup --provider jenkins > stage.groovy\n  agent-ready ci setup --provider none",
                          command_ci_setup)
    setup.add_argument("--provider", dest="ci_provider", choices=ci_providers(),
                       help=f"{PROVIDER_CHOICES_HELP}; changing it retires the files of the previous one "
                            "(asked with a terminal, the detected one first)")
    setup.add_argument("--agent", choices=SUPPORTED_PROVIDERS,
                       help="agent provider whose marketplace the apply refreshes (default: the installation)")
    setup.add_argument("--no-apply", action="store_true", help="only write ci.provider; the next apply creates the files")
    setup.add_argument("--no-input", action="store_true", help="never ask; fail with exit 2 without --provider")
    detect = new_subparser(actions, "detect", "Name the CI provider whose files the repository has, read-only.",
                           "  agent-ready ci detect\n  agent-ready ci detect --json", command_ci_detect)
    detect.add_argument("--json", action="store_true", help="print {provider, evidence} as JSON on stdout")
