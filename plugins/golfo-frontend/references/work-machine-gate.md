# Gate de máquina de trabajo (`~/.work`)

Fuente única del gate que aplican las skills que se activan sin pedido explícito: las que se cargan solas al tocar cierto tipo de código y las que se lanzan solas después de otra acción, como abrir un PR. El usuario marca sus máquinas de trabajo con un archivo o directorio `~/.work` en su home. En las máquinas personales esas skills se activan solas, como dice su descripción. En las de trabajo corren solo a pedido, porque ahí vale hacer solo lo pedido y seguir las convenciones del repo.

## Procedimiento

Es el primer paso de la skill, antes de leer sus referencias.

1. **¿Hubo pedido explícito?** Cuenta como pedido explícito cualquiera de estos casos:
   - el usuario invocó la skill (`/<skill>`, con o sin prefijo de plugin como `/<plugin>:<skill>`, o `$<skill>`) o la nombró;
   - el pedido es justamente lo que la skill cubre, como tarea en sí (la sección «Gate de máquina de trabajo» de cada skill da ejemplos);
   - otra skill que el usuario pidió de forma explícita la carga como complemento.

   Tocar código de ese tipo por otro motivo no cuenta: cambiar un texto en una pantalla no es pedir que se revise su UX. Con pedido explícito, seguir con la skill sin comprobar nada más.
2. **Sin pedido explícito, averiguar si es la máquina del trabajo.** Si las instrucciones globales del agente ya lo dicen (por ejemplo «no existe `~/.work`» o «existe `~/.work`»), usar eso. Si no lo dicen, comprobarlo con un solo comando de lectura: `test -e ~/.work` en bash o zsh, `Test-Path ~/.work` en PowerShell.
   - **Existe**, o no se puede comprobar (no hay shell, o el sandbox o un permiso bloquean el comando): terminar la skill acá. No leer sus referencias, no aplicar sus reglas, no mencionarla y seguir con la tarea del usuario como si no se hubiera cargado. Ante la duda se asume máquina de trabajo, porque correr de más ahí es el error que este gate evita; el usuario siempre puede pedirla.
   - **No existe** (el comando corrió y confirmó que no está): seguir con la skill.
3. El gate no se reporta en el cierre, salvo que el usuario pregunte por qué la skill no corrió.

## Cómo lo declara una skill

- En la descripción, junto al disparador automático: «(con `~/.work`, solo a pedido)».
- En el cuerpo, una sección «Gate de máquina de trabajo (`~/.work`)» antes del flujo, que linkea a la copia de este archivo en el plugin (`../../references/work-machine-gate.md`) y da uno o dos ejemplos de pedido explícito propios de la skill.
- El plugin suma este archivo en `shared/shared-files.json` y corre `pnpm sync-shared-files`.

Una skill que solo corre cuando el usuario pide justamente su tarea (responder un hilo de review, armar el cuerpo de un PR, publicar un paquete) no necesita el gate.

## Cierres que publican

Ninguna skill decide por su cuenta que un cambio termina commiteado, pusheado o en un PR. Lo hace cuando el usuario lo pidió o cuando las reglas globales del agente lo indican, y con `~/.work` nunca por iniciativa propia: deja los cambios sin commitear y los lista en el reporte. Lo mismo vale para lanzar un loop de review o mergear.
