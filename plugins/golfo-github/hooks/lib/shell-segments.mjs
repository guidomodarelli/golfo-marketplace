/**
 * Parte un comando de Bash o PowerShell en tramos: uno por cada invocación de `gh` y uno por cada
 * asignación de variable, sin ejecutarlo. Lo que está entre comillas, en un heredoc o en un
 * here-string es texto, no código: un body que menciona `gh api` no abre un tramo nuevo.
 */

/** Shells que entiende el lexer. */
export const SHELL = { bash: 'bash', powershell: 'powershell' };

/** Tipo de tramo. */
export const SEGMENT_TYPE = { ghInvocation: 'gh-invocation', variableAssignment: 'variable-assignment' };

const GH_START_PATTERN = /(^|[\s;&|(`{])(gh(?:\.exe)?)(?=\s)/g;
const BASH_ASSIGNMENT_PATTERN = /(^|[;&|\n(]|\b(?:do|then|else)\b)[ \t]*(?:(?:local|export|declare|readonly|typeset)(?:[ \t]+-\w+)*[ \t]+)?([A-Za-z_]\w*)=/g;
const POWERSHELL_ASSIGNMENT_PATTERN = /(^|[;\n{(])[ \t]*\$([A-Za-z_]\w*)[ \t]*=(?!=)/g;
const BASH_HEREDOC_PATTERN = /^<<(-?)[ \t]*(?:'([^']+)'|"([^"]+)"|\\?([A-Za-z_]\w*))/;

/**
 * Marca qué posiciones de un comando de Bash son código y cuáles son texto citado o de heredoc.
 *
 * @param {string} command Comando completo.
 * @returns {boolean[]} `true` en cada posición de código.
 */
function bashCodeMask(command) {
  const isCode = new Array(command.length).fill(false);
  const pendingHeredocs = [];
  let index = 0;
  while (index < command.length) {
    const character = command[index];
    if (character === "'" || (character === '$' && command[index + 1] === "'")) {
      const isAnsiQuote = character === '$';
      let cursor = index + (isAnsiQuote ? 2 : 1);
      while (cursor < command.length && command[cursor] !== "'") {
        cursor += isAnsiQuote && command[cursor] === '\\' ? 2 : 1;
      }
      index = cursor + 1;
      continue;
    }
    if (character === '"') {
      let cursor = index + 1;
      while (cursor < command.length && command[cursor] !== '"') {
        cursor += command[cursor] === '\\' ? 2 : 1;
      }
      index = cursor + 1;
      continue;
    }
    if (character === '<' && command[index + 1] === '<' && command[index + 2] !== '<') {
      const heredoc = BASH_HEREDOC_PATTERN.exec(command.slice(index));
      if (heredoc) {
        pendingHeredocs.push({ delimiter: heredoc[2] ?? heredoc[3] ?? heredoc[4], stripTabs: heredoc[1] === '-' });
        for (let cursor = index; cursor < index + heredoc[0].length; cursor += 1) {
          isCode[cursor] = true;
        }
        index += heredoc[0].length;
        continue;
      }
    }
    isCode[index] = true;
    if (character === '\\') {
      index += 2;
      continue;
    }
    if (character === '\n' && pendingHeredocs.length > 0) {
      index = skipHeredocBodies(command, index + 1, pendingHeredocs.splice(0));
      continue;
    }
    index += 1;
  }
  return isCode;
}

/**
 * Saltea los cuerpos de los heredocs abiertos en la línea anterior.
 *
 * @param {string} command Comando completo.
 * @param {number} start Posición donde empieza el primer cuerpo.
 * @param {{ delimiter: string, stripTabs: boolean }[]} heredocs Heredocs en orden.
 * @returns {number} Posición siguiente al último delimitador.
 */
function skipHeredocBodies(command, start, heredocs) {
  let lineStart = start;
  for (const heredoc of heredocs) {
    while (lineStart < command.length) {
      const lineEnd = command.indexOf('\n', lineStart) === -1 ? command.length : command.indexOf('\n', lineStart);
      const line = command.slice(lineStart, lineEnd).replace(/\r$/, '');
      lineStart = lineEnd + 1;
      if ((heredoc.stripTabs ? line.replace(/^\t+/, '') : line) === heredoc.delimiter) {
        break;
      }
    }
  }
  return Math.min(lineStart, command.length);
}

/**
 * Marca qué posiciones de un comando de PowerShell son código y cuáles son texto citado o de
 * here-string (`@'…'@`, `@"…"@`).
 *
 * @param {string} command Comando completo.
 * @returns {boolean[]} `true` en cada posición de código.
 */
function powershellCodeMask(command) {
  const isCode = new Array(command.length).fill(false);
  let index = 0;
  while (index < command.length) {
    const character = command[index];
    if (character === '@' && (command[index + 1] === "'" || command[index + 1] === '"')) {
      const closing = `\n${command[index + 1]}@`;
      const end = command.indexOf(closing, index + 2);
      if (/^[ \t]*\r?\n/.test(command.slice(index + 2))) {
        index = end === -1 ? command.length : end + closing.length;
        continue;
      }
    }
    if (character === "'" || character === '"') {
      let cursor = index + 1;
      while (cursor < command.length) {
        if (command[cursor] === character && command[cursor + 1] === character) {
          cursor += 2;
        } else if (command[cursor] === character) {
          break;
        } else {
          cursor += character === '"' && command[cursor] === '`' ? 2 : 1;
        }
      }
      index = cursor + 1;
      continue;
    }
    isCode[index] = true;
    index += character === '`' ? 2 : 1;
  }
  return isCode;
}

/**
 * Parte el comando en tramos de `gh` y de asignaciones. El texto antes del primer tramo no se
 * devuelve: no pertenece a ninguna invocación ni a ninguna variable.
 *
 * @param {string} command Comando completo.
 * @param {string} shell Un valor de {@link SHELL}.
 * @returns {{ type: string, name?: string, text: string }[]} Tramos en orden.
 */
export function splitCommandSegments(command, shell) {
  const isCode = shell === SHELL.powershell ? powershellCodeMask(command) : bashCodeMask(command);
  const assignmentPattern = shell === SHELL.powershell ? POWERSHELL_ASSIGNMENT_PATTERN : BASH_ASSIGNMENT_PATTERN;
  const starts = [];
  for (const match of command.matchAll(GH_START_PATTERN)) {
    const position = match.index + match[1].length;
    if (isCode[position]) {
      starts.push({ position, type: SEGMENT_TYPE.ghInvocation });
    }
  }
  for (const match of command.matchAll(assignmentPattern)) {
    const namePosition = command.indexOf(match[2], match.index + match[1].length);
    // En PowerShell el tramo empieza en el `$` del nombre.
    const position = shell === SHELL.powershell ? namePosition - 1 : namePosition;
    if (isCode[namePosition]) {
      starts.push({ position, type: SEGMENT_TYPE.variableAssignment, name: match[2] });
    }
  }
  starts.sort((first, second) => first.position - second.position);
  return starts.map((start, index) => ({
    type: start.type,
    ...(start.name ? { name: start.name } : {}),
    text: command.slice(start.position, starts[index + 1]?.position ?? command.length),
  }));
}
