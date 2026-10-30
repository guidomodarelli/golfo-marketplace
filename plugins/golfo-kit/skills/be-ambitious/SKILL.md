---
name: be-ambitious
description: >-
  Convierte una tarea o prompt en una versión más profunda, no más grande: nombra
  el campo, dice qué haría un profesional top que no se pidió, el material más
  crudo del que partiría, los métodos y herramientas concretos y qué chequeo
  externo (ni el usuario ni el modelo) probaría que el resultado está bien, y
  reescribe el prompt para pedir exactamente eso. Usar con /be-ambitious o al
  pedir "be ambitious", "hacé este prompt más profundo", "qué haría un experto
  acá", "subí la vara de esta tarea" o "reescribí mi prompt como lo pediría un
  profesional". No sirve para ampliar alcance, sumar features ni pulir tono o
  largo de un prompt, ni para mejorar specs de docs/specs/ (eso es improve-spec).
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "prompting"
  tags: "prompt, depth, expert, primary-sources, verification, rewrite"
  command: "/be-ambitious"
  source: "Adaptada de be-ambitious de Dan McAteer (github.com/DannyMac180/skills, MIT), basada en un prompt de Felix Rieseberg"
---

# Be Ambitious

Sube el estándar de una tarea sin agrandarla: misma meta, mismo alcance, mejores fuentes, métodos más finos y una verificación que no dependa de la opinión de quien la hizo.

Adaptada de la skill `be-ambitious` de Dan McAteer ([DannyMac180/skills](https://github.com/DannyMac180/skills/tree/main/be-ambitious), licencia MIT), que a su vez parte de un prompt compartido por Felix Rieseberg (Anthropic).

## Entrada

1. La tarea es el texto que sigue a `/be-ambitious`.
2. Si no hay texto, tomá el pedido más reciente del usuario en la conversación.
3. Si tampoco hay pedido previo, pedí la tarea en una sola línea y terminá el turno sin hacer nada más.

## Más profunda, no más grande

- Conservá la meta y el alcance del usuario. Profundidad es un estándar más alto para el MISMO resultado.
- No sumes entregables, features, pantallas, integraciones ni tareas laterales. Si una idea agranda el trabajo en vez de mejorarlo, descartala.
- Si la tarea es trivial y no admite una versión más profunda útil, decilo y devolvé el prompt casi igual en vez de inflarlo.

## Análisis

Primero nombrá el campo con precisión (p. ej. «respuesta a incidentes SRE», «periodismo de investigación», «farmacología clínica», «performance web en Next.js»), no una categoría genérica como «programación». Después respondé estas cuatro preguntas para ese campo, nombrando cosas concretas:

1. **Lo que haría un profesional top y no se pidió.** Dos o tres movimientos que separan el trabajo experto del competente: explicitar qué decisión alimenta el trabajo, mirar tasas base, reproducir antes de arreglar, medir antes de optimizar, escribir el mejor contraargumento.
2. **El material más crudo.** Las fuentes primarias de las que partiría en vez de resúmenes: el dataset y no el gráfico, el expediente o la presentación regulatoria y no la nota periodística, los logs, trazas y el código y no el ticket, la sección de métodos y no el abstract. Si sabés dónde vive (repo, endpoint, base pública, archivo), decilo.
3. **Métodos y herramientas concretos.** Técnicas, instrumentos, librerías, comandos o marcos con nombre propio, y en una frase por qué cada uno sirve para ESTA tarea. En un repo, preferí lo que el proyecto ya usa antes que proponer herramientas nuevas.
4. **Qué probaría que está bien, aparte del usuario o del modelo.** Un chequeo externo: suite de tests o benchmark, una reproducción, datos de referencia, una respuesta conocida contra la cual comparar, una medición, un revisor o experto del dominio, el comportamiento de usuarios reales. Definí qué resultado cuenta como **pasa** y cuál como **falla**.

Si no conocés el campo lo suficiente para responder alguna pregunta, decilo explícitamente. Nunca inventes una fuente, un dataset, una herramienta o un autor para completar la lista.

## Reescritura

1. Escribí el prompt reescrito en un único bloque de código cercado que el usuario pueda copiar.
2. Tiene que pedir exactamente lo que dicen las cuatro respuestas: arrancar del material crudo, usar los métodos nombrados y cerrar con el chequeo externo y su criterio de pasa/falla.
3. Mantené la voz y el idioma del usuario, y el largo que haga falta, no más.

## Cierre

Terminá después de la reescritura con una sola línea que ofrezca ejecutarla ahora. No empieces la tarea, no abras archivos ni corras comandos para resolverla hasta que el usuario lo confirme.

## Formato de salida

```markdown
**Campo:** <campo concreto>

1. **Lo que haría un profesional top:** <movimientos>
2. **Material más crudo:** <fuentes primarias y dónde viven>
3. **Métodos y herramientas:** <nombre — por qué sirve acá>
4. **Chequeo externo:** <chequeo> — pasa si <criterio>; falla si <criterio>

<bloque de código con el prompt reescrito>

¿Lo corro ahora?
```
