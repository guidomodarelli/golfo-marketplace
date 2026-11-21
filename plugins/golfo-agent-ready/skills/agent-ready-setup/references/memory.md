# Memoria con Engram

Cómo agent-ready-setup da memoria de lo que pasó (personas, clientes, proyectos, expedientes y las
decisiones de cada caso) con [Engram](https://github.com/Gentleman-Programming/engram), y qué garantiza
sobre esa memoria. Leer al explicar qué recuerda el agente entre sesiones, al apagar la memoria o al
revisar por qué `agent-ready check` falló con `private-files`.

El profile `memory-engram` llega con el contenido 1.6.0: instala Engram (versión exacta y `sha256` por
plataforma), registra su servidor MCP como `agent-ready tool run engram -- mcp --tools=agent`
([pack-tools.md](pack-tools.md), sección 5) y trae la rule de cuándo guardar y cuándo buscar. El
provider necesita `agent-ready` en su PATH, que pone el paquete npm `@golfo/agent-ready`.

## Memoria y aprendizaje

Son dos cosas distintas, y ninguna guarda lo de la otra:

| | Qué guarda | Dónde vive |
|---|---|---|
| Memoria (Engram) | hechos y contexto: quién es quién, qué se decidió en un caso, qué pasó la semana pasada | en la máquina del usuario, por proyecto |
| Aprendizaje ([learning.md](learning.md)) | cómo trabajar: una preferencia o una restricción que dura, un procedimiento | en el repositorio, como rules y skills |

Una instrucción que debe durar («de ahora en más…») va al aprendizaje, nunca a Engram: así una memoria
vieja no contradice una rule que cambió. Un dato de un caso va a Engram, nunca a una rule.

## Activa por defecto

`memory.engram` (y `memory.enabled`) vienen encendidas: toda selección trae por defecto el profile
`memory-engram` del contenido, también una sin stack (`--profiles none`). El profile instala Engram,
registra su servidor MCP para Claude Code y Codex y trae la rule de cuándo guardar y cuándo buscar.

- **Apagarla.** `{"memory": {"engram": false}}` en el manifest (o `memory.enabled: false`, o
  `AGENT_READY_SETUP_MEMORY=0` en una corrida) deja afuera `memory-engram` aunque la selección lo
  nombre, y el próximo apply retira lo que había instalado y registrado. Un profile que requiere `memory-engram` falla antes de escribir. También se puede dejar
  afuera con `excludedDefaults: ["memory-engram"]`.
- **Sin el profile en el contenido** (una versión anterior a la que lo publica), las dos claves no hacen
  nada.

## Nunca se exporta

La memoria es información confidencial del cliente, y estas garantías no se configuran desde el
repositorio:

- La base de Engram vive solo en la máquina del usuario (`~/.engram/`). agent-ready-setup nunca corre
  `engram sync` sobre el repositorio ni configura un autosync.
- El bloque gestionado del `.gitignore` ignora `.engram/`, la carpeta donde `engram sync` escribiría lo
  que comparte por Git.
- `agent-ready check` falla con `private-files` (código 8) si Git tiene versionado un archivo de
  `.engram/`, antes de cualquier otro chequeo. Ni `ci.mode: warn` ni `ci.enabled: false` lo saltean
  ([ci-check.md](ci-check.md)). Se arregla con `git rm --cached` del archivo.
- `learn export` y `learn harvest` ([learning-share.md](learning-share.md)) leen solo lo aprendido de
  `.agents/learning/candidates.json`: nunca la base de Engram, `.engram/` ni la salida del CLI.

## Alcance por proyecto

Engram guarda cada memoria bajo el proyecto del repositorio (lo detecta por el remoto de Git o la
carpeta), así que buscar desde el repo de un cliente no trae memorias del repo de otro en la misma
máquina.

## Límite

Como no se exporta, la memoria no se comparte entre máquinas ni entre colaboradores: cada uno tiene la
suya. El respaldo de `~/.engram/` es responsabilidad de la máquina del usuario.
