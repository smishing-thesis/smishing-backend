# Duplicados — #10

SHA-256 sobre UTF-8 normalizado (NFC, controles y espacios) y restricción
uq_contributions_content_hash como autoridad bajo concurrencia. No se hace
check-then-insert. El repositorio traduce solo esa restricción a
DuplicateContribution; otros errores de integridad no se confunden con duplicados.
El rollback revierte etiquetas y versiones nuevas antes de devolver 409.
La respuesta no contiene UUID, texto, fecha ni estado del aporte existente.

Pruebas PostgreSQL reales: exacto, espacios y Unicode canónico; para estados
pending, accepted y rejected; dos solicitudes HTTP simultáneas producen 201/409,
un aporte y una etiqueta, sin 500. Datos exclusivamente sintéticos.
No se considera similitud semántica ni normalización del modelo de inferencia.
