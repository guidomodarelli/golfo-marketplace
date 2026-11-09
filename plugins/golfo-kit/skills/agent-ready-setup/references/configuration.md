# Configuración por capas

Fuente única de cómo se configura agent-ready-setup. Leer al cambiar una opción, al explicar de dónde salió un
valor, cuando un valor del manifest aparece como ignorado o al agregar una funcionalidad con opciones nuevas.
La lista de claves, con su tipo, default, variable y dirección de seguridad, se genera desde los schemas en
[configuration-keys.md](configuration-keys.md). Qué hace cada mecanismo (actualizaciones, refresco, chequeo de
CI, packs): sección 4 de [profiles-and-lockfile.md](profiles-and-lockfile.md).

## Contenido

1. Principio y defaults
2. Schemas por módulo
3. Capas y precedencia
4. Merge
5. Claves sensibles y aprobación de la máquina
6. `locked` de la organización
7. Presets
8. Ver la configuración efectiva
9. Agregar una funcionalidad

## 1. Principio y defaults

Todo funciona con una configuración vacía, igual en un proyecto personal y en uno de empresa. Cada funcionalidad
se apaga con su propio `enabled: false` sin tocar las demás, y nada corporativo se impone: la capa de organización
existe solo si alguien distribuye su archivo.

El manifest es disperso: guarda lo que alguien cambió. El apply nunca escribe un default; `--updates auto` quita
`updates.mode` en vez de escribirlo. Lo que una persona escribió queda como está, aunque coincida con el default,
porque puede pisar a propósito un valor de la organización o del usuario. Así un default que mejora llega a todos
los repos sin tocar sus archivos.

## 2. Schemas por módulo

Cada funcionalidad declara sus opciones en `assets/config/<módulo>.schema.json` (JSON Schema): tipo, valores,
`default` y descripción. `x-mount` dice dónde se monta en el manifest (`ci` → `ci.enabled`, `ci.mode`); el módulo
`core` se monta en la raíz (`profiles`, `providers`). Cada módulo que no es `core` declara `enabled`, un booleano con
default. `scripts/agent_ready_config.py` es el único resolvedor y no conoce ninguna opción por nombre.

Metadatos propios de agent-ready-setup en cada opción:

| Clave | Significado |
|---|---|
| `x-env` | variable de entorno que la pisa en una corrida |
| `x-layers` | capas desde las que se puede declarar; sin ella, todas |
| `x-merge: "union"` | una lista que se une entre capas |
| `x-security.strictness` | valores ordenados del más flojo al más estricto: la marca como sensible |
| `x-presets` | valores que fija cada valor del preset |
| `x-role` | rol que usa el motor: `approval-switch` (`security.enabled`) y `approved-projects` (`security.trustedProjects`) |

Una clave desconocida, un tipo o valor inválido, o una clave en una capa que no la admite fallan antes de escribir
nada y nombran la clave y la capa: `project layer (.agents/agent-ready.json): unknown key 'ci.mod'`. Lo mismo vale
para un schema mal formado. `bootstrap.sh` y el hook de SessionStart validan todas las capas antes de cualquier
otro paso; el hook avisa y no sincroniza nada.

## 3. Capas y precedencia

De menor a mayor precedencia:

| Capa | Archivo | Para qué |
|---|---|---|
| `defaults` | los schemas | lo que vale sin configurar nada |
| `organization` | `$AGENT_READY_SETUP_ORGANIZATION_CONFIG` o, sin esa variable, `/etc/agent-ready-setup/config.json` (Linux), `/Library/Application Support/agent-ready-setup/config.json` (macOS) o `%ProgramData%\agent-ready-setup\config.json` (Windows) | lo que una empresa distribuye, por ejemplo por MDM; sin archivo, la capa no existe |
| `user` | `${XDG_CONFIG_HOME:-~/.config}/agent-ready-setup/config.json` | preferencias de la máquina y repos aprobados |
| `project` | `.agents/agent-ready.json` (el manifest, versionado) | lo que el repo necesita |
| `environment` | las variables `x-env` de cada opción | una máquina o un job de CI, solo en esa corrida |
| `flags` | `--offline` (`updates.refresh: false`) | una corrida |

Los tres archivos tienen el mismo formato que el manifest. `profiles`, `providers` y `sources.packs` solo vienen del
proyecto; `security.trustedProjects`, solo de la organización o del usuario. La capa de organización es una
conveniencia, no un control a prueba de manipulación: quien maneja su entorno puede cambiarla. El control
compartido es el chequeo de CI.

