# Detección

Cómo se elige la selección sin manifest: las señales de cada profile, su precedencia, el stack primario
y las capabilities sugeridas. Leer para explicar un resultado de la detección o los formatos de Gradle
reconocidos. Es parte del contrato de [profiles-and-lockfile.md](profiles-and-lockfile.md).

El campo opcional `detect` de un profile declara señales estáticas. Un profile sin
`detect` sigue disponible para selección manual, como `business-flows`, que no tiene una
señal útil. `scripts/agent_ready_detection.py` es el único evaluador, y lo comparten los
subcomandos `detect`, `resolve` y `plan` de `agent-ready-state.py`.

La evaluación solo lee archivos del proyecto: no ejecuta builds, gestores de paquetes ni
nada que nombre un catálogo. No entra a directorios enlazados y un archivo que resuelve
fuera del proyecto no cuenta. Tampoco lee archivos de más de 2 MiB. Un `package.json`
inválido o un archivo que no se puede leer se informa como aviso y no aporta señales.

```json
"detect": {
  "supersedes": ["java"],
  "signals": [
    { "type": "glob", "patterns": ["*/src/main/AndroidManifest.xml"] },
    { "type": "gradle-plugin", "ids": ["com.android.application"] }
  ]
}
```

| `type` | Lista | Coincide cuando |
|---|---|---|
| `file` | `paths` | existe ese archivo, relativo a la raíz, sin comodines |
| `glob` | `patterns` | un archivo coincide por segmentos con `*`, `?` y `[...]`, o con `**` como segmento completo (hasta 8 niveles). Los comodines no entran a `node_modules`, `vendor`, `build`, `dist`, `target`, `out`, `.git`, `.gradle`, `.idea`, `.next`, `.venv`, `venv`, `__pycache__`, `.agents`, `.claude` ni `.codex` |
| `package-dependency` | `names` | el `package.json` raíz declara el nombre en `dependencies`, `devDependencies`, `peerDependencies` u `optionalDependencies` |
| `gradle-plugin` | `ids` | un script de Gradle o el version catalog declara el plugin |
| `gradle-dependency` | `coordinates` | un script de Gradle o el version catalog declara `grupo:artefacto` |

Alcanza con una señal. Las rutas distinguen mayúsculas en todos los sistemas y deben
quedar dentro del proyecto; un `detect` inválido hace fallar la carga del catálogo.

**Gradle.** Se leen como texto y sin comentarios `build.gradle`, `build.gradle.kts`,
`settings.gradle` y `settings.gradle.kts` de la raíz, y `build.gradle` y `build.gradle.kts`
hasta dos niveles de módulos, más `gradle/libs.versions.toml`. Nunca se ejecuta el build
ni se interpreta Groovy o Kotlin.

| Dónde | Formatos reconocidos |
|---|---|
| Plugin en un script | `id 'x'`, `id "x"`, `id("x")`, con `version` o `apply false` detrás; `apply plugin: 'x'`, `apply(plugin = "x")` |
| Plugin en el catalog (`[plugins]`) | `alias = { id = "x", ... }`, `alias = "x:versión"` |
| Dependencia en un script | notación de string con cualquier configuración: `implementation 'g:a:1.0'`, `api("g:a")` |
| Dependencia en el catalog (`[libraries]`) | `alias = "g:a:versión"`, `{ module = "g:a" }`, `{ group = "g", name = "a" }` |

No se reconocen `kotlin("android")`, plugins aplicados por `buildSrc`, convention plugins
o `apply from:`, valores en variables, la notación de mapa `group: 'g', name: 'a'` ni un
`alias(libs...)` sin catalog en esa ruta. Como es una lectura de texto, un string con ese
formato cuenta aunque no se use.

**Precedencia de la selección.**

1. `--profiles` o `--stack`.
2. `profiles` de `.agents/agent-ready.json`.
3. Detección inicial, solo sin manifest: el apply guarda el stack primario en el manifest, y
   sus `defaults` se resuelven en cada apply. Sin ninguna señal de stack no es un error: el apply
   deja solo el núcleo y guarda `"profiles": []` (lo mismo que `--profiles none`), y `detect` sale
   con 0. Una lista vacía en el manifest también es una selección: una señal posterior no la cambia.

`detection.enabled: false` apaga la detección y las sugerencias ([configuration.md](configuration.md)).
Una detección posterior nunca cambia el manifest. `plan` informa la selección (`Selected
by`), las señales y, si apuntan a otro stack, un aviso. Para cambiar la selección hay que
pedirlo con `--stack` o `--profiles`.

**Stack primario.** Detectar varias señales no aplica varios stacks. Una capa reemplaza a
las que requiere cuando coinciden juntas, y hereda lo que ellas reemplazan. Una capa solo
coincide si coinciden también las capas que requiere: un `app/layout.tsx` sin `next` en
`package.json` es un archivo más, no el App Router. La más
específica es el primario y trae las otras por `requires`. `supersedes` declara qué stacks
reemplaza uno sin requerirlos, y solo se usa donde uno es una especialización del otro:

| Coincidencias | Primario | Motivo |
|---|---|---|
| `react` + `nextjs` + `nextjs-app-router` | `nextjs-app-router` | la capa más específica: `next` en `package.json` y un `app/layout.*` (o `src/app/layout.*`) |
| `react` + `nextjs` | `nextjs` | `next` sin App Router |
| `react` + `node` | `react` | un proyecto React también tiene `package.json`; vale igual para las capas de Next.js |
| `react` + `android` | `react` | el directorio `android/` de React Native o Capacitor es un host generado |
| `android` + `java` | `android` | una app Android también tiene Gradle |
| cualquier otra, por ejemplo `node` + `go` | ninguno | nada dice cuál es el principal: se listan las coincidencias y se pide una selección explícita, que puede nombrar las dos (`--profiles go,node`) |

Si queda un solo stack después de quitar los reemplazados, es el primario. Si quedan
varios, `detect` sale con 3, y `resolve`, `plan` y un apply sin selección fallan antes de
escribir; el hook avisa y omite la proyección. Con una selección, el stack primario es el
primero que ningún otro profile seleccionado requiere. Un ciclo en `supersedes` invalida el
catálogo, y el resultado no depende del orden de los archivos ni del catálogo.

**Sugerencias.** Una capability con `detect` que coincide y falta en la selección se
sugiere en `plan`, con el profile, el archivo inspeccionado y la señal. No entra al
manifest ni instala herramientas, tampoco en una detección inicial, y no cambia los `defaults`:
`--stack android` sigue sin `browser` aunque `plan` lo sugiera por `androidx.webkit:webkit`. No se sugiere una capability incompatible con la selección.

`detect` no forma parte del digest de un profile en el lockfile, porque no cambia lo que
se proyecta: ajustar una señal no marca un update pendiente en repos ya aplicados.
