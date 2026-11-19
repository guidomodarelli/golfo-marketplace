---
name: windows-git-bash-agent-gotchas
description: "Gotchas de agentes (Hermes, Claude Code o Codex) que corren comandos en Windows con Git Bash/MSYS, con su arreglo: paths /c/... o /tmp que los programas nativos (git, node, jq, python, gh) no encuentran, flags de Windows con una o dos barras, ~ expandido mal, redirecciones que vacían archivos, CRLF al escribir con Python, wsl.exe que pierde variables, CLIs que no están en el PATH (bats, tailscale), codex exec bloqueado por el sandbox y symlinks que quedan como archivos de texto. Usar siempre que un comando falle raro en Windows con Git Bash (cannot change to, not found, ENOENT con C:\\c\\Users, Invalid argument/option, The system cannot find the path specified), al pasar paths a herramientas nativas o al crear symlinks en Windows."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "agent-tooling"
  tags: "windows, git-bash, msys, paths, wsl, symlinks, crlf, agents"
  command: "/windows-git-bash-agent-gotchas"
---

# Gotchas de agentes en Windows con Git Bash

## Paths y conversión MSYS

- Hermes exporta `MSYS_NO_PATHCONV=1` y `MSYS2_ARG_CONV_EXCL=*`: los programas nativos (`git`, `node`, `jq`, `rg`, `python`) reciben `/c/Users/...` o `/tmp/...` sin traducir y fallan («cannot change to», «not found»). Pasarles paths `C:/...` con barras normales, o correr el script con `env -u MSYS_NO_PATHCONV -u MSYS2_ARG_CONV_EXCL bash <script>` cuando el script (bats, specs) arma los paths por su cuenta.
- `/tmp` de Git Bash no existe para los programas nativos, y `$TMPDIR` dentro del shell puede valer justamente `/tmp`: para un archivo temporal que lee una herramienta nativa, armá el path con `B="$(cygpath -m "$TMPDIR")/<archivo>"` (o `$LOCALAPPDATA/Temp` en forma `C:/...`) y usá ese mismo `$B` al escribirlo y al pasarlo, nunca `"$TMPDIR/<archivo>"` crudo.
- `cygpath -m <path>` convierte un path MSYS a `C:/...` dentro de scripts.
- Con la conversión desactivada, los flags estilo Windows van con una sola barra: `taskkill /PID <n> /T /F`, `icacls <f> /inheritance:r /grant ...`. El truco `//PID` de MSYS acá llega literal y falla («Invalid argument/option», «Invalid parameter "//inheritance:r"»).
- `~` en un argumento (`--passwordfile ~/x`, `--file ~/x`) lo expande bash a `/c/Users/...`, y un CLI nativo de Node lo resuelve como `C:\c\Users\...` (ENOENT): para flags de programas nativos (`bw`, `gh`, `node`) escribir `C:/Users/<user>/...`. La redirección `> ~/archivo` sí funciona porque la hace bash.
- `cmd > archivo` trunca el destino antes de correr `cmd`: si falla, el archivo queda vacío y se pierde lo que tenía (por ejemplo una sesión guardada). Para outputs valiosos, escribir a un temporal y moverlo solo si salió bien: `cmd > f.tmp && mv f.tmp f || rm -f f.tmp`.
- Python en Windows escribe en modo texto con CRLF (`open(p, "w")`), aunque el archivo original tuviera LF: el diff queda «CRLF will be replaced by LF» o el archivo entero cambia. Abrir con `newline=""` (o `"\n"`) al escribir, o normalizar después con `sed -i 's/\r$//' <archivos>`, y confirmar con `file <archivo>` antes de commitear.
- No reescribir a disco texto que vino de la salida capturada de una herramienta del agente (`terminal()['output']` en Hermes): llega con CRLF, y un `open(p, "w")` en modo texto lo convierte en `\r\r\n`, que se ve como líneas en blanco duplicadas (en GitHub rompe tablas y listas). Bajar el contenido con una redirección de bash (`cmd > f`) o con `subprocess` en binario, y si ya pasó por la salida capturada, quitar los `\r` antes de escribir con `newline="\n"`.
- Los programas nativos que reciben un archivo por flag (`gh pr create --body-file`, `python quick_validate.py <dir>`) fallan con `/c/...` («The system cannot find the path specified»): pasarles `$(cygpath -w <path>)` o `C:/...`.

