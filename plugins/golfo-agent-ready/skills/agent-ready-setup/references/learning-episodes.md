# Episodios

Cómo cuenta la evidencia el aprendizaje de agent-ready-setup ([learning.md](learning.md)): qué es un
episodio, qué hacen los hooks, cómo se revisa un episodio al cerrarse y el barrido programado que
cierra los que nadie retoma.


La evidencia cuenta episodios distintos, no mensajes: repetir una instrucción tres veces en el mismo
episodio es una sola evidencia.

- Con `--episode`, el episodio es el que informó el hook de la sesión.
- Sin `--episode`, otra sesión o otro día empiezan un episodio nuevo: el episodio es la sesión más la
  fecha del mensaje.

**El hook del prompt** (`UserPromptSubmit` en Claude Code y en Codex, con
`.agents/hooks/learning-hook.sh`) corre `agent-ready learn episode --session <id> --touch` en cada
mensaje del usuario. Guarda por sesión, en `.git/info/agent-ready/episodes.json` (local, nunca
versionado), el episodio, cuándo empezó y la hora del último mensaje. El mensaje siguiente abre un
episodio nuevo si es de otro día de la máquina o si pasaron `learning.episodeGapHours` horas (4 por
defecto) sin mensajes. Así un chat largo cuenta varios episodios. Nada corre entre mensajes: el corte
se calcula cuando llega el próximo. Al abrir un episodio, el hook le dice al agente el id que tiene que
pasar en `--episode`; el resto de los mensajes no imprime nada.

- `agent-ready learn episode --session <id>` muestra el episodio actual de la sesión.
- `agent-ready learn episode --session <id> --scope-question` registra la única pregunta de alcance
  del episodio, y falla si ya se hizo: ahí el agente aplica la instrucción solo al documento actual y la
  registra sin `--explicit`.

**El resumen al iniciar la sesión** (`SessionStart`, también después de compactar en Claude Code)
corre `agent-ready learn summary`: las últimas líneas de `log.md` y los candidatos que esperan otro
episodio, sin las citas, para que el agente cuente como segunda evidencia una instrucción que vuelve.
No llama a ningún modelo. `learning.hooks.sessionStart` apagado lo deja sin salida.

El hook y el resumen no hacen nada mientras el repositorio no use el profile `learning` (el lockfile
lo registra en `profileOrder`) o `learning.enabled` esté apagado, y nunca hacen fallar el prompt ni la
sesión.

## Revisión al cerrar un episodio

La detección en la conversación puede perder una instrucción: el agente no la registró, o se compactó
el contexto antes. Por eso, al cerrarse un episodio, una revisión en background lee **solo los mensajes
del usuario** de ese episodio en el transcript local del provider y registra como candidatas, con
`source` `session-end`, las instrucciones que deben durar. Nunca escribe una rule ni una skill: el
agente decide en la sesión siguiente con las reglas de «La decisión» de [learning.md](learning.md), y el resumen de inicio se las
muestra.

Un episodio se cierra en cualquiera de estos momentos:

- **Al cerrar el chat:** `SessionEnd` en Claude Code (`learn episode --session <id> --end`).
- **Al empezar el siguiente episodio** del mismo chat.
- **Al barrer desde cualquier hook:** el prompt o el inicio de sesión de cualquier chat del repositorio
  cierra los episodios sin mensajes hace `learning.episodeGapHours` horas o de otro día.
- **Con el barrido programado** (abajo), aunque nadie vuelva a escribir en el repositorio.

Antes de compactar (`PreCompact` en Claude Code, `--review-now`) se revisa lo que el episodio lleva
dicho, y la revisión de su cierre empieza desde ahí. Codex no tiene esos dos eventos: sus episodios se
cierran con el barrido.

- El hook guarda en `episodes.json` el `transcript_path` y el provider del payload; la revisión corre
  con ese provider y el modelo de las revisiones de IA, sin herramientas ni sesión.
