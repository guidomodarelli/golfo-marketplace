#!/usr/bin/env bash
# Verifica que la paleta y los tokens de motion del front matter de DESIGN.md
# (fuente de verdad) y las variables CSS del :root de assets/boilerplate/base.css
# declaren los mismos valores: colors.<token> -> --<token>, motion.<token> -> --motion-<token>.
#
# Uso: check-design-tokens.sh [ruta/a/DESIGN.md] [ruta/a/base.css]
# Exit: 0 sincronizado, 1 desalineado, 2 archivo ilegible o bloques ausentes.
set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIRECTORY
readonly DEFAULT_DESIGN_FILE="${SCRIPT_DIRECTORY}/../DESIGN.md"
readonly DEFAULT_STYLE_FILE="${SCRIPT_DIRECTORY}/../assets/boilerplate/base.css"
readonly EXIT_INVALID_INPUT=2

design_file="${1:-${DEFAULT_DESIGN_FILE}}"
style_file="${2:-${DEFAULT_STYLE_FILE}}"

for input_file in "${design_file}" "${style_file}"; do
  if [[ ! -r "${input_file}" ]]; then
    printf 'check-design-tokens: no se puede leer el archivo "%s".\n' "${input_file}" >&2
    exit "${EXIT_INVALID_INPUT}"
  fi
done

# Estados: el front matter de DESIGN.md va entre los dos primeros "---"; dentro de
# él solo interesan los bloques "colors:" y "motion:". Del CSS base, el primer
# ":root{". Los colores se comparan en minúsculas y expandiendo hex cortos
# (#ccc -> #cccccc); los valores de motion, en minúsculas y sin espacios.
# El bloque "motion:" es opcional, pero si existe debe coincidir con el :root.
awk -v design_file="${design_file}" -v style_file="${style_file}" '
function normalize_hex(hex_value) {
  hex_value = tolower(hex_value)
  if (length(hex_value) == 4) {
    hex_value = "#" substr(hex_value, 2, 1) substr(hex_value, 2, 1) substr(hex_value, 3, 1) substr(hex_value, 3, 1) substr(hex_value, 4, 1) substr(hex_value, 4, 1)
  }
  return hex_value
}

function normalize_motion(motion_value) {
  motion_value = tolower(motion_value)
  gsub(/[ \t]/, "", motion_value)
  return motion_value
}

BEGIN { front_matter_state = 0; inside_colors = 0; inside_motion = 0; inside_root = 0; root_done = 0; token_count = 0; variable_count = 0; motion_token_count = 0; motion_variable_count = 0 }

# Los checkouts con finales de línea CRLF (Windows) se leen igual que los LF.
{ sub(/\r$/, "") }

FNR == 1 && FILENAME == design_file && $0 == "---" { front_matter_state = 1; next }
front_matter_state == 1 && $0 == "---" { front_matter_state = 2; next }

