# AGENTS.md anidados

Instrucciones de una carpeta, no del repo (las rutas de `app/` en Next.js App Router, los handlers de
`src/server/` en un BFF, un módulo Gradle), en el `AGENTS.md` de esa carpeta. Un profile publica el bloque
y el repo decide a qué carpeta va.

## Contenido

1. Cómo cargan los providers los anidados
2. Destinos anidados
3. Escritura, proxy y retiro
4. Lock, plan, status y remove
5. Fuera de alcance

## 1. Cómo cargan los providers los anidados

Verificado en la documentación oficial y probado con Claude Code 2.1.319 y codex-cli 0.162.1, con un
`AGENTS.md` raíz y otro en `web/app/` ([issue #61](https://github.com/guidomodarelli/golfo-marketplace/issues/61#issuecomment-6700093733)).

**Codex** ([doc](https://developers.openai.com/codex/guides/agents-md)):

- Arma la cadena una sola vez, al iniciar: el global (`~/.codex/AGENTS.override.md` o `AGENTS.md`) y, desde la
  raíz de Git hasta el directorio de trabajo, un archivo por directorio (`AGENTS.override.md`, `AGENTS.md` o
  `project_doc_fallback_filenames`), concatenados de la raíz hacia abajo, con un tope combinado de 32 KiB
  (`project_doc_max_bytes`).
- No carga los anidados por debajo del directorio de trabajo. Lanzado desde la raíz, su contexto inicial no
  tiene el de `web/app/`. En una corrida, el modelo lo buscó por su cuenta antes de tocar `web/app/page.ts`,
  pero es comportamiento del modelo, no del loader: no está garantizado.
- La review de Codex en GitHub usa la sección `## Code Review Rules` del `AGENTS.md` más cercano al código:
  ahí los anidados sí cuentan.
- No lee `CLAUDE.md`, salvo que el usuario lo sume a `project_doc_fallback_filenames` en su configuración.

**Claude Code** ([doc](https://code.claude.com/docs/en/memory)):

- Carga al iniciar el `CLAUDE.md` del directorio de trabajo y los de arriba. El de un subdirectorio, a
  demanda: la primera vez que lee, escribe o edita un archivo de ahí.
- Lee `AGENTS.md` de forma nativa desde 2.1.277, pero con el modo por defecto solo si no hay ningún
  `CLAUDE.md`, `.claude/CLAUDE.md` ni `CLAUDE.local.md` en el directorio de trabajo o más arriba. Como
  agent-ready-setup deja un `CLAUDE.md` en la raíz, un `AGENTS.md` anidado sin su `CLAUDE.md` hermano no le
  llega. El modo (`instructionFiles`) solo lo fijan los settings del usuario, `--settings` o los managed: el
  repo no puede cambiarlo.
- Nunca lee `AGENTS.override.md`, `AGENTS.local.md` ni nada bajo `.agents/`.
- Quita los comentarios HTML de bloque antes de inyectar un `CLAUDE.md`, así que los marcadores de los
  bloques no gastan contexto. En Windows recomienda el import `@AGENTS.md` en vez de un symlink.
- Las rules con `paths:` de `.claude/rules/` cargan al leer, escribir o editar un archivo que coincide:
  equivalen a un `AGENTS.md` anidado, pero solo en Claude Code.

**Qué sale de ahí:** el `AGENTS.md` anidado con su `CLAUDE.md` proxy es el único formato que llega a los dos
providers y a la review de Codex en GitHub. Para que Codex lo lea de forma determinista, el bloque raíz
tiene que indicarle cuándo leerlo (parte 61b de la issue).

## 2. Destinos anidados

Un profile, de golfo-kit o de un pack, declara cada destino en su entrada del catálogo y publica el
bloque en `nested/<nombre>.md` de su árbol de assets:

```json
"nested": { "app-router": { "candidates": ["app", "src/app"] } }
```

- **Id:** `<profile>/<nombre>`, como `nextjs-app-router/app-router` o `acme/web/app-router`. Es el id del
  bloque en sus marcadores (`<!-- BEGIN AGENT-READY MANAGED: acme/web/app-router -->`).
- **`candidates`:** carpetas relativas a la raíz, en orden. Es opcional: un destino sin candidatas solo se
  escribe donde lo configura el manifest.
- **Validación:** el nombre va en kebab-case. Cada destino declarado necesita su `nested/<nombre>.md`, y cada
  archivo de `nested/` tiene que ser el de un destino declarado. Un `bundle` no declara destinos.

**Resolución**, por destino:

1. El manifest gana: `nested.targets` le fija las carpetas (`paths`) o lo apaga (`enabled: false`).
2. Si no, la primera candidata que existe como carpeta, a la que se llega sin symlinks y que Git no ignora.
3. Si no hay ninguna, no se escribe nada, y `agent-ready plan` lo informa con las carpetas que probó.

```json
{
  "nested": {
    "targets": [
      { "id": "acme/web/app-router", "paths": ["apps/web/src/app", "apps/admin/src/app"] },
      { "id": "acme/web/handlers", "enabled": false }
    ]
  }
}
```

`nested.enabled: false` apaga todos los destinos. Un destino apagado no escribe, y el apply siguiente retira
sus bloques. Las claves están en [configuration-keys.md](configuration-keys.md).

**Paths rechazados.** Un path de `nested.targets` frena `plan` (exit `2`) y el apply antes de escribir, con un
error que nombra la carpeta y el destino, si:

- no es una carpeta relativa dentro del repo (absoluto, con `..`, `.` o una barra al final);
- es un patrón;
- está bajo `.git/`, `.agents/`, `.claude/` o `.codex/`;
- no existe;
- Git lo ignora.

Una carpeta a la que se llega por un symlink o una junction de Windows queda como conflicto del bloque, igual
que en cualquier bloque gestionado. Un id de `nested.targets` que ningún profile de la selección publica no
frena nada: `plan` lo avisa.

## 3. Escritura, proxy y retiro

- **Escritura:** en `<carpeta>/AGENTS.md` va solo el bloque del destino, con el contrato de los bloques
  gestionados ([managed-agents-block.md](managed-agents-block.md), «Bloques en otros archivos»):
  - Si el archivo no existe, se crea con el bloque.
  - Si existe, el bloque se agrega al final o se actualiza donde está, y el resto es del proyecto.
  - Varios destinos pueden ir a la misma carpeta, cada uno con su id.
- **Proxy:** al escribir un `AGENTS.md` anidado, el apply deja al lado un `CLAUDE.md` con el proxy de
  `assets/claude-proxy.md`, si no hay ninguno. Sin él, Claude Code no lo carga (sección 1).
- **`CLAUDE.md` propio:** si la carpeta tiene un `CLAUDE.md` con instrucciones propias distintas de su
  `AGENTS.md`, el bloque espera, como las secciones de la raíz:
  - El lock conserva lo que sabía del bloque.
  - Primero se unen los dos archivos.
  - Un `CLAUDE.md` sin `AGENTS.md` al lado lo mueve la normalización antes de que se escriban los bloques.
- **Retiro:** un destino que cambia de carpeta, se apaga o sale de la selección deja su bloque en el lock, y
  el apply lo saca del archivo anterior. Si a ese `AGENTS.md` no le queda contenido, se borra junto con su
  `CLAUDE.md`, siempre que sea el proxy o un `@AGENTS.md` solo.

## 4. Lock, plan, status y remove

- **Lock:** guarda los bloques anidados en `blocks`, por archivo e id, como cualquier bloque.
- **`plan`:** muestra una línea por destino, con su carpeta y de dónde salió:
  - `Nested AGENTS.md: acme/web/app-router -> src/app/AGENTS.md (detected)`;
  - `… (nested.targets)` si la carpeta la fija el manifest;
  - `no folder` si no encontró ninguna;
  - `off` si está apagado.

  Muestra el diff de cada bloque que cambia, y `--json` deja los destinos en `nested`.
- **`status`:** informa como `modified` un bloque editado a mano.
- **`--from-lock`:** compara los bloques con el lock.
- **`contentDigest` de golfo-kit:** cuenta cada destino por su id y su contenido, no por la carpeta del repo.
- **`agent-ready remove`:** saca cada bloque, y borra el `AGENTS.md` que queda vacío junto con su proxy.

## 5. Fuera de alcance

- La revisión de redundancias con IA (`merge-instructions.sh`) solo trabaja sobre el `AGENTS.md` raíz.
- Las contradicciones entre el `AGENTS.md` raíz y los anidados son la parte 72e de #72.
- El índice del bloque raíz para Codex, su costo en bytes y el proxy anidado mínimo son la parte 61b de #61.
