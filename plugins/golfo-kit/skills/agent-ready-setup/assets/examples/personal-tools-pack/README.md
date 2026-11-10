# Ejemplo: pack personal con herramientas, sin firma

Un pack de una persona para sus propios proyectos: trae su CLI (`mytool`), una rule y un script que
escribe la config local la primera vez. No firma nada, porque `security.checks.signature` está apagado
por defecto. La guía completa está en `references/publishing-packs-with-tools.md`; la política, en
`references/pack-tools.md`.

## Publicarlo

1. Copiá esta carpeta a un repositorio propio, por ejemplo `github.com/<vos>/mytools`.
2. Reemplazá las URLs y los `sha256` de `agent-ready-pack.json` por los de tus releases
   (`sha256sum mytool-linux-x64.tar.gz`). Con el placeholder de ceros, la descarga se rechaza.
3. Commiteá y pusheá.

## Usarlo en un proyecto

```bash
agent-ready sources add mytools "git+https://github.com/<vos>/mytools#main"
agent-ready profiles add mytools/dev
agent-ready apply
```

- `sources add` confía en la fuente en tu máquina, porque la agregaste vos.
- `apply` instala `mytool` en el caché de tu usuario y corre `write-local-config.sh`.
- `agent-ready plan` muestra antes qué se permite y qué no, con el motivo.

## Restricciones propias (opcional)

En la config de usuario, para que ningún pack instale otra cosa ni haga `curl | sh`:

```bash
agent-ready config set security.allow.clis mytool --layer user
agent-ready config set security.rules '[{"match": {"type": "script", "contains": "| sh"}, "action": "deny"}]' --layer user
```