## WSL desde Git Bash

- `wsl.exe -d <distro> -- bash -lc '...'` vuelve a parsear la línea de comandos y las variables del script (`E=x; $E ...`) llegan vacías, así que se ejecutan comandos equivocados en silencio (`clear`, `install` del sistema). Para algo más que un comando suelto, escribir un `.sh` en un temporal de Windows y correrlo con `wsl.exe -d <distro> -- bash /mnt/c/.../script.sh`. Filtrar la salida con `| tr -d '\0'` (wsl.exe a veces la emite en UTF-16).
- Para tests de scripts solo-Linux/macOS, copiar los archivos al filesystem Linux (`/tmp/...`) y hacer `chmod +x` ahí: así corren con permisos POSIX reales y sin depender de cómo WSL monta `C:`.

## PATH

- Algunos CLIs instalados por npm/pnpm no quedan en el PATH de Git Bash (por ejemplo bats): usar `pnpm exec <cli>` o `npx <cli>`.
- Un proceso lanzado por el Programador de tareas (gateway de Hermes, auto-sync) ve solo el PATH de usuario de Windows, no el de Git Bash: los directorios de los CLIs que necesita (`~/bin`, `~/.local/bin`) tienen que estar en el PATH de usuario, o llamarlos por ruta completa.

## Sandbox de Codex

- `codex exec -s read-only` en Windows bloquea todo proceso, incluso lecturas (`CreateProcessAsUserW ... Access is denied`). Usar `--dangerously-bypass-approvals-and-sandbox` solo en un directorio temporal y con prompts de solo lectura.

## Symlinks

- Git en Windows trae `core.symlinks=false` por defecto: un symlink versionado se baja como archivo de texto con la ruta adentro, y ningún agente lo sigue. Para symlinks reales hace falta `core.symlinks=true` y el modo desarrollador de Windows (o un proceso elevado). Para links de configuración del usuario, preferir los que crea su herramienta de dotfiles (si tiene un repo de configuración) en vez de symlinks versionados en cada repo.
- Crear un symlink nativo desde Git Bash: `MSYS=winsymlinks:nativestrict ln -s <destino> <link>` (falla en vez de copiar si no hay permiso).

## Procesos

- Abrir algo en el escritorio del usuario (`cmd /c start "" <url>`, `Start-Process`) desde el agente puede colgarse o fallar, porque el gateway no corre en la sesión interactiva: lanzarlo siempre con `timeout 15 ... < /dev/null` y, además, pasarle el link al usuario en el chat en vez de esperar a que se abra.

- Matar procesos huérfanos por la ruta del ejecutable, nunca por nombre: matar `chrome.exe` o `node.exe` por nombre cierra también el navegador o los servidores del usuario. Ejemplo: los Chromium del navegador de Hermes viven bajo `hermes/tools/chromium-*`.
- `npx playwright install` que no termina (descarga lenta, timeout del tool) deja un `__dirlock` en `%LOCALAPPDATA%/ms-playwright` y un browser a medias sin el marcador `INSTALLATION_COMPLETE`; los tests fallan con «Looks like Playwright was just installed». Recuperar: matar el árbol del instalador por PID, borrar `__dirlock` y la carpeta del browser incompleto, y reinstalar en background con `npx playwright install --only-shell chromium` (headless alcanza para E2E y baja mucho menos). Nunca lanzar un segundo install mientras otro tiene el lock.
- Los navegadores headless con perfil temporal (como el de Hermes) a veces no arrancan (`DevToolsActivePort`) y dejan procesos colgados: para verificar UI desde un agente, preferir Playwright, Lighthouse o Chrome headless por terminal.
