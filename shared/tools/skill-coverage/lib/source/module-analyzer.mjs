/**
 * Structural analysis of one JavaScript/TypeScript module with the Babel AST.
 *
 * A module is split into hashed *parts* so that a change can be traced to
 * the smallest unit of behavior that contains it:
 *
 * - `<module>`: directives (`"use client"`), side-effect imports and other
 *   top-level statements that run on import.
 * - `Name`: a top-level declaration (function, class, type, variable).
 * - `Name~shell` + `Name/inner`: a function whose body declares inner
 *   functions (handlers such as `handleSubmit`) is split into the inner
 *   functions and everything else (state, JSX), so two handlers of the same
 *   component have independent fingerprints.
 * - `Name~frame` + `Name.member`: an object literal constant (a copy or
 *   config dictionary) is split by property, so editing one message only
 *   affects the code that reads it.
 *
 * Hashes cover the token stream, not the raw text: formatting and comments
 * never invalidate coverage. A part that consumes package or builtin imports
 * also hashes their identity (`local=source#imported`), so pointing a binding
 * at another export or subpath changes only the parts that use it. Each
 * part also lists the identifiers it references (`Name`, `Name.member`, or
 * `/inner` for a sibling inner function), the literal specifiers it loads
 * with `import()` and the load signals used by performance policies.
 */
import path from 'node:path';

import { ANALYZER_VERSION, FILE_LEVEL_ANALYZER, SOURCE_EXTENSIONS } from '../constants.mjs';
import { entryHash, normalizeLineEndings } from '../support.mjs';

const SKIPPED_KEYS = new Set(['loc', 'start', 'end', 'extra', 'range', 'leadingComments', 'trailingComments', 'innerComments', 'tokens', 'comments', 'errors']);
const KEYED_PARENTS = new Set(['ObjectProperty', 'ObjectMethod', 'ClassProperty', 'ClassMethod', 'ClassPrivateProperty', 'ClassAccessorProperty', 'TSPropertySignature', 'TSMethodSignature', 'TSAbstractPropertyDefinition', 'TSAbstractMethodDefinition']);
const LABEL_PARENTS = new Set(['LabeledStatement', 'BreakStatement', 'ContinueStatement']);
const DECLARING_PARENTS = new Set(['VariableDeclarator', 'FunctionDeclaration', 'FunctionExpression', 'ClassDeclaration', 'ClassExpression', 'TSDeclareFunction', 'TSTypeAliasDeclaration', 'TSInterfaceDeclaration', 'TSEnumDeclaration', 'TSModuleDeclaration']);
const TYPE_DECLARATIONS = new Set(['TSTypeAliasDeclaration', 'TSInterfaceDeclaration', 'TSEnumDeclaration', 'TSModuleDeclaration']);
const WRAPPER_EXPRESSIONS = new Set(['TSAsExpression', 'TSSatisfiesExpression', 'TSTypeAssertion', 'TSNonNullExpression', 'ParenthesizedExpression']);
const LOOP_STATEMENTS = new Set(['ForStatement', 'ForOfStatement', 'ForInStatement', 'WhileStatement', 'DoWhileStatement']);
const NESTED_FUNCTION_TYPES = new Set(['ArrowFunctionExpression', 'FunctionExpression', 'ObjectMethod', 'ClassMethod', 'ClassPrivateMethod']);
const MEMOIZING_HOOKS = new Set(['useCallback', 'useMemo', 'useEffectEvent']);

/** Callee names and properties counted as load signals. */
const LOAD_SIGNAL_NAMES = {
  dataHooks: new Set(['useSWR', 'useSWRInfinite', 'useQuery', 'useInfiniteQuery', 'useSuspenseQuery', 'useMutation']),
  database: new Set(['select', 'insert', 'update', 'delete', 'execute', 'query', 'findMany', 'findFirst', 'findUnique', 'transaction', 'batch', '$queryRaw', '$executeRaw']),
  effects: new Set(['useEffect', 'useLayoutEffect', 'useInsertionEffect']),
  iterators: new Set(['map', 'forEach', 'flatMap']),
  listeners: new Set(['addEventListener', 'subscribe', 'onSnapshot', 'watch']),
  observers: new Set(['WebSocket', 'EventSource', 'Worker', 'SharedWorker', 'IntersectionObserver', 'MutationObserver', 'ResizeObserver', 'BroadcastChannel']),
  timers: new Set(['setInterval', 'setTimeout', 'requestAnimationFrame', 'requestIdleCallback']),
};

