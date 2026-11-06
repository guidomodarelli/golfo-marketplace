'use strict';

/**
 * Terminal output helpers: per-stream color decision, width measuring, wrapping and panels.
 * Zero external dependencies, like the rest of `scripts/`.
 */

const { stripVTControlCharacters } = require('util');

const ANSI_RESET = '\u001b[0m';
const ANSI_CODES = {
  bold: '1',
  dim: '2',
  red: '31',
  green: '32',
  yellow: '33',
  magenta: '35',
  cyan: '36',
  gray: '90',
  black: '30',
  yellowBackground: '43',
};
/** Environment values that switch off `FORCE_COLOR` and `CI`. */
const DISABLED_ENVIRONMENT_VALUES = ['0', 'false'];
const DUMB_TERMINAL = 'dumb';
const MONOCHROME_COLOR_DEPTH = 1;

const MAX_BOX_WIDTH = 64;
const MINIMUM_CONTENT_WIDTH = 1;
/** Cells taken by the `│  ` prefix of a panel body line. */
const PANEL_BODY_PREFIX_WIDTH = 3;
/** Cells taken around a panel title: `╭─ `, the space after it and at least one rule cell. */
const PANEL_TITLE_RESERVED_WIDTH = 5;
/** Cells taken around the title on the top border, without the rule. */
const PANEL_TITLE_BORDER_WIDTH = 4;
/** Cells taken by the two side borders of the alert banner. */
const BANNER_BORDERS_WIDTH = 2;

/** Double-width graphemes: emoji, CJK ideographs, Hangul, and fullwidth forms. */
const WIDE_GRAPHEME_PATTERN =
  /\p{Emoji_Presentation}|️|[ᄀ-ᅟ⺀-꓏가-힣豈-﫿︰-﹯＀-｠￠-￦]/u;
