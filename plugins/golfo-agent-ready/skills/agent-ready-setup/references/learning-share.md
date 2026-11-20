# Aprender de varios clientes

Cómo el desarrollador junta lo que aprendieron los repos de varios clientes ([learning.md](learning.md))
con `agent-ready learn export` y `agent-ready learn harvest`, sin que salga ninguna cita, y cómo sube
un candidato a un pack con `agent-ready learn promote`.


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

## Promover a un pack

Lo que aprendieron varios clientes puede pasar al profile, para que lo reciba todo repo que lo usa. Lo
decide siempre el desarrollador, y llega al pack por pull request.

**`learn promote <id> --to <pack>`.** El id es un candidato del último `harvest` (`harvest-…`) o una
entrada aprendida del repo actual (`learn-…`). `--to` es el clon del pack que el desarrollador tiene (la
carpeta con `agent-ready-pack.json`) y `--profile`, el profile que recibe la rule; sin `--profile` alcanza
si el pack tiene un solo profile con assets.

- **Sin `--yes`** imprime el cambio (el archivo, la rule y el diff) y no toca el clon.
- **Con `--yes`** escribe la rule en una rama nueva del clon (`learn/promote-<id de la rule>`), la
  commitea con `Promoted-from: <id>`, pushea la rama y abre el pull request con `gh pr create`. El clon
  vuelve a la rama en la que estaba. Con `--no-pr` solo commitea, para pushear después.
- **Qué escribe.** Si el profile tiene una rule con la misma `key`, le cambia el statement y conserva su
  marcador, sus excepciones y sus detalles: la rule aprendida que la reemplazaba pide eso. Si no, agrega
  una rule nueva al final de `--file` (por defecto `rules/promoted.md` del profile), con un id que no use
  otra rule del pack, la `key` y los `paths` de lo aprendido. La rule pasa el lint de una rule atómica antes
  de escribir nada.
- **No escribe** sobre una rule `locked`, sobre una de la misma `key` para otro alcance, cuando el profile
  ya dice lo mismo, en un clon con cambios sin commitear ni si la rama ya existe. Una skill se sube a mano.
- **Nada de un cliente llega al pack.** El statement es el general de `harvest`, y el pull request dice
  cuántos repos lo aprendieron, nunca cuáles. El candidato del `harvest` queda marcado `promoted` en la
  caché.

**El duplicado después de actualizar.** Cuando el pack publica la rule y un repo actualiza el profile,
`agent-ready plan` (y el plan de cada apply) encuentra la rule aprendida que dice lo mismo que una del
profile (el mismo statement, salvo mayúsculas, espacios y el punto final, y el mismo alcance):

```text
Learned rule duplicated: learned/logging-library (learn-5db4a07240) says what acme:conventions/logger of acme/base says now. Retire it with agent-ready learn retire learn-5db4a07240
```

En `--json` sale en `learnedDuplicates`. Si la rule aprendida reemplazaba a esa misma rule, el plan no la
marca además «customized, review». El retiro lo confirma el desarrollador corriendo `learn retire`: saca
la rule aprendida y el próximo apply proyecta la del profile, que ahora dice lo mismo.
