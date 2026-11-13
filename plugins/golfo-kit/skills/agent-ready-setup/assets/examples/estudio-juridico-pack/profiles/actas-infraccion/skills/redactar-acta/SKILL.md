---
name: redactar-acta
description: Redacta un acta de infracción nueva desde la plantilla del estudio, con su cabecera, el relato de los hechos, las citas normativas y la parte resolutiva. Usar cuando se pida labrar, redactar o armar un acta de infracción.
---

# Redactar un acta de infracción

1. Pedir lo que falte para la cabecera: fecha, lugar, organismo, inspector y la persona o empresa infractora. No inventar ningún dato.
2. Tomar el próximo número libre en `actas/<año>/` y crear `actas/<año>/acta-<número>.md` desde `templates/acta.md`.
3. Relatar los hechos según `.agents/rules/actas-formato.md`, en párrafos numerados.
4. Citar cada norma según `.agents/rules/actas-citas-normativas.md`. Un número de norma o de artículo que no se pueda confirmar queda como `[norma a confirmar]`.
5. Revisar los datos personales según `.agents/rules/actas-datos-personales.md` antes de entregar el acta.
6. Responder con la ruta del acta y la lista de datos que quedaron a confirmar.
