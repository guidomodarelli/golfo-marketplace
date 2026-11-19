---
name: constants-refactor
description: Analiza y refactoriza constantes, literales funcionales y contratos cross-layer en cualquier repositorio y lenguaje. Usar al crear, mover o revisar constantes, limpiar hardcodes, mover valores a constants/ o al archivo de configuración, responder comentarios de PR sobre constantes o reducir duplicación entre capas. En máquinas marcadas con ~/.work solo corre si el usuario la invoca explícitamente (/constants-refactor o nombrándola). Centraliza los valores compartidos entre módulos o capas, los contratos y los literales mágicos sin nombre, y deja locales las constantes ya nombradas de un solo módulo. Usa constants/ para invariantes y contratos, y el archivo de configuración del proyecto (application.yml o .properties en Kotlin y Java, appsettings.json, settings) para valores operativos o ajustables. Se limita al alcance pedido, distingue valores runtime de constantes, preserva comportamiento y valida cada cambio.
license: MIT
metadata:
  version: "1.3.0"
  author: "Guido Modarelli"
  category: "refactor"
  tags: "refactor, constants, configuration, literals, cross-layer"
  command: "/constants-refactor"
---

# Constants Refactor

## Gate de entorno (primer paso, antes de cualquier otra lectura)

El usuario usa esta skill en máquinas personales, donde puede cargarse sola, y en máquinas de trabajo, donde solo debe correr a pedido. La máquina de trabajo se marca con un archivo o directorio `~/.work` en el home del usuario.

1. Determinar si el usuario la invocó explícitamente en este pedido: escribió `/constants-refactor` (con o sin prefijo de plugin, como `/golfo-engineering:constants-refactor` o `$constants-refactor`) o pidió por nombre usar la skill `constants-refactor`. Mencionar constantes, `constants/` o hardcodes no cuenta como invocación explícita.
2. Si fue explícita, saltear el chequeo y seguir al paso 4.
3. Si no fue explícita, comprobar si existe `~/.work` con un solo comando de lectura (`test -e ~/.work` en bash o zsh, `Test-Path ~/.work` en PowerShell):
   - **Existe**, o no se puede comprobar (no hay shell, o el sandbox o un permiso bloquean el comando): terminar la skill acá. No leer `references/`, no aplicar sus reglas, no mencionarla en la respuesta y seguir con la tarea del usuario como si no se hubiera cargado. Ante la duda se asume máquina de trabajo, porque correr de más ahí es el error que el gate existe para evitar; el usuario siempre puede invocarla explícitamente.
   - **No existe** (el comando corrió y confirmó que no está): seguir al paso 4.
4. Leer [references/workflow.md](references/workflow.md) completo y seguirlo. Es el procedimiento de la skill: objetivo, alcance, modos, clasificación, implementación, verificación y formato de salida.