front_matter_state == 1 {
  if ($0 ~ /^[a-z]/) {
    inside_colors = ($0 ~ /^colors:/)
    inside_motion = ($0 ~ /^motion:/)
  } else if (inside_motion && match($0, /^  [a-z0-9-]+:[ ]+/)) {
    motion_name = substr($0, 3, RLENGTH - 2)
    sub(/:.*/, "", motion_name)
    motion_value = substr($0, RLENGTH + 1)
    sub(/[ ]+#.*$/, "", motion_value)
    gsub(/"/, "", motion_value)
    motion_tokens[motion_name] = normalize_motion(motion_value)
    motion_token_order[++motion_token_count] = motion_name
  } else if (inside_colors && match($0, /^  [a-z0-9-]+:[ ]+"#[0-9A-Fa-f]+"/)) {
    declaration = substr($0, RSTART, RLENGTH)
    token_name = declaration
    sub(/^  /, "", token_name)
    sub(/:.*/, "", token_name)
    token_value = declaration
    sub(/^[^"]*"/, "", token_value)
    sub(/"$/, "", token_value)
    tokens[token_name] = normalize_hex(token_value)
    token_order[++token_count] = token_name
  }
  next
}

FILENAME == style_file && !root_done && $0 ~ /^:root[ ]*\{/ { inside_root = 1; next }

inside_root {
  if ($0 ~ /^\}/) { inside_root = 0; root_done = 1; next }
  declaration_count = split($0, declarations, ";")
  for (index_in_line = 1; index_in_line <= declaration_count; index_in_line++) {
    declaration = declarations[index_in_line]
    gsub(/^[ \t]+|[ \t]+$/, "", declaration)
    if (declaration ~ /^--motion-[a-z0-9-]+:/) {
      motion_variable_name = substr(declaration, 10)
      sub(/:.*/, "", motion_variable_name)
      motion_variable_value = declaration
      sub(/^[^:]*:/, "", motion_variable_value)
      motion_variables[motion_variable_name] = normalize_motion(motion_variable_value)
      motion_variable_order[++motion_variable_count] = motion_variable_name
    } else if (declaration ~ /^--[a-z0-9-]+:[ ]*#[0-9A-Fa-f]+$/) {
      variable_name = substr(declaration, 3)
      sub(/:.*/, "", variable_name)
      variable_value = declaration
      sub(/^[^:]*:[ ]*/, "", variable_value)
      variables[variable_name] = normalize_hex(variable_value)
      variable_order[++variable_count] = variable_name
    }
  }
}

END {
  if (token_count == 0) {
    printf "check-design-tokens: no se encontró el bloque \"colors:\" en el front matter de \"%s\".\n", design_file > "/dev/stderr"
    exit 2
  }
  if (variable_count == 0) {
    printf "check-design-tokens: no se encontraron variables de color en el \":root{\" de \"%s\".\n", style_file > "/dev/stderr"
    exit 2
  }
  problem_count = 0
  for (position = 1; position <= token_count; position++) {
    token_name = token_order[position]
    if (!(token_name in variables)) {
      printf "falta la variable --%s (token colors.%s = %s)\n", token_name, token_name, tokens[token_name]
      problem_count++
    } else if (variables[token_name] != tokens[token_name]) {
      printf "valor distinto en --%s: front matter %s, :root %s\n", token_name, tokens[token_name], variables[token_name]
      problem_count++
    }
  }
  for (position = 1; position <= variable_count; position++) {
    variable_name = variable_order[position]
    if (!(variable_name in tokens)) {
      printf "sobra la variable --%s: no existe colors.%s en el front matter\n", variable_name, variable_name
      problem_count++
    }
  }
  for (position = 1; position <= motion_token_count; position++) {
    motion_name = motion_token_order[position]
    if (!(motion_name in motion_variables)) {
      printf "falta la variable --motion-%s (token motion.%s = %s)\n", motion_name, motion_name, motion_tokens[motion_name]
      problem_count++
    } else if (motion_variables[motion_name] != motion_tokens[motion_name]) {
      printf "valor distinto en --motion-%s: front matter %s, :root %s\n", motion_name, motion_tokens[motion_name], motion_variables[motion_name]
      problem_count++
    }
  }
  for (position = 1; position <= motion_variable_count; position++) {
    motion_variable_name = motion_variable_order[position]
    if (!(motion_variable_name in motion_tokens)) {
      printf "sobra la variable --motion-%s: no existe motion.%s en el front matter\n", motion_variable_name, motion_variable_name
      problem_count++
    }
  }
  if (problem_count > 0) {
    printf "check-design-tokens: %d diferencia(s) entre el front matter de \"%s\" y el :root de \"%s\".\n", problem_count, design_file, style_file
    exit 1
  }
  printf "check-design-tokens: %d colores sincronizados", token_count
  if (motion_token_count > 0) printf " y %d tokens de motion", motion_token_count
  printf " en \"%s\".\n", design_file
}
' "${design_file}" "${style_file}"
