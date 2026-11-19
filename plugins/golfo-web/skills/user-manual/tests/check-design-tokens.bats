#!/usr/bin/env bats

setup() {
  export CHECK_SCRIPT="${BATS_TEST_DIRNAME}/../scripts/check-design-tokens.sh"
  export FIXTURE_FILE="${BATS_TEST_TMPDIR}/DESIGN.md"
  export STYLE_FIXTURE="${BATS_TEST_TMPDIR}/base.css"
}

# Escribe un DESIGN.md mínimo con front matter (paleta en $1 y bloque motion
# opcional en $3) y un base.css cuyo :root contiene las declaraciones de $2.
write_design_fixture() {
  local colors_block="$1"
  local root_declarations="$2"
  local motion_block="${3:-}"
  local motion_section=""
  if [[ -n "${motion_block}" ]]; then
    motion_section="motion:
${motion_block}"
  fi
  cat > "${FIXTURE_FILE}" <<EOF
---
name: Fixture
colors:
${colors_block}
${motion_section}
typography:
  body-md:
    fontSize: 14px
---

## Boilerplate

Vive en assets/boilerplate/.
EOF
  cat > "${STYLE_FIXTURE}" <<EOF
:root{
  ${root_declarations}
  --sans:'DM Sans',sans-serif;
}
body{color:var(--primary);}
EOF
}

@test "el DESIGN.md de la skill tiene front matter y :root sincronizados" {
  run bash "${CHECK_SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"colores sincronizados"* ]]
  [[ "${output}" == *"tokens de motion"* ]]
}

@test "acepta tokens de motion con comillas, comentarios y espacios distintos a los del :root" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;--motion-duration-fast:120ms;--motion-easing-standard:cubic-bezier(0.2,0,0,1);' '  duration-fast:   120ms   # hover
  easing-standard: "cubic-bezier(0.2, 0, 0, 1)"'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"1 colores sincronizados y 2 tokens de motion"* ]]
}

@test "falla cuando una variable de motion no coincide con el token" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;--motion-duration-base:300ms;' '  duration-base: 200ms'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"valor distinto en --motion-duration-base: front matter 200ms, :root 300ms"* ]]
}

@test "falla cuando un token de motion no tiene variable en el :root" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;' '  duration-fast: 120ms'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"falta la variable --motion-duration-fast"* ]]
}

@test "falla cuando el :root declara una variable de motion que no es token" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;--motion-duration-slow:400ms;'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"sobra la variable --motion-duration-slow"* ]]
}

@test "acepta hex cortos y mayúsculas equivalentes al token" {
  write_design_fixture '  primary: "#1A1A1A"
  border-neutral: "#CCCCCC"' '--primary:#1a1a1a;--border-neutral:#ccc;'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"2 colores sincronizados"* ]]
}

@test "falla cuando un valor del :root no coincide con el token" {
  write_design_fixture '  label: "#6B6B6B"' '--label:#888888;'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"valor distinto en --label: front matter #6b6b6b, :root #888888"* ]]
}

@test "falla cuando un token no tiene variable en el :root" {
  write_design_fixture '  primary: "#1A1A1A"
  link: "#1A4F7A"' '--primary:#1a1a1a;'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"falta la variable --link"* ]]
}

@test "falla cuando el :root declara un color que no es token" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;--bg:#f8f7f4;'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"sobra la variable --bg"* ]]
}

@test "ignora variables que no son colores, como las familias tipográficas" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 0 ]
  [[ "${output}" != *"--sans"* ]]
}

@test "devuelve 2 si el front matter no tiene bloque colors" {
  cat > "${FIXTURE_FILE}" <<'EOF'
---
name: Fixture
---
EOF
  printf ':root{\n  --primary:#1a1a1a;\n}\n' > "${STYLE_FIXTURE}"

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 2 ]
  [[ "${output}" == *'no se encontró el bloque "colors:"'* ]]
}

@test "devuelve 2 si el archivo no existe" {
  run bash "${CHECK_SCRIPT}" "${BATS_TEST_TMPDIR}/no-existe.md"

  [ "${status}" -eq 2 ]
  [[ "${output}" == *"no se puede leer el archivo"* ]]
}

@test "acepta un DESIGN.md con finales de línea CRLF" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;'
  sed -i 's/$/\r/' "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"1 colores sincronizados"* ]]
}

@test "lee el :root del base.css, no un :root que quede en DESIGN.md" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;'
  printf ':root{\n  --primary:#000000;\n}\n' >> "${FIXTURE_FILE}"

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${STYLE_FIXTURE}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"1 colores sincronizados"* ]]
}

@test "devuelve 2 si el base.css no existe" {
  write_design_fixture '  primary: "#1A1A1A"' '--primary:#1a1a1a;'

  run bash "${CHECK_SCRIPT}" "${FIXTURE_FILE}" "${BATS_TEST_TMPDIR}/no-existe.css"

  [ "${status}" -eq 2 ]
  [[ "${output}" == *"no se puede leer el archivo"* ]]
}
