---
name: golfo-npm-package-release
description: "Publica paquetes @golfo en npm con trusted publishing (OIDC desde release.yml): crea un paquete nuevo con staged publish, configura npm trust sin tokens, guía las aprobaciones 2FA por URL sin pedir contraseñas ni OTP, sigue el run de release, destraba releases que fallan en CI (ENEEDAUTH, --retry-ci, herramientas faltantes en release.yml) y encadena el release de una librería con la app que la consume (golfo-rp, Vercel). Usar siempre que pidan publicar, sacar una versión o un release de un paquete o repo golfo (@golfo/lint, @golfo/ui, @golfo/rp, apps con golfo-rp), configurar npm trust o staged publishing, o arreglar un release de npm que falló."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "release"
  tags: "npm, release, trusted-publishing, oidc, npm-trust, staged-publish, golfo-rp, ci"
  command: "/golfo-npm-package-release"
---

# Publicar paquetes @golfo en npm (trusted publishing)

Sirve para publicar por primera vez un paquete golfo (`@golfo/lint`, `@golfo/rp`, `@golfo/ui`...) o configurar trusted publishing (`npm trust`, OIDC, staged publish). Los paquetes golfo se publican desde el workflow `release.yml` de su repo con OIDC (sin tokens). El release normal lo hace el propio repo (`npm run create-version`, ver su `AGENTS.md`); esta skill cubre lo que va antes (crear el paquete en npm y atarlo al workflow) y cómo destrabar un release normal que falla en CI.

## Regla de rol

Hacelo vos. No le digas al usuario «publicalo vos»: él solo pone el código de 2FA. Nunca pidas ni tipees contraseñas u OTP. Si el usuario ofrece un archivo con su contraseña maestra o exportar el gestor de contraseñas para leer el OTP, no lo uses y decilo en una línea: deja todos sus secretos en texto plano. Ofrecé en cambio registrar una passkey o llave de seguridad en npm (aprobar pasa a ser un toque en el teléfono) y recordá que son solo las aprobaciones del bootstrap: después se publica por OIDC sin 2FA.

Aprobar una URL de npm en el Chrome del usuario, no en un navegador propio del agente:

- Un navegador headless o con perfil descartable (el de Hermes, Playwright, el panel integrado de Claude) queda en el desafío de Cloudflare de `npmjs.com/login`, y ese desafío no se resuelve en nombre del usuario.
- El Chrome del usuario pasa Cloudflare solo y suele tener la sesión de npm abierta. Abrir la URL ahí con la herramienta que maneje su navegador real: Claude in Chrome en Claude Code, el plugin `chrome` en Codex, `computer_use` en Hermes (desde el gateway, `cua-driver call`: `clipboard_write` con la URL, `click` en la barra de direcciones con `delivery_mode: foreground`, `ctrl+v` y `return`). Si navega la pestaña activa, avisarle al usuario cuál pisaste.
- Verificar con una captura. Si queda en «Enter a One-time Password», frenar ahí y pedirle al usuario que ponga el código ya, porque la URL vence en minutos. Si npm no pide OTP, la aprobación es un botón de la página, que sí se puede clickear.
- Si no hay forma de manejar su navegador, mandarle la URL al usuario como dice abajo.

## Cómo correr cada comando que pide 2FA

Corré cada comando que autentica en background con `--auth-type=web` (con pseudoterminal si el agente lo ofrece, como `pty=true` en Hermes), esperá unos segundos y leé su salida (`process_manage log` en Hermes, la salida de la tarea en background en Claude Code): imprime `https://www.npmjs.com/login?...` o `https://www.npmjs.com/auth/cli/<id>`. Pasale ESA URL al usuario, esperá su «listo» y confirmá en el log que el proceso salió bien antes de seguir. Cada URL vale para una sola operación: login, publish, trust, reject y `trust list` piden cada una la suya. Si el usuario dice «dale» pero el log sigue esperando, la aprobación no se hizo: reenviá el mismo link. Las URLs vencen en pocos minutos (el proceso sale con `E404 ... /-/v1/done?authId`, o el usuario dice que expiró aunque el proceso siga vivo): matá el proceso, relanzalo y mandá la URL nueva en un mensaje corto apenas aparezca (puede tardar unos 15 s en imprimirse), sin hacer otras tareas antes de responder.

## Procedimiento para un paquete que todavía no existe

