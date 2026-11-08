# Hitos del 8 de noviembre de 2026

## Completadas e integradas por autorización expresa

#3, #8 y #9: PR #22, #25 y #26 integrados, en ese orden, y las tres historias
cerradas como completadas. No se integró ningún otro PR del backend ni se
desplegó. Main final: `03800d594c2c18a12ccc0c3c8395124afdf816d1`.

Se ensayaron juntas con el main vigente en worktree aislado: **22 pruebas**,
lint y mypy correctos. El árbol final de GitHub coincide exactamente con el
ensayado: `ed01be611f362b255ecd78b89296014db1543844`.

## Nuevas implementaciones independientes y probadas

| Historia | Rama / commit | PR | Pruebas y evidencia |
| --- | --- | --- | --- |
| #15, etiquetas y catálogo | feat/15-label-provenance / 544587f | [#38](https://github.com/smishing-thesis/smishing-backend/pull/38) | 123 passed; [CI verde](https://github.com/smishing-thesis/smishing-backend/actions/runs/42515855331) y registro real de metadatos |
| #13, revisión protegida | feat/13-protected-review / 54a389d | [#39](https://github.com/smishing-thesis/smishing-backend/pull/39) | 138 passed; [CI verde](https://github.com/smishing-thesis/smishing-backend/actions/runs/42516408203), roles, concurrencia y rollback |
| #16, exportación | feat/16-reproducible-export / 977ff94 | [#40](https://github.com/smishing-thesis/smishing-backend/pull/40) | 145 passed; [CI verde](https://github.com/smishing-thesis/smishing-backend/actions/runs/42517047103) y lector real del modelo |
| #14, señales de envenenamiento | feat/14-poisoning-signals | PR separado del hito | 154 passed locales; cuatro señales y 0/20 falsos marcados en controles sintéticos |

Cada PR contiene solo su historia: #38 apunta a #34, #39 a #38, #40 a #39 y
la rama de #14 a #40. No se han integrado estas nuevas funciones en main.
Cuando se integren las bases, retarget y comprobar que el diff siga siendo
exclusivo; no duplicar commits ni sobrescribir trabajo remoto.

Las pruebas completas usan PostgreSQL 17 real y datos sintéticos. Ruff,
formato y mypy correctos; la advertencia de deprecación Starlette/httpx sigue
siendo de mantenimiento. No se copió corpus real ni se entrenó un modelo.

## Qué necesita intervención posterior

- Revisar y aceptar los nuevos PR y las bases funcionales aún abiertas.
- #4 y #6: acuerdo con el equipo móvil sobre contrato/autenticación.
- #14: revisar umbrales y suministrar referencias operativas anonimizadas de
  evaluación; las pruebas sintéticas no sustituyen ese paso.
- #17/#18: respaldos, retención de consola y protección de main siguen pendientes.
- #19/#20: Azure, red privada y secretos de despliegue requieren infraestructura
  y autorización aparte. No se fingió un despliegue por tener Docker local.
- #21: consolidar documentación final contra las funciones que el equipo acepte.

Este documento actualiza el estado posterior al registro histórico de
`development-status.md`; ese archivo conserva la evidencia de la sesión previa.
