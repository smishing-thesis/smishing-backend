# Cuarentena — #12

Todos los aportes nacen pending. El puerto interno register_review admite una
sola transición a accepted o rejected, con fecha del servidor y motivo acotado:
quality_checked / invalid_content / out_of_scope. No admite texto libre ni
identificadores del revisor. No existe una ruta pública de revisión ni exportación;
esas funciones requieren sus historias y controles de acceso correspondientes.

Una actualización condicional hace la transición atómica: dos revisiones
concurrentes no se pisan. PostgreSQL exige fecha y motivo para estado terminal;
un trigger prohíbe cambiar una decisión ya registrada. La consulta interna
accepted_for_training filtra accepted explícitamente, nunca pending o rejected.
No se conecta automáticamente a entrenamiento ni se genera un dataset.

Migración 0002 falla si una instalación anterior tiene registros terminales sin
revisión. Se requiere reconciliación real del equipo; no se fabrican revisiones
ni se aceptan filas para facilitar una migración. Downgrade retira estos controles
y columnas; ensayar solo en base vacía dedicada según docs/database.md.

Pruebas reales PostgreSQL: transiciones válidas/invalidas, registro de fecha y
motivo, restricciones directas, carreras y selección de aceptados. Datos sintéticos.
