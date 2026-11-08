# Estado automático de historias del backend

El Project compartido tiene Backlog, Ready, In progress (límite 3), In review
(límite 5) y Done. Este workflow solo mueve issues de smishing-backend que ya
están en el Project. Nunca crea ni cierra issues, no mueve PR ni otros repos,
y nunca asigna Done.

## Comportamiento

1. Abrir un PR borrador del mismo repositorio con título `feat(#6): ...` mueve
   la historia #6 de Backlog o Ready a In progress si hay cupo. Vincular el PR
   a la historia también activa el workflow nativo del Project para In progress.
2. Marcar el PR listo para revisión mueve esa historia a In review si hay cupo.
   El título antiguo `feat: ... (#3)` también se reconoce. Un título ambiguo
   con dos números de historias se ignora; el cuerpo y los commits no se usan
   como instrucciones de movimiento. Los commits `feat(#6): ...` sí sirven
   para trazabilidad y nunca cierran la historia por sí mismos.
3. Cerrar manualmente la historia **como completada**, tras verificar todos
   sus criterios, activa el workflow nativo Item closed -> Done. Un merge no
   hace ese cierre: el repositorio tiene desactivado Auto-close issues with
   merged linked pull requests y el Project tiene desactivado Pull request
   merged -> Done. `Closes #N` en un PR no tendrá efecto automático mientras
   esa configuración siga desactivada. Usarlo solo cuando el trabajo esté
   realmente completo; la verificación y cierre final siguen siendo humanos.

El workflow no baja In review a In progress por otro PR borrador y nunca toca
Done o una historia cerrada. Si el límite de una columna está lleno, deja el
estado igual y escribe una advertencia en Actions. Los límites 3 y 5 están
en scripts/project_status.py y deben cambiarse si cambia el Project.

## Acceso necesario antes de activar

El GITHUB_TOKEN normal de Actions no puede editar un Project de organización.
Un administrador debe crear o elegir una GitHub App, concederle **Organization
Projects: Read and write**, **Repository Issues: Read-only** y **Repository Pull
requests: Read-only**, e instalarla solo en `smishing-backend`. Guardar su
client ID como variable de Actions `PROJECT_APP_CLIENT_ID` y su clave privada
como secreto de Actions `PROJECT_APP_PRIVATE_KEY`. No pegar la clave en issues,
PR, commits ni chats. Después, crear la variable de Actions
`BACKEND_PROJECT_AUTOMATION_ENABLED=true`. Antes de hacerlo, el job permanece
desactivado aunque el workflow esté en main.

El código usa `pull_request_target` solo para eventos del mismo repositorio,
obtiene el script desde main y no ejecuta código del PR. La App se usa solo
para consultar el Project y actualizar Status. Si GraphQL devuelve 403,
revisar permisos Organization Projects, instalación y acceso de la App.

## Prueba controlada

1. Ejecutar `python -m unittest discover -s tests -p 'test_project_status.py'`.
2. Con el workflow en main, App configurada y variable habilitada, abrir un
   **PR borrador de prueba** del backend con un único título `feat(#N): ...`
   para una historia de prueba abierta y ya presente en el Project. Debe pasar
   de Backlog/Ready a In progress; no debe cerrarse el issue.
3. Marcar ese PR listo para revisión. Debe pasar a In review. Verificar que
   ningún issue de otro repositorio cambió. Convertirlo de nuevo a borrador
   no lo retrocede automáticamente, para evitar pérdidas de progreso.
4. Cerrar el PR de prueba sin merge y retirar el issue de prueba del Project
   cuando termine la verificación. No usar una historia real para la prueba.

El workflow nativo Item closed no distingue cierre `completed` de `not
planned`. Por procedimiento, cerrar como `completed` solo tras validar los
criterios. Si el equipo necesita distinguir esos motivos automáticamente,
habría que reemplazar esa regla global del Project con otra automatización
que compruebe `state_reason`.

