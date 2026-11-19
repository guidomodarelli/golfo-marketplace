/**
 * Recognizes object members that only hold presentation (copy dictionaries
 * and visible text) by the name of the object or of the member. Policies use
 * it to leave coverage current when only copy changed; any member it does
 * not positively identify stays relevant.
 */

/**
 * Last word of an object name that marks it as a copy dictionary (`COPY`,
 * `PROVIDERS_COPY`, `saveMessages`, `UI_TEXT`): its members are presentation.
 */
const COPY_DICTIONARY_WORD_PATTERN = /^(?:cop(?:y|ies)|messages?|labels?|texts?|strings?|i18n|translations?|content)$/i;

/**
 * Last word of a member name that marks it as visible text (`providersTitle`,
 * `helpText`, `errorMessage`) instead of configuration or executable code.
 */
const PRESENTATION_MEMBER_WORD_PATTERN = /^(?:title|subtitle|heading|label|placeholder|description|tooltip|caption|copy|text|message)s?$/i;

/** Separators between the words of an identifier: dots, underscores, dashes and camelCase humps. */
const IDENTIFIER_WORD_SEPARATOR_PATTERN = /[._$-]+|(?<=[a-z])(?=[A-Z])/;

/**
 * @param {string} identifier Object or member name, possibly a dotted path.
 * @returns {string} Last word of the identifier, splitting camelCase and separators.
 */
function lastIdentifierWord(identifier) {
  const words = identifier.split(IDENTIFIER_WORD_SEPARATOR_PATTERN).filter(Boolean);
  return words.at(-1) ?? '';
}

/**
 * Only members positively identified by name as presentation leave the
 * coverage current; unknown configuration and executable members do not.
 *
 * @param {string} objectName Part before the first dot (`COPY` in `COPY.title`).
 * @param {string} member Part after the first dot.
 * @returns {boolean} Whether the object is a copy dictionary or the member is visible text.
 */
export function isPresentationMember(objectName, member) {
  return COPY_DICTIONARY_WORD_PATTERN.test(lastIdentifierWord(objectName)) || PRESENTATION_MEMBER_WORD_PATTERN.test(lastIdentifierWord(member));
}
