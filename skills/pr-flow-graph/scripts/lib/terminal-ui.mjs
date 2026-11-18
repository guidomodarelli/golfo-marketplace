/**
 * Terminal output helpers of the CLI. Color and symbols degrade to plain text when the stream is
 * not a terminal, when `NO_COLOR` is set or when the terminal is `dumb`.
 */

const ANSI_RESET = '\u001b[0m';
const ANSI_STYLE = {
  bold: '\u001b[1m',
  dim: '\u001b[2m',
  red: '\u001b[31m',
  green: '\u001b[32m',
  yellow: '\u001b[33m',
  cyan: '\u001b[36m',
};

const ANSI_CLEAR_LINE = '\r\u001b[2K';
const ANSI_HIDE_CURSOR = '\u001b[?25l';
const ANSI_SHOW_CURSOR = '\u001b[?25h';
const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const SPINNER_INTERVAL_MS = 80;

const STATUS = {
  done: { symbol: '✔', plainSymbol: '[ok]', style: 'green' },
  warning: { symbol: '▲', plainSymbol: '[warn]', style: 'yellow' },
  error: { symbol: '✖', plainSymbol: '[error]', style: 'red' },
  skipped: { symbol: '○', plainSymbol: '[skip]', style: 'dim' },
};

const SUMMARY_BORDER = { horizontal: '─', vertical: '│', topLeft: '╭', topRight: '╮', bottomLeft: '╰', bottomRight: '╯' };
const SUMMARY_PADDING = 1;

/**
 * @param {NodeJS.WriteStream} stream Stream the CLI writes to.
 * @param {NodeJS.ProcessEnv} [environment]
 * @returns {boolean} Whether the stream shows ANSI color.
 */
export function supportsColor(stream, environment = process.env) {
  return Boolean(stream.isTTY) && !('NO_COLOR' in environment) && environment.TERM !== 'dumb';
}

/**
 * @param {NodeJS.WriteStream} stream Stream the CLI writes to.
 * @param {NodeJS.ProcessEnv} [environment]
 * @returns {object} Writers that share one decision about color.
 */
export function createTerminalUi(stream, environment = process.env) {
  const isColorEnabled = supportsColor(stream, environment);
  const paint = (style, text) => (isColorEnabled ? `${ANSI_STYLE[style]}${text}${ANSI_RESET}` : text);
  const writeLine = (text = '') => stream.write(`${text}\n`);
  const writeStatus = (statusName, text) => {
    const status = STATUS[statusName];
    writeLine(`${paint(status.style, isColorEnabled ? status.symbol : status.plainSymbol)} ${text}`);
  };

  return {
    banner: (title) => writeLine(paint('bold', paint('cyan', title))),
    step: (position, total, title) => writeLine(`${paint('cyan', `[${position}/${total}]`)} ${paint('bold', title)}`),
    done: (text) => writeStatus('done', text),
    warning: (text) => writeStatus('warning', text),
    error: (text) => writeStatus('error', text),
    skipped: (text) => writeStatus('skipped', text),
    detail: (text) => writeLine(`    ${paint('dim', text)}`),
    /**
     * Shows an animated spinner while `task` runs. Without color the text is printed once.
     * The spinner line and the cursor are restored even when the task fails.
     */
    withSpinner: async (text, task) => {
      if (!isColorEnabled) {
        writeLine(`${text}...`);
        return task();
      }
      let frameIndex = 0;
      const drawFrame = () => {
        stream.write(`${ANSI_CLEAR_LINE}${paint('cyan', SPINNER_FRAMES[frameIndex])} ${text}`);
        frameIndex = (frameIndex + 1) % SPINNER_FRAMES.length;
      };
      stream.write(ANSI_HIDE_CURSOR);
      drawFrame();
      const timer = setInterval(drawFrame, SPINNER_INTERVAL_MS);
      try {
        return await task();
      } finally {
        clearInterval(timer);
        stream.write(`${ANSI_CLEAR_LINE}${ANSI_SHOW_CURSOR}`);
      }
    },
    summary: (lines) => {
      if (!isColorEnabled) {
        lines.forEach((line) => writeLine(line));
        return;
      }
      const width = Math.max(...lines.map((line) => line.length)) + SUMMARY_PADDING * 2;
      const pad = ' '.repeat(SUMMARY_PADDING);
      writeLine(paint('green', `${SUMMARY_BORDER.topLeft}${SUMMARY_BORDER.horizontal.repeat(width)}${SUMMARY_BORDER.topRight}`));
      for (const line of lines) {
        const filler = ' '.repeat(width - line.length - SUMMARY_PADDING * 2);
        writeLine(`${paint('green', SUMMARY_BORDER.vertical)}${pad}${line}${filler}${pad}${paint('green', SUMMARY_BORDER.vertical)}`);
      }
      writeLine(paint('green', `${SUMMARY_BORDER.bottomLeft}${SUMMARY_BORDER.horizontal.repeat(width)}${SUMMARY_BORDER.bottomRight}`));
    },
  };
}
