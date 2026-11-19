# Patrones SSR y BFF Data Fetching

## Contenido

- Matriz de decisión
- Patrón trabajado: Gestión de Operadores
- Template SSR
- Template BFF same-origin
- Registro de excepción
- Señales de arquitectura incorrecta

## Matriz de decisión

| Situación | Ruta recomendada | Motivo |
|---|---|---|
| Dato conocido durante request y necesario para primer render | SSR → service → upstream | Evita request cliente, flicker y exposición de contexto server |
| Query/params iniciales determinan contenido visible | SSR → service → upstream | Validar antes de usar y serializar snapshot mínimo |
| Catálogo estable para filtros iniciales | SSR → service → upstream | Disponible antes de hydration |
| Búsqueda o filtro aplicado por usuario | Browser → BFF → service → upstream | Interacción posterior, controles server-side preservados |
| Paginación posterior | Browser → BFF | Mantiene auth, mapping y observabilidad server-side |
| Polling o frescura posterior | Browser → BFF | Permite cancelación sin exponer upstream |
| Mutation | Browser → BFF | Requiere schema, authz, ownership y reglas de negocio |
| Trabajo server-only sin browser | Server → service → upstream | No crear BFF innecesario |
| Recurso público que satisface todas condiciones de excepción | Browser → upstream | Documentar restricción y revisar periódicamente |
| Cualquier condición de excepción falla | Browser → BFF | Boundary server sigue siendo necesario |

## Patrón trabajado: Gestión de Operadores

Este flujo ilustra responsabilidades, no nombres obligatorios.

### 1. Hook SSR

`index.hooks.server.ts`:

1. valida query;
2. exige usuario autenticado y permiso;
3. deriva facilities desde atributos confiables;
4. instancia service server-only con `req`;
5. obtiene catálogos iniciales en paralelo;
6. guarda DTO en `res.locals`;
7. degrada catálogos opcionales de forma independiente.

No llama `/api` por HTTP: service ya existe en mismo proceso y conserva request context.

### 2. Props adapter

`getServerSideProps`:

- lee `res.locals`;
- aplica defaults browser-safe;
- copia query validada necesaria para primer render;
- no conoce hosts, scopes ni payloads upstream;
- no repite llamadas ni lógica de negocio.

### 3. Browser service

`app/services/...`:

- usa baseURL relativa `/api/...`;
- expone métodos para filtros, búsqueda, paginación, polling y mutations;
- no importa server service;
- no contiene host, scope, cookie ni authorization header upstream.

### 4. BFF route

`api/...`:

- autentica;
- aplica schema validation;
- verifica permiso exacto;
- comprueba ownership de facility/entity;
- normaliza input validado;
- llama service;
- devuelve contrato controlado y error seguro.

### 5. Server service

`api/services/...`:

- compone uno o más upstreams;
- traduce nombres browser a nombres upstream;
- revalida reglas de negocio;
- hidrata/normaliza respuesta;
- devuelve modelo de dominio, no response HTTP completa.

### 6. Upstream clients

`api/clients/...` encapsula:

- `baseURL`;
- scopes y cookies;
- headers derivados de request;
- timeout/retries;
- configuración por ambiente.

Browser no debe conocer estas decisiones.

## Template SSR

```ts
async function loadPageData(req, res, next) {
  const input = readValidatedInput(req);
  const identity = requireAuthorizedIdentity(req);
  const service = new FeatureService(req);

  try {
    const result = await service.getInitialData({ input, identity });

    res.locals.featurePageData = toBrowserSafeDTO(result);
    return next();
  } catch (error) {
    logSafeServerError('Feature initial data failed', { operation: 'getInitialData' });
    return renderControlledFailure(req, res);
  }
}
```

Adapter:

```ts
export const getServerSideProps = (_req, res) => ({
  props: res.locals.featurePageData ?? EMPTY_BROWSER_SAFE_STATE,
  settings: { title: 'Feature' },
});
```

Evitar:

```ts
// Incorrecto: loopback al mismo proceso.
await fetch('http://localhost:3000/api/feature');
```

## Template BFF same-origin

Browser service:

```ts
const client = createBrowserRestClient({ baseURL: '/api/feature' });

export async function searchItems(params, signal) {
  const { data } = await client.get('/items', { params, signal });
  return data;
}
```

BFF route:

```ts
router.get(
  '/items',
  requireAuthentication,
  validateItemsQuery,
  requireFeaturePermission,
  requireEntityOwnership,
  async (req, res) => {
    try {
      const data = await new FeatureService(req).searchItems(req.query);
      return res.json(toBrowserSafeDTO(data));
    } catch (error) {
      logSafeServerError('Feature search failed', { operation: 'searchItems' });
      return res.status(500).json({ message: 'Unable to load items' });
    }
  }
);
```

Server service/client:

```ts
class FeatureService {
  constructor(req) {
    this.client = FeatureUpstreamClient(req);
  }

  async searchItems(filters) {
    const response = await this.client.get('/internal/items', {
      params: toUpstreamFilters(filters),
    });

    return response.data.results.map(toDomainItem);
  }
}
```

## Registro de excepción browser → upstream

```markdown
Direct upstream exception:
- Endpoint:
- Owner:
- Why BFF is not feasible:
- Authentication/credentials:
- Data classification and exposed fields:
- CORS evidence:
- Transformations, policies, or observability not applied:
- Mitigations:
- Revisit trigger/date:
```

Restricción válida puede ser ausencia real de egress server-side hacia recurso público que browser sí alcanza. Ahorrar un salto, escribir menos código o “CORS funciona” no son restricciones suficientes.

## Señales de arquitectura incorrecta

- `useEffect` carga contenido imprescindible para primera pantalla aunque server ya conoce input.
- URL upstream absoluta aparece en bundle browser.
- SSR llama `localhost`, propio hostname o propia route `/api`.
- Componente React importa service que depende de `req` o config server.
- Browser construye scopes, service cookies o headers internos.
- BFF responde `res.json(upstreamResponse.data)` sin DTO explícito.
- UI oculta acción, pero route no verifica permission u ownership.
- Browser envía `userId`, `facilityId` o tenant y server los confía sin comparar con identidad.
- CORS se presenta como authentication o authorization.
- Polling llama upstream directamente para “evitar latencia”.
- Excepción directa no identifica owner, clasificación de datos ni revisit trigger.
