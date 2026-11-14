# Flags y archivo de configuración: los detalles

Completa «Flags» y «Paridad» del [SKILL.md](../SKILL.md) con lo que apareció en un CLI real. Los ejemplos son Python sin dependencias; la regla vale en cualquier stack.

## Índice

1. [Cortos de una letra](#cortos-de-una-letra)
2. [Alias y combinaciones](#alias-y-combinaciones)
3. [Obligatorios según la acción](#obligatorios-según-la-acción)
4. [Archivo de configuración](#archivo-de-configuración)
5. [Valores que vuelven al comando equivalente](#valores-que-vuelven-al-comando-equivalente)
6. [Lo que vino por flag](#lo-que-vino-por-flag)
7. [El error de la fila 5](#el-error-de-la-fila-5)

## Cortos de una letra

Los cortos son de una letra; para más, el largo con `--`. Un corto de varias letras con un guion (`-ss`, `-scope`) choca con el valor pegado del corto de una letra:

```python
parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument("-s", "--status"); parser.add_argument("-ss", "--substatus")
parser.parse_args(["-ssx"])   # Namespace(status='sx', substatus=None): no es «-ss x»
```

## Alias y combinaciones

- **Alias de un mismo dato** (`--user-id N` y `--user N`): los dos con el mismo valor vale; con valores distintos, exit 2. El choque se mira **solo entre los flags de la línea de comandos**, antes de mezclarlos con el archivo de configuración: comparar contra el valor ya mezclado hace fallar `-c archivo.json --user-id 777` cuando el archivo trae otro `user`, que el flag tiene que pisar.
- **Combinaciones sin sentido.** Si los dos datos vienen por flag, exit 2 (fila 2), y el mensaje nombra la alternativa («`--email` solo sirve al crear un usuario nuevo: con uno existente, usá `--email auto`»). Si uno vino por flag y el otro se eligió en el wizard, el usuario no se contradijo: avisar en una línea que el flag no se usa («No se usa `--email`: un usuario que ya existe conserva su mail») y seguir.

## Obligatorios según la acción

Cuando las acciones son flags (`--list`, `--dry-run`, `--history`) y no subcomandos, cada una tiene su conjunto de obligatorios: `--history` ninguno, `--list` dos, `--dry-run` cuatro, crear todos.

- Una acción de solo lectura no arma ni valida los datos de crear.
- El flag de acción fija la acción: el wizard no pregunta «¿qué querés hacer?».
- La ayuda dice «obligatorio al crear».
- En el inventario de parámetros (paso 2 del flujo), anotar en qué acciones es obligatorio cada uno.

## Archivo de configuración

- Solo cuentan las claves presentes; `null` y `""` equivalen a ausente.
- Un valor de otro tipo da error con el tipo recibido («`site` tiene que ser texto (vino int)»).
- Un JSON inválido da error con línea y columna, y el archivo tiene que ser un objeto.
- Un valor inválido nombra el archivo como origen («`scope` de `config.json` no es válido; opciones: …»).
- Lo que vino del archivo **cuenta como dado** y no se pregunta, igual que un flag.
- **El secreto nunca va en el archivo:** si aparece la clave, error con la alternativa (`--token-file`, variable).

```python
import json

CONFIG_KEY_TYPES = {"site": str, "scope": str, "user_id": int}
SECRET_CONFIG_KEYS = {"token"}

class ConfigError(Exception):
    pass

def load_config(path) -> dict:
    try:
        with open(path, encoding="utf-8") as config_file:
            data = json.load(config_file)
    except json.JSONDecodeError as decode_error:
        raise ConfigError(f"{path} no es JSON válido (línea {decode_error.lineno}, columna {decode_error.colno}).") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} tiene que ser un objeto JSON (vino {type(data).__name__}).")
    for key in SECRET_CONFIG_KEYS & data.keys():
        raise ConfigError(f"{path} no puede traer «{key}»: pasalo con --{key}-file o con la variable TOOL_{key.upper()}.")
    values = {}
    for key, value in data.items():
        if value is None or value == "" or key not in CONFIG_KEY_TYPES:
            continue
        expected_type = CONFIG_KEY_TYPES[key]
        if not isinstance(value, expected_type) or isinstance(value, bool):
            raise ConfigError(f"«{key}» de {path} tiene que ser {expected_type.__name__} (vino {type(value).__name__}).")
        values[key] = value
    return values   # después, la misma validación que los flags, nombrando el archivo como origen
```

Una clave desconocida se ignora o se informa según el proyecto; lo que no vale es tomarla en silencio con otro nombre.

## Valores que vuelven al comando equivalente

- **Allow-list además de citar.** Si un valor no puede traer metacaracteres de shell (un mail, un ID, una región), validarlo con una allow-list: un mail con `$(...)`, `;` o comillas termina impreso en el comando para copiar y pegar. La regex, sin backtracking catastrófico: `.` fuera de las clases que se repiten en el dominio, como `^[A-Za-z0-9._-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$`.
- **IDs numéricos: enteros positivos con dígitos ASCII**, en el flag y en el prompt: `text.isascii() and text.isdigit() and int(text) > 0`. Un `0` aceptado se lee como «sin valor» en `if user_id:` y cambia la acción (`--user-id 0` terminaba creando un usuario nuevo).
- **Los defaults también se escriben.** Lo que salió del default, o se eligió con la opción por defecto, va en el comando equivalente (`--scope release`, `--email auto`): así reproduce lo mismo aunque el default cambie en otra versión.

## Lo que vino por flag

Si un valor con nombre se guarda internamente como `None` (`--user nuevo` → `user_id=None`, `--email auto` → `email=None`), el parser lleva un booleano aparte (`is_user_given`) para no volver a preguntarlo. Sin ese indicador, `--user nuevo` se pregunta igual.

## El error de la fila 5

El error dice por qué no se pudo preguntar: sin terminal, con `--no-input` o con `CI`. Así el usuario sabe qué cambiar. Sin argumentos, el mensaje es otro que con flags incompletos: «Sin flags el CLI pregunta todo, pero acá no puede preguntar (sin terminal, con `--no-input` o con `CI`). Faltan: …».