- Del transcript lee los mensajes del usuario y deja afuera lo que escribió el agente, los resultados de
  herramientas y lo que agrega el harness (comandos, recordatorios, contexto del entorno), que se
  reconoce por sus etiquetas. Un mensaje del usuario que empieza con otro markup se revisa igual.
- Una cita que no está en los mensajes del usuario se descarta: la revisión no puede inventar evidencia.
- Cada mensaje cuenta en un solo episodio: la ventana de cada revisión empieza donde terminó la
  anterior del mismo chat, aunque dos episodios empiecen con minutos de diferencia (por ejemplo, a
  medianoche). La ventana nunca pasa del momento en que cerró el episodio, así que un chat que se
  retoma enseguida revisa sus mensajes nuevos en el episodio siguiente.
- Lo que se manda al provider tiene un tope de caracteres: entran primero los mensajes más nuevos, y
  un mensaje enorme (un documento pegado) entra recortado.
- Cada episodio se revisa una vez. Si el provider falla o otra sesión tiene tomado el registro, queda
  en la cola para el barrido siguiente, hasta tres intentos. Un episodio sin transcript se cierra sin revisión.
- La cola vive en `episodes.json` hasta que cada revisión termina: si el barrido se corta (se apaga la
  máquina), otro barrido retoma esas revisiones una hora después.
- Nunca llama a un provider en CI ni en review mode: el episodio queda en la cola para la máquina del
  usuario.
- La revisión corre desacoplada del hook con `scripts/run-detached.py` (`agent-ready learn sweep`, con
  su log privado en `~/.cache/agent-ready-setup/learning-sweeps/`), así que el prompt no la espera.
- `learning.hooks.sessionEnd` apagado cierra los episodios sin revisarlos.

## Barrido programado

El apply registra una tarea del usuario en el planificador del sistema que corre
`agent-ready learn sweep --registered` cada `learning.sweep.intervalMinutes` minutos (60 por defecto).
Así un episodio que nadie retoma se cierra y se revisa como mucho `episodeGapHours` +
`sweep.intervalMinutes` después de su último mensaje.

- **Sin permisos de administrador:** Windows usa una tarea del usuario actual del Programador de tareas
  (`schtasks`, nunca `/RU SYSTEM`); macOS, un LaunchAgent en `~/Library/LaunchAgents` (nunca un
  LaunchDaemon); Linux, el `crontab` del usuario. Corre solo con la sesión del usuario iniciada.
- **Una tarea por máquina:** cada repositorio que usa learning se anota en
  `~/.cache/agent-ready-setup/learning-schedule/projects/`. La tarea corre tan seguido como pide el más
  frecuente, barre todos y olvida los que ya no están en el disco. Se va con el último repositorio.
- **El motor del último apply:** la tarea arranca `learning-schedule/run-sweep.py`, que apunta al
  motor que la registró. Cada apply la reescribe solo si cambió. El runner restaura el `PATH` y el
  `XDG_CACHE_HOME` del apply, porque el planificador arranca con un entorno mínimo. Si la tarea no le
  da salida (`pythonw.exe`), la escribe en `learning-schedule/last-sweep.log`.
- **Retiro:** `intervalMinutes: 0`, un apply sin el profile `learning` o `agent-ready remove` sacan al
  repositorio de la tarea. Si el sistema rechazó borrar la tarea del último repositorio, el próximo
  `learn schedule`, apply o barrido lo vuelve a intentar.
- **Si el sistema la rechaza** (una política de la máquina, `cron.deny`, sin `crontab`), el apply no
  falla: lo avisa en una línea, y `agent-ready status` y `agent-ready doctor` informan que falta. Los
  episodios se siguen cerrando al terminar el chat y desde otro hook. `agent-ready learn schedule`
  vuelve a registrarla, igual que un apply.
- **CI y review mode:** nunca tocan el planificador.
