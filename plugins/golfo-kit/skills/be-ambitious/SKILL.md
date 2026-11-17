---
name: be-ambitious
description: >-
  Hace la tarea con la máxima ambición posible en vez de la versión mínima que
  cumple. Fija lo pedido como piso, imagina el techo (la versión que el usuario
  no sabía que podía pedir), elige los saltos más grandes que se pueden terminar
  en la sesión, pone a prueba los límites que el agente se pone solo, exprime el
  resultado en varias pasadas y cierra separando lo verificado de lo que no. La
  ambición va al resultado, nunca al riesgo. Usar con /be-ambitious o cuando
  pidan "sé ambicioso", "be ambitious", "andá más allá", "pensá en grande",
  "superá tus límites", "exprimilo al máximo", "dalo todo", "no te limites",
  "sorprendeme", "go all out" o "la mejor versión posible" de una tarea. No
  usar en tareas comunes sin ese pedido, cuando piden un cambio mínimo o
  acotado, ni para reescribir un prompt sin ejecutarlo (eso es deepen-prompt).
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "execution"
  tags: "ambition, moonshot, stretch, initiative, iteration, verification"
  command: "/be-ambitious"
---

# Be Ambitious

Un agente tiende a entregar la primera versión que cumple: lee el pedido al pie de la letra, resuelve lo justo y frena. Esta skill invierte ese default. Quien la invoca quiere ver hasta dónde se puede llegar, así que lo pedido pasa a ser el piso y el trabajo es acercarse al techo.

## Entrada

1. La tarea es el texto que sigue a `/be-ambitious`.
2. Si no hay texto, tomá el pedido más reciente del usuario en la conversación.
3. Si tampoco hay pedido previo, pedí la tarea en una sola línea y terminá el turno sin hacer nada más. Una tarea inventada no sirve para mostrar ambición.

## 1. Piso y techo

Antes de trabajar, escribí dos líneas:

- **Piso:** lo que se pidió, tal cual. Se entrega completo pase lo que pase: ningún salto justifica dejar a medias lo pedido.
- **Techo:** el mejor resultado imaginable para la meta que hay detrás del pedido, el que haría decir «no sabía que podía pedir esto». Pensalo sin filtrar por costo ni por dificultad. El filtro viene en el paso siguiente.

Para encontrar el techo, preguntate para qué quiere esto el usuario y cómo se vería el resultado hecho por el mejor equipo del mundo con tiempo de sobra.

## 2. Saltos

Un salto es una mejora que cambia de nivel el resultado, no un detalle prolijo. Recorré estas palancas y anotá al menos una idea audaz en cada una que aplique:

| Palanca | Pregunta |
|---|---|
| Alcance | ¿Puedo resolver la clase entera del problema y no solo este caso? |
| Imaginación | ¿Qué idea le serviría al usuario y no se le ocurrió pedir? |
| Profundidad | ¿Puedo llegar a la causa, a la fuente primaria, al dato real? |
| Oficio | ¿Puedo terminarlo al nivel de algo que se publica y no de un borrador? |
| Prueba | ¿Puedo demostrar que funciona en vez de afirmarlo? |
| Apalancamiento | ¿Puedo dejar algo reutilizable (script, test, plantilla, guía) para que la próxima vez cueste menos? |

Elegí los saltos más grandes que puedas **terminar** en esta sesión con lo que tenés a mano. Un salto a medias vale menos que no intentarlo, porque le deja trabajo sin cerrar al usuario. Si no llegás con todos, quedate con los de mayor efecto y mandá el resto al cierre como próximo salto.

Si la tarea tiene el techo bajo (un dato, una cuenta, un cambio de una línea), decilo en una frase, entregá lo pedido y sumá como mucho un salto que de verdad aporte, sin el bloque de cierre. Inflar una respuesta simple es relleno, y el relleno es lo opuesto a la ambición.

## 3. Límites autoimpuestos

La mayor parte de lo que frena a un agente no es un límite real sino una costumbre. Cuando te descubras en una de estas, hacé lo de la derecha:

| Costumbre | Qué hacer |
|---|---|
| Describir cómo se haría | Hacerlo. |
| «Podrías agregar…», «quedaría como mejora…» | Agregarlo ahora si entra en la sesión. |
| «No puedo verificar esto» | Intentarlo: correr el código, buscar la fuente, armar un caso de prueba. Solo después de un intento real se declara que no se pudo. |
| Cubrir una muestra o los casos principales | Cubrir todos, o decir cuáles quedaron afuera y por qué. |
| Dejar `TODO`, placeholders o «etc.» | Completarlos. |
| Dar una sola opción | Explorar varias en serio, elegir la mejor y decir por qué ganó. |
| Frenar en la primera versión que funciona | Seguir con el paso 4. |
| Suponer que algo es demasiado largo o difícil | Probar barato si lo es, antes de descartarlo. |

Usá todo lo que tengas disponible: herramientas, ejecución de código, búsqueda, lectura completa del material, trabajo en paralelo si el entorno lo permite. Tener una capacidad y no usarla es un límite que nadie te puso.

## 4. Exprimir

Con la primera versión completa, hacé al menos dos pasadas más. En cada una:

1. Releé el resultado como lo leería el crítico más exigente del campo y anotá lo que marcaría.
2. Preguntate qué lo haría el doble de bueno, no un poco mejor.
3. Hacelo.

Cortá cuando la mejora siguiente sea marginal, cuando necesite una decisión del usuario o cuando choque con una barrera de la sección siguiente.

## 5. Ambición en el resultado, no en el riesgo

Ser ambicioso es apuntar más alto, no pedir menos permiso. Estas barreras no se negocian, y respetarlas es parte de hacerlo bien:

- **Restricciones explícitas del usuario.** Plazo, presupuesto, stack, archivos que no se tocan, largo máximo: el techo se busca adentro de esas paredes. Si una restricción deja afuera el mejor salto, mencionalo en el cierre y no la rompas.
- **Acciones destructivas, irreversibles o hacia afuera.** Borrar, pisar historia, desplegar, publicar, enviar mensajes o gastar dinero se confirman antes, igual que sin esta skill. Preparalas hasta el último paso y pedí el ok.
- **Costo que se multiplica.** Si el techo implica horas de cómputo, servicios pagos o un cambio mucho más grande que lo pedido en un repo ajeno, mostrá piso y techo y preguntá antes de arrancar. En los demás casos, arrancá sin esperar.
- **Extras separables.** En un repo, seguí sus convenciones y dejá cada salto en un cambio que se pueda descartar sin romper lo pedido (commits, archivos o secciones aparte).
- **Honestidad.** Nunca inventes una fuente, un número, un benchmark ni un resultado de test para que el trabajo parezca más grande. Una afirmación sin verificar se marca como tal.

## Cierre

Terminá con este bloque, corto, después del trabajo:

```markdown
**Piso:** <lo pedido> — cumplido
**Saltos:** <cada salto hecho, en una línea, con la palanca que usó>
**Evidencia:** verificado: <qué y cómo> · sin verificar: <qué y por qué>
**Próximo salto:** <el salto más grande que quedó afuera y qué hace falta para darlo>
```

El próximo salto es una oferta concreta, no una lista de ideas: uno solo, el que más cambiaría el resultado.
