"""agent-ready ci setup: choose the CI provider whose files agent-ready-setup manages, and apply.

The choice is ci.provider in the project layer (.agents/agent-ready.json, versioned); the files are
the assets of the CI profile it picks (ci-<provider>), so an apply creates them, keeps their
ownership and retires those of the previous provider like any other asset. This module only
writes the key, runs the apply and says what the repository still has to do in its CI.
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
from agent_ready_config import LAYER_PROJECT, load_schema
from agent_ready_options import CI_PROVIDER_KEY, CI_PROVIDER_NONE, PROFILES_KEY, UPDATES_FROM_LOCK_KEY

CI_SCRIPT_PATH = ".agents/ci/agent-ready-check.sh"
JENKINS_STAGE_PATH = ".agents/ci/jenkins-stage.groovy"
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


def apply_arguments(project_root):
    """Selection flags of the apply: explicit when updates.fromLock reproduces the lock."""
    state = engine()
    configuration = state.configuration_of(project_root)
    selection = configuration.value(PROFILES_KEY)
    if selection and configuration.value(UPDATES_FROM_LOCK_KEY) and os.path.isfile(
            os.path.join(project_root, state.LOCK_RELATIVE_PATH)):
        # The lock holds the CI profile of the previous provider: an apply from it could not change it.
        return ["--profiles", ",".join(selection)]
    return []


def command_ci_setup(arguments):
    """Write ci.provider into the project layer, then apply so the files of that provider exist."""
    if arguments.ci_provider is None:
        raise UsageError(f"choose the CI provider with --provider {'|'.join(ci_providers())}")
    arguments.layer = LAYER_PROJECT

    def change(schema, document):
        section = document.setdefault("ci", {})
        previous = section.get("provider")
        section["provider"] = arguments.ci_provider
        return previous != arguments.ci_provider

    path, changed = write_layer(arguments, change)
    sys.stderr.write(f"{CI_PROVIDER_KEY}={arguments.ci_provider} {'set' if changed else 'already set'} in {path}.\n")
    if arguments.no_apply:
        sys.stderr.write(f"Not applied: run {CLI_NAME} apply to create the files of the provider.\n")
        return EXIT_OK
    status = apply_selection(arguments, resolve_provider(arguments.agent), apply_arguments(arguments.project_root))
    if status != EXIT_OK:
        return status
    if arguments.ci_provider == CI_PROVIDER_NONE:
        sys.stderr.write("No CI file is managed now; those of a previous provider were retired.\n")
        return EXIT_OK
    sys.stderr.write(NEXT_STEPS[arguments.ci_provider] + "\n" + SECRET_HINT + "\n")
    if arguments.ci_provider == "jenkins":
        with open(os.path.join(arguments.project_root, JENKINS_STAGE_PATH), encoding="utf-8") as stage:
            sys.stdout.write(stage.read())
    return EXIT_OK


def register(subparsers, new_subparser):
    """Add ci setup to the CLI parser."""
    ci = new_subparser(subparsers, "ci", "Set up the CI check of this repository.",
                       "  agent-ready ci setup --provider github", None, with_project=False)
    actions = ci.add_subparsers(dest="ci_action", metavar="<action>", required=True)
    setup = new_subparser(actions, "setup", "Choose the CI provider (ci.provider) and create its files with an apply.",
                          "  agent-ready ci setup --provider github\n  agent-ready ci setup --provider jenkins > stage.groovy\n"
                          "  agent-ready ci setup --provider none", command_ci_setup)
    setup.add_argument("--provider", dest="ci_provider", choices=ci_providers(),
                       help="github (workflow), gitlab (job and include), jenkins (stage to copy), generic (script only) "
                            "or none (no file); changing it retires the files of the previous one")
    setup.add_argument("--agent", choices=SUPPORTED_PROVIDERS,
                       help="agent provider whose marketplace the apply refreshes (default: the installation)")
    setup.add_argument("--no-apply", action="store_true", help="only write ci.provider; the next apply creates the files")
