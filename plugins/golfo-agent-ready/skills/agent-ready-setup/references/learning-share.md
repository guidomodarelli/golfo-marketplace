# Aprender de varios clientes

Cómo el desarrollador junta lo que aprendieron los repos de varios clientes ([learning.md](learning.md))
con `agent-ready learn export` y `agent-ready learn harvest`, sin que salga ninguna cita.


Cada cliente tiene su repo, privado, y lo aprendido puede tener datos suyos. Por eso **nada sale solo de
un repositorio**: no hay envío automático. Lo junta el desarrollador, a pedido, desde los clones que ya
tiene en su máquina.

**Qué sale de un repo.** Solo los `statement` de lo aprendido (estado `learned`), con su `kind`, `key` y
`paths`. Nunca las citas del usuario, que quedan en `candidates.json`, ni los candidatos que esperan, ni
documentos. `export` y `harvest` leen el registro y descartan la evidencia al leerla: ninguna cita llega
a la salida, al provider ni a la caché.

**Participación.** `learning.share` viene encendido: todo repo que el desarrollador tiene clonado
participa del `harvest`. Un cliente que no quiere participar pone `{"learning": {"share": false}}` en su
manifest (`.agents/agent-ready.json`), y `harvest` no lee nada más de ese repo. Apagarlo nunca necesita la
aprobación de la máquina; encenderlo desde el repo, sí, como cualquier valor que afloja.

**`learn export`.** Escribe lo aprendido del repo en un JSON (`--output`, o por la salida estándar), con
el nombre del repo (`--name`, o su carpeta). Es para el cliente que hostea su repo y no le da acceso al
desarrollador: lo revisa, lo edita si quiere y se lo pasa. `harvest --export <archivo>` lo lee igual que
un clon, y de cada ítem toma solo `statement`, `kind`, `key` y `paths`: lo demás que tenga el archivo se
ignora.

**`learn harvest`.** Lee los repos de `--repos` (o, sin esa opción, los de `learning.harvest.repos` de la
config de usuario: un repo no puede sumarse a esa lista) y los exports de `--export`. Propone como
candidato lo que aprendieron al menos `learning.harvest.threshold` repos distintos (2 por defecto, o
`--threshold`):

1. Con menos repos que el umbral con algo aprendido, no hay nada que agrupar y no llama a ningún modelo.
2. Si no, un provider (`--provider`, Claude por defecto) agrupa los statements que piden lo mismo y
   escribe cada grupo como un statement general, sin nombres, expedientes, montos ni nada propio de un
   cliente. Ve los repos solo como `repo-1`, `repo-2`…, nunca por su nombre ni su ruta, y trata los
   statements como datos.
3. Un grupo vale si sus índices existen, cada statement está en un solo grupo, junta al menos el umbral
   de repos y su statement es una oración que `record` aceptaría (y su `key`, si trae una, también).
4. En CI, en review mode o si el provider falla, propone solo lo que varios repos aprendieron con las
   mismas palabras (salvo mayúsculas, espacios y el punto final), y el reporte dice por qué.

Cada candidato tiene un id `harvest-<hash>`, el statement general, de qué repos sale y el statement
original de cada uno. El resultado queda en la caché del desarrollador
(`~/.cache/agent-ready-setup/learning-harvest/latest.json`), nunca en un repositorio: `harvest` no
escribe nada en los repos que lee. Un repo que no existe o no se puede leer figura con su estado y no
frena a los demás. Un repo o export que se pasa dos veces se lee una, y dos fuentes con el mismo nombre
(un clon y el export del mismo cliente) cuentan como un solo repo: nada suma evidencia de más. Un
statement viaja con sus `paths`, y un grupo nunca junta alcances distintos: el candidato conserva el suyo.
