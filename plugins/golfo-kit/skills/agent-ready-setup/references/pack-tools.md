# Herramientas de un pack y política de seguridad

Qué puede declarar un profile de un pack además de archivos (CLIs, servidores MCP y scripts), y la
política que decide, en cada máquina, si cada herramienta puede ejecutarse. Leer al publicar un pack
con herramientas, al explicar por qué una herramienta quedó bloqueada, al confiar en una fuente o al
cambiar las claves `security.*`.

> **Estado.** El motor valida las declaraciones y evalúa la política, pero todavía no instala,
> registra ni corre nada. `plan` y `status` muestran el veredicto de cada herramienta. La instalación
> llega en las próximas partes de #65.

## Contenido

1. Declaraciones
2. Política
3. Confiar en una fuente o aprobar un repositorio
4. Ver el veredicto

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
  - `package` usa `npm`, `pip`, `brew` o `winget`, con un `sha256` opcional.
- **`mcpServers`**
  - Por nombre en kebab-case: un `command` (el nombre de un ejecutable, sin ruta ni argumentos), con
    `args` y `env`, o una `url` https con `headers`.
  - Los valores de `env` son solo referencias (`${ACME_TOKEN}`). Los de `headers` admiten una
    palabra antes (`Bearer ${ACME_TOKEN}`). Nunca un valor: ningún secreto entra al pack, al
    manifest ni al lock.
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
   (default `install` y `post-apply`; `session-start` correría en cada inicio de sesión).
2. Los `checks`, que se apagan por separado:
   - `trustedSource` (default `true`): la fuente tiene que ser de confianza en esta máquina.
   - `signature` (default `false`): el commit o tag firmado. El motor todavía no verifica firmas, así
     que con `true` nada se permite.
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

## 4. Ver el veredicto

`agent-ready plan` lista cada herramienta como `allowed` o `blocked` con su motivo, y la política
efectiva con la capa de cada valor. `agent-ready status` muestra lo mismo de forma breve. En el JSON
del plan van en `packTools`, con `policy` (`value` y `origin` de cada clave), `tools` (cada una con
`decision` y `reason`) y `executes: false`. Las rules y skills de un pack se proyectan siempre,
pase lo que pase con sus herramientas.
