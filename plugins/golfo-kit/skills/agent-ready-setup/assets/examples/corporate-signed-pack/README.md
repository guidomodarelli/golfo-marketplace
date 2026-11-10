# Ejemplo: pack corporativo firmado

El pack de una empresa con su CLI (`acme`, un paquete de npm con `sha256`), un servidor MCP de
documentación y un script que avisa si falta el login. La empresa exige que cada release esté firmado
con la clave SSH del equipo de plataforma, y lo hace cumplir con una config de organización. La guía
completa está en `references/publishing-packs-with-tools.md`; la política, en `references/pack-tools.md`.

## Publicar un release firmado

El equipo de plataforma firma los tags con su clave SSH de releases:

```bash
git config gpg.format ssh
git config user.signingkey ~/.ssh/platform-release.pub
git tag -s v2.4.0 -m "acme-platform 2.4.0"
git push origin v2.4.0
```

Un tag firmado vale por el commit al que apunta, aunque el commit no esté firmado. Cada repositorio
declara la fuente fijada a ese tag:

```json
{
  "profiles": ["acme-platform/platform"],
  "sources": {
    "packs": [
      { "name": "acme-platform", "source": "git+https://git.acme.example/platform/agent-ready-pack#v2.4.0" }
    ]
  }
}
```

## Distribuir la política

`organization-config.json` es la config de organización que se instala en cada máquina, por ejemplo
por MDM, en `/etc/agent-ready-setup/config.json` (Linux), `/Library/Application Support/agent-ready-setup/config.json`
(macOS) o `%ProgramData%\agent-ready-setup\config.json` (Windows). Antes de distribuirla, reemplazá
`key` por la línea del `.pub` de la clave de releases.

- Exige la firma (`security.checks.signature`) y confía en el origen del pack. Los desarrolladores no
  tienen que correr `agent-ready trust add`.
- `locked` impide que el usuario o un repositorio apaguen los checks o sumen otras claves.
- La regla `deny` bloquea cualquier script de cualquier pack que pipee a `sh`.

Con eso, un commit nuevo sin firma ni tag firmado no ejecuta nada: `agent-ready plan` lo muestra
bloqueado con el motivo, y las rules y skills del pack se proyectan igual.