/** Splits a line into SGR sequences, whitespace, and chunks that can break after a slash. */
const WRAP_TOKEN_PATTERN = /\u001b\[[0-9;]*m|\s+|[^\s\u001b/]*\/|[^\s\u001b/]+/gu;
const WHITESPACE_START_PATTERN = /^\s/;
const LEADING_WHITESPACE_PATTERN = /^\s*/;

const graphemeSegmenter = new Intl.Segmenter();

/**
 * Decides whether a stream may carry color, following section 1 of
 * `plugins/golfo-kit/skills/vivid-visual-output/references/terminal.md`. The tool has no
 * machine output or `--color` flag, so its first two steps do not apply and the order is:
 * 1. `NO_COLOR` (non-empty) or `TERM=dumb`: plain, even with `FORCE_COLOR`.
 * 2. `FORCE_COLOR=0` or `false`: plain.
 * 3. Any other non-empty `FORCE_COLOR`: color, even in CI or without a TTY.
 * 4. `CI` set (other than `0` and `false`), or a stream that is not a TTY: plain.
 * 5. Otherwise, whatever the terminal reports.
 *
 * @param {NodeJS.WriteStream} stream Stream the text is written to.
 * @param {NodeJS.ProcessEnv} [environment=process.env] Environment to read.
 * @returns {boolean} True when the stream may carry ANSI colors.
 */
function isColorEnabledFor(stream, environment = process.env) {
  const { NO_COLOR, TERM, FORCE_COLOR, CI } = environment;
  if (NO_COLOR || TERM === DUMB_TERMINAL || DISABLED_ENVIRONMENT_VALUES.includes(FORCE_COLOR)) {
    return false;
  }
  if (FORCE_COLOR) {
    return true;
  }
  if ((CI && !DISABLED_ENVIRONMENT_VALUES.includes(CI)) || !stream.isTTY) {
    return false;
  }
  return stream.getColorDepth() > MONOCHROME_COLOR_DEPTH;
}

/**
 * Builds the output descriptor of a stream; the color decision is taken once per run.
 *
 * @param {NodeJS.WriteStream} stream Stream the text is written to.
 * @returns {{ stream: NodeJS.WriteStream, isColorEnabled: boolean }} Output descriptor.
 */
function createTerminalOutput(stream) {
  return { stream, isColorEnabled: isColorEnabledFor(stream) };
}

const stdoutOutput = createTerminalOutput(process.stdout);
const stderrOutput = createTerminalOutput(process.stderr);

/**
 * Tells whether readline may use its terminal mode, which writes cursor escapes on its own.
 * Plain output has to stay free of them, so plain runs rely on the line editing of the system.
 *
 * @param {{ stream: NodeJS.WriteStream, isColorEnabled: boolean }} output Output descriptor.
 * @returns {boolean} True on a real terminal that allows escapes.
 */
function supportsLineEditing(output) {
  return Boolean(output.stream.isTTY) && output.isColorEnabled;
}

/**
 * Wraps text in an ANSI style when the output allows colors.
 *
 * @param {string} styleName Key of ANSI_CODES.
 * @param {string} text Text to style.
 * @param {{ isColorEnabled: boolean }} [output=stdoutOutput] Output the text is written to.
 * @returns {string} Styled text, or the original text when colors are disabled.
 */
function paint(styleName, text, output = stdoutOutput) {
  return output.isColorEnabled ? `\u001b[${ANSI_CODES[styleName]}m${text}${ANSI_RESET}` : text;
}

/**
 * Measures graphemes in terminal cells, counting wide ones as two and ANSI codes as zero.
 *
 * @param {string} text Text to measure.
 * @returns {number} Visible width in terminal cells.
 */
function visibleWidth(text) {
  let width = 0;
  for (const { segment } of graphemeSegmenter.segment(stripVTControlCharacters(text))) {
    width += WIDE_GRAPHEME_PATTERN.test(segment) ? 2 : 1;
  }
  return width;
}

/**
 * Reads the current terminal width. Read on every draw, because it can change during a run.
 *
 * @param {{ stream: NodeJS.WriteStream }} output Output descriptor.
 * @returns {number} Columns, or Infinity when there is no terminal and nothing should be split.
 */
function getTerminalColumns(output) {
  const { isTTY, columns } = output.stream;
  return isTTY && columns > 0 ? columns : Infinity;
}

/**
 * Wraps one line without losing data: breaks at spaces and after slashes, and inside a chunk
 * only when it does not fit on a line of its own. Open styles are closed at each break and
 * reopened on the next line; continuation lines keep the indentation of the original line.
 *
 * @param {string} line Line to wrap, which may contain SGR sequences.
 * @param {number} maximumWidth Maximum visible width of each resulting line.
 * @returns {string[]} Wrapped lines; the original line alone when it already fits.
 */
function wrapStyledLine(line, maximumWidth) {
  const availableWidth = Math.max(maximumWidth, MINIMUM_CONTENT_WIDTH);
  if (visibleWidth(line) <= availableWidth) {
    return [line];
  }

  const [leadingWhitespace] = stripVTControlCharacters(line).match(LEADING_WHITESPACE_PATTERN);
  const continuationIndent = leadingWhitespace.length < availableWidth ? leadingWhitespace : '';
  const wrappedLines = [];
  let currentLine = '';
  let currentWidth = 0;
  let activeStyles = '';
  let pendingWhitespace = '';

  const closeLine = () => {
    wrappedLines.push(activeStyles ? `${currentLine}${ANSI_RESET}` : currentLine);
  };
  const breakLine = () => {
    closeLine();
    currentLine = `${continuationIndent}${activeStyles}`;
    currentWidth = continuationIndent.length;
    pendingWhitespace = '';
  };
  const appendText = (text, textWidth) => {
    currentLine += `${pendingWhitespace}${text}`;
    currentWidth += pendingWhitespace.length + textWidth;
    pendingWhitespace = '';
  };
  const appendSplittingGraphemes = (chunk) => {
    if (currentWidth + pendingWhitespace.length >= availableWidth) {
      breakLine();
    }
    for (const { segment } of graphemeSegmenter.segment(chunk)) {
      const graphemeWidth = visibleWidth(segment);
      if (currentWidth + pendingWhitespace.length + graphemeWidth > availableWidth) {
        breakLine();
      }
      appendText(segment, graphemeWidth);
    }
  };

  for (const [token] of line.matchAll(WRAP_TOKEN_PATTERN)) {
    if (token.startsWith('\u001b')) {
      activeStyles = token === ANSI_RESET ? '' : `${activeStyles}${token}`;
      currentLine += token;
    } else if (WHITESPACE_START_PATTERN.test(token)) {
      pendingWhitespace += token;
    } else {
      const tokenWidth = visibleWidth(token);
      if (currentWidth + pendingWhitespace.length + tokenWidth <= availableWidth) {
        appendText(token, tokenWidth);
      } else if (tokenWidth <= availableWidth - continuationIndent.length) {
        breakLine();
        appendText(token, tokenWidth);
      } else {
        appendSplittingGraphemes(token);
      }
    }
  }
  closeLine();

  return wrappedLines;
}

/**
 * Fits free-standing text, line by line, to the terminal width. Without a terminal it is unchanged.
 *
 * @param {string} text Text to fit, which may span several lines.
 * @param {{ stream: NodeJS.WriteStream }} [output=stdoutOutput] Output the text is written to.
 * @returns {string} Text whose lines fit in the terminal.
 */
function fitToTerminal(text, output = stdoutOutput) {
  const columns = getTerminalColumns(output);
  return text
    .split('\n')
    .flatMap((line) => wrapStyledLine(line, columns))
    .join('\n');
}

/**
 * Renders a left-bordered panel; omitting the right border keeps emoji alignment stable.
 * Borders shrink with the terminal and content wraps to it, so no data is ever cut.
 *
 * @param {string} title Panel title shown on the top border.
 * @param {string[]} lines Panel body lines.
 * @param {string} [borderStyle='cyan'] Key of ANSI_CODES for the border.
 * @param {{ stream: NodeJS.WriteStream, isColorEnabled: boolean }} [output=stdoutOutput] Output
 *   the panel is written to.
 * @returns {string} Rendered panel.
 */
function renderPanel(title, lines, borderStyle = 'cyan', output = stdoutOutput) {
  const border = (text) => paint(borderStyle, text, output);
  const bold = (text) => paint('bold', text, output);
  const columns = getTerminalColumns(output);
  const panelWidth = Math.min(MAX_BOX_WIDTH, columns);
  const [firstTitleLine, ...remainingTitleLines] = wrapStyledLine(title, columns - PANEL_TITLE_RESERVED_WIDTH);
  const topRuleLength = Math.max(panelWidth - visibleWidth(firstTitleLine) - PANEL_TITLE_BORDER_WIDTH, 0);
  const bodyLines = [
    ...remainingTitleLines.map(bold),
    ...lines.flatMap((line) => wrapStyledLine(line, columns - PANEL_BODY_PREFIX_WIDTH)),
  ];
  return [
    `${border('╭─')} ${bold(firstTitleLine)} ${border('─'.repeat(topRuleLength))}`,
    ...bodyLines.map((line) => `${border('│')}  ${line}`),
    border(`╰${'─'.repeat(panelWidth - 1)}`),
  ].join('\n');
}

/**
 * Renders a full-width, heavy-bordered banner with highlighted body lines.
 *
 * @param {string} message Banner message.
 * @param {{ stream: NodeJS.WriteStream, isColorEnabled: boolean }} [output=stdoutOutput] Output
 *   the banner is written to.
 * @returns {string} Rendered banner.
 */
function renderAlertBanner(message, output = stdoutOutput) {
  const columns = getTerminalColumns(output);
  const innerWidth = Math.max(Math.min(MAX_BOX_WIDTH, columns) - BANNER_BORDERS_WIDTH, 0);
  const highlight = (text) =>
    paint('yellowBackground', paint('black', paint('bold', text, output), output), output);
  const border = (text) => paint('yellow', paint('bold', text, output), output);
  const bodyRows = wrapStyledLine(`  ${message}`, columns - BANNER_BORDERS_WIDTH).map((bodyLine) => {
    const paddedBody = `${bodyLine}${' '.repeat(Math.max(innerWidth - visibleWidth(bodyLine), 0))}`;
    return `${border('┃')}${highlight(paddedBody)}${border('┃')}`;
  });
  return [
    border(`┏${'━'.repeat(innerWidth)}┓`),
    ...bodyRows,
    border(`┗${'━'.repeat(innerWidth)}┛`),
  ].join('\n');
}

module.exports = {
  fitToTerminal,
  paint,
  renderAlertBanner,
  renderPanel,
  stderrOutput,
  stdoutOutput,
  supportsLineEditing,
  visibleWidth,
};
