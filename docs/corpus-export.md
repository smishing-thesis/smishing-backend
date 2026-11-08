# Hito #16: exportación reproducible del corpus aceptado

Comando para un operador con acceso a la base, sin endpoint público de descarga:

```sh
uv run --locked python -m smishing_backend.export_corpus --output-dir exports
```

SMISHING_DATABASE_URL se configura fuera de Git. La salida se crea en
`exports/backend-<sha256>/corpus.csv` y `manifest.json`. El directorio exports
está ignorado por Git; no versionar corpus reales ni subirlos a CI. Los logs
del comando solo incluyen cantidad y versión, nunca filas ni revisores.

## Selección y formato

Una consulta PostgreSQL selecciona únicamente accepted. Por cada aporte usa
la última etiqueta manual o, si falta, la automática; nunca exporta ambas como
dos ejemplos. Pending y rejected no salen, ni siquiera si tienen etiquetas.
No se incluyen UUID, fecha de recepción/revisión, identidad del revisor ni
campos de dispositivo, remitente o dirección de red.

CSV UTF-8, salto de línea LF y comillas estándar:

| Columna | Valor |
| --- | --- |
| text | Texto anonimizado, conservado exactamente |
| label | 0 para safe/legítimo; 1 para smishing |
| label_origin | manual o device |
| model_version | Versión de la etiqueta automática; vacío si la elegida es manual |
| corpus_version | backend- seguido del SHA-256 canónico del contenido |

El lector real `smishing_charcnn.data.sources.load_local_legit_corpus` ya acepta
text y label numérica e ignora las columnas extra. No se cambia código del
modelo ni se exige editar el CSV. Ese lector aplica sus propios reemplazos de
placeholders, tal como en su pipeline. La exportación no los aplica ni infiere.
El experimento histórico que exige un corpus congelado, recuentos exactos y
device_id no se hace pasar por compatible con nuevos datos; este hito verifica
el lector estándar que consume el pipeline, no altera los experimentos publicados.

## Versión, integridad y publicación

Se ordenan filas por huella del texto y desempates estables; se calcula SHA-256
sobre representación JSON canónica del formato, texto, etiqueta, origen y
versión de modelo. UUID, orden de consulta y horas no participan. Cambiar una
etiqueta elegida cambia la versión; repetir el mismo contenido conserva todos
los bytes. No se añade una fecha de exportación que rompa la reproducibilidad.

El manifiesto incluye formato, versión, cantidad, nombre y SHA-256 del CSV.
Ambos archivos se escriben en staging y se publica el directorio completo por
renombrado en el mismo sistema de archivos. Si existe esa versión, se comprueba
que sus bytes coincidan; no se sobrescribe una exportación alterada.
Los archivos se crean con permisos de propietario y los directorios con 0700
en sistemas POSIX; en Windows se debe mantener el ACL del directorio del operador.
Un corpus vacío produce cabecera y manifiesto de cero filas; no significa que
haya datos suficientes para entrenar. La exportación carga el snapshot elegido
en memoria; evaluar streaming si el volumen futuro lo requiere.

## Evidencia

Suite con PostgreSQL 17 real: **152 pruebas pasaron**; Ruff, formato y mypy
correctos. Cubre exclusión de pendientes/rechazados, etiqueta corregida, origen,
reproducibilidad ante orden e IDs distintos, fallback automático, corrupción,
concurrencia y el comando real. Solo se usan SMS sintéticos.

La prueba de compatibilidad ejecuta el consumidor real, sin modificar, fijado
al commit `b9c72dcc27a42b0ddeb2a642683dd280e35e325f` del repositorio del modelo;
su huella se comprueba antes de cargarlo. Ve `tests/compat/README.md`. Leyó el
CSV exportado con las dos clases correctas y procesó los placeholders.
No se ejecutó entrenamiento ni se afirma calidad estadística con esas pruebas.

Revalidado sobre main con #13 y #15 integradas: 152 pruebas y dos subtests.
Un ensayo real con dos servidores HTTPS, certificado verificado y PostgreSQL
creó cuatro aportes sintéticos: dos aceptados, uno rechazado y uno pendiente.
Solo los dos aceptados llegaron al CSV; el lector real del modelo los leyó
y una segunda exportación produjo exactamente los mismos bytes.
[Resultado del flujo](evidence/corpus-flow-2026-11-08.json).
El PR #40 tiene base main; no se ha desplegado ni entrenado un modelo.
Las señales de envenenamiento específicas son la historia #14, no se simulan
por el hecho de que un aporte tenga revisión manual.
