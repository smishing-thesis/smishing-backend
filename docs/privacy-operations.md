# Logs y respaldos — #17

Ejecutar el servidor soportado con `uv run python -m smishing_backend.server`,
TLS_CERT_PATH y TLS_KEY_PATH fuera del repositorio. SMISHING_LOG_DIR configura
el directorio (por defecto var/log/smishing-backend). El runner desactiva access
logs y encabezados de proxy y aplica PrivateFormatter tanto a consola como a
archivo. No registrar cuerpos/headers, direcciones, IDs, hashes o versiones por
solicitud. Solo tiempo y evento fijo. Mensajes arbitrarios de dependencias,
args, extras y tracebacks se descartan sin interpolar. No usar logging externo
de peticiones ni SQL echo, ni captura automática de errores con request bodies.

Retención: rotación diaria UTC, seis archivos históricos y uno activo (siete
días de operación). La poda se ejecuta en la rotación; si el servicio se detiene,
el operador debe retirar archivos con antigüedad superior a siete días antes
de reiniciar. La retención de consola la debe limitar la plataforma a siete
días; no se configura ni se afirma verificada infraestructura aún inexistente.
Restringir permisos del directorio a 0750 y el acceso a operadores autorizados.

Respaldos: tablas del corpus contributions, labels y model_versions, auditoría
interna reviews/risk_flags y metadatos de migración; nunca el entorno,
credenciales, directorios de logs,
archivos del dispositivo o corpus originales. El esquema almacena únicamente
texto aportado anonimizado, etiqueta, versiones y revisión acotada; no hay
campos de dispositivo, remitente o red. El hash y UUID son del aporte, no del
contribuyente. Los IDs seudónimos de revisores pertenecen a la auditoría del
operador, no identifican a quienes aportan ni sus dispositivos. Usar pg_dump
de base dedicada, cifrar el respaldo y controlar
acceso; política propuesta de siete días. El servicio no crea respaldos por su
cuenta ni publica exportaciones. Auditar una restauración aislada antes de
adoptar backups. La anonimización tiene los límites de docs/anonymization.md.

Pruebas: solicitudes aceptada y rechazada reales sobre PostgreSQL sintético,
búsqueda de texto, dirección de prueba y metadatos en archivo; excepción con
texto no se imprime. Configuración de retención y mensajes de access log probados.
Pendiente #17: revisar los respaldos y configurar/verificar retención de consola
en la infraestructura que el equipo decida desplegar. No se declara esa revisión.
