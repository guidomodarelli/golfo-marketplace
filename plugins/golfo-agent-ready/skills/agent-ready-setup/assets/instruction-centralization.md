## Centralización recursiva de instrucciones

`AGENTS.md` es fuente canónica para instrucciones de agente. Regla aplica a cada `CLAUDE.md` del proyecto, tanto en raíz como en subdirectorios.

Para cada `CLAUDE.md`, usar únicamente `AGENTS.md` hermano ubicado en mismo directorio. Nunca sustituirlo por `AGENTS.md` de raíz, directorio padre u otro nivel.

Cuando usuario solicite agregar, modificar o eliminar contenido de cualquier `CLAUDE.md`:

1. Identificar directorio exacto de `CLAUDE.md` solicitado.
2. Resolver `AGENTS.md` hermano en ese directorio.
3. Aplicar cambio en `AGENTS.md`.
4. No editar directamente `CLAUDE.md`.
5. Evitar instrucciones duplicadas o contradictorias entre ambos archivos.

La referencia `@AGENTS.md` se resuelve relativa al directorio que contiene `CLAUDE.md`.