`AGENT_READY_SETUP_REVIEW_MODE=1` no es una opción sino un modo de corrida: nunca escribe ni usa la red
([review-consumption.md](review-consumption.md)).

## 4. Merge

Los objetos se combinan clave por clave. Una lista con `x-merge: "union"` junta los elementos de todas las capas
(por ejemplo, `security.trustedProjects`; las listas de restricciones como `allow`, `deny` o `rules` se declaran
así). El resto de las listas y todos los escalares se reemplazan: gana la capa más alta que los declara.

## 5. Claves sensibles y aprobación de la máquina

Una opción con `x-security.strictness` es sensible. Endurecer desde el proyecto siempre se toma. Aflojar, es decir,
pedir un valor más flojo que el que dejan las capas de abajo (defaults, organización y usuario), solo se toma si la
máquina aprobó ese repositorio; si no, el valor se ignora y `config`, `plan`, `status` y el inicio de sesión lo
informan con el comando exacto para aprobarlo. El usuario, el entorno y los flags son de la máquina: no necesitan
aprobación, solo respetan `locked`.

Ejemplos: con `tools.enabled: false` en la config de usuario, `tools.enabled: true` en el manifest se ignora; con
`updates.mode: pinned` en el usuario, `updates.mode: auto` del manifest o `"updates": "auto"` en una fuente de
`sources.packs` se ignoran. `security.preset: off` desde el proyecto también cuenta como aflojar.

```bash
python3 "$SKILL_DIR/scripts/agent-ready-state.py" trust --project .           # aprueba este repo en esta máquina
python3 "$SKILL_DIR/scripts/agent-ready-state.py" trust --revoke --project .  # quita la aprobación
```

`trust` guarda la raíz del repo en `security.trustedProjects` de la config de usuario y no escribe en el repo.
`security.enabled: false` en el usuario o la organización deja aflojar a todos los proyectos sin aprobación.

## 6. `locked` de la organización

La organización puede declarar `"locked": ["ci", "updates.mode"]`: claves o namespaces enteros que ninguna capa de
arriba (usuario, proyecto, entorno ni flags) puede cambiar. El intento se ignora y se informa. Solo la organización
declara `locked`, y cada entrada tiene que existir en los schemas.

## 7. Presets

Un preset fija varias claves con una sola. `security.preset` es `standard` (default), `strict` (además
`updates.mode: pinned`) u `off` (`security.enabled: false`). `updates.preset` es `none` (default) o
`delivered`, para una solución entregada a un cliente ([stable-delivery.md](stable-delivery.md)); se elige
también con `agent-ready preset delivered`. Dentro de una capa, el preset se aplica primero y las
claves explícitas de esa misma capa lo pisan; las capas superiores también. Cada clave que fija pasa por las mismas
reglas de aflojar y de `locked` que si se hubiera escrito a mano, y el origen lo muestra: `user (preset
security.preset=strict)`. El preset de default coincide con los defaults.

## 8. Ver la configuración efectiva

```bash
python3 "$SKILL_DIR/scripts/agent-ready" config explain                     # valor y capa de cada opción
python3 "$SKILL_DIR/scripts/agent-ready" config explain updates.mode --json # una opción, para scripts
python3 "$SKILL_DIR/scripts/agent-ready" config set ci.mode warn            # escribe en el manifest
python3 "$SKILL_DIR/scripts/agent-ready" config set updates.mode pinned --layer user
python3 "$SKILL_DIR/scripts/agent-ready" config unset ci.mode
```

`config` muestra cada capa (con su archivo y si existe), si el repo está aprobado, cada opción con su valor
efectivo y su capa de origen, y lo ignorado. `--plan` incluye la misma sección. `--format tsv` es para Bash: una
línea `clave<TAB>valor` por opción y la línea derivada `auto_sources`. Ninguno usa la red ni escribe.

## 9. Agregar una funcionalidad

Sumar `assets/config/<módulo>.schema.json` con `enabled` y sus opciones alcanza: validación, merge, origen,
dirección de seguridad, `locked`, presets y la referencia generada no cambian. Después de tocar un schema,
regenerar la referencia:

```bash
python3 scripts/agent-ready-state.py config-reference > references/configuration-keys.md
```

`tests/agent-ready-config.bats` falla si la referencia commiteada no coincide con los schemas. Respetar «Opciones
con uso real» del `AGENTS.md` de la skill: una opción entra con el código que la usa.
