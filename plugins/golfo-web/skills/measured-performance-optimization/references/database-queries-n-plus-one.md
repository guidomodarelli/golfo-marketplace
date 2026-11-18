# Queries lentas y N+1

## Qué es el problema N+1

Se hace 1 query para traer una lista y después 1 query más por cada elemento de esa lista.

Ejemplo: traer 100 usuarios y sus pedidos.

```sql
-- 1 query para los usuarios
SELECT id, name FROM users LIMIT 100;

-- + 100 queries, una por usuario
SELECT * FROM orders WHERE user_id = 1;
SELECT * FROM orders WHERE user_id = 2;
-- ... hasta user_id = 100
```

Son 101 queries cuando con 1 o 2 alcanza. El costo crece linealmente con la cantidad de items: con 1.000 usuarios son 1.001 viajes a la base, cada uno con su latencia de red, parseo y pool de conexiones ocupado. En desarrollo, con poca data y la base local, no se nota; en producción, sí.

## Detectar

- Log de queries del ORM durante un request: muchas queries con la misma forma y distinto parámetro.
- `pg_stat_statements`: queries con más tiempo total o medio acumulado, para elegir cuál optimizar.
- Sentry: issue de tipo "N+1 Query" o spans `db` repetidos dentro de una transacción.
- Señales en el código: aplicar el criterio de Database And Remote Calls de la skill `review-performance` (plugin `golfo-engineering`); acá solo se confirma con las señales en runtime de esta sección.
- Un endpoint cuyo tiempo crece proporcionalmente con el tamaño de la página.
- Un job periódico que relee toda una ventana en cada corrida y casi todo sale sin cambios: no es N+1 sino barrido completo; ver [incremental-sweep-jobs.md](incremental-sweep-jobs.md).

## Corregir

Elegir según el caso. JOIN, `WHERE IN` y eager loading solo aplican cuando ambas relaciones viven en el mismo datastore; si los datos hijos pertenecen a otro servicio, no hay tabla compartida que consultar y corresponde un endpoint batch o DataLoader (ver [Equivalentes en ORMs y APIs](#equivalentes-en-orms-y-apis)).

**JOIN** — una sola query, conveniente cuando se necesitan columnas de ambas tablas y la relación no multiplica demasiado las filas:

```sql
SELECT u.id, u.name, o.id AS order_id, o.total
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
WHERE u.id IN (SELECT id FROM users LIMIT 100);
```

**WHERE IN** — dos queries, conveniente cuando el JOIN duplicaría muchas filas; después se agrupa en memoria con un `Map`:

```sql
SELECT id, name FROM users LIMIT 100;
SELECT * FROM orders WHERE user_id IN (1, 2, ..., 100);
```

<a id="equivalentes-en-orms-y-apis"></a>**Equivalentes en ORMs y APIs**:

- Eager loading: Prisma `include`, TypeORM `relations`/`leftJoinAndSelect`, Sequelize `include`, Django `select_related`/`prefetch_related`, Rails `includes`, Hibernate `JOIN FETCH`/`@BatchSize`, GORM `Preload`.
- GraphQL, llamadas remotas por item o datos que pertenecen a otro servicio: DataLoader (batch + cache por request) o un endpoint batch del servicio dueño, que reciba la lista de ids y devuelva los resultados en una sola llamada.

Cuidar listas de `IN` muy grandes (partir en chunks) y no traer relaciones que la vista no usa.

## Queries lentas que no son N+1

- `EXPLAIN ANALYZE` de la query: buscar seq scans sobre tablas grandes, sorts en disco y estimaciones de filas muy erradas.
  - `EXPLAIN ANALYZE` ejecuta la sentencia de verdad: usarlo solo contra una base local, de staging o una réplica de lectura. Contra producción, únicamente con autorización explícita del usuario y límites acotados (sentencia exacta, filas afectadas y `statement_timeout`), con el mismo criterio que los generadores de carga de [measurement-tools.md](measurement-tools.md#alternativas-sin-mcp); sin esa autorización, usar `EXPLAIN` sin `ANALYZE` o telemetría pasiva (`pg_stat_statements`, APM).
  - Para `INSERT`/`UPDATE`/`DELETE` usar `EXPLAIN` sin `ANALYZE`, o envolverlo en una transacción revertida (`BEGIN; EXPLAIN ANALYZE ...; ROLLBACK;`). El `ROLLBACK` deshace las filas, pero no evita la carga ni los locks que toma la sentencia, los avances de secuencias ni los efectos externos de triggers.
- Índices sobre columnas de `WHERE`, `JOIN` y `ORDER BY`. En un índice compuesto, primero las columnas comparadas por igualdad y después la de rango (o la del `ORDER BY` que el índice debe resolver), sin copiar el orden textual del `WHERE`; verificar con `EXPLAIN` antes y después.
- Paginación por cursor/keyset en lugar de `OFFSET` grande.
- Proyectar solo las columnas necesarias en lugar de `SELECT *`.
- Mover filtros, sorts y agregaciones a la base en lugar de hacerlos en memoria.

## Métricas antes/después

- Cantidad de queries por request (por ejemplo, 101 → 2).
- Tiempo total de DB y p95 del endpoint con la misma data.
- Plan de `EXPLAIN ANALYZE` y tiempo de ejecución de la query (en sentencias de escritura, ver la advertencia de [Queries lentas que no son N+1](#queries-lentas-que-no-son-n1)).
- Para que no vuelva: un test de integración que cuente queries del endpoint y falle si supera el límite esperado.
