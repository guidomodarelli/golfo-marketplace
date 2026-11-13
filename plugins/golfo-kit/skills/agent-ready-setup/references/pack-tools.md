# Herramientas de un pack y política de seguridad

Qué puede declarar un profile de un pack además de archivos (CLIs, servidores MCP y scripts), y la
política que decide, en cada máquina, si cada herramienta puede ejecutarse. Leer al publicar un pack
con herramientas, al explicar por qué una herramienta quedó bloqueada, al confiar en una fuente o al
cambiar las claves `security.*`. Cómo publicar un pack así, personal o corporativo firmado, está en
[publishing-packs-with-tools.md](publishing-packs-with-tools.md).

> **Estado.** Un apply registra los servidores MCP (sección 5), instala los CLIs (sección 6) y corre
> los scripts (sección 7) que la política permite. Con `security.checks.signature: true` verifica la
> firma SSH de la revisión de cada fuente (sección 3); las firmas GPG todavía no cuentan.

## Contenido

1. Declaraciones
2. Política
3. Confiar en una fuente o aprobar un repositorio
4. Ver el veredicto
5. Registro de servidores MCP
6. Instalación de CLIs
7. Scripts

## 1. Declaraciones

Van en el profile del pack, en `agent-ready-pack.json`. El schema es cerrado: una clave desconocida o
un valor fuera del schema frena el apply antes de escribir y nombra el pack y el profile.

```json
"kafka-interno": {
  "kind": "capability",
  "assets": "profiles/kafka-interno",
  "clis": [
    { "name": "acme", "version": "1.4.2", "artifacts": [
      { "platform": "linux-x64", "url": "https://downloads.acme.dev/acme-linux-x64.tar.gz",
        "sha256": "<64 caracteres hex>", "binary": "acme" } ] },
    { "name": "acme-helper", "version": "2.0.0", "package": { "manager": "npm", "name": "@acme/helper" } }
  ],
  "mcpServers": {
    "acme-docs": { "command": "acme", "args": ["mcp"], "env": { "ACME_TOKEN": "${ACME_TOKEN}" } },
    "acme-remote": { "url": "https://mcp.acme.dev", "headers": { "Authorization": "Bearer ${ACME_TOKEN}" } }
  },
  "scripts": [
    { "event": "install", "path": "scripts/setup.sh", "interpreter": "bash", "timeoutSeconds": 60 }
  ]
}
```

- **`clis`**
  - `name` en kebab-case y `version` exacta: sin rangos ni tags, para que sea reproducible.
  - Lleva `artifacts` o `package`, nunca los dos.
  - `artifacts` tiene un archivo por plataforma (`linux-x64`, `linux-arm64`, `darwin-x64`,
    `darwin-arm64`, `windows-x64`, `windows-arm64`), con una `url` https sin credenciales y su `sha256`.
  - `package` usa `npm`, `pip`, `brew` o `winget`, con un `sha256` opcional. Con `npm` y `pip`, `name` es
    un nombre del registro: nunca una ruta, una URL ni un spec de Git.
  - `binary` es el nombre del ejecutable, si no es el `name` del CLI.
- **`mcpServers`**
  - Por nombre en kebab-case: un `command` (el nombre de un ejecutable, sin ruta ni argumentos), con
    `args` y `env`, o una `url` https con `headers`.
  - Los valores son solo referencias, nunca un valor: ningún secreto entra al pack, al manifest, al
    lock ni a la config de los providers. En `env`, cada variable pasa con su propio nombre
    (`"ACME_TOKEN": "${ACME_TOKEN}"`). En `headers`, el valor es `${VAR}`, y solo `Authorization`
    acepta `Bearer ${VAR}`. Así los dos providers leen la variable de su entorno.
- **`provides`** (opcional, en un CLI o un servidor): las capacidades que da, en kebab-case
  (`["browser-automation"]`). Sirve para avisar de dos herramientas que compiten por lo mismo; no
  cambia lo que se instala ni lo que se registra.
- **El mismo CLI o servidor en dos profiles.** Declarado igual (sin contar `provides`), se instala o
  registra una vez. Con el mismo nombre y otra versión, paquete, comando, URL o argumentos, es un
  conflicto: el plan y el apply fallan antes de escribir y nombran los dos profiles.
- **`scripts`**
  - `event` es `install`, `post-apply` o `session-start`.
  - `path` es un archivo dentro del pack, sin symlinks.
  - `interpreter` es `bash`, `python3`, `node` o `pwsh`.
  - `timeoutSeconds` va de 1 a 3600.

## 2. Política

Vive en el módulo `security` de la configuración por capas ([configuration.md](configuration.md));
las claves, en [configuration-keys.md](configuration-keys.md). Para cada herramienta se evalúa, en
este orden, y la primera que la frena da el motivo:

