# Fuentes

Investigación usada para los criterios de esta skill (octubre 2026). Las guías de design systems públicos (Material, Carbon, Polaris, Primer, GOV.UK, SAP Fiori, CMS) pesan más que los artículos de blogs; los números (tiempos, duraciones, cantidad de pasos) son puntos de partida, no reglas absolutas.

## Estados vacíos

- [SAP Fiori: Designing for empty states](https://www.sap.com/design-system/fiori-design-web/v1-136/foundations/best-practices/global-patterns/designing-for-empty-states): explicar propósito, causa y siguiente paso; tono no negativo.
- [Shopify Polaris: Empty state](https://polaris.shopify.com/components/empty-state): para listas, tablas o gráficos sin datos; banner para estados que no son ausencia de contenido.
- [Setproduct: Empty states UI design](https://setproduct.com/blog/empty-state-ui-design): tipos (primer uso, sin resultados, vaciado por el usuario).
- [Vendasta: Empty state best practices](https://www.vendasta.com/blog/user-experience-empty-state-best-practices/).

## Carga

- [VirtusLab: UX patterns beyond raw performance](https://virtuslab.com/blog/software-development/ux-patterns-beyond-raw-performance) y [SaaS UI: loading skeleton patterns](https://www.saasui.design/blog/saas-loading-skeleton-ux-patterns): umbrales 0,1 s / 1 s / 10 s, skeleton vs spinner vs barra, tiempo mínimo de display.
- [OpenReplay: Skeleton screens vs loading screens](https://blog.openreplay.com/skeleton-screens-vs-loading-screens--a-ux-battle/): evidencia mixta (Mejtoft 2018 a favor de skeletons, estudio de Viget en contra para layouts nuevos).

## Toasts, banners y canales

- [Carbon: Notification pattern](https://v10.carbondesignsystem.com/patterns/notification-pattern/): notificaciones inline persistentes vs toasts.
- [Material: Snackbars](https://material.io/components/snackbars): baja prioridad, una acción, de a uno; diálogo para dos o más acciones.
- [Polaris: Toast (deprecated)](https://polaris.shopify.com/components/deprecated/toast): mensajes cortos, rara vez para errores, banner para errores persistentes.
- [Guidewire Jutro: Toast](https://docs.guidewire.com/jutro/documentation/10.13/toast-component): no para información de campos ni crítica; límite de largo.
- [Chameleon: Toast notifications](https://www.chameleon.io/patterns/toast-notifications): no autodescartar lo que hay que consultar.
- NN/g, "Indicators, validations and notifications: pick the correct communication option" (2015), citado por el [Intelligence Community Design System](https://design.sis.gov.uk/components/badge/accessibility).
- [Carbon: Notification usage](https://carbondesignsystem.com/components/notification/usage/): inline, toast, actionable y callout; las notificaciones accionables no se descartan solas y llevan cierre.
- [Material 3: Snackbar guidelines](https://m3.material.io/components/snackbar/guidelines): una acción, cierre opcional, no tapar acciones principales.
- [GOV.UK: Notification banner](https://design-system.service.gov.uk/components/notification-banner/) y [Problem with the service pages](https://design-system.service.gov.uk/patterns/problem-with-the-service-pages/): banner para lo que afecta a toda la página; página dedicada cuando el servicio no está disponible, con qué hacer.

## Confirmar o deshacer

- [Primer: Delete pattern](https://primer.style/product/scenario-patterns/delete): deshacer para reversibles, diálogo para irreversibles.
- [Automattic design system: Destructive actions](https://system.automattic.design/foundations/destructive-actions/).
- [SaaS UI: Destructive actions confirmation](https://www.saasui.design/blog/saas-destructive-actions-confirmation-ux-patterns) y [DEV: confirmation vs undo vs soft delete](https://dev.to/137foundry/how-to-choose-between-confirmation-dialogs-undo-windows-and-soft-delete-patterns-1opj): ventana de deshacer de 5–10 s, escribir el nombre para alto impacto.

## Formularios y errores

- [CMS Design System: Validation](https://design.cms.gov/v/8.0.2/patterns/Forms/validation/) e [Inline error](https://design.cms.gov/components/inline-error): `aria-describedby`, no solo color, copy de qué falta hacer.
- [Yukon: help people recover from a form error](https://guide.yukon.ca/en/content-and-design/forms/user-experience-ux-standards-forms/how-help-people-recover-form-error): validación inline ~500 ms después de dejar de tipear (cita a NN/g).
- [Cengage: Inline errors](https://styleguide.cengage.com/inline-errors.html).
- [GOV.UK: Error message](https://design-system.service.gov.uk/components/error-message/) y [Error summary](https://design-system.service.gov.uk/components/error-summary/): error junto al campo con cómo corregirlo, resumen con links y foco al enviar.
- [WCAG 2.2: Error identification (3.3.1)](https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html), [Error suggestion (3.3.3)](https://www.w3.org/WAI/WCAG22/Understanding/error-suggestion.html) y [Use of color (1.4.1)](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html).
- [GOV.UK: Question pages](https://design-system.service.gov.uk/patterns/question-pages) y [One thing per page](https://designnotes.blog.gov.uk/2015/07/03/one-thing-per-page/); [GDS blog sobre GOV.UK Forms](https://gds.blog.gov.uk/2024/01/12/how-were-making-it-easier-to-access-government-forms-online/): check answers y confirmación.

## Wizards y onboarding

- [Visa: Wizard pattern](https://design.visa.com/patterns/wizard): guardar y salir, autosave.
- [Kompassify: Onboarding wizard guide](https://kompassify.com/blog/onboarding-wizard-guide) y [Userpilot: progressive disclosure](https://userpilot.com/blog/progressive-disclosure/): indicador de progreso, checklist corto, pasos salteables que quedan pendientes.

## Colecciones, búsqueda y upload

- [SaaS UI: data table patterns](https://www.saasui.design/blog/saas-data-table-ui-patterns): header y acciones masivas fijos, paginación vs scroll infinito.
- [Algolia: debouncing sources](https://www.algolia.com/doc/ui-libraries/autocomplete/guides/debouncing-sources.md) y [Voyado: autocomplete best practices](https://help.elevate.voyado.com/hc/en-gb/articles/26905204041116-Autocomplete-design-and-behavior-UX-best-practices): recientes al enfocar, "Buscar '…'", cancelar respuestas viejas.
- [SaaS UI: file upload patterns](https://www.saasui.design/blog/saas-file-upload-ux-patterns) y [Filestack: upload UI patterns](https://blog.filestack.com/file-upload-ui-patterns-improve-completion-rates/): validar antes de subir, estado y reintento por archivo.

## Operaciones asíncronas y recuperación

- [NN/g: Visibility of system status](https://www.nngroup.com/articles/visibility-system-status/): la primera heurística de Nielsen; el sistema informa siempre qué está pasando, con feedback oportuno.
- [NN/g: Progress indicators](https://www.nngroup.com/articles/progress-indicators/): indicador según la duración; porcentaje solo con avance medible.
- [Carbon: Inline loading](https://carbondesignsystem.com/components/inline-loading/usage/) y [Progress bar](https://carbondesignsystem.com/components/progress-bar/usage/): pending → éxito o error en el lugar de la acción; barra determinada solo con progreso medible.
- [Material 3: Progress indicators](https://m3.material.io/components/progress-indicators/guidelines): determinado frente a indeterminado.
- [Stripe: Idempotent requests](https://docs.stripe.com/api/idempotent_requests): claves de idempotencia para reintentar mutaciones sin duplicarlas.
- [AWS: Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/): espera creciente con jitter y límite de intentos.
- [MDN: AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController): cancelar peticiones en curso.
- [MDN: 409 Conflict](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/409), [429 Too Many Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429) y [Retry-After](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After).

## Verificación por código

- [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html): vigencia de los códigos de un solo uso y límites de intentos; la UX explica las restricciones sin debilitarlas.

## Accesibilidad del feedback

- [Adrian Roselli: Defining toast messages](https://adrianroselli.com/2020/01/defining-toast-messages.html).
- [WCAG 4.1.3 Status messages](https://www.disabilityworld.org/toolkit/standards/wcag/4-1-3-status-messages/): live region presente antes del mensaje, polite vs assertive. Versión oficial: [Understanding 4.1.3](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html).
- [WCAG 2.2: Timing adjustable (2.2.1)](https://www.w3.org/WAI/WCAG22/Understanding/timing-adjustable.html): lo que desaparece solo da tiempo o se puede pausar.
- [WCAG 2.2: Target size minimum (2.5.8)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), [Focus not obscured (2.4.11)](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html) y [Animation from interactions (2.3.3)](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html): áreas táctiles de 24×24 px, avisos que no tapan el foco y `prefers-reduced-motion`.
- [DEV: replacing toasts with accessible feedback patterns](https://dev.to/miasalazar/replacing-toasts-with-accessible-user-feedback-patterns-1p8l).

## Productos de referencia

- [Linear design breakdown](https://blakecrosley.com/guides/design/linear): keyboard-first, optimistic UI, paleta de comandos.
- [Modern SaaS patterns (Exxat DS)](https://cdn.jsdelivr.net/npm/@exxatdesignux/ui@0.6.59/consumer-extras/patterns/modern-saas-patterns.md): Notion (edición inline, slash commands) y Stripe Dashboard (chips de estado, activity log).
- [Botones en pending y doble envío](https://flaviocopes.com/courses/forms/pending-success-and-error/).
