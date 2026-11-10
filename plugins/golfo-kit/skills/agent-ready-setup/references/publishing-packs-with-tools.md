# Publicar un pack con herramientas

Cómo publicar un profile pack que, además de rules y skills, trae CLIs, servidores MCP o scripts, y
cómo lo adopta un proyecto personal o una empresa. Leer al armar un pack así o al explicar cómo
adoptarlo. El formato de las declaraciones y la política que decide si cada herramienta corre están en
[pack-tools.md](pack-tools.md); el contrato de los packs, en
[profiles-and-lockfile.md](profiles-and-lockfile.md) (sección «Profile packs»).

## Contenido

1. Qué cambia entre un pack personal y uno corporativo
2. Armar el pack
3. Pack personal
4. Pack corporativo firmado
5. Verificar antes de publicar

## 1. Qué cambia entre un pack personal y uno corporativo

Las herramientas, el catálogo y la política son los mismos. Cambia quién confía en la fuente y si se
exige firma:

| | Personal | Corporativo |
|---|---|---|
| Confianza en la fuente | `agent-ready sources add` la aprueba en la máquina de quien la agrega | `security.trustedSources` en la config de organización |
| Firma | apagada (`security.checks.signature: false`, el default) | exigida, con las claves en `security.signers` |
| Quién fija la política | cada persona, en su config de usuario | la organización, con `locked` para que nadie la afloje |
| Ejemplo | `assets/examples/personal-tools-pack/` | `assets/examples/corporate-signed-pack/` |

Todo es opcional: un pack sin herramientas sigue funcionando igual, y cada check se apaga por separado.

## 2. Armar el pack

- **CLIs.** Preferí artefactos de release con `sha256` por plataforma. Un paquete de npm o pip también
  necesita su `sha256`, salvo que la política lo apague. brew y winget nunca se ejecutan.
- **Servidores MCP.** Los secretos van por referencia (`${ACME_TOKEN}`) y nunca con su valor: el
  catálogo se publica.
- **Scripts.** Cada script declara su `event` (`install`, `post-apply` o `session-start`), su
  intérprete y un `timeoutSeconds`.
  - Tienen que ser idempotentes: `post-apply` corre en cada apply.
  - No tienen que pedir input: corren sin terminal.
  - Tienen que usar las variables `AGENT_READY_PROJECT_ROOT` y `AGENT_READY_PACK_ROOT` en vez de
    suponer el directorio actual.
  - `session-start` está apagado por defecto: corre en cada inicio de sesión.
- **Nombres propios.** Usá nombres propios para las rules, skills, CLIs y servidores. Un destino que ya
  publica Golfo u otro pack hace fallar la resolución.

## 3. Pack personal

1. Publicá el pack en un repositorio propio, sin firmar nada.
2. En cada proyecto:

   ```bash
   agent-ready sources add mytools "git+https://github.com/<vos>/mytools#main"
   agent-ready profiles add mytools/dev
   agent-ready apply
   ```

3. `sources add` confía en la fuente en tu máquina. Un compañero que clona el repositorio la aprueba una
   vez con `agent-ready trust add mytools`.
4. Si querés límites propios, ponelos en tu config de usuario: `security.allow.clis`, `security.deny.*`
   o `security.rules`. El README del ejemplo muestra cómo permitir solo `mytool` y prohibir `| sh`.

## 4. Pack corporativo firmado

1. **Firmar los releases.** El equipo dueño del pack firma con una clave SSH de releases. Puede firmar
   cada commit (`git commit -S`) o los tags (`git tag -s`). Un tag anotado y firmado vale por el commit
   al que apunta, aunque el commit no esté firmado. Las firmas GPG no cuentan.
2. **Fijar la versión.** Cada repositorio declara la fuente en un tag de release (`#v2.4.0`). Con
   `updates.mode: auto`, la fuente sigue su ref y cada commit nuevo tiene que estar firmado, o tener un
   tag firmado, para ejecutar algo.
3. **Distribuir la política.** La config de organización (`organization-config.json` del ejemplo) se
   instala en cada máquina; las rutas por sistema están en [configuration.md](configuration.md),
   sección 3. Hace tres cosas:
   - confía en el origen del pack, así que nadie corre `trust add`;
   - exige la firma con la clave del equipo;
   - bloquea con `locked` los checks y las claves, para que ni el usuario ni un repositorio los aflojen.
4. **Rotar una clave.** Sumá la clave nueva a `security.signers` y distribuí la config. Quitá la vieja
   cuando ningún repositorio quede fijado a un release firmado con ella.

Sin config de organización, cada persona puede exigir lo mismo en su config de usuario. La única
diferencia es que nadie se lo bloquea:

```bash
agent-ready trust add acme-platform --signer platform-release.pub
agent-ready config set security.checks.signature true --layer user
```

## 5. Verificar antes de publicar

- Declará el pack con `path:` en un repositorio de prueba. Para un pack corporativo, apagá
  `security.checks.signature` en el proyecto de prueba, porque una fuente `path:` no tiene revisión
  propia que verificar. Después corré `agent-ready plan`: cada herramienta aparece `allowed` o `blocked`
  con su motivo, y un error del catálogo nombra el campo.
- Corré `agent-ready apply` y mirá que las rules y skills se proyecten, que los CLIs se instalen y que
  los scripts terminen bien.
- Para un pack firmado, publicá un tag firmado y corré `agent-ready plan` con la config de organización
  instalada: las herramientas tienen que quedar `allowed`.