1. `security.execution.enabled` (default `true`) y, para un script, `security.execution.events`
   (default `install` y `post-apply`; `session-start` correría en cada inicio de sesión). En
   integración continua (`CI` definida), además, `security.execution.ci` (default `false`): un
   workflow que quiere las herramientas de sus packs lo prende en su propia configuración.
2. Los `checks`, que se apagan por separado:
   - `trustedSource` (default `true`): la fuente tiene que ser de confianza en esta máquina.
   - `signature` (default `false`): el commit de la fuente, o un tag de su origen que apunta a ese
     commit, tiene una firma SSH válida de una clave de `security.signers` para esa fuente (sección 3).
     Una fuente `path:` no tiene revisión propia, así que con `true` sus herramientas no pasan.
   - `artifactSha256` (default `true`): cada artefacto de un CLI declara su `sha256`. Un paquete sin
     `sha256` queda bloqueado.
   - `lockDigest` (default `true`): lo que se ejecute tiene que coincidir con el digest del lock. Se
     aplica cuando haya ejecución.
3. `security.deny.commands` y `security.deny.scripts`: patrones glob que ganan siempre. Se unen entre
   capas, así que una capa de arriba nunca borra un deny de abajo.
   - `commands` se compara con el nombre del CLI y con el comando de un servidor MCP.
   - `scripts`, con `<fuente>/<ruta en el pack>`.
4. `security.rules`: cada regla elige por `source`, `profile`, `type` (`cli`, `mcpServer` o
   `script`), `pattern` (nombre o `<fuente>/<ruta>`, glob) o `contains` (texto del script), y su
   `action` es `allow` o `deny`.
   - Una regla `deny` gana sobre una `allow`.
   - Una `allow` deja pasar una herramienta que una lista `allow` dejaría afuera, pero nunca saltea
     los checks ni las listas `deny`.
   - Ejemplo: `{"match": {"type": "script", "contains": "| sh"}, "action": "deny"}`.
5. Las listas `security.allow.clis`, `commands`, `scripts` y `mcpServers`: vacías no restringen nada.
   Con algo, solo pasa lo que nombran.

**Quién puede aflojar.** Endurecer desde el proyecto siempre se toma: sumar `deny`, achicar `allow`,
exigir firma o apagar la ejecución. Aflojar desde el manifest solo cuenta en un repositorio aprobado
en la máquina ([configuration.md](configuration.md), sección 5). Si no, se ignora y `plan` lo informa.
Cuenta como aflojar:

- apagar un check;
- sumar una fuente de confianza o un evento;
- vaciar o ampliar una lista `allow` no vacía;
- sumar una regla `allow`.

La organización puede bloquear claves con `locked`.

## 3. Confiar en una fuente o aprobar un repositorio

```bash
agent-ready trust add acme          # confía en la fuente acme del manifest, en esta máquina
agent-ready trust remove acme
agent-ready trust add --project .   # aprueba este repositorio: su manifest puede aflojar
agent-ready trust list [--json]     # si el repo está aprobado y en qué fuentes confía la máquina
```

- **Dónde se guarda.** La confianza va en la config de usuario (`security.trustedSources`, por el
  origen de la fuente), nunca en el repositorio. Un PR no puede aprobarse a sí mismo.
- **Quien agrega una fuente la aprueba.** `agent-ready sources add` confía en ella en la máquina de
  quien la agrega. Un compañero que la recibe por Git la aprueba una vez con `agent-ready trust add <fuente>`.
- **Fuentes `path:`.** Viven en el repositorio, así que son de confianza si el repositorio está aprobado.

### Claves que firman una fuente

```bash
agent-ready trust add acme --signer ~/.ssh/acme-release.pub   # confía en acme y en esa clave para firmarla
agent-ready config set security.checks.signature true --layer user
```

- **Qué se guarda.** `--signer` lee la clave pública SSH (el `.pub`, nunca la privada) y la suma a
  `security.signers` de la config de usuario como `{"key": "<clave>", "source": "acme"}`. Sin
  `source`, una clave firma todas las fuentes. `trust remove acme` borra también sus claves.
- **Qué se verifica.** Git verifica, contra un archivo de firmantes permitidos armado solo con esas
  claves, la firma del commit al que resolvió la fuente o la de un tag de su origen que apunta a ese
  commit. Cuando el check está prendido, un apply o un plan trae al mirror del caché los tags anotados
  del origen que apuntan a ese commit, sea cual sea el ref que sigue la fuente. Verificar no usa la red. Un commit nuevo sin firma en el ref vuelve a bloquear.
