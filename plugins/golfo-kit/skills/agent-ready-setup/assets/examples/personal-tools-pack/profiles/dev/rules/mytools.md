# mytool

- Run `mytool check` before committing; it reads `.mytool/config.json`.
- `mytool` comes from the `mytools` profile pack and lives in the cache of the user, not on the PATH.
  Put the directories the pack lists first, then run it:
  - bash: `PATH="$(paste -sd: "$(git rev-parse --git-path agent-ready/cli-path)"):$PATH" mytool check`
    (on Windows Git Bash, convert each line with `cygpath -u` first)
  - PowerShell: `$env:PATH = ((Get-Content (git rev-parse --git-path agent-ready/cli-path)) -join ';') + ';' + $env:PATH; mytool check`
- Never commit `.mytool/`: it is local to each checkout.