1. Chequeo: `npm view <pkg> version` (404 = no existe) y `npm whoami` (401 = token vencido).
2. Login: `npm login --auth-type=web --registry=https://registry.npmjs.org/`.
3. Crear el paquete con staged publishing: en un dir del scratch, un `package.json` stub (`name`, versión prerelease tipo `0.0.0-bootstrap.0`, `description` de placeholder, `license`, `repository` del repo real, `publishConfig.access: public`) y `npm stage publish --tag stage --access public`. No hace falta 2FA. No uses `npm publish` con versión `0.0.0-stage`: npm la reserva para el placeholder y da 403. Mientras solo haya staged, `npm view` sigue en 404: es normal.
4. Probar el trust: `npm trust github <pkg> --repo guidomodarelli/<repo> --file release.yml --allow-publish --dry-run`. Después corré lo mismo sin `--dry-run`, con `--yes --auth-type=web`. Pide 2FA y queda con permisos `publish` y `stage publish`.
5. Nunca apruebes el stub (`npm stage approve`): publicaría una versión basura. **No lo rechaces antes de la primera publicación real**: si el paquete solo tiene ese staged, `npm stage reject` deja el paquete sin existir y el trust deja de funcionar (el release por OIDC falla con `ENEEDAUTH`). Rechazalo (`npm stage reject <stage-id>`, id de `npm stage list <pkg>`, pide 2FA) recién después de que el workflow publicó la versión real. No verifiques el trust con `npm trust list`: pide otro 2FA y sus URLs vencen antes de que el usuario las abra. La verificación es el primer release por OIDC.
6. Publicar la primera versión real por el workflow dentro de los 2 días, o la config de trust vence y hay que crearla de nuevo. Por eso los pasos 3 y 4 se hacen cuando el PR que agrega el paquete y su `release.yml` está listo para mergear, no cuando se decide publicar: si el código todavía no existe, el trust vence antes. Avisale al usuario la fecha límite. Si el PR que motivaba la publicación se atrasa, publicá la versión actual de `main` antes del vencimiento. Desde el checkout principal en `main` limpio: `npm run create-version -- --ci --minor --dry-run`, revisá el plan y corré lo mismo sin `--dry-run` (bump, tag, push y dispatch de `release.yml`). `create-version -l` no sirve: con `publication.authentication: "oidc"` se niega a publicar fuera de CI.
7. Seguir el run (`gh run list -w release.yml -L 1`, `gh run watch <id> --exit-status`). El éxito se confirma con la línea `+ <pkg>@<versión>` del log y con `npm view <pkg>@<versión> version --prefer-online`: el documento público del registry tarda en actualizarse y durante un rato sigue mostrando solo `0.0.0-stage` como `latest`.

## Release normal de un paquete que ya existe

1. Elegí el bump según el AGENTS.md del repo, no según cómo lo nombró el usuario: en 0.x, una regla nueva que puede hacer fallar un proyecto que hoy pasa, o un `engines` más alto, sube el minor (`--minor`); solo arreglos sin efecto en consumidores van como `--patch`. Si cambia el número que el usuario dijo, explicalo en el reporte.
2. Desde `main` limpio y al día (`git pull --ff-only` después de mergear: si el merge todavía no llegó, `create-version` no hace nada útil): `npm run create-version -- --ci --<tipo> --dry-run`, revisá el plan y corré sin `--dry-run`. Seguí el run como en el paso 7 de arriba.
3. **Cada herramienta que use `npm run ci` tiene que instalarse también en `release.yml`**, no solo en `ci.yml`: el release corre `npm run ci` antes de publicar. Al cambiar el typecheck o el lint a otra herramienta (p. ej. `bun check`), agregá su setup (por SHA) a los dos workflows en el mismo PR.
4. **`--retry-ci vX.Y.Z` reusa el `release.yml` del tag**, no el de `main`: si lo que falló es el workflow, arreglarlo en `main` no rescata ese tag. No borres ni muevas el tag publicado: mergeá el arreglo con una entrada en `[Unreleased]` del CHANGELOG (`create-version` exige entradas nuevas) y sacá el siguiente patch con `npm run create-version -- --ci --patch --skip-unpublished`. Avisá que el tag anterior quedó sin paquete en npm.

## Release de una app con `golfo-rp` (sin paquete npm, p. ej. TuTribu → Vercel)

