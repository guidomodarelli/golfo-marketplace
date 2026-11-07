# Chequeo de CI de agent-ready-setup

Leer al agregar el chequeo a un pipeline o al explicar un código de salida. Configuración y defaults:
[configuration.md](configuration.md) (`ci.enabled`, `ci.mode`).

Es un comando común que sirve en cualquier proveedor de CI, porque no depende de `gh` ni de variables de GitHub. Necesita `python3`, `git` y `bash`, y no necesita la CLI de Claude ni la de Codex.
agent-ready-setup no proyecta ni crea workflows en `.github/workflows`: el job lo agrega cada repo si lo quiere.

```bash
python3 "$SKILL_DIR/scripts/agent-ready-state.py" check --project . --skill-dir "$SKILL_DIR" [--offline] [--format json]
```

Trae las fuentes, resuelve cada `ref` y compara contra el lock y los assets commiteados: profiles, digests,
assets faltantes o modificados, archivos fusionados y una versión nueva de golfo-kit. No escribe en el repo.

| Resultado (`status` en JSON) | Código de salida | Significado |
|---|---|---|
| `up-to-date` | 0 | todo está al día |
| `outdated` | 4 | hay assets, lock o fuentes desactualizados; los lista |
| `source-unavailable` | 5 | no se pudo llegar a una fuente: no se puede afirmar que esté al día |
| `config-error` | 2 | una capa de configuración, el catálogo, un pack o la selección inválidos, o una variable con un valor que no existe |
| `skipped` | 0 | `ci.enabled: false`: no evalúa nada, no usa la red y no ejecuta nada |

`ci.mode: warn` informa lo mismo pero sale con 0 ante `outdated` y `source-unavailable`. `config-error` sale con 2 en
cualquier modo, y un argumento inválido del comando también sale con 2. Una fuente en `pinned` que sigue una `ref` también cuenta como
desactualizada si la `ref` avanzó, porque el chequeo responde si falta actualizar y no si se aplica solo. Un commit
completo nunca queda desactualizado. `updates.refresh` configura `plan` y `status`; el chequeo solo evita la red
con `--offline`. `--format json` imprime un objeto con `status`, `ci` (`enabled` y `mode`), `exitStatus`,
`problems` y `unavailable`.

## Autenticación de packs privados

 Solo por Git, con lo que el entorno ya tenga, y nunca con `gh`: SSH
(`git+ssh://…` con el agente de SSH del proveedor) o un token en una variable de entorno. Git ≥ 2.31 toma la
configuración del entorno, así el token no queda escrito en ningún archivo:

```bash
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="url.https://oauth2:${PACKS_TOKEN}@git.example.com/.insteadOf"
export GIT_CONFIG_VALUE_0="https://git.example.com/"
```

El token no entra al manifest ni al lock, y los errores de Git se sanean antes de imprimirse. El nombre de usuario de
la URL depende del servidor (`oauth2`, `x-access-token`).

## Ejemplos

Los tres ejemplos clonan la skill **fuera** del repo. Dentro, sus `CLAUDE.md` contarían como archivos del proyecto.
Para que una versión nueva de golfo-kit no falle un PR ajeno, usar `AGENT_READY_SETUP_CI=warn` en los PR y dejar
`fail` en una corrida programada.

GitHub Actions (`.github/workflows/agent-ready.yml`):

```yaml
name: Agent Ready
on:
  pull_request:
  schedule:
    - cron: "17 6 * * 1"
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verificar que Agent Ready esté al día
        env:
          # Solo para packs privados: un token de lectura como secret.
          GIT_CONFIG_COUNT: "1"
          GIT_CONFIG_KEY_0: url.https://oauth2:${{ secrets.AGENT_PACKS_READ_TOKEN }}@github.com/acme/.insteadOf
          GIT_CONFIG_VALUE_0: https://github.com/acme/
        run: |
          git clone --depth 1 https://github.com/guidomodarelli/golfo-marketplace "$RUNNER_TEMP/golfo-marketplace"
          SKILL_DIR="$RUNNER_TEMP/golfo-marketplace/plugins/golfo-kit/skills/agent-ready-setup"
          python3 "$SKILL_DIR/scripts/agent-ready-state.py" check --project . --skill-dir "$SKILL_DIR"
```

Jenkins (`Jenkinsfile`):

```groovy
pipeline {
  agent any
  triggers { cron('H 6 * * 1') }
  stages {
    stage('Agent Ready') {
      steps {
        // Solo para packs privados: un token de lectura guardado en las credenciales de Jenkins.
        withCredentials([string(credentialsId: 'agent-packs-read-token', variable: 'PACKS_TOKEN')]) {
          sh '''
            set -u
            CHECKOUT="$(mktemp -d)"
            trap 'rm -rf "$CHECKOUT"' EXIT
            git clone --depth 1 https://github.com/guidomodarelli/golfo-marketplace "$CHECKOUT/golfo-marketplace"
            SKILL_DIR="$CHECKOUT/golfo-marketplace/plugins/golfo-kit/skills/agent-ready-setup"
            export GIT_CONFIG_COUNT=1
            export GIT_CONFIG_KEY_0="url.https://oauth2:${PACKS_TOKEN}@git.example.com/.insteadOf"
            export GIT_CONFIG_VALUE_0="https://git.example.com/"
            python3 "$SKILL_DIR/scripts/agent-ready-state.py" check --project . --skill-dir "$SKILL_DIR"
          '''
        }
      }
    }
  }
}
```

Cualquier otro proveedor, con shell y los códigos de salida:

```sh
#!/bin/sh
CHECKOUT="$(mktemp -d)"
trap 'rm -rf "$CHECKOUT"' EXIT
git clone --depth 1 https://github.com/guidomodarelli/golfo-marketplace "$CHECKOUT/golfo-marketplace" || exit 1
SKILL_DIR="$CHECKOUT/golfo-marketplace/plugins/golfo-kit/skills/agent-ready-setup"

python3 "$SKILL_DIR/scripts/agent-ready-state.py" check --project . --skill-dir "$SKILL_DIR" --format json > agent-ready-check.json
check_status=$?
case "$check_status" in
  0) echo "Agent Ready al día" ;;
  4) echo "Agent Ready desactualizado: ver agent-ready-check.json" ;;
  5) echo "Fuente de profiles no disponible: revisar la red y la autenticación de Git" ;;
  2) echo "Configuración de Agent Ready inválida: ver agent-ready-check.json" ;;
esac
exit "$check_status"
```
