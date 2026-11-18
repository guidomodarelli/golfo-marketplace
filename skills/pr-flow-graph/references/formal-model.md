# Modelo formal en Lean 4

Opcional: solo cuando el pedido incluye `--lean` o habla de un modelo formal.

## Qué prueba y qué no

El modelo es una abstracción del flujo de negocio escrita a mano a partir del PR. Lo que Lean demuestra vale para ese modelo. No demuestra que el código Kotlin, TypeScript o el que sea se comporte igual: entre el código y el modelo hay un paso que hizo el agente, y ese paso puede estar mal. Decilo así en el reporte.

Sirve para dos cosas concretas: obliga a enumerar todos los estados y eventos (los casos olvidados aparecen como `match` incompletos) y deja propiedades escritas que un revisor puede leer y discutir.

## Cómo escribirlo

Escribí `pr-flow-graph/FlowModel.lean` a partir de `businessFlow`, sin importar Mathlib (así compila con una instalación limpia de Lean):

1. Un tipo inductivo `State` con un constructor por estado y otro `Event` con uno por `trigger`.
2. Una función total `step : State → Event → State`. Un evento que no aplica en un estado lo deja igual.
3. Una o más propiedades como `theorem`, elegidas porque importan para este PR.

El ejemplo completo está en [../assets/example-flow-model.lean](../assets/example-flow-model.lean): modela el flujo de [../assets/example-flow-graph.json](../assets/example-flow-graph.json) y compila con Lean 4.36.0 (la suite lo vuelve a compilar cuando `lean` está instalado). Leelo antes de escribir el tuyo y seguí su forma.

Propiedades que suelen valer la pena: un estado de éxito solo se alcanza por el camino previsto, un error no deja un estado de éxito, un estado terminal no tiene salida, una acción repetida no duplica el efecto.

Para tipos finitos chicos, `cases … <;> simp [step]` o `decide` alcanzan. Si una prueba no sale, la propiedad puede ser falsa: revisá el flujo antes de insistir, porque eso suele ser un hallazgo real sobre el PR.

## La compuerta

`flow-graph.mjs render --lean pr-flow-graph/FlowModel.lean` incluye el modelo en el grafo solo si:

- `lean` lo compila con código de salida 0, y
- el archivo no usa `sorry`, `admit` ni `axiom` (con cualquiera de ellos Lean acepta el archivo sin que la propiedad esté probada).

Qué informar en cada caso:

| Resultado | Qué decir |
|---|---|
| Compila | «Modelo formal incluido», con las propiedades probadas en una línea cada una. |
| Lean no está instalado | «Modelo formal no verificado: Lean no está instalado». Ofrecé el archivo como borrador sin verificar, nunca como modelo probado. |
| No compila o usa `sorry` | «Modelo formal no incluido», con el primer error. Corregilo y reintentá; si una propiedad resulta falsa, reportala como hallazgo. |

Lean se instala con [elan](https://github.com/leanprover/elan). No lo instales sin que el usuario lo pida.
