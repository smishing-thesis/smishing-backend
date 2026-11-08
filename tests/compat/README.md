# Consumidor real fijado para compatibilidad

`charcnn-sources-b9c72dc.py.txt` es una copia **sin modificaciones** del código
`smishing_charcnn/data/sources.py` de
https://github.com/smishing-thesis/charcnn-smishing-model/tree/b9c72dcc27a42b0ddeb2a642683dd280e35e325f .

SHA-256: `2302f3c51b816e613aff3558112d7da1bcef42b25e3e3435f414d91824622b0a`.
La extensión .txt conserva los bytes originales sin reformatear código ajeno.
La prueba verifica esa huella, carga el módulo y llama a su lector real
`load_local_legit_corpus` sobre el CSV recién generado con datos sintéticos.
No es una reimplementación del lector. Actualizar la referencia exige volver
a contrastarla con el repositorio del modelo y revisar la prueba.

Pandas es solo una dependencia de desarrollo. No se instala TensorFlow ni se
entrena o clasifica desde el backend. No hay corpus, mensajes de evaluación ni
parámetros privados en esta copia; es únicamente código del consumidor.
