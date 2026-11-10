# Chequeo de CI de agent-ready-setup

Leer al agregar el chequeo a un pipeline o al explicar un código de salida. Configuración y defaults:
[configuration.md](configuration.md) (`ci.enabled`, `ci.mode`, `ci.provider`).

Es un comando común que sirve en cualquier proveedor de CI, porque no depende de `gh` ni de variables de GitHub. Necesita `python3`, `git` y `bash`, y no necesita la CLI de Claude ni la de Codex.
Con `ci.provider` agent-ready-setup deja armado el job del proveedor (sección siguiente); sin él no crea nada
y el job se arma a mano con los ejemplos del final.

```bash
python3 "$SKILL_DIR/scripts/agent-ready" check [--offline] [--json]
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

## Archivos por proveedor (`ci.provider`)

`agent-ready ci setup --provider <proveedor>` escribe `ci.provider` en el manifest (solo la capa del proyecto) y
aplica. Los archivos son assets de un profile de CI (`ci-<proveedor>`, `kind: ci`) que elige esa clave y nunca la
selección de profiles: se proyectan, se registran en el lock y se retiran como cualquier asset gestionado.
`--no-apply` solo escribe la clave, y el próximo `apply` crea los archivos; hasta entonces `check` sale con 4.

| `ci.provider` | Qué deja armado |
|---|---|
| `github` | el script y `.github/workflows/agent-ready.yml`, que lo corre en cada PR, una vez por semana y a mano |
| `gitlab` | el script, el job `.agents/ci/gitlab-ci.yml` en el stage `.pre`, que existe en cualquier pipeline sin importar sus `stages`, y, en `.gitlab-ci.yml`, solo un bloque gestionado con su `include: local:` |
| `jenkins` | el script y `.agents/ci/jenkins-stage.groovy`, el stage para copiar en el `Jenkinsfile`, que nunca se edita; `ci setup` lo imprime por stdout |
| `generic` | solo el script, para llamarlo desde cualquier pipeline |
| `none` | nada; queda registrado que se eligió no configurar el CI |

Todos los proveedores llaman al mismo script, `.agents/ci/agent-ready-check.sh`: clona golfo-marketplace fuera del
repo, corre `agent-ready check` con los argumentos que reciba y sale con su código. Con `ci.enabled: false` en el
manifest sale con 0 antes de clonar, así un chequeo apagado no depende de la red. El workflow de GitHub hace el
checkout con `persist-credentials: false`, para que el `GITHUB_TOKEN` no reemplace el token de los packs privados. Cambiar el proveedor, o pasarlo
a `none`, retira los archivos y bloques del anterior. Si `.gitlab-ci.yml` ya tiene un `include:` propio, sumar
`- local: .agents/ci/gitlab-ci.yml` a esa lista y no elegir `gitlab`: dos claves `include:` invalidan el YAML. GitLab
no corre un pipeline que solo tiene jobs de `.pre`: en un repo sin otros jobs, elegir `generic` y llamar al script desde
un job propio.

Ningún archivo generado contiene un secreto. Para packs privados, el CI expone dos variables que el script
convierte en la configuración de Git del entorno: `AGENT_READY_GIT_TOKEN`, un token de lectura guardado como
secret (en GitHub Actions, el secret del mismo nombre; en GitLab, una variable enmascarada; en Jenkins, una
credencial de tipo string), y `AGENT_READY_GIT_URL`, el prefijo de las URLs de los packs (por ejemplo
`https://github.com/acme/`). El usuario de la URL es `oauth2` salvo que `AGENT_READY_GIT_USER` diga otro.

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

## Ejemplos a mano

Para armar el job sin `ci.provider`. Los tres ejemplos clonan la skill **fuera** del repo. Dentro, sus `CLAUDE.md` contarían como archivos del proyecto.
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
          python3 "$SKILL_DIR/scripts/agent-ready" check
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
            python3 "$SKILL_DIR/scripts/agent-ready" check
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

python3 "$SKILL_DIR/scripts/agent-ready" check --json > agent-ready-check.json
check_status=$?
case "$check_status" in
  0) echo "Agent Ready al día" ;;
  4) echo "Agent Ready desactualizado: ver agent-ready-check.json" ;;
  5) echo "Fuente de profiles no disponible: revisar la red y la autenticación de Git" ;;
  2) echo "Configuración de Agent Ready inválida: ver agent-ready-check.json" ;;
esac
exit "$check_status"
```
