---
name: react-act-test-fixes
description: "Resuelve warnings de act() en tests React (fix act warnings): not wrapped in act, timers y promesas."
license: MIT
metadata:
  version: "1.0.0"
  author: "Golfo"
  category: "testing"
  tags: "react, vitest, testing-library, act, async, context-optimized-v1.20.1"
  command: "/react-act-test-fixes"
---

# Resolver warnings act() en tests React

Localizar Promise, evento o timer que dispara `setState` y sincronizar el test con esa causa. Ejecutar los tests, corregirlos y verificar el resultado; no limitarse a recomendar cambios.

## Diagnóstico

1. Leer runner, scripts y versiones instaladas de React, RTL, user-event y Vitest. Conservar helpers y providers reales del proyecto. Usar las APIs de Vitest (`vi.*`); nunca introducir Jest.
2. Reproducir spec afectado y suite completa con el script real, incluyendo coverage si lo usa. Usar logs nuevos por ejecución: el warning puede aparecer únicamente en suite completa.
3. Correlacionar warning con test activo, renders y mensajes anteriores/posteriores. El owner stack puede señalar otro test; `Timeout.task` de jsdom indica un timer real. Seguir la actualización hasta su Promise/evento/timer antes de editar.

## Corrección según causa

- Interacción async, dropdown o popover: `const user = userEvent.setup(); await user.click(...)` / `await user.type(...)`; reemplazar `fireEvent` cuando no espera efectos async. Esperar estado final con `await screen.findBy*` o `await waitFor(() => expect(...))` antes de terminar. No envolver indiscriminadamente helpers RTL en `act`: ya integran ese mecanismo.
- Callbacks manuales de `ResizeObserver`, `IntersectionObserver` o listeners que actualizan React: dispararlos dentro de `act(() => { ... })`; usar `await act(async () => { ... })` si disparan trabajo async, esperando su Promise.
- Debounce con fake timers y handler que espera fetch: el avance sincrónico deja resolver la Promise fuera de `act`. Con fake timers de Vitest:

  ```ts
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  await user.type(screen.getByRole('textbox'), 'query');
  await act(async () => {
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS);
  });
  ```

  Usar duración del componente. Verificar disponibilidad de API; con timers legacy/versiones anteriores avanzar dentro de `await act(async ...)` y esperar Promise controlada del handler. No usar `delay: null` como arreglo de timeout de user-event.
- Promise resuelta manualmente: `await act(async () => { resolveSearch(results); await pendingPromise; });`, luego verificar resultado visible. No esperar dentro de `act` una Promise cuya resolución depende de una acción posterior fuera de ese bloque.
- Espera arbitraria con `setTimeout`: reemplazar por `findBy*` / `waitFor` con assertion observable. Si el test verifica deliberadamente un fallback temporizado, avanzar su timer dentro de `act`; no agregar sleeps ni subir timeouts.
- Timer interno al montar, sin resultado observable que esperar, durante operación larga como `axe`: drenar timers de montaje dentro de `act` y restaurar reales antes de ejecutar `axe`. Caso típico: hooks de accesibilidad de spinners del design system que agendan un timer al montar; confirmar esa causa en la versión instalada.

  ```ts
  vi.useFakeTimers();
  let container: HTMLElement;
  try {
    ({ container } = setup({ loading: true }));
    act(() => { vi.runOnlyPendingTimers(); });
  } finally {
    vi.useRealTimers();
  }
  await expect(axe(container)).resolves.toHaveNoViolations();
  ```

  Si callbacks de timers crean Promises, usar drenaje async dentro de `await act`. Restaurar timers en `finally` también en otros tests que los cambien; conservar limpieza del proyecto.

## Límites y validación

- No silenciar ni filtrar `console.error`, desactivar entorno `act`, mockear el design system, Tippy/Popper ni librerías de UI/plataforma. No cambiar producción únicamente para facilitar tests. Respetar `../../rules/frontend-testing.md` y `../../rules/no-unnecessary-mocks.md`.
- No agregar detectores temporales a setup global sin permiso explícito. Conservar protecciones existentes documentadas que evitan timers/listeners colgados.
- Ejecutar spec, suite completa dos veces y lint del proyecto. Para warnings sensibles al timing, repetir suite 1–2 veces bajo carga acotada; registrar PIDs propios y detener únicamente esos procesos en cleanup, nunca usar `pkill` global.
- Exigir tests verdes, cero `not wrapped in act` y cero `Exceeded timeout` en logs nuevos. Reportar causa, cambio, comandos y resultado; declarar cualquier validación pendiente y su motivo.

Origen: nota memory MCP «Patrón canónico para eliminar warnings act() en tests React (cualquier repo)», consultada al crear esta skill. No requiere memory MCP para ejecutarse.
Referencias de APIs: [React act](https://react.dev/reference/react/act), [user-event advanceTimers](https://testing-library.com/docs/user-event/options/#advancetimers), [Vitest fake timers](https://vitest.dev/api/vi.html#vi-advancetimersbytimeasync).