/** Imported functions whose name starts with one of these verbs usually do I/O. */
const LOAD_VERB_PATTERN = /^(?:fetch|load|get|list|save|set|create|update|delete|remove|post|put|patch|send|resend|request|start|reconcile|cancel|grant|revoke|decide|approve|reject|verify|confirm|discard|join|invite|accept|decline|activate|connect|disconnect|archive|restore|publish|enroll|pause|resume|apply|mark|toggle|query|sync|upload|download|refresh|reload|submit|search|import|export|enqueue|dispatch|run|execute)/i;

/**
 * @param {string} filePath
 * @returns {boolean}
 */
export function isSourceFile(filePath) {
  return SOURCE_EXTENSIONS.includes(path.posix.extname(filePath));
}

/**
 * Babel plugins for an extension: JSX only where the syntax allows it
 * (`<T>() => x` is a generic in `.ts`, an element in `.tsx`).
 *
 * @param {string} filePath
 * @returns {string[]}
 */
function parserPlugins(filePath) {
  const extension = path.posix.extname(filePath);
  if (extension === '.tsx') return ['typescript', 'jsx'];
  if (['.ts', '.mts', '.cts'].includes(extension)) return ['typescript'];
  return ['jsx'];
}

/**
 * Import sources found by pattern matching, used only when no parser is
 * available: they let the whole-file fallback still follow dependencies.
 *
 * @param {string} source
 * @returns {string[]}
 */
export function scanImportSources(source) {
  const patterns = [
    /(?:^|[^\w$.])(?:import|export)\s[^'"`;]*?\bfrom\s*['"]([^'"\n]+)['"]/g,
    /(?:^|[^\w$.])import\s*['"]([^'"\n]+)['"]/g,
    /\bimport\s*\(\s*['"]([^'"\n]+)['"]\s*\)/g,
    /\brequire\s*\(\s*['"]([^'"\n]+)['"]\s*\)/g,
  ];
  const sources = new Set();
  for (const pattern of patterns) for (const match of source.matchAll(pattern)) sources.add(match[1]);
  return [...sources];
}

/**
 * Whole-file analysis: the fallback for non-JS files, files that do not
 * parse and projects without a parser.
 *
 * @param {string} filePath
 * @param {string} source
 * @param {string | undefined} reason Why symbol analysis was not used.
 */
function fileLevelAnalysis(filePath, source, reason) {
  return {
    analyzer: FILE_LEVEL_ANALYZER,
    fallbackReason: reason,
    fileHash: entryHash(normalizeLineEndings(source)),
    importSources: isSourceFile(filePath) ? scanImportSources(source) : [],
    path: filePath,
  };
}

/**
 * Depth-first walk over Babel nodes. `visit` returns `false` to skip children.
 *
 * @param {any} node
 * @param {(node: any, parent: any, key: string | null) => boolean | void} visit
 * @param {any} [parent]
 * @param {string | null} [key]
 */
function walk(node, visit, parent = null, key = null) {
  if (!node || typeof node.type !== 'string') return;
  if (visit(node, parent, key) === false) return;
  for (const childKey of Object.keys(node)) {
    if (SKIPPED_KEYS.has(childKey)) continue;
    const child = node[childKey];
    if (Array.isArray(child)) {
      for (const item of child) if (item && typeof item.type === 'string') walk(item, visit, node, childKey);
    } else if (child && typeof child.type === 'string') {
      walk(child, visit, node, childKey);
    }
  }
}

/**
 * @param {any} node
 * @returns {any} The expression without `as const`, `satisfies` and similar wrappers.
 */
function unwrapExpression(node) {
  let current = node;
  while (current && WRAPPER_EXPRESSIONS.has(current.type)) current = current.expression;
  if (current?.type === 'CallExpression' && current.callee?.type === 'MemberExpression' && current.callee.object?.name === 'Object' && current.callee.property?.name === 'freeze') {
    return unwrapExpression(current.arguments[0]);
  }
  return current;
}

/**
 * @param {any} init Declarator initializer.
 * @returns {boolean} Whether it defines an inner function (directly or through `useCallback`).
 */
