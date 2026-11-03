# Integración continua — #18

Backend CI / backend-verify corre en todos los pull requests y pushes a main.
Usa Python 3.12, uv.lock, PostgreSQL 17 de servicio y únicamente datos sintéticos.
Verifica Ruff, formato, mypy, snapshot OpenAPI, pruebas HTTP/TLS/PostgreSQL y
upgrade/check/downgrade/upgrade. La contraseña del servicio CI es ficticia,
pública y exclusivamente para la base efímera del runner; no es un secreto real.
No requiere credenciales ni corpus de producción.

Los cambios de contrato deben actualizar intencionalmente docs/openapi-v1.json,
sus pruebas y docs/contract-review.md, y contar con revisión móvil antes de
declarar #4 finalizada. El snapshot falla ante cambios no reflejados en contrato.
Los tipos comprueban todo src, incluidos cuerpos no anotados; imports de
dependencias sin stubs se permiten. No se afirma tipado estricto de esas librerías.

Para bloquear merges, un administrador debe exigir backend-verify en el ruleset
o protección de main después de integrar el workflow. Un check rojo por sí solo
no garantiza que GitHub impida la unión. No se modifica main ni sus reglas aquí.
Prueba negativa real: [Actions 41556539745](https://github.com/smishing-thesis/smishing-backend/actions/runs/41556539745),
commit 4ace4ca: falló el snapshot por versión alterada intencionalmente después
de pasar instalación, Ruff, formato y mypy. Se restaura el contrato en el
siguiente commit; la ejecución verde se registrará al terminar.

Lectura de branch protection: 403 Resource not accessible by integration.
No se puede verificar ni afirmar que backend-verify sea obligatorio.
Project: 404 desde el entorno; las historias completas sí se recuperaron por API.
