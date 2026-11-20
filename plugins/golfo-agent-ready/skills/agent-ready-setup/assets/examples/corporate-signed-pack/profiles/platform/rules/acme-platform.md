# Acme platform

- Deploy only with `acme deploy`; it checks the service contract first.
- `acme` comes from the `acme-platform` profile pack and lives in the cache of the user, not on the
  PATH. Put the directories the pack lists first, then run it:
  - bash: `PATH="$(paste -sd: "$(git rev-parse --git-path agent-ready/cli-path)"):$PATH" acme deploy`
    (on Windows Git Bash, convert each line with `cygpath -u` first)
  - PowerShell: `$env:PATH = ((Get-Content (git rev-parse --git-path agent-ready/cli-path)) -join ';') + ';' + $env:PATH; acme deploy`
- Ask the `acme-docs` MCP server before guessing how an internal API works.