function isFunctionInitializer(init) {
  const value = unwrapExpression(init);
  if (!value) return false;
  if (value.type === 'ArrowFunctionExpression' || value.type === 'FunctionExpression') return true;
  return value.type === 'CallExpression' && value.callee?.type === 'Identifier' && MEMOIZING_HOOKS.has(value.callee.name)
    && ['ArrowFunctionExpression', 'FunctionExpression'].includes(value.arguments[0]?.type);
}

/**
 * @param {any} pattern Binding pattern.
 * @returns {string[]} Names it binds.
 */
function bindingNames(pattern) {
  const names = [];
  walk(pattern, (node, parent, key) => {
    if (node.type === 'Identifier' && !(parent && KEYED_PARENTS.has(parent.type) && key === 'key' && !parent.computed)) names.push(node.name);
    if (node.type === 'AssignmentPattern') {
      walk(node.left, (inner) => {
        if (inner.type === 'Identifier') names.push(inner.name);
      });
      return false;
    }
    return undefined;
  });
  return names;
}

/**
 * Analyzes a module. Never throws: parse failures degrade to whole-file analysis.
 *
 * @param {{ path: string, source: string, parser: { parse: Function } | null, resolver?: { resolve: Function } }} input
 *   `resolver` tells project files apart from packages and builtins, whose
 *   import identities are part of the hashes (without it, every import is).
 */
export function analyzeModule({ path: filePath, source, parser, resolver }) {
  if (!isSourceFile(filePath)) return fileLevelAnalysis(filePath, source, 'not a JavaScript or TypeScript module');
  if (!parser) return fileLevelAnalysis(filePath, source, 'no Babel parser available in the project');
  let ast;
  try {
    ast = parser.parse(source, {
      allowAwaitOutsideFunction: true,
      allowImportExportEverywhere: true,
      allowReturnOutsideFunction: true,
      allowUndeclaredExports: true,
      errorRecovery: true,
      plugins: parserPlugins(filePath),
      sourceType: 'module',
      tokens: true,
    });
  } catch (error) {
    return fileLevelAnalysis(filePath, source, `parse error: ${error.message.split('\n')[0]}`);
  }
  if (ast.errors?.length) return fileLevelAnalysis(filePath, source, `parse error: ${String(ast.errors[0].message ?? ast.errors[0]).split('\n')[0]}`);
  return symbolLevelAnalysis(filePath, source, ast, resolver);
}

/**
 * @param {string} filePath
 * @param {string} source
 * @param {any} ast
 * @param {{ resolve: Function } | undefined} resolver
 */
