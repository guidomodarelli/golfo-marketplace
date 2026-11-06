# Node

Probado en pseudoconsolas de Windows y Linux con Node 24, `@clack/prompts` 1.8 y `@inquirer/prompts` 8.7. Antes de usar otra versión, mirar su documentación.

Usar la librería de prompts que el proyecto ya tenga. Sin ninguna, `@clack/prompts` trae lista con búsqueda y multiselect con menos código; proponerla como decisión explícita.

## Parser

`parseArgs` es nativo y alcanza para flags sin subcomandos. Con `strict: true` falla ante un flag desconocido, y el mensaje trae varias líneas.

```js
import { parseArgs } from 'node:util';

const FLAG_OPTIONS = {
  help: { type: 'boolean', short: 'h' },
  version: { type: 'boolean', short: 'V' },
  'no-input': { type: 'boolean' },
  force: { type: 'boolean', short: 'f' },
  name: { type: 'string' },
  runtime: { type: 'string' },
  features: { type: 'string', multiple: true },
};

class UsageError extends Error {}
class CancelledError extends Error {}

function parseFlags(argv) {
  try {
    return parseArgs({ args: argv, options: FLAG_OPTIONS, strict: true }).values;
  } catch (parseError) {
    throw new UsageError(parseError.message.split('\n')[0], { cause: parseError });
  }
}
```

`multiple: true` acepta el flag repetido. Para aceptar también comas y `none`:

```js
const features = flags.features?.flatMap((value) => value.split(',')).filter((value) => value && value !== NONE_VALUE);
```

## Se puede preguntar

```js
function canPrompt(flags, env = process.env) {
  const isContinuousIntegration = env.CI && env.CI !== '0' && env.CI !== 'false';
  return Boolean(process.stdin.isTTY && process.stderr.isTTY)
    && !flags['no-input'] && !isContinuousIntegration && env.TERM !== 'dumb';
}
```

## Widgets

Las dos librerías dibujan en stdout por default. Cambiarlo en **cada** prompt: en clack va en las opciones y en Inquirer, en el segundo argumento.

| Widget | `@clack/prompts` | `@inquirer/prompts` |
|---|---|---|
| Confirm | `confirm({ message, initialValue: false, output })` | `confirm({ message, default: false }, { output })` |
| Radio | `select({ message, options, output })` | `select({ message, choices }, { output })` |
| Lista con búsqueda | `autocomplete({ message, options, maxItems, output })` | `search({ message, source }, { output })` |
| Multiselect | `multiselect({ message, options, required: false, output })` | `checkbox({ message, choices }, { output })` |
| Texto | `text({ message, validate, output })` | `input({ message, validate }, { output })` |
| Secreto | `password({ message, output })` | `password({ message, mask: true }, { output })` |

Las opciones de clack son `{ value, label }` y las de Inquirer, `{ value, name }`. En clack, `validate` devuelve el texto del error o `undefined`; en Inquirer, `true` o el texto del error.

`multiselect` de clack tiene `required` en `true` por default: sin `required: false`, la lista vacía no se puede confirmar.

## Cancelación

Clack devuelve un símbolo y no lanza nada. Chequearlo en cada respuesta:

```js
import * as prompts from '@clack/prompts';

const PROMPT_STREAM = { output: process.stderr };

function unwrap(answer) {
  if (prompts.isCancel(answer)) throw new CancelledError();
  return answer;
}

const runtime = unwrap(await prompts.select({ message: 'Runtime', options: RUNTIME_OPTIONS, ...PROMPT_STREAM }));
```

Inquirer lanza una excepción: distinguirla por nombre con `error.name === 'ExitPromptError'`.

## Punto de entrada

```js
main(process.argv.slice(2)).catch((error) => {
  if (error instanceof CancelledError) {
    prompts.cancel('Cancelado: no se cambió nada.', PROMPT_STREAM);
    process.exitCode = EXIT_CODE.cancelled;
  } else if (error instanceof UsageError) {
    process.stderr.write(`${TOOL_NAME}: ${error.message}\n`);
    process.exitCode = EXIT_CODE.usage;
  } else {
    process.stderr.write(`${TOOL_NAME}: ${error.message}\n`);
    process.exitCode = EXIT_CODE.failure;
  }
});
```

Asignar `process.exitCode` en vez de llamar a `process.exit()`, que puede cortar datos todavía sin escribir en un pipe.

## Comando equivalente

Las comillas dependen de la plataforma: simples en POSIX, donde dejan el valor literal, y dobles en Windows, porque `cmd.exe` no entiende las simples.

```js
const POSIX_SAFE_TOKEN = /^[\w@%+=:,./-]+$/;
const WINDOWS_SAFE_TOKEN = /^[\w@+=:,./\\-]+$/;

function quoteForShell(value) {
  if (process.platform !== 'win32') {
    return POSIX_SAFE_TOKEN.test(value) ? value : `'${value.replaceAll("'", `'\\''`)}'`;
  }
  if (WINDOWS_SAFE_TOKEN.test(value)) return value;
  // En Windows una barra solo se duplica antes de una comilla o al final del argumento.
  const escaped = value.replace(/(\\*)"/g, '$1$1\\"').replace(/(\\+)$/, '$1$1');
  return `"${escaped}"`;
}
```

En Windows no hay una forma de citar que sirva igual en `cmd.exe` y en PowerShell cuando el valor trae `%`, `$`, acento grave o comillas dobles: `cmd.exe` expande `%VAR%` aun entre comillas, y PowerShell, `$var`. Si el valor trae alguno, avisar junto al comando que puede necesitar ajuste según el shell. Una ruta que termina en barra llega a PowerShell con una barra de más, que Windows tolera.

## Trampas

- **`argv.length === 0`** distingue la invocación sin argumentos, que abre el wizard completo.
- **`--help` junto a un flag desconocido:** con `strict: true` gana el error. Es aceptable, porque el usuario igual recibe a qué flag apuntar.
- **Sin dependencias:** `readline` da preguntas de texto y menús numerados, pero no flechas. Es una degradación válida si el proyecto no admite dependencias; decirlo en el reporte. `rl.question` escribe en la `output` que se le pase: pasarle `process.stderr`.
