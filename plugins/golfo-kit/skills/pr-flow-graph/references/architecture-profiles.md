# Perfiles de arquitectura

Cada perfil dice qué `kind` usar para cada pieza y qué relaciones buscar en el código. Los valores de `kind` están definidos en [flow-graph-schema.md](flow-graph-schema.md). Elegí el perfil por cómo se comporta el código, no por el nombre de la librería: muchas variantes propias de un equipo siguen uno de estos patrones con otros nombres.

## Contenido

- [Flux unidireccional](#flux-unidireccional)
- [Redux y derivados](#redux-y-derivados)
- [MVVM y MVI](#mvvm-y-mvi)
- [Capas de backend](#capas-de-backend)
- [Si ninguno encaja](#si-ninguno-encaja)

## Flux unidireccional

`architecture: "flux-unidirectional"`. El dato viaja en un solo sentido: la vista crea una acción, un dispatcher la reparte, los stores cambian su estado y la vista se entera.

| Pieza | `kind` | Cómo reconocerla |
|---|---|---|
| Activity, Fragment, Composable, View | `view` | Renderiza y recibe eventos del usuario. |
| Acción, evento, intent | `action` | Objeto inmutable que describe qué pasó o qué se pide. |
| Dispatcher, bus | `dispatcher` | Único punto por el que pasan las acciones. |
| Store | `store` | Guarda estado y lo cambia solo al recibir una acción. |
| Efecto, middleware, action creator asíncrono | `effect` | Hace trabajo asíncrono y despacha el resultado. |
| Repositorio, cliente HTTP, DAO | `service` | Habla con la red o la base. |
| API, servicio de terceros | `external` | Vive fuera del repo. |

Relaciones a buscar: vista `dispatches` acción; acción `dispatches` dispatcher; dispatcher `updates` store; store `observes` vista (flecha del store a la vista); store o efecto `calls` servicio; servicio `requests` sistema externo.

Dónde suele haber relaciones `inferred`: el registro de un store en el dispatcher (inyección de dependencias, anotaciones o reflexión) y la suscripción de una vista (un observer montado en una clase base). Buscá el módulo de inyección y la clase base antes de marcar la relación; si la línea existe, es `verified`.

## Redux y derivados

`architecture: "redux"`. Igual que Flux con un solo store: usá `dispatcher` para el store raíz si el flujo pasa por él, `store` para cada reducer o slice, `effect` para thunks, sagas o epics y `state` para un selector relevante. Relaciones: componente `dispatches` acción; acción `updates` slice; slice `observes` componente (vía selector); thunk `calls` servicio.

## MVVM y MVI

`architecture: "mvvm"` o `"mvi"`. La vista observa un ViewModel que expone estado.

| Pieza | `kind` |
|---|---|
| Pantalla, Composable, Fragment | `view` |
| ViewModel, Presenter | `store` |
| UiState, sealed class de estado | `state` |
| Intent o evento de UI (MVI) | `action` |
| Use case, interactor | `service` |
| Repositorio, data source | `service` |
| API, base remota | `external` |

Relaciones: vista `calls` ViewModel (o `dispatches` un intent en MVI); ViewModel `updates` estado; estado `observes` vista; ViewModel `calls` use case; repositorio `requests` API. La navegación entre pantallas es `navigates`.

## Capas de backend

`architecture: "layered-backend"`.

| Pieza | `kind` |
|---|---|
| Ruta, controller, handler, consumer | `view` |
| Servicio de dominio, use case | `service` |
| Job, worker, listener asíncrono | `effect` |
| Repositorio, modelo, tabla | `data` |
| Cola, topic, evento publicado | `action` |
| Otro servicio, API de terceros | `external` |

Relaciones: handler `calls` servicio; servicio `calls` repositorio; servicio `dispatches` evento; evento `updates` worker; servicio `requests` sistema externo. En el flujo de negocio, los estados son los del recurso (por ejemplo, «Pedido pendiente», «Pedido pagado»).

## Si ninguno encaja

Describí la arquitectura en `architecture` con tus palabras, usá el `kind` más cercano para cada pieza y `other` cuando ninguno aplique. No fuerces un perfil: un grafo con roles mal puestos confunde más que uno con varios `other`.