- **Solo SSH.** Una firma GPG no cuenta: verificarla depende del keyring y del agente de cada máquina.
- **Sumar claves afloja.** `security.signers` se une entre capas, y el manifest de un repositorio
  solo suma claves si la máquina lo aprobó: un PR no puede firmar sus propios packs.

## 4. Ver el veredicto

`agent-ready plan` lista cada herramienta como `allowed` o `blocked` con su motivo, y la política
efectiva con la capa de cada valor. `agent-ready status` muestra lo mismo de forma breve. En el JSON
del plan van en `packTools`, con `policy` (`value` y `origin` de cada clave), `tools` (cada una con
`decision` y `reason`) y `applies`, los tipos que un apply ya aplica (`cli`, `mcpServer` y `script`). Las rules y
skills de un pack se proyectan siempre, pase lo que pase con sus herramientas.

## 5. Registro de servidores MCP

Un apply registra cada servidor MCP permitido para los providers del repo (`providers`):

| Provider | Archivo | Cómo pasan las referencias |
|---|---|---|
| Claude Code | `.mcp.json`, en `mcpServers` | `env` y `headers` tal cual: Claude Code expande `${VAR}` |
| Codex | `.codex/config.toml`, entre `# BEGIN AGENT-READY PACK MCP SERVERS` y `# END AGENT-READY PACK MCP SERVERS` | `env_vars` con los nombres de `env`; `bearer_token_env_var` para `Authorization: Bearer ${VAR}`; `env_http_headers` para los demás headers |

- **Ownership por el lock.** El lock guarda cada servidor registrado en `mcpServers`, con su
  fuente, su profile, el sha256 de la declaración y los providers. Un servidor que el lock registra
  se reemplaza o se borra libremente. Uno del proyecto con el mismo nombre nunca se toca: el apply
  lo informa como conflicto y no registra el del pack para ese provider.
- **Se desregistra solo.** Un servidor que deja de estar permitido (se quita la confianza, una regla
  lo prohíbe) o cuyo profile se retira se borra en el próximo apply.
  `agent-ready remove` desregistra todos los de los packs y deja los del proyecto.
- **Solo un apply.** `plan`, `status`, la detección y las revisiones automáticas
  (`AGENT_READY_SETUP_REVIEW_MODE=1`) nunca cambian los servidores registrados.
- **Si dos packs declaran el mismo nombre,** declarado igual se registra una vez; distinto, el plan
  falla antes de escribir (sección 1).
- **Si el usuario ya lo tiene** para todos los proyectos (`~/.claude.json`, `config.toml` de Codex),
  con el mismo URL, paquete o comando, no se registra la copia del proyecto en ese provider y se
  informa (`references/ai-reviews.md`, «Choques con la máquina»).
- **El `command` se busca en el PATH del provider.** Claude Code y Codex lanzan el comando tal cual.
  Un CLI que instala un pack queda en el caché del usuario (sección 6), fuera de ese PATH, así que un
  servidor no puede lanzarse con él. La entrada no lleva la ruta del caché porque `.mcp.json` y
  `.codex/config.toml` se versionan en el repo. Para un servidor propio, usar uno remoto (`url`) o un
  comando instalado en cada máquina.

## 6. Instalación de CLIs

Un apply instala cada CLI permitido en la caché del usuario (`$XDG_CACHE_HOME/agent-ready-setup/clis`,
o `~/.cache/agent-ready-setup/clis`), nunca en el repositorio:

| Origen | Qué hace el apply |
|---|---|
| `artifacts` | Descarga por https el archivo de la plataforma de la máquina y compara su `sha256` antes de abrirlo. Un `.tar.gz`, `.tgz` o `.zip` se extrae sin links ni rutas que salgan de su directorio; cualquier otro archivo es el ejecutable. |
| `npm` | `npm pack --ignore-scripts` baja el tarball sin correr sus scripts, se compara su `sha256` y recién después `npm install` lo instala en un prefijo propio. |
| `pip` | Solo wheels: un paquete fuente correría su build antes de que el `sha256` pudiera rechazarlo. `pip download --no-deps --only-binary=:all:` lo baja, con el `sha256` como hash de la requirement para que pip lo verifique, y se instala en un entorno virtual propio, creado donde queda. |
| `brew`, `winget` | Nunca se ejecutan, porque instalan para toda la máquina. El apply dice el comando para instalarlo a mano y si el ejecutable ya está en el PATH. |

- **Un `sha256` distinto no instala nada.** El apply informa el error, conserva lo que el repositorio
  usaba y sigue con el resto. Las dependencias de un paquete npm o pip las resuelve su gestor: el
  `sha256` cubre el paquete declarado, no sus dependencias.