1. Antes del bump, mergeá los PRs abiertos cuyas entradas de `[Unreleased]` tienen que salir en esta versión (CI verde y review limpia): `create-version` solo publica lo que ya está en `origin/main`. Mirá la estrategia de merge permitida (`gh api repos/<owner>/<repo> --jq '{s:.allow_squash_merge,m:.allow_merge_commit}'`) y usá `--merge` si squash está deshabilitado.
2. Desde `main` limpio y al día: `pnpm create-version --<tipo> --dry-run`, revisá el plan y corré `pnpm create-version --<tipo> --ci` (bump, tag, push y dispatch de `release.yml`).
3. Seguí el run sin bloquear el terminal. El release corre los checks completos y el deploy, y tarda unos 25-30 min. Eso supera el timeout de un comando en foreground, así que `gh run watch` directo se corta. Usá un loop acotado a menos de 6 min por llamada y repetilo hasta que termine: `for i in $(seq 1 12); do s=$(gh run view <id> -R <owner>/<repo> --json status,conclusion -q '.status+" "+.conclusion'); case "$s" in completed*) break;; esac; sleep 25; done; echo "$s"`. Los agentes cortan el foreground (Hermes a unos 420 s aunque pidas un `timeout` mayor, Claude Code a 10 min) y un loop más largo se pierde entero sin imprimir nada. La otra opción es el watch en background con aviso.
4. El éxito es `conclusion=success` del run más el deploy `Ready` con los alias de producción. Sacá la URL y el alias del log sin bajarlo entero: `gh run view <id> --log | grep -E 'Production|Aliased'`. Si hace falta, confirmá con `vercel inspect <deployment-url>` desde un dir cualquiera. No hay GitHub Release: `gh release view vX.Y.Z` devuelve «not found» y es normal.
5. Si el release de un tag falla por el workflow (p. ej. una herramienta que `pnpm run ci` necesita y `release.yml` no instala), arreglá `release.yml` en `main` por PR y reenviá el mismo tag con el workflow de `main`: `gh workflow run release.yml --ref main -f version=X.Y.Z -f tag=vX.Y.Z -f sha=$(git rev-parse 'vX.Y.Z^{commit}')`. La verificación de identidad sigue exigiendo tag, SHA y ancestro de `main`, así que no hace falta otro bump.
6. Los repos golfo (TuTribu, golfo-ui) no permiten squash: mergeá con `gh pr merge --merge --delete-branch --match-head-commit <head>`. Ante la duda, mirá la estrategia permitida como en el paso 1.
7. Las env vars de Vercel cambiadas antes del release quedan aplicadas recién con ese deploy: mencionalo en el reporte si el usuario acababa de cargar alguna.

## Release encadenado: librería → app que la consume

Cuando el pedido es «sacá una versión» y hay arreglos pendientes en la librería y en la app, preguntá con opciones (`clarify`, `AskUserQuestion` o en texto) qué repo publicar (librería, app, o las dos encadenadas). No lo adivines: la cadena completa tarda y cambia qué entra en cada versión. Orden de la cadena:

1. Mergeá el PR de la librería (review limpia + CI verde) y corré su release (`pnpm create-version --ci --patch`).
2. Confirmá la publicación con la línea `+ <pkg>@<versión>` del log del run y con `curl -s https://registry.npmjs.org/<pkg-url-encoded>` (`dist-tags`): `npm view <pkg>@<versión>` puede dar 404 unos minutos después de publicar.
3. En la app, en la rama de los arreglos que dependen de la librería: `git rebase origin/main` (en un conflicto de `CHANGELOG.md` conservá las entradas de los dos lados dentro de `[Unreleased]`), `pnpm add <pkg>@^<versión>` en un commit propio, entrada de CHANGELOG para el usuario, PR y merge.
4. Release de la app como en la sección anterior.

## Antes de mergear o publicar con CI en rojo

Si falla un job, leé el log (`gh run view <run> --job <job> --log-failed`, sin los códigos ANSI) antes de tocar código. Si el fallo es un test ajeno al diff (animación muestreada por frames, timer que dispara después del teardown de jsdom) y todos los tests pasaron, confirmá que también falla a veces en `main` (`--repeat-each` sobre el build de `main`) y relanzá solo lo fallido con `gh run rerun <run> --failed`. Mencioná el flake en el reporte; no lo arregles dentro del PR.

## `main` abierto en otro worktree

Si `git switch main` falla porque `main` está en otro worktree, no lo muevas: corré el release desde ese worktree (`git status` limpio, `git pull --ff-only`, `pnpm install --frozen-lockfile`, después `create-version`). Dejá el checkout principal en `origin/main` sin rama (detached) y avisá al usuario dónde quedó `main`.

## Si el release por OIDC falla con `ENEEDAUTH`

El trust no existe para ese paquete (p. ej. se rechazó el stub y el paquete dejó de existir). El tag ya está en origin: no hagas otro bump. Stageá otro stub (`0.0.0-bootstrap.<n+1>`), recreá el trust (paso 4; si devuelve un id nuevo, el viejo ya no estaba) y reenviá el mismo tag con `npm run create-version -- --retry-ci vX.Y.Z`.

## Requisitos

npm CLI >= 11.15 para `npm trust` y `npm stage`; 2FA activo en la cuenta.