function symbolLevelAnalysis(filePath, source, ast, resolver) {
  const tokens = ast.tokens.filter((token) => typeof token.type !== 'string');
  const tokenText = (token) => {
    const text = source.slice(token.start, token.end);
    return token.type.label === 'jsxText' ? text.replace(/\s+/g, ' ').trim() : text;
  };

  /**
   * Hash of the tokens inside `ranges` and outside `excluded`.
   *
   * @param {[number, number][]} ranges
   * @param {[number, number][]} [excluded]
   * @param {{ dropCommas?: boolean }} [options]
   */
  const hashRanges = (ranges, excluded = [], options = {}) => {
    const texts = [];
    for (const [start, end] of ranges) {
      let low = 0;
      let high = tokens.length;
      while (low < high) {
        const middle = (low + high) >> 1;
        if (tokens[middle].start < start) low = middle + 1;
        else high = middle;
      }
      for (let index = low; index < tokens.length && tokens[index].end <= end; index += 1) {
        const token = tokens[index];
        if (excluded.some(([excludedStart, excludedEnd]) => token.start >= excludedStart && token.end <= excludedEnd)) continue;
        if (options.dropCommas && token.type.label === ',') continue;
        const text = tokenText(token);
        if (text) texts.push(text);
      }
    }
    return entryHash(texts.join('\u0000'));
  };

  const imports = new Map();
  const sideEffectImports = [];
  const localExports = new Map();
  const reExports = new Map();
  const exportAllSources = [];
  const declarations = new Map();
  const shellNodes = [];
  const topLevelDeclarators = [];

  /**
   * @param {string} name
   * @param {string} kind
   * @param {any} node Node whose source range is the declaration.
   * @param {any} [valueNode] Node that holds the value (declarator).
   */
  const addDeclaration = (name, kind, node, valueNode = node) => {
    if (!declarations.has(name)) declarations.set(name, { kind, nodes: [] });
    declarations.get(name).nodes.push({ node, valueNode });
  };

  /** @param {any} declaration */
  const registerDeclaration = (declaration) => {
    const type = declaration.type;
    if ((type === 'FunctionDeclaration' || type === 'TSDeclareFunction') && declaration.id) addDeclaration(declaration.id.name, 'function', declaration);
    else if (type === 'ClassDeclaration' && declaration.id) addDeclaration(declaration.id.name, 'class', declaration);
    else if (type === 'VariableDeclaration') {
      for (const declarator of declaration.declarations) {
        const rangeNode = declaration.declarations.length === 1 ? declaration : declarator;
        topLevelDeclarators.push({ declarator, rangeNode });
        if (declarator.id.type === 'Identifier') addDeclaration(declarator.id.name, 'variable', rangeNode, declarator);
        else for (const name of bindingNames(declarator.id)) addDeclaration(name, 'variable', rangeNode, null);
      }
    } else if (TYPE_DECLARATIONS.has(type) && declaration.id?.type === 'Identifier') addDeclaration(declaration.id.name, 'type', declaration);
    else shellNodes.push(declaration);
    return type === 'VariableDeclaration'
      ? declaration.declarations.flatMap((declarator) => (declarator.id.type === 'Identifier' ? [declarator.id.name] : bindingNames(declarator.id)))
      : declaration.id?.name ? [declaration.id.name] : [];
  };

  for (const statement of ast.program.body) {
    switch (statement.type) {
      case 'ImportDeclaration': {
        const importSource = statement.source.value;
        if (!statement.specifiers.length) sideEffectImports.push(importSource);
        for (const specifier of statement.specifiers) {
          const typeOnly = statement.importKind === 'type' || specifier.importKind === 'type';
          if (specifier.type === 'ImportDefaultSpecifier') imports.set(specifier.local.name, { imported: 'default', source: importSource, typeOnly });
          else if (specifier.type === 'ImportNamespaceSpecifier') imports.set(specifier.local.name, { imported: '*', source: importSource, typeOnly });
          else imports.set(specifier.local.name, { imported: specifier.imported.name ?? specifier.imported.value, source: importSource, typeOnly });
        }
        break;
      }
      case 'ExportNamedDeclaration':
        if (statement.declaration) for (const name of registerDeclaration(statement.declaration)) localExports.set(name, name);
        for (const specifier of statement.specifiers ?? []) {
          const exported = specifier.exported.name ?? specifier.exported.value;
          if (statement.source) reExports.set(exported, { imported: specifier.type === 'ExportNamespaceSpecifier' ? '*' : specifier.local.name ?? specifier.local.value, source: statement.source.value });
          else localExports.set(exported, specifier.local.name);
        }
        break;
      case 'ExportDefaultDeclaration': {
        const declaration = statement.declaration;
        if (['FunctionDeclaration', 'ClassDeclaration', 'TSDeclareFunction'].includes(declaration.type)) {
          if (declaration.id) {
            registerDeclaration(declaration);
            localExports.set('default', declaration.id.name);
          } else {
            addDeclaration('default', declaration.type === 'ClassDeclaration' ? 'class' : 'function', declaration);
            localExports.set('default', 'default');
          }
        } else if (declaration.type === 'Identifier') {
          localExports.set('default', declaration.name);
        } else {
          addDeclaration('default', 'variable', declaration);
          localExports.set('default', 'default');
        }
        break;
      }
      case 'ExportAllDeclaration':
        if (statement.exported) reExports.set(statement.exported.name ?? statement.exported.value, { imported: '*', source: statement.source.value });
        else exportAllSources.push(statement.source.value);
        break;
      default:
        if ((statement.type.endsWith('Declaration') || statement.type === 'TSDeclareFunction') && statement.type !== 'TSImportEqualsDeclaration') registerDeclaration(statement);
        else shellNodes.push(statement);
    }
  }

  const topLevelNames = new Set([...declarations.keys(), ...imports.keys()]);
  const importedLocals = new Set(imports.keys());

  /**
   * Identifiers a node references, restricted later to known bindings.
   *
   * @param {any[]} nodes
   * @param {{ skip?: Set<any>, innerNames?: Set<string> }} [options]
   * @returns {string[]}
   */
  const collectReferences = (nodes, options = {}) => {
    const references = new Set();
    const innerNames = options.innerNames ?? new Set();
    const add = (name, member) => {
      if (innerNames.has(name)) references.add(`/${name}`);
      else if (topLevelNames.has(name)) references.add(member ? `${name}.${member}` : name);
    };
    const visit = (node, parent, key) => {
      if (options.skip?.has(node)) return false;
      switch (node.type) {
        case 'MemberExpression':
        case 'OptionalMemberExpression': {
          const property = node.property;
          const member = !node.computed && property.type === 'Identifier' ? property.name : node.computed && property.type === 'StringLiteral' ? property.value : null;
          if (node.object.type === 'Identifier') add(node.object.name, member);
          else walk(node.object, visit, node, 'object');
          if (node.computed) walk(property, visit, node, 'property');
          return false;
        }
        case 'TSQualifiedName':
          if (node.left.type === 'Identifier') add(node.left.name, node.right.name);
          else walk(node.left, visit, node, 'left');
          return false;
        case 'JSXOpeningElement': {
          const name = node.name;
          if (name.type === 'JSXIdentifier') add(name.name);
          else if (name.type === 'JSXMemberExpression' && name.object.type === 'JSXIdentifier') add(name.object.name, name.property.name);
          for (const attribute of node.attributes) walk(attribute, visit, node, 'attributes');
          for (const parameter of node.typeArguments?.params ?? node.typeParameters?.params ?? []) walk(parameter, visit, node, 'typeArguments');
          return false;
        }
        case 'JSXClosingElement':
          return false;
        case 'JSXAttribute':
          walk(node.value, visit, node, 'value');
          return false;
        case 'Identifier':
          if (parent && KEYED_PARENTS.has(parent.type) && key === 'key' && !parent.computed) return false;
          if (parent && LABEL_PARENTS.has(parent.type) && key === 'label') return false;
          if (parent?.type === 'TSEnumMember' && key === 'id') return false;
          // The declared name is a binding, not a use: a symbol never depends on itself.
          if (key === 'id' && parent && DECLARING_PARENTS.has(parent.type)) return false;
          if (parent?.type === 'MetaProperty') return false;
          add(node.name);
          return false;
        default:
          return undefined;
      }
    };
    for (const node of nodes) walk(node, visit);
    return [...references].sort();
  };

  /**
   * Literal specifiers loaded at run time, with `import()`
   * (`dynamic(() => import('./x'))`) or with `require('./x')`, like the
   * whole-file fallback of `scanImportSources`. A computed specifier cannot
   * be resolved statically and is not listed.
   *
   * @param {any[]} nodes
   * @param {Set<any>} [skip]
   * @returns {string[]}
   */
  const collectDynamicImportSources = (nodes, skip) => {
    const sources = new Set();
    const visit = (node) => {
      if (skip?.has(node)) return false;
      const isLoaderCall = node.type === 'CallExpression'
        && (node.callee.type === 'Import' || (node.callee.type === 'Identifier' && node.callee.name === 'require'));
      const specifier = node.type === 'ImportExpression' ? node.source
        : isLoaderCall ? node.arguments[0]
          : undefined;
      if (specifier?.type === 'StringLiteral') sources.add(specifier.value);
      else if (specifier?.type === 'TemplateLiteral' && !specifier.expressions.length) sources.add(specifier.quasis[0].value.cooked);
      return undefined;
    };
    for (const node of nodes) walk(node, visit);
    return [...sources].sort();
  };

  /**
   * Load signals: work a part adds per render, request or run.
   *
   * @param {any[]} nodes
   * @param {Set<any>} [skip]
   * @returns {Record<string, number> | undefined} Non-zero counters only.
   */
  const collectSignals = (nodes, skip) => {
    const counters = {};
    const increment = (name) => {
      counters[name] = (counters[name] ?? 0) + 1;
    };
    let loopDepth = 0;
    const visit = (node) => {
      if (skip?.has(node)) return false;
      if (LOOP_STATEMENTS.has(node.type)) {
        loopDepth += 1;
        for (const key of Object.keys(node)) if (!SKIPPED_KEYS.has(key) && node[key]?.type) walk(node[key], visit);
        loopDepth -= 1;
        return false;
      }
      if (node.type === 'AwaitExpression') increment(loopDepth > 0 ? 'awaitInLoop' : 'awaits');
      if (node.type === 'TaggedTemplateExpression' && node.tag.type === 'Identifier' && node.tag.name === 'sql') increment('database');
      if (node.type === 'NewExpression' && node.callee.type === 'Identifier' && LOAD_SIGNAL_NAMES.observers.has(node.callee.name)) increment('listeners');
      if (node.type === 'ImportExpression') increment('dynamicImports');
      if (node.type === 'CallExpression' || node.type === 'OptionalCallExpression') {
        const callee = node.callee;
        if (callee.type === 'Import') increment('dynamicImports');
        else if (callee.type === 'Identifier') {
          const name = callee.name;
          if (name === 'fetch') increment('fetch');
          else if (LOAD_SIGNAL_NAMES.timers.has(name)) increment('timers');
          else if (LOAD_SIGNAL_NAMES.effects.has(name)) increment('effects');
          else if (LOAD_SIGNAL_NAMES.dataHooks.has(name)) increment('fetch');
          else if (importedLocals.has(name) && LOAD_VERB_PATTERN.test(name)) increment('projectCalls');
        } else if (callee.type === 'MemberExpression' || callee.type === 'OptionalMemberExpression') {
          const property = callee.property.type === 'Identifier' ? callee.property.name : callee.property.value;
          if (property === 'fetch') increment('fetch');
          else if (LOAD_SIGNAL_NAMES.listeners.has(property)) increment('listeners');
          else if (LOAD_SIGNAL_NAMES.database.has(property)) increment('database');
          else if (LOAD_SIGNAL_NAMES.iterators.has(property) && node.arguments[0]?.async) increment('awaitInLoop');
          else if (callee.object.type === 'Identifier' && importedLocals.has(callee.object.name) && LOAD_VERB_PATTERN.test(property ?? '')) increment('projectCalls');
        }
      }
      return undefined;
    };
    for (const node of nodes) walk(node, visit);
    return Object.keys(counters).length ? counters : undefined;
  };

  /**
   * Identities (`local=source#imported`) of the import bindings that
   * `references` consume and that the traversal cannot follow. Import
   * declarations are not part of any token range and a package or builtin
   * is traversed only by name and version, so without them
   * `import { Check as Icon }` → `import { X as Icon }` (or a change of
   * subpath) would leave every fingerprint unchanged. Bindings to project
   * files are left out: the traversal already keys them by target path and
   * symbol, and their specifiers change when code is moved between files.
   *
   * @param {string[]} references
   * @returns {string[]}
   */
  const importIdentities = (references) => {
    const identities = new Set();
    for (const reference of references) {
      if (reference.startsWith('/')) continue;
      const [localName] = reference.split('.');
      const binding = declarations.has(localName) ? undefined : imports.get(localName);
      if (!binding || resolver?.resolve(filePath, binding.source).kind === 'file') continue;
      identities.add(`${localName}=${binding.source}#${binding.imported}`);
    }
    return [...identities].sort();
  };

  /**
   * One hashed part: its token hash combined with the identity of the
   * imports it consumes (unchanged when it consumes none), plus references,
   * literal runtime loads and load signals.
   *
   * @param {string} tokenHash Hash of the part's own tokens.
   * @param {any[]} nodes Nodes the part covers.
   * @param {{ skip?: Set<any>, innerNames?: Set<string> }} [options]
   */
  const createPart = (tokenHash, nodes, options = {}) => {
    const references = collectReferences(nodes, options);
    const identities = importIdentities(references);
    return {
      hash: identities.length ? entryHash(`${tokenHash}\u0000${identities.join('\u0000')}`) : tokenHash,
      dynamicImportSources: collectDynamicImportSources(nodes, options.skip),
      references,
      signals: collectSignals(nodes, options.skip),
    };
  };

  const rangeOf = (node) => [node.start, node.end];
  const symbols = new Map();

  for (const [name, declaration] of declarations) {
    const parts = new Map();
    const single = declaration.nodes.length === 1 ? declaration.nodes[0] : undefined;
    const initializer = single?.valueNode?.type === 'VariableDeclarator' ? unwrapExpression(single.valueNode.init) : undefined;
    const callable = declaration.kind === 'function' || isFunctionInitializer(initializer)
      || (initializer?.type === 'CallExpression' && ['ArrowFunctionExpression', 'FunctionExpression'].includes(initializer.arguments[0]?.type));
    const symbol = { callable, kind: declaration.kind, layout: 'single', name, parts };
    symbols.set(name, symbol);
    const declarationNodes = declaration.nodes.map((entry) => entry.node);

    const functionNode = single && (single.valueNode?.type === 'FunctionDeclaration'
      ? single.valueNode
      : single.valueNode?.type === 'VariableDeclarator' && ['ArrowFunctionExpression', 'FunctionExpression'].includes(unwrapExpression(single.valueNode.init)?.type)
        ? unwrapExpression(single.valueNode.init)
        : undefined);
    const objectNode = single?.valueNode?.type === 'VariableDeclarator' ? unwrapExpression(single.valueNode.init) : undefined;

    if (functionNode?.body?.type === 'BlockStatement') {
      const inners = [];
      for (const statement of functionNode.body.body) {
        if (statement.type === 'FunctionDeclaration' && statement.id) inners.push({ name: statement.id.name, node: statement });
        if (statement.type === 'VariableDeclaration') {
          for (const declarator of statement.declarations) {
            if (declarator.id.type === 'Identifier' && isFunctionInitializer(declarator.init)) {
              inners.push({ name: declarator.id.name, node: statement.declarations.length === 1 ? statement : declarator });
            }
          }
        }
      }
      if (inners.length) {
        symbol.layout = 'container';
        const innerNames = new Set(inners.map((inner) => inner.name));
        const innerNodes = new Set(inners.map((inner) => inner.node));
        for (const inner of inners) {
          parts.set(`${name}/${inner.name}`, createPart(hashRanges([rangeOf(inner.node)]), [inner.node], { innerNames }));
        }
        parts.set(`${name}~shell`, createPart(hashRanges([rangeOf(single.node)], inners.map((inner) => rangeOf(inner.node))), [single.node], { innerNames, skip: innerNodes }));
        continue;
      }
    }

    if (objectNode?.type === 'ObjectExpression') {
      const members = objectNode.properties.filter((property) => (property.type === 'ObjectProperty' || property.type === 'ObjectMethod') && !property.computed
        && ['Identifier', 'StringLiteral', 'NumericLiteral'].includes(property.key.type));
      if (members.length) {
        symbol.layout = 'object';
        const memberNodes = new Set(members);
        for (const member of members) {
          const memberName = String(member.key.name ?? member.key.value);
          parts.set(`${name}.${memberName}`, createPart(hashRanges([rangeOf(member)]), [member]));
        }
        parts.set(`${name}~frame`, createPart(hashRanges([rangeOf(single.node)], members.map(rangeOf), { dropCommas: true }), [single.node], { skip: memberNodes }));
        continue;
      }
    }

    parts.set(name, createPart(hashRanges(declarationNodes.map(rangeOf)), declarationNodes));
  }

  // A top-level initializer runs when the module is imported, whether or not
  // its binding is used: if it does work there (timers, requests, listeners,
  // queries...), it belongs to the module shell, which every unit reaching
  // the file depends on. Work inside nested functions only runs when called.
  for (const { declarator, rangeNode } of topLevelDeclarators) {
    if (!declarator.init || isFunctionInitializer(declarator.init) || shellNodes.includes(rangeNode)) continue;
    const nestedFunctions = new Set();
    walk(declarator.init, (node) => {
      if (!NESTED_FUNCTION_TYPES.has(node.type)) return undefined;
      nestedFunctions.add(node);
      return false;
    });
    if (collectSignals([declarator.init], nestedFunctions)) shellNodes.push(rangeNode);
  }

  const shellRanges = [...ast.program.directives.map(rangeOf), ...shellNodes.map(rangeOf)];
  const moduleShell = createPart(entryHash(`${hashRanges(shellRanges)}\u0000${sideEffectImports.join('\u0000')}`), shellNodes);

  return {
    analyzer: ANALYZER_VERSION,
    exportAllSources,
    fileHash: entryHash(normalizeLineEndings(source)),
    imports,
    localExports,
    moduleShell,
    path: filePath,
    reExports,
    sideEffectImports,
    symbols,
  };
}
