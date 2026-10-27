#!/usr/bin/env bats

# The installed run-evals command must always run the current repo script: a frozen copy keeps old
# bugs after they are fixed in the repo (it happened on Windows, where ln -s copies the file).

setup() {
    RUNNER_COPY="${BATS_TEST_TMPDIR}/skill-eval-runner"
    mkdir -p "${RUNNER_COPY}"
    cp "${BATS_TEST_DIRNAME}/../install.sh" "${BATS_TEST_DIRNAME}/../run-evals.sh" "${RUNNER_COPY}/"
    export HOME="${BATS_TEST_TMPDIR}/home"
    mkdir -p "${HOME}"
    INSTALLED="${HOME}/.local/bin/run-evals"
}

@test "the installed command runs the repo script, also after the repo changes" {
    run bash "${RUNNER_COPY}/install.sh" </dev/null

    [ "${status}" -eq 0 ]
    [[ "${output}" == *"run-evals installed"* ]]
    [ -x "${INSTALLED}" ]

    run "${INSTALLED}" --help
    [[ "${output}" == *"Skill Eval Runner"* ]]

    sed -i 's/Skill Eval Runner/Skill Eval Runner (updated)/' "${RUNNER_COPY}/run-evals.sh"
    run "${INSTALLED}" --help
    [[ "${output}" == *"Skill Eval Runner (updated)"* ]]
}

@test "reinstalling replaces a stale copy with a command that follows the repo" {
    mkdir -p "${HOME}/.local/bin"
    printf '#!/usr/bin/env bash\necho stale copy\n' > "${INSTALLED}"
    chmod +x "${INSTALLED}"

    run bash "${RUNNER_COPY}/install.sh" <<< "y"

    [ "${status}" -eq 0 ]
    run "${INSTALLED}" --help
    [[ "${output}" == *"Skill Eval Runner"* ]]
    [[ "${output}" != *"stale copy"* ]]
}
