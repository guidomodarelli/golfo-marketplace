# Chequeo de permisos: `--check-access`

Para un CLI que llama a servicios cuyos permisos el usuario pide por separado (una capa de autorización que pide un grupo por endpoint, scopes de OAuth, roles). Sin chequeo, el usuario se entera en el paso 4 de 6, con la mitad del alta ya creada.

## Índice

1. [Sondeos sin efectos](#sondeos-sin-efectos)
2. [Clasificar la respuesta](#clasificar-la-respuesta)
3. [Obligatorios, opcionales y lo que no se chequea](#obligatorios-opcionales-y-lo-que-no-se-chequea)
4. [Reporte y exit](#reporte-y-exit)
5. [Antes de la primera alta](#antes-de-la-primera-alta)

## Sondeos sin efectos

- **Un request por permiso, armado para que la API lo rechace sin efectos:** IDs inexistentes (`0`) y cuerpo vacío. La capa de autorización decide **antes** que la API, así que su respuesta dice si el permiso está, aunque la API después habría rechazado el request.
- **En producción solo se sondean lecturas.** Un request inválido de escritura deja errores de validación en los logs de la API de producción, y alguien los va a investigar. Marcar cada sondeo con `is_scope_write`. Si un servicio usa siempre su host de test aunque el entorno sea prod, ese sí se sondea.
- **En paralelo** (`ThreadPoolExecutor(max_workers=len(probes))`): son independientes y de solo lectura.
- `--check-access` no pide el secreto si los sondeos no lo necesitan, y no crea nada.
- En el modo interactivo, una opción del menú principal («Ver qué permisos me faltan») hace lo mismo que el flag: paridad.

## Clasificar la respuesta

| Respuesta | Resultado |
|---|---|
| 403 con la marca de la capa de autorización y la lista de grupos | `missing`: falta el permiso. Parsear los grupos y su link para pedirlos |
| 403 de la capa con la marca de «endpoint sin permiso configurado» | `not-configured`: no hay nada que pedir. Se informa aparte |
| Cualquier otra respuesta (200, 400, 404, 500 o un 403 propio de la API, sin la marca) | `granted`: la capa dejó pasar el request |
| Sin respuesta (timeout, DNS, VPN) | `unverified`: **no se sabe**. Nunca cuenta como permitido |
| Escritura en producción | `skipped`: no se sondea |

```python
import re

FORBIDDEN_STATUS_CODE = 403
AUTHORIZATION_LAYER_MARKER = "[AUTHZ-"                 # la marca que pone la capa en sus 403
AUTHORIZATION_NOT_CONFIGURED_MARKER = "[AUTHZ-1]"
# Cada grupo que nombra el 403: "* group_name (descripción): https://link-para-pedirlo"
GROUP_LINE_PATTERN = re.compile(r"^\* ([a-z0-9_]+) \(([^)]*)\)(?::\s*(\S+))?", re.MULTILINE)

def classify(probe, error):
    if error is None:
        return Result(probe, "granted")
    if error.status_code is None:
        return Result(probe, "unverified", detail="sin respuesta (¿VPN?)")
    body = error.response_body or ""
    if error.status_code != FORBIDDEN_STATUS_CODE or AUTHORIZATION_LAYER_MARKER not in body:
        return Result(probe, "granted")                  # la API contestó: la capa dejó pasar
    if AUTHORIZATION_NOT_CONFIGURED_MARKER in body:
        return Result(probe, "not-configured")
    groups = [Group(name, description, link or None) for name, description, link in GROUP_LINE_PATTERN.findall(body)]
    return Result(probe, "missing", groups=groups)
```

`Result`, `Group` y el error con `status_code` y `response_body` son del proyecto; las marcas, las de su capa de autorización.

## Obligatorios, opcionales y lo que no se chequea

- Cada permiso sabe si sin él no hay alta (`is_required`) o si el flujo sigue con un aviso ([pasos opcionales](remote-actions.md#pasos-opcionales)).
- Un permiso puede ser obligatorio según otra respuesta: el de crear el recurso propio es obligatorio con `--vehicle nuevo` y opcional con `--vehicle fijo`. Con el modo que no lo necesita **se sondea igual, como opcional**, así lo guardado sirve para una corrida posterior que sí lo necesite.
- Lo que no se puede chequear (autenticado por token, servicios que no pasan por la capa) se lista igual, con el motivo, para que se vea que no quedó afuera por olvido.

## Reporte y exit

- Una fila por capacidad, con `✔` / `✖` / `○` (saltado) / `?` (sin verificar).
- Debajo, los grupos a pedir **sin repetir** y con los obligatorios primero. Cada grupo con las capacidades que destraba y si es obligatorio u opcional: un grupo destraba varias capacidades, y para una capacidad alcanza con cualquiera de sus grupos.
- El link para pedirlo, si la respuesta lo trae.
- El entorno y la región en el encabezado del reporte, con el cartel de producción si corresponde (`vivid-visual-output`, `references/terminal.md`, «Entorno peligroso»).
- **Exit `0` solo si no falta nada y todo respondió** (`is_complete = not missing and not unverified`). Un chequeo que no respondió no es un ok.

```text
── 🔐 Permisos · 🇧🇷 BR · 🚨 PROD ─────────────
  ✔ Leer los estados
  ○ Registrar el recurso                       en prod solo se verifican lecturas
  ✖ Buscar si el usuario ya existe             example_read
  ? Leer la preferencia                        sin respuesta (¿VPN?)
── 🔑 Te falta 1 permiso ─────────────────────
  ✖ example_read  opcional: el alta sigue con un aviso
    Para: Buscar si el usuario ya existe, Leer el recurso (resumen)
    🔗 https://example.com/access/new-request?resources=example_read
```

## Antes de la primera alta

- **Automático antes de la primera alta de cada entorno.** Si pasan los obligatorios, se recuerda en las preferencias locales (`verified_access_scopes: {release: {verified_at, vehicle_new: true|false}}`, sin vencimiento) y no se vuelve a chequear. Si falta uno obligatorio, se chequea en cada alta hasta que esté.
- Una corrida que necesita un permiso que no había pasado (`vehicle_new: false` y ahora `--vehicle nuevo`) vuelve a chequear. `--check-access` lo repite a pedido y actualiza lo guardado.
- Un estado guardado con forma desconocida cuenta como no verificado ([native-prompts.md](native-prompts.md#recordar-respuestas)).
- **Producción nunca queda verificada:** sus escrituras no se sondean, así que cada alta en prod chequea las lecturas antes de crear.
- **Si falta un opcional:** con terminal, preguntar si seguir; sin terminal, seguir con un aviso. **Si falta un obligatorio:** no crear nada, mostrar el reporte y salir con error.
