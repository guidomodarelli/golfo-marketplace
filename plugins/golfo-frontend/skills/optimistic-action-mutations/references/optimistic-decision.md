# Decidir la clase de una mutación

Fuente única de cuándo una mutación es **optimistic**, **pending-first** o **server-confirmed**. El [catálogo](action-catalog.md) da la clase por defecto de cada tipo de operación; esta tabla decide con los datos reales.

## Clases

| Clase | Qué hace la UI | Cuándo |
|---|---|---|
| **Optimistic** | Actualiza al instante la representación local con la intención del usuario, envía, y reconcilia o revierte con la respuesta. | La acción es segura, reversible y reconciliable: si falla, volver al estado anterior no causa daño ni confusión. |
| **Pending-first** | Da feedback inmediato de que la acción está en curso (control en pending, ítem marcado "enviando"), pero no muestra el resultado de negocio hasta la confirmación. | El resultado depende de una decisión del servidor (validación, disponibilidad, cálculo) o la acción tiene un efecto externo, pero esperar sin feedback sería peor. |
| **Server-confirmed** | Espera la respuesta autoritativa antes de comunicar o aplicar el cambio definitivo; mientras tanto, solo el pending del control. | Mostrar un éxito que después se revierte causaría daño, confusión o un riesgo de seguridad. |

## Criterios

Recorrer en orden; la primera respuesta que obliga a una clase más conservadora gana:

1. **¿El efecto es irreversible o no compensable?** (cobro, envío real de SMS o email, eliminación definitiva, proceso externo disparado) → server-confirmed, o pending-first si el usuario necesita ver que se está procesando.
2. **¿Involucra seguridad, identidad o acceso?** (autenticación, verificación, permisos, roles, restablecer contraseña) → server-confirmed.
3. **¿El servidor decide el resultado con datos que el cliente no tiene?** (validación de negocio, stock, cupo, cálculo de precio, unicidad) → pending-first.
4. **¿Es probable que falle?** (límites del plan conocidos, permisos dudosos, conflictos frecuentes) → pending-first. Un optimismo que se revierte seguido enseña al usuario a no creerle a la UI.
5. **¿El rollback es caro o confuso?** (afecta orden, contadores de otros, navegación, otras entidades) → pending-first, salvo que el rollback pueda restaurar exactamente el baseline.
6. **¿Es idempotente o se puede hacer idempotente?** Si no y se va a reintentar, necesita una clave de idempotencia o pasa a pending-first.
7. **¿Otros clientes ven el cambio y pueden contradecirlo?** (colaboración en tiempo real, recursos compartidos) → optimistic solo con reconciliación desde el servidor (versión o evento) y resolución de conflictos.
8. **Si nada de lo anterior aplica** y la acción es frecuente y reversible (toggle, voto, reordenar, archivar con deshacer, mensaje de chat con estado de envío) → optimistic.

## Casos que nunca anticipan éxito

- Pagos, cobros y suscripciones.
- Autenticación y verificación de identidad.
- Envío real de SMS, emails o notificaciones.
- Permisos, roles y acceso.
- Eliminaciones irreversibles.
- Acciones que disparan procesos externos o consecuencias no compensables.

En estos casos la velocidad percibida sale del pending inmediato y de un buen copy, no de un resultado falso. Una UI rápida no justifica mostrar un éxito que el servidor todavía no confirmó.

## Lecturas

GET, refetch, invalidación, paginación y búsqueda no se clasifican con estas clases: no hay resultado de negocio que anticipar. Se revisan con la sección de lecturas del [catálogo](action-catalog.md#lectura-y-obtención-de-datos). Prefetch o placeholder data no son optimismo: muestran datos ya conocidos, marcados como provisorios.

## Reportar la decisión

Una línea por operación: `<operación> → <clase>: <criterio que decidió>`. Por ejemplo: `Archivar curso → optimistic: reversible con deshacer, idempotente`; `Reenviar código → pending-first: envío real de SMS, cooldown del servidor`; `Pagar → server-confirmed: cobro no compensable, consultar estado ante timeout`.
