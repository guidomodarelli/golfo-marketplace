# Destinos por lenguaje: constantes y archivo de configuración

Leer cuando el repositorio no sea TypeScript/JavaScript o cuando haya que decidir si un valor va a `constants/` o al archivo de configuración. El criterio de decisión vive en "Mover al archivo de configuración" del `SKILL.md`; acá está solo el **dónde** de cada ecosistema.

## Cómo detectar el mecanismo del proyecto

Buscar lo que el repositorio ya usa antes de proponer un destino; ese mecanismo manda sobre esta tabla:

```bash
rg --files -g "application*.{yml,yaml,properties,conf}" -g "appsettings*.json" -g "settings*.py" -g "*.env.example"
rg -n "@ConfigurationProperties|@ConfigMapping|@Value\(|IOptions<|BaseSettings|environment\.config" .
```

Revisar también perfiles y overrides (`application-<perfil>.yml`, `appsettings.<Entorno>.json`, variables de entorno del deployment): un valor que ya tiene override en algún entorno es configuración, no constante.

## Tabla por ecosistema

| Ecosistema | Archivo de configuración | Binding tipado | Constantes (equivalente a `constants/`) |
|---|---|---|---|
| Kotlin / Java con Spring Boot | `src/main/resources/application.yml` o `application.properties`, más perfiles | Clase `@ConfigurationProperties` (con `@Validated` si hay límites) | Package `constants` |
| Kotlin / Java con Micronaut | `application.yml` | `@ConfigurationProperties` | Package `constants` |
| Kotlin / Java con Quarkus | `application.properties` | Interfaz `@ConfigMapping` | Package `constants` |
| Kotlin con Ktor | `application.conf` (HOCON) o `application.yaml` | Clase de settings cargada una vez desde `environment.config` | Package `constants` |
| Android (Kotlin / Java) | `build.gradle(.kts)` con `buildConfigField` por variante; `res/values/` para recursos | `BuildConfig` y recursos tipados (`R.integer`, `R.dimen`) | Package `constants`; el copy va a `strings.xml` |
| C# / .NET | `appsettings.json` y `appsettings.<Entorno>.json` | Options pattern (`IOptions<T>`) | Clase estática en un namespace `Constants` |
| Python | `settings.py` (Django) o módulo de settings | Clase de settings (por ejemplo `BaseSettings`) | Módulo `constants.py` o package `constants/` |
| Go | Sin archivo estándar: variables de entorno o flags | Struct de config cargado una vez (suele vivir en `internal/config`) | Bloque `const` en un package del dominio |
| TypeScript / JavaScript | Módulo `config/` que lee y valida el entorno | Objeto de config validado con el schema del proyecto | `constants/` |

Si el framework del repositorio no figura, aplicar el mismo patrón: un archivo de configuración versionado con defaults, un único punto de lectura tipado y un package o módulo de constantes para los invariantes.

## Kotlin y Java

- **Constantes de compilación.** Los argumentos de anotaciones (`@RequestMapping(PATH)`, `@Size(max = MAX_NAME_LENGTH)`, `@JsonProperty(FIELD)`) exigen una constante de compilación: `const val` en Kotlin, `static final` con inicializador literal en Java. Un valor inyectado desde configuración no compila ahí, así que ese valor queda como constante. Si la anotación acepta placeholders, usar esa variante para leer configuración (`@Scheduled(fixedDelayString = "\${jobs.sync.fixed-delay}")`, `@Value("\${...}")`).
- **Forma de las constantes.** Kotlin: `const val` top-level o dentro de un `object` del dominio (`object PaymentErrorCodes`); usar `companion object` solo cuando la constante pertenece al contrato de esa clase. Java: clase `final` con constructor privado; no usar una interfaz solo para colgar constantes. Agrupar por dominio dentro del package `constants`, no en una única clase `Constants` genérica.
- **Estados y códigos cerrados.** Si el conjunto es cerrado y el proyecto ya usa `enum class` o `sealed`, ese tipo es la fuente canónica; no duplicarlo con strings sueltos.
- **Lectura de configuración.** Preferir una clase de propiedades por dominio (`PaymentProperties` con prefijo `payment`) inyectada en los consumers. Varios `@Value("\${payment.timeout}")` repartidos repiten el nombre de la clave como hardcode y dispersan el default.
- **Defaults.** Al mover un valor, el literal actual pasa a ser el default: en el `application.yml` base o como valor por defecto de la propiedad (`val timeout: Duration = Duration.ofSeconds(5)`). Una clave obligatoria sin default hace fallar el arranque donde no esté definida, y eso es un cambio de comportamiento.
- **Unidades.** Preferir tipos con unidad (`Duration`, `DataSize`) en la clase de propiedades antes que un número con sufijo en el nombre; conservar el valor efectivo al convertir.
- **Tests.** Fijar el valor en la configuración de test (`application-test.yml`, propiedades del test) o construir la clase de propiedades a mano; no depender del archivo de producción.

## Android

- Valores que cambian por build type o flavor (base URLs, flags, ids de servicios) van a `buildConfigField` y se leen desde `BuildConfig`.
- Dimensiones, enteros de UI y copy van a `res/values/` (`dimens.xml`, `integers.xml`, `strings.xml`); `strings.xml` es el i18n del proyecto.
- Invariantes y contratos (claves de `Bundle`/`Intent`, nombres de preferencias, códigos) quedan como `const val` en el package `constants`.
