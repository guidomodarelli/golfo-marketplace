# Acciones remotas: crear, cambiar y dejar registro

Para un CLI que crea o cambia recursos llamando a APIs (usuarios de prueba, entornos, registros). Salió de un CLI real en Python 3.9+ sin dependencias, con un wrapper de bash, que crea datos de prueba encadenando varias APIs. Los ejemplos son genéricos: `ApiError` tiene `status_code` (`None` sin respuesta), `response_body` y `attempts`.

## Índice

1. [Antes del primer efecto](#antes-del-primer-efecto)
2. [Valores de una fuente viva](#valores-de-una-fuente-viva)
3. [Pasos opcionales](#pasos-opcionales)
4. [Releer después de cambiar](#releer-después-de-cambiar)
5. [Reintentos](#reintentos)
6. [Errores sin datos sensibles](#errores-sin-datos-sensibles)
7. [Registro de lo creado](#registro-de-lo-creado)
8. [`--dry-run` y `--status`](#--dry-run-y---status)
9. [Datos generados por default](#datos-generados-por-default)

## Antes del primer efecto

- **En el wizard, mostrar el plan y confirmar.** Si se preguntó algo y la acción crea o cambia algo, mostrar el mismo plan que `--dry-run` y confirmar («¿Creo …?», default «sí» si no es peligroso; si lo es, la confirmación fuerte de la fila «Acción peligrosa» del `SKILL.md`). Con «no»: «No se creó nada», exit 0. Con todos los datos por flag no se confirma: el usuario ya fue explícito.
- **Buscar si ya existe.** Consultar si el recurso equivalente ya existe. Si existe, cortar con sus IDs en vez de crear un duplicado. Si la búsqueda no está permitida (403), avisar y seguir.
- **Ordenar los pasos para no dejar huérfanos.** Entre dos pasos con efectos, va primero el que más probablemente falla, si el otro, quedando solo, sería un huérfano. Ejemplo: crear el recurso secundario antes del registro principal, así un fallo no deja el principal a medias.
- **No sustituir en silencio.** Si lo pedido explícitamente no se puede hacer y hay una alternativa (un recurso fijo en vez de uno nuevo), no usarla por cuenta propia. Con terminal se pregunta, **con default «no»**. Sin terminal, o si dice que no, se corta antes del primer efecto, y el error nombra el flag que pide la alternativa explícitamente (`--vehicle fijo`). Si se acepta, el comando equivalente lleva la alternativa.
- **Entorno peligroso.** Elegir producción muestra el cartel y pide escribir el nombre (`prod`). Cualquier otra respuesta (Enter, `s`, `sí`) no crea nada y lo dice («No se confirmó prod: no se creó nada»). Sin terminal y sin `--confirm-prod`: exit 2 **antes de llamar a cualquier API**. `--list`, `--dry-run`, `--history` y `--check-access` no lo piden, porque no crean nada. Después, el entorno queda en el encabezado del resumen y de cada reporte (`🚨 PROD · producción`), para que se vea dónde se creó. Cómo se ve el cartel: `vivid-visual-output` (`references/terminal.md`, «Entorno peligroso»).
- **Permisos:** si el CLI depende de permisos que se piden por separado, chequearlos antes de la primera alta ([preflight.md](preflight.md)).

## Valores de una fuente viva

Un valor con la forma correcta que no existe en la fuente (estados, regiones, versiones) se valida contra ella **antes del primer efecto**. El error sugiere los parecidos y el comando para ver todos:

```python
import difflib

SUGGESTION_COUNT = 3
SUGGESTION_CUTOFF = 0.5

def unknown_value_message(value, valid_values, region, scope):
    suggestions = difflib.get_close_matches(value, valid_values, n=SUGGESTION_COUNT, cutoff=SUGGESTION_CUTOFF)
    hint = f" ¿Quisiste decir {' o '.join(suggestions)}?" if suggestions else ""
    return f"{value} no existe en {region} ({scope}).{hint} Para ver los {len(valid_values)} valores: tool --region {region} --list"
```

```text
✖ inactve no existe en BR (release). ¿Quisiste decir inactive? Para ver los 23 valores: tool --region BR --list
```

- `--list` muestra los valores y termina, sin efectos y sin pedir el secreto si la lectura no lo necesita.
- No copiar esa lista en el código: un valor nuevo en la fuente se puede pedir sin cambiar el CLI.

## Pasos opcionales

Clasificar cada paso en **obligatorio** (sin él no hay resultado) u **opcional** (el resultado sirve igual).

- Si un opcional falla, avisar en una línea qué no se hizo, por qué (con el permiso que falta, si la respuesta lo nombra) y cómo completarlo después. Seguir, y marcarlo como pendiente en el resumen y en el registro. El exit sigue siendo 0 si lo obligatorio salió bien.
- **Antes** de crear el recurso principal, un paso opcional tolera solo su error esperado (por ejemplo, 403): cualquier otro se propaga, porque todavía se puede cortar sin dejar nada a medias.
- **Después** de crearlo (el punto de no retorno), un paso opcional tolera **cualquier** error con un aviso: cortar ahí deja el alta a medias sin ganar nada. El resumen y el registro lo marcan pendiente, con el comando para completarlo. Lo mismo vale para un opcional que agotó sus reintentos.
- Si se sabe antes de actuar que un opcional va a fallar (por el chequeo de permisos), con terminal preguntar si seguir y sin terminal seguir con un aviso.

```python
FORBIDDEN_STATUS_CODE = 403

def forbidden_error(call):
    """Corre `call`. Devuelve el error si fue 403; cualquier otro error se propaga."""
    try:
        call()
    except ApiError as caught_error:
        if caught_error.status_code != FORBIDDEN_STATUS_CODE:
            raise
        return caught_error
    return None
```

## Releer después de cambiar

Una API puede responder 5xx y aplicar el cambio igual, o responder 200 y dejar el recurso en otro estado. Después de cada cambio remoto que el paso siguiente da por hecho, leer el estado real:

- Falló pero quedó aplicado: seguir con un aviso («respondió HTTP 500 pero quedó aplicado»).
- Respondió bien pero quedó en otro estado: detenerse con un error que diga qué se pidió y en qué quedó.
- Falló y no se aplicó: propagar el error original.

```python
def transition_with_verification(client, resource, target):
    update_error = None
    try:
        client.change_status(resource, target)
    except ApiError as caught_error:
        update_error = caught_error
    actual = client.get_status(resource)
    if actual == target:
        return f"El cambio a {target} respondió HTTP {update_error.status_code} pero quedó aplicado." if update_error else None
    if update_error:
        raise update_error
    raise FlowError(f"Flow:transition: se pidió {target} y {resource.id} quedó en {actual}.")
```

Si para llegar a un estado hay varios caminos, preferir el que **no pasa por estados con efectos laterales** (bloqueado, deshabilitado, eliminado), aunque sea más largo. Usar uno de esos solo si no queda otro, y avisarlo en el plan y antes de moverlo.

## Reintentos

Se reintenta solo lo pasajero: sin respuesta (red, timeout), 429 o 5xx, con esperas crecientes y tope (1, 2 y 4 s, en una constante). No se reintenta:

- un 4xx salvo 429, un request que no se pudo armar ni una respuesta 2xx con forma inesperada: otro intento no cambia nada;
- un request que no es idempotente. Se reintenta un GET, o un PUT que deja el mismo estado. Un POST, solo si el error prueba que no llegó a la API (el 503 del gateway mientras la API levanta);
- un error que ya agotó su espera: no vuelve a entrar en otro ciclo.

Las esperas se inyectan (`sleep`) para que los tests verifiquen la secuencia sin esperar. El error guarda cuántas veces se mandó (`attempts`) y lo conserva al envolverse en otro (`cause`), así el mensaje lo dice: «la API no levantó en 120 s (8 intentos). Probá de nuevo en un rato».

```python
import time

TOO_MANY_REQUESTS_STATUS_CODE = 429
SERVER_ERROR_STATUS_CODE = 500
RETRY_DELAYS_SECONDS = (1, 2, 4)

def is_transient(error) -> bool:
    if isinstance(error, (InvalidRequestError, UnexpectedResponseError, UpstreamAsleepError)):
        return False
    return (
        error.status_code is None
        or error.status_code == TOO_MANY_REQUESTS_STATUS_CODE
        or error.status_code >= SERVER_ERROR_STATUS_CODE
    )

def request_with_retries(client, delays_seconds, *request_arguments, sleep=time.sleep):
    """Solo para requests idempotentes."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return client.request(*request_arguments)
        except ApiError as request_error:
            request_error.attempts = attempt
            if attempt > len(delays_seconds) or not is_transient(request_error):
                raise
        sleep(delays_seconds[attempt - 1])
```

`UpstreamAsleepError` es el que ya agotó la espera de una API que levanta: no se reintenta de nuevo.

## Errores sin datos sensibles

El secreto que **entra** (token por flag, variable o prompt) nunca se muestra ([SKILL.md](../SKILL.md#paridad)). Lo mismo vale para lo sensible que **genera** la API, como la contraseña de un usuario de prueba, y para lo que se filtra por una excepción de la librería HTTP.

- Una respuesta con forma inesperada se informa con método, URL y qué se esperaba, **sin el cuerpo**, si el endpoint devuelve credenciales o PII. En los errores HTTP, el cuerpo va recortado (los primeros N caracteres, en una constante) y solo en endpoints que no devuelven datos sensibles.
- **Una excepción de la librería HTTP puede traer el valor de una cabecera (el token) o de la URL.** `http.client` (y por lo tanto `urllib`) rechaza una cabecera con un carácter inválido, como un `\n` pegado al final del token, con un `ValueError` que incluye el valor. Envolverla en un error propio **sin el mensaje original** (`raise ... from None`), con operación, método, URL sin parámetros sensibles y status. El error propio nunca guarda las cabeceras.

```python
try:
    response = opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
except ValueError:
    # http.client rechaza cabeceras inválidas incluyendo su valor (puede ser el token): no se propaga el mensaje.
    raise InvalidRequestError(operation, method, url, None, "request inválido (cabecera o URL mal formada)") from None
```

- Lo que el CLI guarda con datos sensibles generados va con permisos `600`, fuera del repo, y el resumen dice dónde quedó.

## Registro de lo creado

El resumen final se pierde al limpiar la terminal, y con él el ID, el usuario y la contraseña del recurso de prueba. Cuando el alta se corta a la mitad, sin registro se empieza de cero con otro usuario.

- **Un archivo por alta** (Markdown legible: es para personas) más un **índice** con una fila por alta. Nombre: `<fecha>_<hora>_<región>-<entorno>_<id>.md`. Si dos altas caen en el mismo segundo, la segunda lleva `-2`, la tercera `-3`.
- **Dónde:** fuera del repo, para que nunca se commitee (`~/.<herramienta>/<recursos>`). Se cambia con una variable de entorno (`TOOL_OUTPUT_DIR`, que además usan los tests) o con `--output-dir`. `--no-save` lo apaga.
- **Permisos `600` y directorio `700`** si el registro trae datos sensibles generados.
- **Escritura atómica y lock entre procesos** mientras se elige el nombre libre, se escribe el archivo y se suma la fila al índice. Sin lock, dos corridas que terminan a la vez leen el mismo índice y una pisa la fila de la otra, aunque cada escritura sea atómica. `fcntl.flock` vale entre procesos y entre hilos (cada uno abre su descriptor). `fcntl` no existe en Windows: ahí, `msvcrt.locking`, o documentar que no se soporta.
- **El índice se reescribe sin romper lo que el usuario agregó:** solo se toca la tabla. El título, las notas y las filas que no se pueden parsear quedan en su lugar.
- **Celdas escapadas:** `\` → `\\`, `|` → `\|` y los saltos de línea pasan a espacio; al releer se revierte. Si no, un nickname o un error con `|` rompe la fila y `--history` deja de leerla. Las columnas se alinean al ancho visible, con emojis y banderas de 2 celdas (`display_width` del kit de Python de `vivid-visual-output`).
- **Contenido de cada registro:** el resultado (`✔ creado · <estado>` o `▲ incompleto: <qué cortó>` con el último estado conocido); los datos del resumen, con los que se copian (mail, contraseña) en bloques de código; el camino recorrido; «Para seguir con el mismo recurso» (el comando que retoma con lo ya creado, si quedó incompleta) y «Para crear otro igual» (el comando equivalente, sin el secreto).
- **Las altas incompletas también se guardan**, con los datos **reales** que llegaron a existir (el ID del usuario creado), no con los pedidos.
- **Guardar es una comodidad:** si falla, avisar con la ruta y seguir. El alta ya terminó y el exit no cambia por eso.

```python
import fcntl, os, tempfile
from contextlib import contextmanager

RECORD_FILE_MODE = 0o600
RECORD_DIRECTORY_MODE = 0o700
INDEX_FILE_NAME = "index.md"
LOCK_FILE_NAME = ".lock"
INDEX_TITLE = "# Altas"
INDEX_HEADER = ["Fecha", "Entorno", "ID", "Resultado", "Archivo"]

@contextmanager
def directory_lock(directory):
    descriptor = os.open(os.path.join(directory, LOCK_FILE_NAME), os.O_RDWR | os.O_CREAT, RECORD_FILE_MODE)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)                       # cerrar el descriptor libera el lock

def write_atomically(path, text):
    descriptor, temporary_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(text)
        os.chmod(temporary_path, RECORD_FILE_MODE)
        os.replace(temporary_path, path)
    except BaseException:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise

def free_name(directory, base_name):
    candidate, suffix = f"{base_name}.md", 1
    while os.path.exists(os.path.join(directory, candidate)):
        suffix += 1
        candidate = f"{base_name}-{suffix}.md"
    return candidate

def escape_table_cell(value) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")

def split_table_row(line):
    """Celdas de una fila `| a | b |`, con los escapes revertidos, o None si la línea no es una fila."""
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    cells, current, characters = [], "", iter(stripped[1:])
    for character in characters:
        if character == "\\":
            current += next(characters, "")
        elif character == "|":
            cells.append(current.strip())
            current = ""
        else:
            current += character
    return cells

def is_separator(cells) -> bool:
    return all(cell and set(cell) <= set("-:") for cell in cells)

def with_row(lines, new_cells):
    """Devuelve las líneas del índice con la fila nueva. Fuera de la tabla, todo queda como estaba."""
    header_index = next((index for index, line in enumerate(lines) if split_table_row(line) == INDEX_HEADER), None)
    if header_index is None:
        before, block, after = list(lines), [], []
    else:
        end = header_index + 1
        while end < len(lines) and lines[end].strip().startswith("|"):
            end += 1
        before, block, after = lines[:header_index], lines[header_index + 1:end], lines[end:]
    entries = []                                   # filas de datos (listas) o líneas que no se parsean (texto)
    for line in block:
        cells = split_table_row(line)
        if cells is not None and is_separator(cells):
            continue
        entries.append(cells if cells is not None and len(cells) == len(INDEX_HEADER) else line)
    entries.append([str(cell) for cell in new_cells])
    rows = [INDEX_HEADER, *(entry for entry in entries if isinstance(entry, list))]
    escaped_rows = [[escape_table_cell(cell) for cell in row] for row in rows]
    widths = [max(display_width(row[column]) for row in escaped_rows) for column in range(len(INDEX_HEADER))]

    def render(row):
        return "| " + " | ".join(cell + " " * (widths[column] - display_width(cell)) for column, cell in enumerate(row)) + " |"

    data_rows = iter(escaped_rows[1:])
    table = [render(escaped_rows[0]), "| " + " | ".join("-" * width for width in widths) + " |"]
    table += [render(next(data_rows)) if isinstance(entry, list) else entry for entry in entries]
    if before and before[-1].strip():
        before = [*before, ""]
    return [*before, *table, *after]

def save_record(directory, base_name, markdown, index_cells):
    """Guarda un alta y su fila del índice, y devuelve la ruta del registro."""
    os.makedirs(directory, mode=RECORD_DIRECTORY_MODE, exist_ok=True)
    os.chmod(directory, RECORD_DIRECTORY_MODE)
    with directory_lock(directory):
        file_name = free_name(directory, base_name)
        write_atomically(os.path.join(directory, file_name), markdown)
        index_path = os.path.join(directory, INDEX_FILE_NAME)
        try:
            with open(index_path, encoding="utf-8") as index_file:
                lines = index_file.read().splitlines()
        except FileNotFoundError:
            lines = [INDEX_TITLE, ""]
        write_atomically(index_path, "\n".join(with_row(lines, [*index_cells, file_name])) + "\n")
    return os.path.join(directory, file_name)

def history_rows(directory, limit):
    """Las últimas `limit` altas del índice, la más nueva primera."""
    try:
        with open(os.path.join(directory, INDEX_FILE_NAME), encoding="utf-8") as index_file:
            lines = index_file.read().splitlines()
    except FileNotFoundError:
        return []
    rows = [split_table_row(line) for line in lines]
    data = [cells for cells in rows if cells and len(cells) == len(INDEX_HEADER) and cells != INDEX_HEADER and not is_separator(cells)]
    return data[::-1][:limit]
```

Quien llama a `save_record` atrapa `OSError`, avisa con la ruta y sigue.

**`--history [N]`** muestra las últimas N (10 por default) en una tabla, la más nueva primera. No crea nada y **no pide el secreto**. Sin índice: «todavía no hay altas guardadas en <ruta>», exit 0.

## `--dry-run` y `--status`

- **Ramas cuando el servidor decide un dato intermedio.** Si el estado en que queda un recurso recién creado lo decide la API, el plan no puede mostrar un solo camino: muestra **una rama por cada valor inicial posible** («si queda en `pending-a`: … → destino»), y en la corrida real se sigue la que corresponde.
- **`--status <id>`**, si el CLI crea o modifica recursos con estado: muestra el estado de **cualquier** recurso del entorno, no solo de los que creó el CLI, a qué estados puede pasar y sus datos. No crea nada y no pide el secreto si la lectura no lo necesita.

## Datos generados por default

Un dato que el CLI genera por default (un documento de prueba, una patente, un nombre):

- pasa la misma validación que uno escrito por el usuario, incluido el dígito verificador;
- evita los valores degenerados que pasan el cálculo pero el destino rechaza (todos los dígitos iguales);
- usa rangos con poca chance de coincidir con datos reales;
- sale de un generador criptográfico por default (`secrets.SystemRandom()`) y acepta un `random.Random(semilla)` inyectable para que los tests sean reproducibles.

```python
import secrets

TEST_DOCUMENT_PREFIX = "99"            # rango que casi no usan los documentos reales
TEST_DOCUMENT_BODY_DIGITS = 6

def generate_test_document(random_source=None) -> str:
    random_source = random_source or secrets.SystemRandom()
    while True:
        body = TEST_DOCUMENT_PREFIX + "".join(str(random_source.randrange(10)) for _ in range(TEST_DOCUMENT_BODY_DIGITS))
        candidate = body + check_digit(body)
        if len(set(body)) > 1 and validate_document(candidate):   # la misma validación que el flag y el prompt
            return candidate
```

Si para una opción no hay generador, eso se decide antes del primer efecto ([No sustituir en silencio](#antes-del-primer-efecto)).
