# Despliegue en Azure App Service — #19 y #20

Estado al 23 de noviembre de 2026: el backend está desplegado a mano en un App Service
(`smishy-backend`, Brasil Sur, Linux, Python 3.12, publicación Code, plan Free F1) con
HTTPS solo y TLS mínimo 1.2 configurados en el portal. **No hay base de datos en
Azure:** por ahora la base es un PostgreSQL gratuito de Render, con acceso externo
(ver [Riesgos](#riesgos-conocidos-con-el-plan-free-f1)). El despliegue no está
automatizado; el procedimiento de abajo es el que se ejecutó y funcionó. Lo que sigue
sin comprobar está marcado en la lista de verificación.

## Qué cambia en el código

App Service termina TLS en su entrada y reenvía HTTP al contenedor. Para eso existe
el modo `SMISHING_BEHIND_TLS_PROXY=true`, apagado por defecto:

- El runner (`python -m smishing_backend.server`) escucha en `SMISHING_HOST`
  (por defecto 0.0.0.0) y en el puerto de `PORT`, `WEBSITES_PORT` o `SMISHING_PORT`
  (por defecto 8000, el que espera App Service para Python). No usa TLS propio ni
  exige `TLS_CERT_PATH`. Sigue sin access logs ni proxy headers de uvicorn.
- Un middleware marca la solicitud como HTTPS solo si llega **exactamente un**
  `X-Forwarded-Proto: https`. Sin él, con `http` o repetido, el esquema sigue siendo
  `http` y las rutas de aportes responden 400 sin guardar nada.
- No se lee `X-Forwarded-For` ni la dirección del cliente. Por eso la cuota por par de
  red pasa a ser la global (todo llega del proxy): la protección real es la cuota
  global, y un cliente abusivo puede agotarla para todos. Es una limitación conocida;
  limitar por cliente exigiría leer su dirección, lo que el proyecto evita.
- Supone que el puerto de la aplicación solo es alcanzable a través del proxy. Un
  cliente que llegara directo podría falsear el encabezado. En App Service el
  contenedor no se expone por otra vía, pero **no se ha comprobado**.

## Variables y ajustes de la aplicación

| Ajuste | Valor |
| --- | --- |
| SMISHING_BEHIND_TLS_PROXY | true |
| SMISHING_DATABASE_URL | `postgresql+psycopg://usuario:clave@host:5432/base?sslmode=require`; ajuste de la app o Key Vault, nunca el repositorio. Con Render se usa la **External** Database URL (la Internal solo funciona dentro de Render) cambiando el inicio `postgresql://` por `postgresql+psycopg://` y agregando `?sslmode=require`, que hace fallar la conexión en vez de bajar a texto plano |
| SMISHING_ADMIN_CREDENTIALS | Objeto JSON ID de operador a secreto Bearer; distinto de Android y de revisión. Ajuste seguro de la app. Sin valor, las rutas de gestión responden 401. |
| SMISHING_API_KEY | clave de la app; para rotar con solapamiento, SMISHING_API_KEYS con una lista JSON |
| SMISHING_LOG_DIR | un directorio bajo /home, p. ej. /home/smishing-logs |
| PYTHONPATH | `src` (relativo; ver la nota de abajo) |
| SCM_DO_BUILD_DURING_DEPLOYMENT | true |
| WEBSITES_PORT | 8000 |

Comando de inicio: `python -m smishing_backend.server`.

**`PYTHONPATH` debe ser `src`, no `/home/site/wwwroot/src`.** Oryx comprime el
resultado del build y lo extrae al arrancar en una carpeta temporal
(`/tmp/<hash>`); en `/home/site/wwwroot` solo queda `output.tar.zst`. Con la ruta
absoluta, el contenedor se cae con `No module named 'smishing_backend'`. La ruta
relativa funciona porque la app arranca desde la carpeta temporal (comprobado el
23-11-2026; se desconoce si Oryx cambiaría ese comportamiento en otra versión).

Configuración del recurso (#20): solo HTTPS activado, TLS mínimo 1.2, **lista de
orígenes CORS vacía** (la app móvil no la necesita y el código no emite
encabezados CORS), Application Insights apagado (es telemetría), registros de la
plataforma (aplicación, servidor web, solicitudes detalladas) apagados o revisados
para que no queden URL, IP ni cuerpos, FTP desactivado.

## Dependencias

App Service construye con `requirements.txt`, no con `uv.lock`. El archivo se genera
desde el lock y una prueba (`tests/test_proxy_mode.py`) comprueba que coincide en
versiones y que no incluye herramientas de desarrollo. Tras cambiar dependencias:

```sh
uv export --locked --no-dev --no-emit-project --format requirements-txt -o requirements.txt
```

Incluye el modelo de spaCy `es_core_news_lg` como enlace directo a GitHub.

### PR de Dependabot (#60)

Dependabot actualiza `pyproject.toml` y `uv.lock`, pero no `requirements.txt`. Un PR
suyo que cambie `uv.lock` falla en `test_requirements_match_the_lock_and_exclude_development_tools`
hasta que se regenere el archivo. Antes de fusionarlo, desde su rama:

```sh
git fetch origin && git switch <rama-de-dependabot>
uv export --locked --no-dev --no-emit-project --format requirements-txt -o requirements.txt
git add requirements.txt && git commit -m "chore(deps): regenerar requirements.txt" && git push
```

Fusionar el PR no despliega nada: hay que volver a desplegar con el procedimiento de
abajo para que App Service reciba la versión nueva. `spacy` queda excluido de las
subidas menores y mayores porque debe coincidir con el modelo `es_core_news_lg-3.8.0`.

## Procedimiento (ejecutado a mano el 23-11-2026)

Requiere la CLI de Azure con la sesión iniciada (`az login`) en la suscripción
correcta. Apuntar siempre a `smishy-backend` en el grupo `smishy-rg`: la suscripción
puede tener otras apps.

1. Zip solo con archivos versionados, sin pruebas, claves ni archivos sin versionar:

   ```sh
   git archive --format=zip -o app.zip HEAD src migrations alembic.ini requirements.txt
   ```

2. Desplegar:

   ```sh
   az webapp deploy --resource-group smishy-rg --name smishy-backend --src-path app.zip --type zip
   ```

   El build de Oryx tardó unos 106 s (instala los 56 paquetes, incluido spaCy). Si el
   contenedor no arranca, la CLI espera hasta 10 minutos, da el despliegue por fallido
   y **deja la app detenida**; el motivo está en los registros de arranque
   (`az webapp log download`). Guardar un ajuste de la app la reinicia.
3. Aplicar las migraciones y registrar el modelo **desde un equipo con el entorno del
   proyecto instalado**, con `SMISHING_DATABASE_URL` puesta solo en esa terminal (sin
   escribirla en un comando, para que no quede en el historial):

   ```sh
   alembic upgrade head
   alembic current          # debe decir 0006 (head)
   python -m smishing_backend.catalog --release v1.0.0
   ```

   El registro del modelo lee la publicación con `gh`, que debe tener sesión iniciada.
   Esto funciona porque la base de Render admite conexiones externas. Con una base
   privada habría que aplicarlas desde la consola SSH de la app (`cd
   /home/site/wwwroot` y los mismos comandos); **ese camino no se ha probado**.
4. Comprobar `GET /health`, `/docs` y `/openapi.json` por HTTPS, y enviar un aporte
   sintético con la clave de la app: debe responder 201 con `status: pending`.
   La primera respuesta tras el despliegue tardó unos 78 s; los reinicios posteriores
   tardaron bastante más (ver Riesgos).

## Riesgos conocidos con el plan Free (F1)

- **Sin red privada.** El portal muestra "Virtual network integration: Not supported" y
  "Private endpoint connections: Not supported". No se puede cumplir el criterio de #19
  "la base de datos no es accesible desde internet" con este plan. Lo más cercano sería
  una base con acceso público limitado por firewall, y eso no equivale a lo pedido.
- **Sin Always On:** la app se duerme tras inactividad y la primera solicitud es lenta,
  más con la carga del modelo de spaCy al arrancar. Mediciones del 23-11-2026: la
  primera solicitud tras el despliegue tardó unos 78 s, pero dos reinicios posteriores
  tardaron **195 s y 207 s** en pasar la prueba de arranque de Azure. El límite por
  defecto es de unos 230 s: hay poco margen y no se ha comprobado cuánto varía. El
  cliente móvil debe usar tiempos de espera generosos y reintentar.
- **Plan compartido con otra app.** `smishy-backend` usa el plan
  `ASP-UPCEstrellados-ab3a`, que está en el grupo `UPC-Estrellados` y lo comparte con
  `restyle-web-services` (otro proyecto). La cuota diaria de CPU y la memoria del plan
  Free son comunes: si esa app se enciende, nos quita cuota. Borrar el grupo
  `UPC-Estrellados` o ese plan dejaría esta app sin plan. Conviene moverla a un plan
  propio cuando haya presupuesto.
- **Cada reinicio gasta CPU de la cuota diaria** (60 minutos en F1) por la carga de
  spaCy: evitar reinicios innecesarios. No se ha medido cuántos caben al día.
- **1 GB de memoria:** el modelo de spaCy cabió y la app respondió, pero no se ha medido
  el consumo con tráfico real.
- **La clave por `http://` se expone.** Azure redirige `http://` a `https://` (301)
  sin procesar la solicitud, pero un cliente que mande la clave por HTTP ya la dejó en
  claro antes de la redirección. La app móvil debe usar siempre `https://`.
- **Sin registros de la plataforma** (apagados a propósito para que no queden URL, IP ni
  cuerpos), el diagnóstico de fallos de arranque depende de los registros de despliegue
  (`az webapp log download`). Para diagnosticar otra cosa habría que activarlos de
  forma temporal y apagarlos después.
- **La base de datos es pública.** Está en Render, accesible desde internet y
  protegida solo por contraseña y TLS (`sslmode=require`). Las bases gratuitas de
  Render pueden caducar: revisar la fecha en su panel. Cambiar de base solo exige
  cambiar `SMISHING_DATABASE_URL`, repetir las migraciones y registrar el modelo; los
  datos no se mueven solos.
- La suscripción puede no permitir F1 en algunas regiones (ocurrió en East US).

## Lista de verificación (a registrar en #19 y #20)

- [x] HTTPS responde y HTTP redirige con 301 (comprobado desde fuera el 23-11-2026
  sobre el App Service vacío).
- [x] TLS mínimo 1.2 en la app y en el sitio de administración (consultado con la CLI
  el 23-11-2026). Desde fuera, TLS 1.2 y 1.3 responden 200 y TLS 1.1 no completa el
  apretón de manos (salida 35 de curl; no distingue si lo rechaza Azure o si el curl
  local no soporta 1.1).
- [x] Una solicitud `http://` se redirige con 301 a `https://`, tanto `GET` como `POST`,
  sin procesarla (probado el 23-11-2026 con una clave falsa).
- [x] El backend desplegado responde `/health`, `/docs` y `/openapi.json` con 200
  (23-11-2026).
- [x] Un aporte sintético individual con clave responde 201 `pending` por HTTPS: la
  clave, la conexión Azure → Render y `X-Forwarded-Proto` funcionan juntos.
- [x] Sin clave, `POST /api/v1/contributions` responde 401.
- [ ] Un lote sintético (`/batch`) en el entorno real: no probado.
- [ ] Un aporte sin `X-Forwarded-Proto: https` se rechaza en el entorno real: no se ha
  podido comprobar, porque el proxy de App Service siempre lo agrega.
- [x] Migraciones (0006) y registro del modelo `v1.0.0` aplicados, desde un equipo
  externo y contra la base de Render, no desde la consola de la app.
- [x] `SMISHING_DATABASE_URL` y `SMISHING_API_KEY` están como ajustes de la app, fuera
  del repositorio (comprobado el formato de la URL sin mostrar el valor).
- [x] Rotar la clave sin cambiar código: se reemplazó `SMISHING_API_KEY` por una clave
  nueva en el portal. Tras reiniciar la app, la clave nueva responde 422 (autenticada,
  cuerpo vacío a propósito para no guardar aportes) y una clave falsa responde 401;
  solo existe un ajuste de clave. **No se probó que la clave anterior concreta esté
  rechazada**, porque no se conservaba: es una consecuencia de que ya no esté
  configurada, no una comprobación. **Observado una vez:** justo después de guardar el
  ajuste, la app siguió respondiendo 401 a la clave nueva (con el valor ya correcto en
  Azure) y solo la aceptó tras un reinicio manual; no se identificó la causa. Tras
  rotar, comprobar con una solicitud y reiniciar si no surte efecto.
- [ ] Rotación con solapamiento (`SMISHING_API_KEYS` junto a `SMISHING_API_KEY`, para no
  cortar a clientes con la clave anterior): el código la soporta, no se probó en Azure.
- [x] Configuración del recurso consultada con la CLI el 23-11-2026: solo HTTPS, FTPS
  únicamente, autenticación básica de FTP y SCM desactivada, CORS vacío, depuración
  remota apagada, sin Application Insights ni ajustes de diagnóstico de Azure Monitor.
- [x] Registros de la plataforma revisados: registros de aplicación, de servidor web,
  errores detallados y trazas de solicitudes fallidas, todos apagados.
- [x] Sin secretos en el repositorio: la clave de prueba usada antes no aparece en el
  historial ni hay hosts de Render ni URLs de base con contraseña real; solo la
  contraseña sintética de la CI y marcadores de ejemplo en este documento. Búsqueda por
  patrones, no una auditoría exhaustiva.
- [ ] Secretos fuera de los logs de la aplicación: el código no registra mensajes ni
  claves (regla del proyecto), pero no se revisó un registro real porque la plataforma
  no guarda ninguno.
- [ ] Base de datos sin acceso desde internet (**no alcanzable con el plan Free**).
- [ ] Verificar revisión y administración de #54 en el Swagger principal después de aprobar el PR. Los runners 8444 y 8445 se reservan para uso local. Comprobar 401 y no-store sin enviar credenciales. Las pruebas con datos sintéticos se hacen en la base local. Coordinar un solo despliegue para cuidar la cuota del plan Free.