- **Una versión por máquina.** Cada versión vive una vez en la caché
  (`installs/<nombre>/<versión>/<origen>-<id>`, donde `<id>` sale del `sha256` declarado) y la comparten
  los repositorios que declaran los mismos bytes. Dos packs con el mismo nombre y versión pero otro
  `sha256` (o otro `binary`) quedan en instalaciones distintas, así uno nunca reemplaza lo que corre el
  otro. La limpieza nunca sigue un symlink ni un junction dentro de la caché. Cada
  repositorio anota cuáles usa (`projects/<clave>.json`); una versión que ningún repositorio usa se
  borra en el próximo apply o `remove` de cualquiera de ellos.
- **PATH del repositorio.** Los directorios de los ejecutables quedan, uno por línea, en
  `agent-ready/cli-path` dentro del directorio de Git (`git rev-parse --git-path agent-ready/cli-path`).
  De ahí los toma el runner de los scripts del pack. Ningún otro proceso los recibe solo: ni el shell
  del agente ni el de la persona. Una rule que pide correr el CLI dice cómo sumar esos directorios al
  PATH; `assets/examples/personal-tools-pack/` lo muestra en bash y PowerShell.
- **Sin escrituras de más.** Un apply que no cambia nada no reescribe el registro del repositorio ni
  `agent-ready/cli-path`.
- **Lock.** `clis` guarda, por nombre, la fuente, el profile, la versión, el origen y el `sha256`.
- **Se desinstala solo.** Un CLI que deja de estar permitido o cuyo profile se retira deja de usarse
  en el próximo apply. `agent-ready remove` deja de usar todos.
- **Solo un apply.** `plan`, `status`, la detección y las revisiones automáticas
  (`AGENT_READY_SETUP_REVIEW_MODE=1`) nunca descargan ni instalan.
- **Si dos packs declaran el mismo nombre,** se instala el primero y se informa el otro.

## 7. Scripts

Un script permitido corre con su `interpreter` desde la raíz del proyecto, con su `timeoutSeconds`. Si un
pack instaló ese intérprete (sección 6), se usa ese; si no, el `bash` del PATH, el mismo Python del motor,
o `node` y `pwsh` del PATH:

| Evento | Cuándo corre |
|---|---|
| `install` | En un apply, la primera vez y cada vez que cambia su contenido (sha256), o si la vez anterior falló. |
| `post-apply` | Al final de cada apply, después de proyectar los archivos, registrar los MCP e instalar los CLIs. |
| `session-start` | En cada inicio de sesión, en segundo plano desde el hook. Solo si `security.execution.events` lo incluye. |

- **Entorno.** El script hereda el entorno de la sesión, con los CLIs de los packs primero en el PATH
  (`agent-ready/cli-path`, sección 6), y recibe `AGENT_READY_PACK_ROOT`, `AGENT_READY_PROJECT_ROOT` y
  `AGENT_READY_EVENT`. Corre con los permisos del usuario.
- **Logs.** La salida de cada script va a un log privado en el directorio de Git
  (`agent-ready/scripts/<id>-<evento>.log`). El motor nunca imprime variables de entorno; lo que el
  script imprima es responsabilidad del script.
- **Timeout.** Un script que se pasa de `timeoutSeconds` se corta con todo lo que lanzó (en Windows,
  con un job object) y se informa. Si se corta el sync que lo lanzó, se cortan los scripts de ese sync, no los de otra sesión. Un script que
  declaran dos profiles corre una sola vez por apply.
- **Falla.** Un script que sale con un código distinto de 0 o se corta se informa con su log (una línea
  `ERROR:`, que la actualización en segundo plano muestra en la sesión siguiente), y el apply termina
  como `partial`. Un `install` que falló vuelve a correr en el próximo apply.
- **Lock.** `scripts` guarda, por `<evento>:<fuente>/<ruta>`, el intérprete y el sha256 del script. Un
  mismo script declarado en dos eventos tiene una entrada por evento. Si un `install` ya corrió se
  anota en el checkout (`agent-ready/scripts/installed.json`, en el directorio de Git), nunca en el lock:
  un clon del repositorio lo corre para sí.
- **`session-start` y el lock.** Con `security.checks.lockDigest` (default `true`), el hook corre solo
  el script exacto que registró el último apply: un pack que cambió espera al próximo apply. Dos
  sesiones que arrancan juntas en el mismo checkout nunca los corren a la vez. Si uno falla, la sesión
  siguiente lo muestra una vez. Después de 3 corridas fallidas seguidas, la siguiente espera una hora;
  un apply vuelve a contar de cero. Un script que declaran dos profiles corre una vez.
- **Solo un apply o el hook.** `plan`, `status`, la detección y las revisiones automáticas
  (`AGENT_READY_SETUP_REVIEW_MODE=1`) nunca corren scripts.
